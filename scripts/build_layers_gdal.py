"""Build the configurable map layers with the GDAL Python shipped by QGIS."""

import argparse
import json
import math
import os
import re
import uuid
from pathlib import Path

import numpy as np
from matplotlib import colormaps
from osgeo import gdal, ogr, osr
from PIL import Image
from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[1]
MAX_TILE_PAIRS = 12000
MERCATOR_RADIUS = 20037508.342789244
MAX_LATITUDE = 85.05112878
ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

gdal.UseExceptions()
ogr.UseExceptions()


def tile_xy(lon, lat, zoom):
    lat = max(-MAX_LATITUDE, min(MAX_LATITUDE, lat))
    n = 2**zoom
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def tile_bounds(x, y, zoom):
    size = 2 * MERCATOR_RADIUS / 2**zoom
    left, top = -MERCATOR_RADIUS + x * size, MERCATOR_RADIUS - y * size
    return left, top - size, left + size, top


def tile_ranges(bounds, minzoom, maxzoom):
    for zoom in range(minzoom, maxzoom + 1):
        x0, y1 = tile_xy(bounds[0], bounds[1], zoom)
        x1, y0 = tile_xy(bounds[2], bounds[3], zoom)
        yield zoom, range(x0, x1 + 1), range(y0, y1 + 1)


def colorize(values, valid, palette, low, high):
    positions = np.clip((np.where(valid, values, low) - low) / (high - low), 0, 1)
    rgba = (palette(positions) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def terrarium(heights):
    encoded = np.clip(np.round((heights + 32768) * 256), 0, 16777215).astype(np.uint32)
    rgb = np.empty((*heights.shape, 3), dtype=np.uint8)
    rgb[..., 0] = encoded >> 16
    rgb[..., 1] = (encoded >> 8) & 255
    rgb[..., 2] = encoded & 255
    return Image.fromarray(rgb, "RGB")


def source_path(entry, suffixes):
    name = entry.get("file")
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError(f"{entry['id']}: 'file' debe ser una ruta relativa")
    path = (ROOT / name).resolve()
    if ROOT not in path.parents or path.suffix.lower() not in suffixes or not path.is_file():
        raise ValueError(f"{entry['id']}: fuente inválida: {name}")
    return path


def validate_catalog(catalog):
    surfaces = catalog.get("surfaces", [])
    geometries = catalog.get("geometries", [])
    if not isinstance(surfaces, list) or not isinstance(geometries, list):
        raise ValueError("'surfaces' y 'geometries' deben ser listas")
    seen = {"surface", "basal", "hydraulic-correction", "hydraulic-filled", "glaciers", "gradient"}
    for entry in surfaces + geometries:
        if not isinstance(entry, dict) or not ID_PATTERN.fullmatch(str(entry.get("id", ""))):
            raise ValueError("Cada capa debe tener un 'id' válido")
        if entry["id"] in seen:
            raise ValueError(f"ID duplicado o reservado: {entry['id']}")
        seen.add(entry["id"])
        if not isinstance(entry.get("label"), str) or not entry["label"]:
            raise ValueError(f"{entry['id']}: falta 'label'")
    return surfaces, geometries


def zoom_range(entry):
    minimum, maximum = entry.get("minzoom", 5), entry.get("maxzoom", 10)
    if any(type(value) is not int for value in (minimum, maximum)) or not 0 <= minimum <= maximum <= 14:
        raise ValueError(f"{entry['id']}: rango de zoom inválido")
    return minimum, maximum


def build_surface(entry, build_dir, url_prefix):
    identifier = entry["id"]
    path = source_path(entry, {".nc", ".tif", ".tiff", ".map"})
    variable = entry.get("variable")
    if path.suffix.lower() == ".nc":
        if not isinstance(variable, str) or not variable:
            raise ValueError(f"{identifier}: falta 'variable'")
        root_dataset = gdal.Open(str(path))
        names = [name.rsplit(":", 1)[-1] for name, _ in root_dataset.GetSubDatasets()]
        if variable not in names:
            raise ValueError(f"{identifier}: variable {variable!r} no existe; disponibles: {names}")
        source = gdal.Open(f'NETCDF:"{path}":{variable}')
    else:
        source = gdal.Open(str(path))
    if source is None or source.RasterCount != 1 or not source.GetProjection():
        raise ValueError(f"{identifier}: el ráster debe tener una banda y CRS declarado")

    display = entry.get("display", "own")
    if display not in {"own", "relief", "overlay"}:
        raise ValueError(f"{identifier}: 'display' inválido")
    low, high = entry["range"]
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (low, high)) or low >= high:
        raise ValueError(f"{identifier}: 'range' inválido")
    palette = colormaps[entry["palette"]]
    mode = entry.get("height", {}).get("mode", "value")
    scale = entry.get("height", {}).get("scale", 1)
    offset = entry.get("height", {}).get("offset", 0)
    if mode not in {"value", "absolute"} or scale <= 0:
        raise ValueError(f"{identifier}: 'height' inválido")
    minzoom, maxzoom = zoom_range(entry)

    band = source.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    source_array = band.ReadAsArray()
    valid = np.isfinite(source_array)
    if nodata is not None:
        valid &= source_array != nodata
    if not valid.any():
        raise ValueError(f"{identifier}: el ráster no tiene píxeles válidos")
    rows = np.flatnonzero(valid.any(axis=1))
    columns = np.flatnonzero(valid.any(axis=0))
    gt = source.GetGeoTransform()
    if gt[2] != 0 or gt[4] != 0:
        raise ValueError(f"{identifier}: la cuadrícula rotada no está admitida")
    xmin = gt[0] + columns[0] * gt[1]
    xmax = gt[0] + (columns[-1] + 1) * gt[1]
    ymax = gt[3] + rows[0] * gt[5]
    ymin = gt[3] + (rows[-1] + 1) * gt[5]
    bounds = list(Transformer.from_crs(source.GetProjection(), "EPSG:4326", always_xy=True).transform_bounds(
        xmin, ymin, xmax, ymax, densify_pts=21
    ))
    if bounds[0] < -180 or bounds[2] > 180 or bounds[1] < -85 or bounds[3] > 85:
        raise ValueError(f"{identifier}: cobertura fuera de Web Mercator")
    total = sum(len(xs) * len(ys) for _, xs, ys in tile_ranges(bounds, minzoom, maxzoom))
    if total > MAX_TILE_PAIRS:
        raise ValueError(f"{identifier}: {total} teselas exceden el límite {MAX_TILE_PAIRS}")
    print(f"{identifier}: {total} pares de teselas", flush=True)
    del source_array, valid

    any_valid = False
    for zoom, xs, ys in tile_ranges(bounds, minzoom, maxzoom):
        for x in xs:
            for y in ys:
                warped = gdal.Warp(
                    "", source, format="MEM", outputBounds=tile_bounds(x, y, zoom),
                    width=256, height=256, dstSRS="EPSG:3857", srcNodata=nodata,
                    dstNodata=-9999, outputType=gdal.GDT_Float32, resampleAlg="bilinear",
                )
                values = warped.ReadAsArray()
                valid = np.isfinite(values) & (values != -9999)
                any_valid |= bool(valid.any())
                color_file = build_dir / identifier / "color" / str(zoom) / str(x) / f"{y}.png"
                color_file.parent.mkdir(parents=True, exist_ok=True)
                colorize(values, valid, palette, low, high).save(color_file, compress_level=6)
                if display == "own":
                    dem_file = build_dir / identifier / "dem" / str(zoom) / str(x) / f"{y}.png"
                    dem_file.parent.mkdir(parents=True, exist_ok=True)
                    elevations = np.where(valid, (np.abs(values) if mode == "absolute" else values) * scale + offset, 0)
                    if elevations.min() < -32768 or elevations.max() > 32767:
                        raise ValueError(f"{identifier}: altura fuera del rango Terrarium")
                    terrarium(elevations).save(dem_file, compress_level=6)
                warped = None
        print(f"{identifier}: zoom {zoom} listo", flush=True)
    if not any_valid:
        raise ValueError(f"{identifier}: las teselas no contienen datos")
    bar_values = np.linspace(low, high, 1024, dtype=np.float32)[None, :]
    bar = np.repeat(np.asarray(colorize(bar_values, np.ones_like(bar_values, dtype=bool), palette, low, high)), 20, axis=0)
    Image.fromarray(bar, "RGBA").save(build_dir / identifier / "colorbar.png")
    prefix = f"{url_prefix}/{identifier}"
    return {
        "id": identifier, "label": entry["label"], "description": entry.get("description", ""),
        "unit": entry["unit"], "display": display,
        "visible": entry.get("visible", False) if display == "overlay" else False,
        "clip": entry.get("clip"), "range": [low, high], "bounds": bounds,
        "minzoom": minzoom, "maxzoom": maxzoom,
        "height": {"mode": mode, "scale": scale, "offset": offset},
        "demTiles": f"{prefix}/dem/{{z}}/{{x}}/{{y}}.png" if display == "own" else None,
        "colorTiles": f"{prefix}/color/{{z}}/{{x}}/{{y}}.png",
        "colorbar": f"{prefix}/colorbar.png",
    }


def build_geometry(entry, build_dir, url_prefix):
    identifier = entry["id"]
    path = source_path(entry, {".gpkg", ".geojson", ".json"})
    source = ogr.Open(str(path))
    layer = source.GetLayerByName(entry.get("layer", path.stem))
    if layer is None:
        raise ValueError(f"{identifier}: la capa no existe en {path.name}")
    source_srs = layer.GetSpatialRef()
    if source_srs is None:
        raise ValueError(f"{identifier}: la geometría no declara CRS")
    source_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target_srs = osr.SpatialReference()
    target_srs.ImportFromEPSG(4326)
    target_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(source_srs, target_srs)
    simplify_m = entry.get("simplify_m", 0)
    if simplify_m and (not source_srs.IsProjected() or abs(source_srs.GetLinearUnits() - 1) > 0.001):
        raise ValueError(f"{identifier}: simplify_m requiere un CRS en metros")

    output = build_dir / identifier / "features.geojson"
    output.parent.mkdir(parents=True, exist_ok=True)
    bounds = [math.inf, math.inf, -math.inf, -math.inf]
    count = 0
    geometry_types = set()
    with output.open("w", encoding="utf-8") as dest:
        dest.write('{"type":"FeatureCollection","features":[')
        for feature in layer:
            geometry = feature.GetGeometryRef()
            if geometry is None or geometry.IsEmpty():
                continue
            geometry = geometry.Clone()
            if simplify_m:
                geometry = geometry.SimplifyPreserveTopology(simplify_m)
            if geometry is None or geometry.IsEmpty():
                continue
            geometry.Transform(transform)
            geometry_types.add(geometry.GetGeometryName().upper())
            left, right, bottom, top = geometry.GetEnvelope()
            bounds = [min(bounds[0], left), min(bounds[1], bottom), max(bounds[2], right), max(bounds[3], top)]
            if count:
                dest.write(",")
            dest.write('{"type":"Feature","properties":{},"geometry":')
            dest.write(geometry.ExportToJson())
            dest.write("}")
            count += 1
        dest.write("]}")
    if not count or bounds[0] < -180 or bounds[2] > 180 or bounds[1] < -85 or bounds[3] > 85:
        raise ValueError(f"{identifier}: extensión geográfica inválida")
    print(f"{identifier}: {count} geometrías", flush=True)
    return {
        "id": identifier, "label": entry["label"], "description": entry.get("description", ""),
        "bounds": bounds, "color": entry.get("color", "#cf302b"),
        "width": entry.get("width", 2), "radius": entry.get("radius", 5),
        "fillOpacity": entry.get("fillOpacity", 0), "visible": entry.get("visible", True),
        "geojson": f"{url_prefix}/{identifier}/features.geojson", "featureCount": count,
        "geometryTypes": sorted(geometry_types),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "layers.json")
    parser.add_argument("--output", type=Path, default=ROOT / "terrain")
    args = parser.parse_args()
    surfaces, geometries = validate_catalog(json.loads(args.catalog.read_text(encoding="utf-8")))
    output_root = args.output.resolve()
    version = uuid.uuid4().hex[:12]
    build_dir = output_root / "custom-builds" / version
    build_dir.mkdir(parents=True, exist_ok=False)
    url_prefix = f"./terrain/custom-builds/{version}"
    built_surfaces = [build_surface(entry, build_dir, url_prefix) for entry in surfaces]
    manifest = {
        "surfaces": [item for item in built_surfaces if item["display"] != "overlay"],
        "overlays": [item for item in built_surfaces if item["display"] == "overlay"],
        "geometries": [build_geometry(entry, build_dir, url_prefix) for entry in geometries],
    }
    temp_manifest = output_root / f"custom-layers-{version}.tmp"
    temp_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_manifest, output_root / "custom-layers.json")
    print(f"Listo: {len(manifest['surfaces'])} superficies y {len(manifest['geometries'])} geometrías", flush=True)


if __name__ == "__main__":
    main()
