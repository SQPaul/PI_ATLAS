"""Compare regenerated hydraulic DEM tiles with the source raster values."""

import json
from pathlib import Path

import numpy as np
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject

from build_terrain import tile_bounds
from raster_sources import open_raster


ROOT = Path(__file__).resolve().parents[1]


def decode_terrarium(path):
    rgb = np.asarray(Image.open(path)).astype(np.int32)
    return rgb[:, :, 0] * 256 + rgb[:, :, 1] + rgb[:, :, 2] / 256 - 32768


def check(name, variable, absolute):
    with open_raster(ROOT / "Fuerts_2024_hydraulic_head_catchments.nc", variable) as src:
        source = src.read(1, masked=True).astype(np.float32).filled(np.nan)
        for color_path in (ROOT / "terrain" / name).rglob("*.png"):
            alpha = np.asarray(Image.open(color_path))[:, :, 3]
            if not (np.any(alpha == 0) and np.any(alpha == 255)):
                continue
            y = int(color_path.stem)
            x = int(color_path.parent.name)
            zoom = int(color_path.parent.parent.name)
            values = np.full((256, 256), np.nan, dtype=np.float32)
            reproject(
                source=source, destination=values, src_transform=src.transform,
                src_crs=src.crs, src_nodata=np.nan,
                dst_transform=from_bounds(*tile_bounds(x, y, zoom), 256, 256),
                dst_crs="EPSG:3857", dst_nodata=np.nan,
                resampling=Resampling.bilinear, init_dest_nodata=True,
            )
            valid = np.isfinite(values)
            if not np.any(valid & (np.abs(values) > 1)):
                continue
            expected = np.where(valid, np.abs(values) if absolute else values, 0)
            actual = decode_terrarium(ROOT / "terrain" / f"{name}-dem" / str(zoom) / str(x) / f"{y}.png")
            assert np.allclose(actual, expected, atol=1 / 256 + 0.001), name
            assert np.array_equal(alpha == 255, valid), name
            print(f"OK: {name} z{zoom}/{x}/{y}, rango {actual.min():.2f} a {actual.max():.2f} m")
            return
    raise AssertionError(f"No se encontró una tesela mixta para {name}")


def main():
    metadata = json.loads((ROOT / "terrain" / "hydraulic-metadata.json").read_text(encoding="utf-8"))
    assert metadata["terrain_height_outside_coverage"] == "zero plane"
    check("hydraulic-correction", "hydraulic_head_difference", absolute=True)
    check("hydraulic-filled", "hydraulic_head_filled", absolute=False)


if __name__ == "__main__":
    main()
