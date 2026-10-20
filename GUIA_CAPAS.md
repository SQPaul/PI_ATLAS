# Guía para añadir y actualizar capas

El navegador muestra teselas PNG y GeoJSON generados en `terrain/`. Los NetCDF y GeoPackage son las fuentes de trabajo. Los scripts usan Rasterio, Fiona, NumPy, Matplotlib, Pillow, PyProj y Shapely del entorno `geopy` indicado en el README.

## 1. Inspeccionar la fuente

Copia cada archivo nuevo dentro de `Explorador` (por ejemplo, en `data/`). Para consultar nombres, cuadrícula y CRS:

Con el entorno `geopy` del README activado y desde la carpeta `Explorador`:

```bash
python scripts/inspect_sources.py data/mi_variable.nc
python scripts/inspect_sources.py data/mi_geometria.gpkg
```

El generador acepta una variable NetCDF **2D de una banda**, georreferenciada y con CRS correcto. Selecciona la variable con `variable`, no el nombre del archivo. Si el archivo no declara CRS, `crs` puede indicar el CRS comprobado del dato; nunca se reproyecta mediante una suposición. Para GeoPackage, usa `layer` si hay varias capas internas. Todas las rutas de `layers.json` son relativas a `Explorador`.

## 2. Elegir la presentación

| `display` | Control del dashboard | Altura 3D | Uso típico |
| --- | --- | --- | --- |
| `own` | Radio en «Superficie 3D» | Valores de la variable según `height` | DEM, carga o variable que define su propio relieve |
| `relief` | Radio en «Superficie 3D» | DEM SRTM existente; color de la variable | Variable temática sobre relieve SRTM |
| `overlay` | Interruptor en «Capas del mapa» | La superficie 3D que esté seleccionada; color superpuesto con 78 % de opacidad | Comparar una variable con cualquier superficie activa |

En `own`, los píxeles sin dato forman un plano a 0 m y son transparentes. En `relief` y `overlay`, los píxeles sin dato son transparentes y dejan visible la capa inferior. `relief` siempre toma la altura del SRTM original. `overlay` se puede activar junto a otra capa; si activas varias, la última definida en `layers.json` queda encima.

## 3. Editar `layers.json`

El siguiente catálogo es un ejemplo completo. Cambia las rutas, variables, rangos y unidades por tus datos; no copies estos nombres si los archivos no existen. La lista `surfaces` admite los tres modos.

```json
{
  "surfaces": [
    {
      "id": "temperatura-relieve",
      "file": "data/temperatura.nc",
      "variable": "temperature",
      "label": "Temperatura sobre SRTM",
      "description": "Temperatura media",
      "unit": "°C",
      "palette": "coolwarm",
      "range": [-20, 10],
      "display": "relief"
    },
    {
      "id": "espesor-superpuesto",
      "file": "data/espesor.nc",
      "variable": "ice_thickness",
      "label": "Espesor del hielo",
      "unit": "m",
      "palette": "viridis",
      "range": [0, 1500],
      "display": "overlay",
      "visible": false
    },
    {
      "id": "carga-propia",
      "file": "data/carga.nc",
      "variable": "hydraulic_head",
      "label": "Carga con relieve propio",
      "unit": "m",
      "palette": "YlGnBu",
      "range": [0, 4000],
      "display": "own",
      "height": {"mode": "value", "scale": 1, "offset": 0},
      "clip": {"file": "data/cuencas.gpkg", "layer": "cuencas"}
    }
  ],
  "geometries": [
    {
      "id": "cuencas",
      "file": "data/cuencas.gpkg",
      "layer": "cuencas",
      "label": "Límites de cuencas",
      "description": "Contornos sobre el terreno",
      "color": "#00a9b7",
      "width": 2,
      "visible": true
    }
  ]
}
```

`clip` es opcional y recorta los píxeles de cualquier variable NetCDF a los polígonos de un GeoPackage. El recorte no dibuja los límites: para verlos, añade el mismo archivo a `geometries`, como en el ejemplo. Un GeoPackage de líneas o puntos no sirve para `clip`, pero sí para `geometries`. Si cambias los polígonos manteniendo el nombre de archivo, vuelve a generar la capa para aplicar el recorte nuevo.

Cada `id` debe empezar con una letra y usar minúsculas, números y guiones. Debe ser único y no coincidir con las capas originales. `label`, `unit`, `palette` y `range` son obligatorios para superficies. `palette` usa un nombre de Matplotlib. `range` controla color y leyenda; **no recorta alturas ni modifica los valores fuente**. Las alturas 3D de `own` se calculan como `valor × scale + offset` en metros. Con `"mode": "absolute"` se usa la magnitud de valores negativos. La codificación Terrarium admite aproximadamente de −32768 a 32767 m, por lo que ajusta `scale` y `offset` si hace falta. En las superficies nuevas, el control «Escala vertical» solo aparece para `own` y modifica la visualización, no los datos.

Para geometrías: `color` usa `#RRGGBB`; `width` es ancho de línea en píxeles, `radius` es radio de puntos, `fillOpacity` rellena polígonos de 0 a 1 y `visible` indica el estado inicial. `simplify_m` es una tolerancia opcional en metros para geometrías complejas. Los GeoPackage deben declarar CRS; las geometrías se exportan a WGS84. También se admite GeoJSON con coordenadas WGS84.

Puedes ajustar `minzoom` y `maxzoom` por capa (por defecto 5 y 10, máximo 14). Un zoom máximo alto multiplica el número de teselas. El generador limita a 12.000 pares de teselas por capa. Empieza con 10 y aumenta solo si el detalle lo requiere.

## 4. Generar y comprobar

```bash
python scripts/build_layers.py
python iniciar_explorador.py
```

Abre <http://127.0.0.1:8765/> y recarga con **Ctrl+F5** después de cada generación. Las capas nuevas aparecen en los controles existentes. El generador escribe `terrain/custom-layers.json` y `terrain/custom-builds/`; conserva el manifiesto anterior si falla la validación. El archivo `layers.json` es la fuente editable.

Para comprobar el generador y el relieve hidráulico actual:

```bash
python scripts/test_build_layers.py
python scripts/test_hydraulic_tiles.py
```

## 5. Sustituir fuentes originales

Los scripts originales fijan las rutas y variables actuales en `build_terrain.py`, `build_hydraulic.py` y `build_outlines.py`. Si sustituyes un archivo conservando el mismo nombre y variables, ejecuta el comando correspondiente del README. Si cambias un nombre o variable, edita la constante `SURFACE`, `BED` o `SOURCES` antes de regenerar. Comprueba que el CRS sea correcto y que las variables sigan representando las magnitudes esperadas. La diferencia hidráulica actual es **positiva**; `build_hydraulic.py` colorea y dibuja su magnitud. La leyenda roja satura a partir de 320 m, aunque el máximo de la fuente actual ronda 370 m.

`build_outlines.py` recorta los GeoPackage originales al DEM. Al cambiar la delimitación del gradiente, regenera los contornos aunque el archivo conserve el mismo nombre. El navegador usa una versión de URL para evitar mostrar una geometría antigua de la caché; tras una actualización futura, usa Ctrl+F5. Si necesitas invalidar cachés de usuarios que ya abrieron el sitio, cambia `assetRevision` en `app.js` y el parámetro `v` del script en `index.html`.
