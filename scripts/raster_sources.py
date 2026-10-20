"""Open a named NetCDF variable or a conventional single-band raster."""

from contextlib import contextmanager
import warnings

import rasterio
from rasterio.errors import NotGeoreferencedWarning


@contextmanager
def open_raster(path, variable=None):
    path = path.resolve()
    if path.suffix.lower() == ".nc":
        if not variable or not isinstance(variable, str):
            raise ValueError(f"{path.name}: indica el nombre de la variable NetCDF")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with rasterio.open(path) as root:
                subdatasets = root.subdatasets
                if not subdatasets:
                    names = [root.tags(band).get("NETCDF_VARNAME") for band in range(1, root.count + 1)]
                    if root.count != 1 or names != [variable]:
                        raise ValueError(f"{path.name}: no existe la variable {variable!r}; disponibles: {names}")
                    uri = str(path)
                else:
                    matches = [uri for uri in subdatasets if uri.rsplit(":", 1)[-1] == variable]
                    if len(matches) != 1:
                        names = [uri.rsplit(":", 1)[-1] for uri in subdatasets]
                        raise ValueError(f"{path.name}: no existe la variable {variable!r}; disponibles: {names}")
                    uri = matches[0]
    else:
        if variable is not None:
            raise ValueError(f"{path.name}: 'variable' solo se usa con NetCDF")
        uri = str(path)
    with rasterio.open(uri) as source:
        if source.count != 1:
            raise ValueError(f"{path.name}: la variable debe tener una sola banda (2D)")
        yield source
