"""Build 3D and color tiles for hydraulic correction and filled head."""

import json
from pathlib import Path
from contextlib import ExitStack

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds

from build_terrain import terrarium, tile_bounds, tile_xy
from raster_sources import open_raster


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "terrain"
SOURCES = {
    "hydraulic-correction": (ROOT / "Fuerts_2024_hydraulic_head_catchments.nc", "hydraulic_head_difference"),
    "hydraulic-filled": (ROOT / "Fuerts_2024_hydraulic_head_catchments.nc", "hydraulic_head_filled"),
}
MIN_HEAD, MAX_HEAD = -4, 3800
MAX_CORRECTION_MAGNITUDE = 320
PALETTES = {
    "hydraulic-correction": colormaps["Reds"],
    "hydraulic-filled": colormaps["YlGnBu"],
}


def colorize(values, name):
    valid = np.isfinite(values)
    if name == "hydraulic-correction":
        position = np.clip(np.abs(np.nan_to_num(values, nan=0)) / MAX_CORRECTION_MAGNITUDE, 0, 1)
    else:
        position = np.clip((np.nan_to_num(values, nan=MIN_HEAD) - MIN_HEAD) / (MAX_HEAD - MIN_HEAD), 0, 1)
    rgba = (PALETTES[name](position) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def main():
    with ExitStack() as stack:
        reference = stack.enter_context(open_raster(ROOT / "DEM_SRTM.nc", "dem"))
        bounds = transform_bounds(reference.crs, "EPSG:4326", *reference.bounds, densify_pts=21)
        sources = {name: stack.enter_context(open_raster(*spec)) for name, spec in SOURCES.items()}
        shapes = {(src.crs, src.transform, src.shape) for src in sources.values()}
        if len(shapes) != 1 or any(src.crs != reference.crs for src in sources.values()):
            raise ValueError("Las variables hidráulicas deben compartir cuadrícula y CRS con el DEM")
        arrays = {name: src.read(1, masked=True).astype(np.float32).filled(np.nan) for name, src in sources.items()}
        count = 0
        for zoom in range(5, 11):
            x0, y1 = tile_xy(bounds[0], bounds[1], zoom)
            x1, y0 = tile_xy(bounds[2], bounds[3], zoom)
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    transform = from_bounds(*tile_bounds(x, y, zoom), 256, 256)
                    for name, src in sources.items():
                        values = np.full((256, 256), np.nan, dtype=np.float32)
                        reproject(
                            source=arrays[name], destination=values,
                            src_transform=src.transform, src_crs=src.crs, src_nodata=np.nan,
                            dst_transform=transform, dst_crs="EPSG:3857", dst_nodata=np.nan,
                            resampling=Resampling.bilinear, init_dest_nodata=True,
                        )
                        path = OUT / name / str(zoom) / str(x) / f"{y}.png"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        colorize(values, name).save(path, compress_level=6)
                        dem_path = OUT / f"{name}-dem" / str(zoom) / str(x) / f"{y}.png"
                        dem_path.parent.mkdir(parents=True, exist_ok=True)
                        # Hydraulic variables define their own 3D height.
                        height = np.abs(values) if name == "hydraulic-correction" else values
                        terrarium(np.where(np.isfinite(values), height, 0)).save(dem_path, compress_level=6)
                    count += 1
            print(f"zoom {zoom} complete", flush=True)
    scales = (
        ("hydraulic-correction", np.linspace(0, MAX_CORRECTION_MAGNITUDE, 1024, dtype=np.float32)[None, :], "correction-colorbar.png"),
        ("hydraulic-filled", np.linspace(MIN_HEAD, MAX_HEAD, 1024, dtype=np.float32)[None, :], "hydraulic-colorbar.png"),
    )
    for name, scale, filename in scales:
        bar = np.repeat(np.asarray(colorize(scale, name)), 20, axis=0)
        Image.fromarray(bar, "RGBA").save(OUT / filename)
    (OUT / "hydraulic-metadata.json").write_text(json.dumps({
        "bounds": bounds, "minzoom": 5, "maxzoom": 10,
        "palettes": {
            "hydraulic-correction": {"name": "Matplotlib Reds", "magnitude_range_m": [0, MAX_CORRECTION_MAGNITUDE]},
            "hydraulic-filled": {"name": "Matplotlib YlGnBu", "range_m": [MIN_HEAD, MAX_HEAD]},
        },
        "sources": {name: {"file": path.name, "variable": variable} for name, (path, variable) in SOURCES.items()},
        "terrain_height_inside_coverage": "absolute correction magnitude or raw filled head",
        "terrain_height_outside_coverage": "zero plane",
        "tile_pairs": count,
    }, indent=2), encoding="utf-8")
    print(f"Wrote {count} hydraulic tile pairs", flush=True)


if __name__ == "__main__":
    main()
