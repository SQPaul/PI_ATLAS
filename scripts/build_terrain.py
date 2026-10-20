"""Build static Terrarium terrain tiles from the two local Patagonia DEMs."""

import json
import math
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from rasterio.transform import from_bounds

from raster_sources import open_raster


ROOT = Path(__file__).resolve().parents[1]
SURFACE = ROOT / "DEM_SRTM.nc"
BED = ROOT / "Fuerst_2024.nc"
OUT = ROOT / "terrain"
MIN_ELEVATION = -600
MAX_ELEVATION = 4000
PALETTE = colormaps["terrain"]
MAX_LAT = 85.05112878
R = 20037508.342789244


def tile_xy(lon, lat, zoom):
    lat = max(-MAX_LAT, min(MAX_LAT, lat))
    n = 2**zoom
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def tile_bounds(x, y, zoom):
    size = 2 * R / 2**zoom
    left, top = -R + x * size, R - y * size
    return left, top - size, left + size, top


def sample(src, transform, dst, method):
    reproject(
        source=rasterio.band(src, 1), destination=dst,
        src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
        dst_transform=transform, dst_crs="EPSG:3857", dst_nodata=np.nan,
        resampling=method, init_dest_nodata=True,
    )


def terrarium(height):
    encoded = np.clip(np.round((height + 32768) * 256), 0, 16777215).astype(np.uint32)
    rgb = np.empty((*height.shape, 3), dtype=np.uint8)
    rgb[..., 0] = encoded >> 16
    rgb[..., 1] = (encoded >> 8) & 255
    rgb[..., 2] = encoded & 255
    return Image.fromarray(rgb, "RGB")


def colored(height, valid):
    """Use the ocean and land sections of Matplotlib terrain around sea level."""
    # Classify sea level exactly as the encoded 3D elevation tile does.
    encoded = np.clip(np.round((height + 32768) * 256), 0, 16777215).astype(np.uint32)
    height = encoded.astype(np.float64) / 256 - 32768
    below = height < 0
    positions = np.empty(height.shape, dtype=np.float32)
    positions[below] = np.clip(height[below] / -MIN_ELEVATION + 1, 0, 1) * 0.17
    positions[~below] = 0.25 + np.clip(height[~below] / MAX_ELEVATION, 0, 1) * 0.75
    rgba = (PALETTE(positions) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def main():
    with open_raster(SURFACE, "dem") as surface, open_raster(BED, "bedrock_elevation") as bed:
        if surface.crs is None or bed.crs is None:
            raise ValueError("Ambos NetCDF deben declarar un CRS")
        bounds = transform_bounds(surface.crs, "EPSG:4326", *surface.bounds, densify_pts=21)
        print("WGS84 bounds:", bounds, flush=True)
        count = 0
        for zoom in range(5, 11):
            x0, y1 = tile_xy(bounds[0], bounds[1], zoom)
            x1, y0 = tile_xy(bounds[2], bounds[3], zoom)
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    transform = from_bounds(*tile_bounds(x, y, zoom), 256, 256)
                    top = np.full((256, 256), np.nan, dtype=np.float32)
                    bottom = np.full_like(top, np.nan)
                    sample(surface, transform, top, Resampling.bilinear)
                    sample(bed, transform, bottom, Resampling.bilinear)
                    valid = np.isfinite(top)
                    # The basal DEM is defined only beneath mapped ice. Keep the
                    # surrounding topography from SRTM for geographic context.
                    top = np.nan_to_num(top, nan=0)
                    bottom = np.where(np.isfinite(bottom), bottom, top)
                    for key, values in (("surface", top), ("basal", bottom)):
                        path = OUT / key / str(zoom) / str(x) / f"{y}.png"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        terrarium(values).save(path, compress_level=6)
                        color_path = OUT / f"{key}-color" / str(zoom) / str(x) / f"{y}.png"
                        color_path.parent.mkdir(parents=True, exist_ok=True)
                        colored(values, valid).save(color_path, compress_level=6)
                    count += 1
            print(f"zoom {zoom} complete", flush=True)
        scale = np.linspace(MIN_ELEVATION, MAX_ELEVATION, 1024, dtype=np.float32)[None, :]
        bar = np.repeat(np.asarray(colored(scale, np.ones(scale.shape, dtype=bool))), 20, axis=0)
        Image.fromarray(bar, "RGBA").save(OUT / "colorbar.png")
        (OUT / "metadata.json").write_text(json.dumps({
            "bounds": bounds, "minzoom": 5, "maxzoom": 10,
            "surface": {"file": SURFACE.name, "variable": "dem"},
            "basal": {"file": BED.name, "variable": "bedrock_elevation"},
            "palette": "Matplotlib terrain; negative values use ocean section 0–0.17; nonnegative use land section 0.25–1",
            "palette_range_m": [MIN_ELEVATION, MAX_ELEVATION],
            "basal_outside_coverage": "SRTM surface context",
            "tile_pairs": count,
        }, indent=2), encoding="utf-8")
        print(f"Wrote {count} tile pairs", flush=True)


if __name__ == "__main__":
    main()
