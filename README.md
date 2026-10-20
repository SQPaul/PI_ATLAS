# Explorador de los Campos de Hielo Patagónicos

Dashboard local con relieve 3D, colores de variables NetCDF y contornos GeoPackage. El diseño y la selección de las cuatro superficies originales se conservan.

## Abrir

En este PC (Linux), ejecuta en una terminal:

```bash
bash /media/isa/KINGSTON/PHD/Explorador/Abrir_explorador.sh
```

El lanzador abre el navegador en <http://127.0.0.1:8765/> y sirve los archivos directamente desde este disco. Mantén la terminal abierta mientras lo usas; **Ctrl+C** cierra el servidor. Si el puerto está ocupado, elige otro automáticamente. Si este mismo dashboard ya está abierto, reutiliza su servidor.

Solo se necesita **Python 3**, que ya está instalado en este PC. Las capas locales y MapLibre están incluidas y funcionan sin Internet. La imagen satelital Esri requiere conexión.

También puedes abrir una terminal en `Explorador` y ejecutar `python3 iniciar_explorador.py`. El lanzador detecta su carpeta: si cambia la ubicación del disco, sigue funcionando al ejecutarlo desde la nueva ubicación. No abras `index.html` directamente; las teselas necesitan un servidor HTTP.

Para abrirlo sin lanzar el navegador: `python3 iniciar_explorador.py --no-browser`. Para elegir un puerto: `python3 iniciar_explorador.py --port 8800`.

En Windows, si no tienes Python, abre PowerShell en `Explorador` y ejecuta `powershell -ExecutionPolicy Bypass -File .\iniciar_explorador.ps1`. Este lanzador usa PowerShell y sirve el mismo dashboard en <http://127.0.0.1:8765/>. También acepta `-NoBrowser` y `-Port 8800`.

## Fuentes actuales

| Capa | Archivo | Variable / capa |
| --- | --- | --- |
| Elevación superficial | `DEM_SRTM.nc` | `dem` |
| Elevación basal | `Fuerst_2024.nc` | `bedrock_elevation` |
| Elevación basal Frank 2026 | `Frank_2026_200m.nc` | `bedrock_elevation` |
| Elevación basal Maffezzoli 2026 | `Maffezzoli_2026_100m.nc` | `bedrock_elevation` |
| Carga hidráulica rellenada | `Fuerts_2024_hydraulic_head_catchments.nc` | `hydraulic_head_filled` |
| Corrección de carga | `Fuerts_2024_hydraulic_head_catchments.nc` | `hydraulic_head_difference` |
| Glaciares | `RGI_v6.gpkg` | `RGI_v6` |
| Gradiente hidráulico | `Delimitacion_gradiente_hidraulico.gpkg` | `Delimitacion_gradiente_hidraulico_dem_rellenado` |
| Cuencas Frank 2026 | `catchment_Frank2026.gpkg` | `catchment_Frank2026` |
| Cuencas Maffezzoli 2026 | `catchment_Maffezzoli2026_200m.gpkg` | `catchment_Maffezzoli2026_200m` |
| Cuencas dh/dt Fürst (25 años) | `catchment_Fuerst_dhdt_hydraulic_head_25years.gpkg` | `catchment_Fuerst_dhdt_hydraulic_head_25years` |

La elevación basal usa SRTM como contexto fuera de su cobertura. Las dos variables hidráulicas conservan relieve propio y altura cero donde faltan datos. La diferencia hidráulica actual es positiva; la paleta roja y la altura 3D muestran su magnitud. Los límites de color actuales siguen siendo −600 a 4000 m para elevación, −4 a 3800 m para carga y 0 a 320 m para diferencia; los valores fuera de esos límites usan el color extremo.

Las nuevas superficies de Frank y Maffezzoli usan relieve propio y una escala de color común de −1000 a 4000 m. El NetCDF de Maffezzoli declara el geoide EIGEN-6C4 como datum vertical; el de Frank no declara datum vertical. Las tres capas de cuencas se activan por separado en «Capas del mapa».

## Actualizar las fuentes

Esto solo es necesario al cambiar las fuentes; **no hace falta regenerar nada para abrir el dashboard actual**. Para regenerar se necesitan Rasterio, Fiona, NumPy, Matplotlib, Pillow, PyProj y Shapely. Puedes preparar un entorno con Conda:

```bash
conda create -n geopy -c conda-forge python=3.12 rasterio fiona numpy matplotlib pillow pyproj shapely
conda activate geopy
```

Cuando sustituyas un NetCDF o GeoPackage con el mismo nombre, ejecuta desde `Explorador`, con ese entorno activado:

```bash
python scripts/build_terrain.py
python scripts/build_hydraulic.py
python scripts/build_outlines.py
python scripts/build_layers.py
```

En Windows con QGIS 3.44 instalado, estas superficies y cuencas de `layers.json` se pueden regenerar con el Python de QGIS, sin instalar Rasterio ni Fiona:

```powershell
$qgis = 'C:\Program Files\QGIS 3.44.15'
$env:PATH = "$qgis\bin;$qgis\apps\Python312;$env:PATH"
$env:MPLCONFIGDIR = Join-Path $env:TEMP 'explorador-matplotlib'
& "$qgis\apps\Python312\python.exe" scripts\build_layers_gdal.py
```

Para publicar la versión estática, se incluyen `index.html`, `app.js`, `style.css`, `vendor/` y `terrain/`. Los NetCDF, GeoPackage y otros rásteres originales permanecen locales y están excluidos por `.gitignore`; el sitio publicado funciona con las teselas y GeoJSON generados.

El flujo `.github/workflows/pages.yml` publica esos archivos al enviar cambios a `main` o `master`. En la configuración del repositorio de GitHub, activa **Pages → Build and deployment → Source: GitHub Actions** antes de la primera publicación.

Para actualizar solo un GeoPackage original, basta `build_outlines.py`. Para actualizar una capa definida en `layers.json`, basta `build_layers.py`. Después recarga el navegador con **Ctrl+F5**. No edites a mano los PNG ni los GeoJSON generados en `terrain/`.

Consulta [GUIA_CAPAS.md](GUIA_CAPAS.md) para integrar nuevas variables NetCDF y geometrías, con ejemplos de los tres modos de visualización.
