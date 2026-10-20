"""List variables in a NetCDF or layers in a GeoPackage."""

import argparse
from pathlib import Path

import fiona
import rasterio
from rasterio.errors import NotGeoreferencedWarning
import warnings

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    path = args.file.resolve()
    if not path.is_file():
        parser.error(f"No existe: {path}")
    if path.suffix.lower() == ".gpkg":
        for layer in fiona.listlayers(path):
            with fiona.open(path, layer=layer) as source:
                print(f"{layer}: {len(source)} objetos; {source.schema['geometry']}; CRS {source.crs}; límites {source.bounds}")
    elif path.suffix.lower() == ".nc":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with rasterio.open(path) as root:
                variables = [(uri.rsplit(":", 1)[-1], uri) for uri in root.subdatasets]
                if not variables:
                    variables = [(root.tags(i).get("NETCDF_VARNAME"), str(path)) for i in range(1, root.count + 1)]
        for variable, uri in variables:
            with rasterio.open(uri) as source:
                print(f"{variable}: {source.width} x {source.height}; {source.count} banda(s); CRS {source.crs}; límites {source.bounds}; nodata {source.nodata}")
    else:
        parser.error("Se admiten archivos .nc y .gpkg")


if __name__ == "__main__":
    main()
