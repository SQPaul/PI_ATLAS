"""Build configurable 3D surfaces and geometry overlays for the local map."""

import argparse
import json
import math
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

import fiona
import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds, transform_geom
from rasterio.windows import Window, bounds as window_bounds
from shapely.geometry import mapping, shape
from shapely.ops import transform

from build_terrain import terrarium, tile_bounds, tile_xy
from raster_sources import open_raster


ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / "terrain"
RESERVED_IDS = {"surface", "basal", "hydraulic-correction", "hydraulic-filled", "glaciers", "gradient"}
ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_TILE_PAIRS = 12000


def fail(message):
    raise ValueError(message)


def text_field(entry, key, label, default=None):
    value = entry.get(key, default)
    if not isinstance(value, str) or not value.strip():
        fail(f"{label}: '{key}' debe ser un texto no vacío")
    return value.strip()


def number_field(entry, key, label, default=None, minimum=None, maximum=None):
    value = entry.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        fail(f"{label}: '{key}' debe ser un número finito")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        fail(f"{label}: '{key}' está fuera del rango permitido")
    return float(value)


def source_path(entry, label, suffixes):
    name = text_field(entry, "file", label)
    candidate = Path(name)
    if candidate.is_absolute():
        fail(f"{label}: usa una ruta relativa a la carpeta del dashboard")
    path = (ROOT / candidate).resolve()
    if ROOT != path and ROOT not in path.parents:
        fail(f"{label}: el archivo debe estar dentro del proyecto")
    if path.suffix.lower() not in suffixes:
        fail(f"{label}: formato no admitido: {path.suffix}")
    if not path.is_file():
        fail(f"{label}: no existe {name}")
    return path


def validate_entry(entry, seen):
    if not isinstance(entry, dict):
        fail("Cada capa de layers.json debe ser un objeto")
    identifier = text_field(entry, "id", "capa")
    if not ID_PATTERN.fullmatch(identifier):
        fail(f"{identifier}: 'id' debe usar minúsculas, números y guiones; comenzar con letra")
    if identifier in RESERVED_IDS or identifier in seen:
        fail(f"{identifier}: 'id' duplicado o reservado")
    seen.add(identifier)
    text_field(entry, "label", identifier)
    return identifier


def load_catalog(path):
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict):
        fail("layers.json debe ser un objeto JSON")
    surfaces = catalog.get("surfaces", [])
    geometries = catalog.get("geometries", [])
    if not isinstance(surfaces, list) or not isinstance(geometries, list):
        fail("'surfaces' y 'geometries' deben ser listas")
    seen = set()
    for entry in surfaces + geometries:
        validate_entry(entry, seen)
    return surfaces, geometries


def zoom_range(entry, label):
    minimum = entry.get("minzoom", 5)
    maximum = entry.get("maxzoom", 10)
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (minimum, maximum)):
        fail(f"{label}: minzoom y maxzoom deben ser enteros")
    if not 0 <= minimum <= maximum <= 14:
        fail(f"{label}: minzoom/maxzoom deben estar entre 0 y 14")
    return minimum, maximum


def raster_bounds(source_bounds, crs, label):
    bounds = transform_bounds(crs, "EPSG:4326", *source_bounds, densify_pts=21)
    if not all(math.isfinite(v) for v in bounds) or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        fail(f"{label}: cobertura geográfica inválida")
    if bounds[0] < -180 or bounds[2] > 180 or bounds[1] < -85 or bounds[3] > 85:
        fail(f"{label}: cobertura fuera del rango admitido por las teselas Web Mercator")
    return [float(v) for v in bounds]


def tile_count(bounds, minzoom, maxzoom):
    total = 0
    for zoom in range(minzoom, maxzoom + 1):
        x0, y1 = tile_xy(bounds[0], bounds[1], zoom)
        x1, y0 = tile_xy(bounds[2], bounds[3], zoom)
        total += (x1 - x0 + 1) * (y1 - y0 + 1)
    return total


def colorize(values, valid, palette, low, high):
    positions = np.clip((np.where(valid, values, low) - low) / (high - low), 0, 1)
    rgba = (palette(positions) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def polygon_mask(entry, src, crs, label):
    clip = entry.get("clip")
    if clip is None:
        return None
    if not isinstance(clip, dict):
        fail(f"{label}: 'clip' debe ser un objeto con 'file' y opcionalmente 'layer'")
    path = source_path(clip, label, {".gpkg"})
    available = fiona.listlayers(path)
    layer = clip.get("layer")
    if layer is None and len(available) != 1:
        fail(f"{label}: 'clip.layer' es obligatorio si el GeoPackage tiene varias capas")
    layer = layer or available[0]
    if layer not in available:
        fail(f"{label}: 'clip.layer' no existe en {path.name}")
    with fiona.open(path, layer=layer) as vector:
        if not vector.crs:
            fail(f"{label}: el GeoPackage de recorte no declara CRS")
        polygons = []
        for feature in vector:
            geometry = feature["geometry"]
            if geometry and geometry["type"] in {"Polygon", "MultiPolygon"}:
                polygons.append(transform_geom(vector.crs, crs, dict(geometry)))
        if not polygons:
            fail(f"{label}: 'clip' no contiene polígonos")
    return geometry_mask(polygons, out_shape=src.shape, transform=src.transform, invert=True)


def build_surface(entry, build_dir, url_prefix):
    identifier = entry["id"]
    path = source_path(entry, identifier, {".nc", ".tif", ".tiff", ".map"})
    variable = entry.get("variable")
    if path.suffix.lower() == ".nc" and (not isinstance(variable, str) or not variable.strip()):
        fail(f"{identifier}: indica 'variable' para el NetCDF")
    display = entry.get("display", "own")
    if display not in {"own", "relief", "overlay"}:
        fail(f"{identifier}: 'display' debe ser 'own', 'relief' u 'overlay'")
    if display == "overlay" and not isinstance(entry.get("visible", False), bool):
        fail(f"{identifier}: 'visible' debe ser true o false")
    label = text_field(entry, "label", identifier)
    description = entry.get("description", "")
    if not isinstance(description, str):
        fail(f"{identifier}: 'description' debe ser un texto")
    unit = text_field(entry, "unit", identifier)
    palette_name = text_field(entry, "palette", identifier)
    try:
        palette = colormaps[palette_name]
    except KeyError:
        fail(f"{identifier}: paleta Matplotlib desconocida: {palette_name}")
    value_range = entry.get("range")
    if not isinstance(value_range, list) or len(value_range) != 2:
        fail(f"{identifier}: 'range' debe contener [mínimo, máximo]")
    low = number_field({"v": value_range[0]}, "v", identifier)
    high = number_field({"v": value_range[1]}, "v", identifier)
    if low >= high:
        fail(f"{identifier}: el máximo de 'range' debe ser mayor al mínimo")
    height = entry.get("height", {})
    if not isinstance(height, dict):
        fail(f"{identifier}: 'height' debe ser un objeto")
    mode = height.get("mode", "value")
    if mode not in {"value", "absolute"}:
        fail(f"{identifier}: 'height.mode' debe ser 'value' o 'absolute'")
    scale = number_field(height, "scale", identifier, default=1, minimum=0.000001)
    offset = number_field(height, "offset", identifier, default=0)
    minzoom, maxzoom = zoom_range(entry, identifier)

    with open_raster(path, variable) as src:
        declared_crs = entry.get("crs")
        if src.crs is None and not declared_crs:
            fail(f"{identifier}: el ráster no tiene CRS; indica 'crs' (por ejemplo EPSG:32718)")
        try:
            crs = rasterio.crs.CRS.from_user_input(declared_crs or src.crs)
        except Exception as exc:
            fail(f"{identifier}: CRS inválido: {exc}")
        if src.crs is not None and declared_crs and crs != src.crs:
            fail(f"{identifier}: 'crs' no coincide con el CRS del archivo")
        # The valid-pixel footprint gives a useful view and avoids generating
        # empty tiles for rasters with wide nodata margins.
        source_array = src.read(1, masked=True).astype(np.float32).filled(np.nan)
        valid_source = np.isfinite(source_array)
        clip_mask = polygon_mask(entry, src, crs, identifier)
        if clip_mask is not None:
            valid_source &= clip_mask
            source_array[~valid_source] = np.nan
        if not np.any(valid_source):
            fail(f"{identifier}: el ráster no contiene píxeles válidos")
        rows = np.flatnonzero(np.any(valid_source, axis=1))
        columns = np.flatnonzero(np.any(valid_source, axis=0))
        window = Window(int(columns[0]), int(rows[0]), int(columns[-1] - columns[0] + 1), int(rows[-1] - rows[0] + 1))
        bounds = raster_bounds(window_bounds(window, src.transform), crs, identifier)
        count = tile_count(bounds, minzoom, maxzoom)
        if count > MAX_TILE_PAIRS:
            fail(f"{identifier}: {count} pares de teselas exceden el límite {MAX_TILE_PAIRS}; reduce maxzoom")
        valid_any = False
        for zoom in range(minzoom, maxzoom + 1):
            x0, y1 = tile_xy(bounds[0], bounds[1], zoom)
            x1, y0 = tile_xy(bounds[2], bounds[3], zoom)
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    transform_tile = from_bounds(*tile_bounds(x, y, zoom), 256, 256)
                    values = np.full((256, 256), np.nan, dtype=np.float32)
                    reproject(
                        source=source_array, destination=values,
                        src_transform=src.transform, src_crs=crs, src_nodata=np.nan,
                        dst_transform=transform_tile, dst_crs="EPSG:3857", dst_nodata=np.nan,
                        resampling=Resampling.bilinear, init_dest_nodata=True,
                    )
                    valid = np.isfinite(values)
                    valid_any = valid_any or bool(valid.any())
                    color_file = build_dir / identifier / "color" / str(zoom) / str(x) / f"{y}.png"
                    color_file.parent.mkdir(parents=True, exist_ok=True)
                    colorize(values, valid, palette, low, high).save(color_file, compress_level=6)
                    if display == "own":
                        dem_file = build_dir / identifier / "dem" / str(zoom) / str(x) / f"{y}.png"
                        dem_file.parent.mkdir(parents=True, exist_ok=True)
                        interpreted = np.abs(values) if mode == "absolute" else values
                        elevations = np.where(valid, interpreted * scale + offset, 0)
                        if valid.any() and (np.min(elevations) < -32768 or np.max(elevations) > 32767):
                            fail(f"{identifier}: altura 3D fuera del rango Terrarium; ajusta height.scale/offset")
                        terrarium(elevations).save(dem_file, compress_level=6)
            print(f"{identifier}: zoom {zoom} listo", flush=True)
        if not valid_any:
            fail(f"{identifier}: no hay datos válidos en las teselas; revisa el CRS o aumenta maxzoom")

    scale_values = np.linspace(low, high, 1024, dtype=np.float32)[None, :]
    bar = np.repeat(np.asarray(colorize(scale_values, np.ones(scale_values.shape, dtype=bool), palette, low, high)), 20, axis=0)
    Image.fromarray(bar, "RGBA").save(build_dir / identifier / "colorbar.png")
    prefix = f"{url_prefix}/{identifier}"
    return {
        "id": identifier, "label": label, "description": description, "unit": unit,
        "display": display, "visible": entry.get("visible", False) if display == "overlay" else False,
        "clip": entry.get("clip"),
        "range": [low, high], "bounds": bounds, "minzoom": minzoom, "maxzoom": maxzoom,
        "height": {"mode": mode, "scale": scale, "offset": offset},
        "demTiles": f"{prefix}/dem/{{z}}/{{x}}/{{y}}.png" if display == "own" else None,
        "colorTiles": f"{prefix}/color/{{z}}/{{x}}/{{y}}.png",
        "colorbar": f"{prefix}/colorbar.png",
    }


def build_geometry(entry, build_dir, url_prefix):
    identifier = entry["id"]
    path = source_path(entry, identifier, {".gpkg", ".geojson", ".json"})
    label = text_field(entry, "label", identifier)
    description = entry.get("description", "")
    if not isinstance(description, str):
        fail(f"{identifier}: 'description' debe ser un texto")
    color = entry.get("color", "#cf302b")
    if not isinstance(color, str) or not COLOR_PATTERN.fullmatch(color):
        fail(f"{identifier}: 'color' debe ser #RRGGBB")
    width = number_field(entry, "width", identifier, default=2, minimum=0.1, maximum=20)
    radius = number_field(entry, "radius", identifier, default=5, minimum=0.1, maximum=30)
    fill_opacity = number_field(entry, "fillOpacity", identifier, default=0, minimum=0, maximum=1)
    visible = entry.get("visible", True)
    if not isinstance(visible, bool):
        fail(f"{identifier}: 'visible' debe ser true o false")
    simplify_m = number_field(entry, "simplify_m", identifier, default=0, minimum=0)
    requested_layer = entry.get("layer")
    if requested_layer is not None and (not isinstance(requested_layer, str) or not requested_layer.strip()):
        fail(f"{identifier}: 'layer' debe ser el nombre de una capa GeoPackage")
    if path.suffix.lower() == ".gpkg":
        available = fiona.listlayers(path)
        if requested_layer is None and len(available) != 1:
            fail(f"{identifier}: GeoPackage con varias capas; especifica 'layer' ({', '.join(available)})")
        if requested_layer is not None and requested_layer not in available:
            fail(f"{identifier}: 'layer' no existe en el GeoPackage")
        requested_layer = requested_layer or available[0]

    features = []
    geometry_types = set()
    extent = [math.inf, math.inf, -math.inf, -math.inf]
    with fiona.open(path, layer=requested_layer) as source:
        if not source.crs and path.suffix.lower() not in {".geojson", ".json"}:
            fail(f"{identifier}: la geometría no declara CRS")
        source_crs = source.crs or "EPSG:4326"
        to_wgs84 = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True).transform
        to_meters = Transformer.from_crs(source_crs, "EPSG:3857", always_xy=True).transform if simplify_m else None
        from_meters = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform if simplify_m else None
        for item in source:
            if not item["geometry"]:
                continue
            geometry = shape(item["geometry"])
            if geometry.is_empty:
                continue
            geographic = transform(from_meters, transform(to_meters, geometry).simplify(simplify_m, preserve_topology=True)) if simplify_m else transform(to_wgs84, geometry)
            if geographic.is_empty:
                continue
            if not geographic.is_valid:
                geographic = geographic.buffer(0)
            if geographic.is_empty:
                continue
            geometry_types.add(geographic.geom_type.upper())
            bbox = geographic.bounds
            extent = [min(extent[0], bbox[0]), min(extent[1], bbox[1]), max(extent[2], bbox[2]), max(extent[3], bbox[3])]
            features.append({"type": "Feature", "properties": {}, "geometry": mapping(geographic)})
    if not features:
        fail(f"{identifier}: no hay geometrías válidas")
    if extent[0] < -180 or extent[2] > 180 or extent[1] < -85 or extent[3] > 85:
        fail(f"{identifier}: cobertura fuera del mapa Web Mercator")
    output = build_dir / identifier / "features.geojson"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    return {
        "id": identifier, "label": label, "description": description, "bounds": extent,
        "color": color, "width": width, "radius": radius, "fillOpacity": fill_opacity,
        "visible": visible, "geojson": f"{url_prefix}/{identifier}/features.geojson",
        "featureCount": len(features), "geometryTypes": sorted(geometry_types),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "layers.json", help="JSON de capas (por defecto layers.json)")
    parser.add_argument("--output", type=Path, default=TERRAIN, help="Carpeta de salida, útil para pruebas")
    args = parser.parse_args()
    catalog_path = args.catalog.resolve()
    output_root = args.output.resolve()
    if not catalog_path.is_file():
        fail(f"No existe el catálogo: {catalog_path}")
    surfaces, geometries = load_catalog(catalog_path)
    build_root = output_root / "custom-builds"
    manifest_path = output_root / "custom-layers.json"
    build_root.mkdir(parents=True, exist_ok=True)
    previous_versions = set()
    if manifest_path.is_file():
        try:
            old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            urls = [item.get("geojson", "") for item in old_manifest.get("geometries", [])]
            urls += [item.get("colorTiles", "") for item in old_manifest.get("surfaces", []) + old_manifest.get("overlays", [])]
            previous_versions = {match.group(1) for url in urls if (match := re.search(r"/custom-builds/([0-9a-f]{12})/", url))}
        except (ValueError, AttributeError, TypeError):
            pass
    version = uuid.uuid4().hex[:12]
    build_dir = build_root / version
    build_dir.mkdir()
    url_prefix = f"./terrain/custom-builds/{version}"
    temp_manifest = output_root / f"custom-layers-{version}.tmp"
    try:
        built_surfaces = [build_surface(item, build_dir, url_prefix) for item in surfaces]
        result = {
            "surfaces": [item for item in built_surfaces if item["display"] != "overlay"],
            "overlays": [item for item in built_surfaces if item["display"] == "overlay"],
            "geometries": [build_geometry(item, build_dir, url_prefix) for item in geometries],
        }
        temp_manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_manifest, manifest_path)
    except Exception:
        temp_manifest.unlink(missing_ok=True)
        shutil.rmtree(build_dir)
        raise
    # Keep the current and immediately previous build so an open tab can finish
    # loading old tile URLs until the next browser refresh.
    keep = previous_versions | {version}
    for child in build_root.iterdir():
        if child.is_dir() and re.fullmatch(r"[0-9a-f]{12}", child.name) and child.name not in keep:
            if child.resolve().parent != build_root.resolve():
                continue
            try:
                shutil.rmtree(child)
            except OSError as exc:
                print(f"Aviso: no se pudo borrar la versión antigua {child.name}: {exc}", file=sys.stderr)
    print(f"Listo: {len(result['surfaces'])} superficies, {len(result['overlays'])} capas superpuestas y {len(geometries)} geometrías. Manifiesto: {manifest_path}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, json.JSONDecodeError, rasterio.errors.RasterioError, fiona.errors.FionaError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
