"""Export glacier polygon boundaries inside the DEM footprint as GeoJSON."""

import json
from pathlib import Path

import fiona
from pyproj import Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform

from raster_sources import open_raster


ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    (ROOT / "RGI_v6.gpkg", ROOT / "terrain" / "rgi-v6-outlines.geojson"),
    (ROOT / "Delimitacion_gradiente_hidraulico.gpkg", ROOT / "terrain" / "hydraulic-gradient-outlines.geojson"),
)


def export(source_path, destination):
    with open_raster(ROOT / "DEM_SRTM.nc", "dem") as dem, fiona.open(source_path) as source:
        if not source.crs:
            raise ValueError(f"{source_path.name}: GeoPackage sin CRS")
        to_source = Transformer.from_crs(dem.crs, source.crs, always_xy=True).transform
        footprint = transform(to_source, box(*dem.bounds))
        to_wgs84 = Transformer.from_crs(source.crs, "EPSG:4326", always_xy=True).transform
        features = []
        for item in source.filter(bbox=footprint.bounds):
            geometry = shape(item["geometry"])
            if not geometry.intersects(footprint):
                continue
            clipped = geometry.intersection(footprint).simplify(40, preserve_topology=True)
            if clipped.is_empty:
                continue
            geographic = transform(to_wgs84, clipped)
            rounded = transform(lambda x, y, z=None: (round(x, 6), round(y, 6)), geographic)
            if not rounded.is_valid:
                rounded = rounded.buffer(0)
            if rounded.is_empty:
                continue
            features.append({"type": "Feature", "properties": {}, "geometry": mapping(rounded)})
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {len(features)} outlines to {destination.name}", flush=True)


def main():
    for source, destination in SOURCES:
        export(source, destination)


if __name__ == "__main__":
    main()
