"""Small end-to-end check for the configurable layer builder."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import fiona
import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_origin


ROOT = Path(__file__).resolve().parents[1]


def run_builder(catalog, output):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_layers.py"), "--catalog", str(catalog), "--output", str(output)],
        text=True, capture_output=True, check=False,
    )


def main():
    # TemporaryDirectory only owns a fresh folder created inside this workspace.
    with tempfile.TemporaryDirectory(prefix="layer-test-", dir=ROOT) as temporary:
        folder = Path(temporary)
        raster = folder / "sample.tif"
        values = np.full((64, 64), -9999, dtype=np.float32)
        values[:, :32] = -100
        with rasterio.open(
            raster, "w", driver="GTiff", height=64, width=64, count=1,
            dtype="float32", crs="EPSG:4326", transform=from_origin(-72.2, -45.0, 0.002, 0.002), nodata=-9999,
        ) as dataset:
            dataset.write(values, 1)
        vector = folder / "geometry.geojson"
        vector.write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [-71.5, -44.5]}},
            {"type": "Feature", "properties": {}, "geometry": {"type": "LineString", "coordinates": [[-71.5, -44.5], [-71.4, -44.4]]}},
            {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[-71.3, -44.5], [-71.2, -44.5], [-71.2, -44.4], [-71.3, -44.5]]]}},
        ]}), encoding="utf-8")
        geopackage = folder / "stations.gpkg"
        with fiona.open(geopackage, "w", driver="GPKG", layer="stations", crs="EPSG:4326", schema={"geometry": "Point", "properties": {"name": "str"}}) as dataset:
            dataset.write({"geometry": {"type": "Point", "coordinates": [-71.1, -44.1]}, "properties": {"name": "test"}})
        clip = folder / "clip.gpkg"
        with fiona.open(clip, "w", driver="GPKG", layer="clip", crs="EPSG:4326", schema={"geometry": "Polygon", "properties": {"name": "str"}}) as dataset:
            dataset.write({"geometry": {"type": "Polygon", "coordinates": [[[-72.2, -45.0], [-72.17, -45.0], [-72.17, -45.12], [-72.2, -45.12], [-72.2, -45.0]]]}, "properties": {"name": "test"}})
        output = folder / "output"
        catalog = folder / "layers.json"
        config = {
            "surfaces": [{
                "id": "test-head", "file": str(raster.relative_to(ROOT)).replace("\\", "/"),
                "label": "Test head", "unit": "m", "palette": "viridis", "range": [-200, 0],
                "height": {"mode": "absolute", "scale": 2, "offset": 10}, "minzoom": 9, "maxzoom": 9,
                "clip": {"file": str(clip.relative_to(ROOT)).replace("\\", "/"), "layer": "clip"},
            }, {
                "id": "test-map", "file": "Carga_hidraulica_rellenada.map", "crs": "EPSG:32718",
                "label": "Test MAP", "unit": "m", "palette": "YlGnBu", "range": [-4, 3800],
                "minzoom": 5, "maxzoom": 5,
            }, {
                "id": "test-netcdf-relief", "file": "Fuerst_2024.nc", "variable": "bedrock_elevation",
                "label": "Test relief", "unit": "m", "palette": "terrain", "range": [-600, 4000],
                "display": "relief", "minzoom": 5, "maxzoom": 5,
            }, {
                "id": "test-netcdf-overlay", "file": "Fuerts_2024_hydraulic_head_catchments.nc", "variable": "hydraulic_head_difference",
                "label": "Test overlay", "unit": "m", "palette": "Reds", "range": [0, 320],
                "display": "overlay", "visible": True, "minzoom": 5, "maxzoom": 5,
            }],
            "geometries": [{
                "id": "test-geometry", "file": str(vector.relative_to(ROOT)).replace("\\", "/"),
                "label": "Test geometry", "color": "#ff0000", "visible": True,
            }, {
                "id": "test-gpkg", "file": str(geopackage.relative_to(ROOT)).replace("\\", "/"),
                "layer": "stations", "label": "Test GPKG", "color": "#00ff00",
            }],
        }
        catalog.write_text(json.dumps(config), encoding="utf-8")
        result = run_builder(catalog, output)
        assert result.returncode == 0, result.stderr
        manifest_path = output / "custom-layers.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert len(manifest["surfaces"]) == 3 and len(manifest["overlays"]) == 1 and len(manifest["geometries"]) == 2
        assert manifest["surfaces"][2]["demTiles"] is None
        assert manifest["overlays"][0]["demTiles"] is None
        assert manifest["overlays"][0]["visible"] is True
        assert manifest["geometries"][0]["featureCount"] == 3
        assert manifest["geometries"][1]["featureCount"] == 1
        assert manifest["geometries"][0]["bounds"][0] > -72.8627  # outside the original SRTM edge
        version = next((output / "custom-builds").iterdir())
        dem_tiles = list((version / "test-head" / "dem").rglob("*.png"))
        assert dem_tiles
        heights = np.concatenate([np.asarray(Image.open(path)).reshape(-1, 3) for path in dem_tiles], axis=0).astype(np.int32)
        decoded = heights[:, 0] * 256 + heights[:, 1] + heights[:, 2] / 256 - 32768
        assert np.any(np.isclose(decoded, 210, atol=1 / 256))
        assert np.any(np.isclose(decoded, 0, atol=1 / 256))
        color_tiles = list((version / "test-head" / "color").rglob("*.png"))
        alpha = np.concatenate([np.asarray(Image.open(path))[:, :, 3].reshape(-1) for path in color_tiles])
        assert 0 in alpha and 255 in alpha
        previous = manifest_path.read_bytes()
        del config["surfaces"][1]["crs"]
        catalog.write_text(json.dumps(config), encoding="utf-8")
        invalid_crs = run_builder(catalog, output)
        assert invalid_crs.returncode != 0 and "no tiene CRS" in invalid_crs.stderr
        assert manifest_path.read_bytes() == previous
        config["surfaces"][0]["file"] = "missing.tif"
        catalog.write_text(json.dumps(config), encoding="utf-8")
        invalid = run_builder(catalog, output)
        assert invalid.returncode != 0 and "no existe" in invalid.stderr
        assert manifest_path.read_bytes() == previous
        print("OK: GeoTIFF, MAP, NetCDF, GeoJSON, GPKG, modos, recorte, altura, nodata y fallo sin publicar")


if __name__ == "__main__":
    main()
