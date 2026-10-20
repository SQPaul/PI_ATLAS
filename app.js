import * as maplibregl from './vendor/maplibre-gl.mjs';

const message = document.getElementById('map-message');
const coverage = [-74.2206005, -51.4580171, -72.8625765, -46.4486230];
const bounds = [[coverage[0], coverage[1]], [coverage[2], coverage[3]]];
const assetRevision = 'basal-20261020-lines';
const exaggerationByLayer = new Map();
const customSurfaces = [];
const customOverlays = [];
const customGeometries = [];
const customSourceIds = new Set();
let focusedBounds = bounds;
let focusedPitch = 58;
const tileSource = name => ({
  type: 'raster-dem',
  tiles: [`./terrain/${name}/{z}/{x}/{y}.png?v=${assetRevision}`],
  tileSize: 256,
  encoding: 'terrarium',
  minzoom: 5,
  maxzoom: 10,
  bounds: coverage,
  attribution: name === 'surface' ? 'Relieve: DEM_SRTM.nc · dem' : name === 'basal' ? 'Relieve basal: Fuerst_2024.nc · bedrock_elevation; contexto SRTM' : 'Variables: Fuerts_2024_hydraulic_head_catchments.nc'
});
const colorSource = name => ({
  type: 'raster',
  tiles: [`./terrain/${name}-color/{z}/{x}/{y}.png?v=${assetRevision}`],
  tileSize: 256,
  minzoom: 5,
  maxzoom: 10,
  bounds: coverage
});
const hydraulicSource = name => ({
  type: 'raster',
  tiles: [`./terrain/hydraulic-${name}/{z}/{x}/{y}.png?v=${assetRevision}`],
  tileSize: 256,
  minzoom: 5,
  maxzoom: 10,
  bounds: coverage
});

const map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
    sources: {
      surface: tileSource('surface'), basal: tileSource('basal'),
      'hydraulic-correction-dem': tileSource('hydraulic-correction-dem'),
      'hydraulic-filled-dem': tileSource('hydraulic-filled-dem'),
      'surface-color': colorSource('surface'), 'basal-color': colorSource('basal'),
      'hydraulic-correction': hydraulicSource('correction'),
      'hydraulic-filled': hydraulicSource('filled'),
      'esri-imagery': {
        type: 'raster',
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        tileSize: 256,
        maxzoom: 19,
        attribution: '<a href="https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9" target="_blank" rel="noopener noreferrer">© Esri, Maxar, Earthstar Geographics y GIS User Community</a>'
      },
      glaciers: {type: 'geojson', data: `./terrain/rgi-v6-outlines.geojson?v=${assetRevision}`},
      gradient: {type: 'geojson', data: `./terrain/hydraulic-gradient-outlines.geojson?v=${assetRevision}`}
    },
    layers: [
      {id: 'background', type: 'background', paint: {'background-color': '#dbe8e3'}},
      {id: 'surface-color', type: 'raster', source: 'surface-color', paint: {'raster-fade-duration': 0}},
      {id: 'basal-color', type: 'raster', source: 'basal-color', layout: {visibility: 'none'}, paint: {'raster-fade-duration': 0}},
      {id: 'hydraulic-correction', type: 'raster', source: 'hydraulic-correction', layout: {visibility: 'none'}, paint: {'raster-fade-duration': 0}},
      {id: 'hydraulic-filled', type: 'raster', source: 'hydraulic-filled', layout: {visibility: 'none'}, paint: {'raster-fade-duration': 0}},
      {id: 'surface-shade', type: 'hillshade', source: 'surface', paint: {
        'hillshade-illumination-direction': 315,
        'hillshade-shadow-color': 'rgba(22, 35, 33, 0.32)',
        'hillshade-highlight-color': 'rgba(255, 255, 255, 0.22)',
        'hillshade-accent-color': 'rgba(22, 35, 33, 0.12)'
      }},
      {id: 'basal-shade', type: 'hillshade', source: 'basal', layout: {visibility: 'none'}, paint: {
        'hillshade-illumination-direction': 315,
        'hillshade-shadow-color': 'rgba(22, 35, 33, 0.32)',
        'hillshade-highlight-color': 'rgba(255, 255, 255, 0.22)',
        'hillshade-accent-color': 'rgba(22, 35, 33, 0.12)'
      }},
      {id: 'hydraulic-correction-shade', type: 'hillshade', source: 'hydraulic-correction-dem', layout: {visibility: 'none'}, paint: {
        'hillshade-illumination-direction': 315,
        'hillshade-shadow-color': 'rgba(22, 35, 33, 0.32)',
        'hillshade-highlight-color': 'rgba(255, 255, 255, 0.22)',
        'hillshade-accent-color': 'rgba(22, 35, 33, 0.12)'
      }},
      {id: 'hydraulic-filled-shade', type: 'hillshade', source: 'hydraulic-filled-dem', layout: {visibility: 'none'}, paint: {
        'hillshade-illumination-direction': 315,
        'hillshade-shadow-color': 'rgba(22, 35, 33, 0.32)',
        'hillshade-highlight-color': 'rgba(255, 255, 255, 0.22)',
        'hillshade-accent-color': 'rgba(22, 35, 33, 0.12)'
      }},
      {id: 'satellite-imagery', type: 'raster', source: 'esri-imagery', layout: {visibility: 'none'}, paint: {'raster-fade-duration': 0}},
      {id: 'gradient-casing', type: 'line', source: 'gradient', paint: {
        'line-color': '#f8f8f2',
        'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.5, 10, 3],
        'line-opacity': 0.85
      }},
      {id: 'gradient-outlines', type: 'line', source: 'gradient', paint: {
        'line-color': '#00a9b7',
        'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.7, 10, 1.8],
        'line-opacity': 0.95
      }},
      {id: 'glacier-casing', type: 'line', source: 'glaciers', paint: {
        'line-color': '#f8f8f2',
        'line-width': ['interpolate', ['linear'], ['zoom'], 5, 2, 10, 3.4],
        'line-opacity': 0.85
      }},
      {id: 'glacier-outlines', type: 'line', source: 'glaciers', paint: {
        'line-color': '#cf302b',
        'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1, 10, 2],
        'line-opacity': 0.95
      }}
    ],
    terrain: {source: 'surface', exaggeration: 1}
  },
  center: [-73.5, -48.9], zoom: 6, pitch: 58, bearing: -18,
  maxPitch: 80,
  attributionControl: false
});

map.addControl(new maplibregl.AttributionControl({compact: true}), 'bottom-right');
map.addControl(new maplibregl.ScaleControl({maxWidth: 120, unit: 'metric'}), 'bottom-left');

function reset() {
  map.fitBounds(focusedBounds, {padding: {top: 80, bottom: 75, left: 60, right: 60}, pitch: focusedPitch, bearing: -18, duration: 700, maxZoom: 10});
}

let mapReady = false;
map.on('load', async () => {
  try {
    await loadCustomLayers();
  } catch (error) {
    message.textContent = `No se pudieron cargar las capas agregadas: ${error.message}`;
    message.classList.remove('hidden');
  }
  mapReady = true;
  applyTerrain();
  applyOutlines();
  reset();
  if (!message.textContent.startsWith('No se pudieron')) message.classList.add('hidden');
});
map.on('error', event => {
  if (event.sourceId === 'esri-imagery') {
    if (document.getElementById('show-satellite').checked) {
      message.textContent = 'No se pudo cargar la imagen satelital Esri. Comprueba la conexión a Internet o desactiva esa capa.';
      message.classList.remove('hidden');
    }
    return;
  }
  if (['surface', 'basal', 'surface-color', 'basal-color', 'hydraulic-correction', 'hydraulic-filled', 'hydraulic-correction-dem', 'hydraulic-filled-dem', 'glaciers', 'gradient'].includes(event.sourceId) || customSourceIds.has(event.sourceId)) {
    message.textContent = `No se pudieron cargar los datos de ${event.sourceId}. Revisa que las capas estén generadas y abre el explorador desde un servidor local.`;
    message.classList.remove('hidden');
  }
});

function updateLabels() {
  const selected = document.querySelector('input[name="terrain"]:checked').value;
  const labels = {
    surface: ['Elevación superficial', 'SRTM DEM'],
    basal: ['Elevación basal', 'Fürst · elevación basal'],
    'hydraulic-correction': ['Corrección de carga hidráulica', 'Corrección de carga · diferencia'],
    'hydraulic-filled': ['Carga hidráulica rellenada', 'Carga hidráulica · rellenada']
  };
  const custom = customSurfaces.find(item => item.id === selected);
  const [label, source] = custom ? [custom.label, custom.description || custom.label] : labels[selected];
  document.getElementById('view-label').textContent = `${label} · superficie 3D`;
  document.getElementById('source-label').textContent = source;
  const exaggeration = custom && custom.display === 'own' ? exaggerationByLayer.get(selected) || 1 : 1;
  const heightText = custom
    ? custom.display === 'relief' ? 'RELIEVE SRTM · COLOR DE LA VARIABLE' : `${custom.height.mode === 'absolute' ? 'MAGNITUD' : 'VALOR'} · 1 ${custom.unit} = ${custom.height.scale} m 3D · VISTA ${exaggeration}×${custom.height.offset ? ` + ${custom.height.offset} m` : ''}`
    : selected === 'hydraulic-correction' ? `ALTURA 3D · MAGNITUD DE CORRECCIÓN · ${exaggeration}×`
      : selected === 'hydraulic-filled' ? `ALTURA 3D · CARGA HIDRÁULICA · ${exaggeration}×` : 'ALTURA 3D · 1×';
  document.getElementById('height-label').textContent = heightText;
}

function applyTerrain() {
  if (!mapReady) return;
  const selected = document.querySelector('input[name="terrain"]:checked').value;
  const custom = customSurfaces.find(item => item.id === selected);
  const hydraulic = selected.startsWith('hydraulic-');
  const ownTerrain = custom && custom.display === 'own';
  const exaggeration = ownTerrain ? exaggerationByLayer.get(selected) || 1 : 1;
  map.setTerrain({source: ownTerrain ? custom.demSourceId : custom ? 'surface' : hydraulic ? `${selected}-dem` : selected, exaggeration});
  const controls = document.getElementById('vertical-controls');
  controls.hidden = !ownTerrain;
  if (!controls.hidden) {
    const slider = document.getElementById('vertical-exaggeration');
    slider.max = '10';
    slider.value = String(exaggeration);
    document.getElementById('vertical-exaggeration-value').textContent = `${exaggeration}×`;
  }
  map.setLayoutProperty('surface-color', 'visibility', selected === 'surface' ? 'visible' : 'none');
  map.setLayoutProperty('basal-color', 'visibility', selected === 'basal' ? 'visible' : 'none');
  for (const name of ['hydraulic-correction', 'hydraulic-filled']) {
    map.setLayoutProperty(name, 'visibility', selected === name ? 'visible' : 'none');
  }
  for (const name of ['surface', 'basal', 'hydraulic-correction', 'hydraulic-filled']) {
    const visibility = selected === name || (name === 'surface' && custom?.display === 'relief') ? 'visible' : 'none';
    map.setLayoutProperty(`${name}-shade`, 'visibility', visibility);
  }
  for (const item of customSurfaces) {
    const visibility = selected === item.id ? 'visible' : 'none';
    map.setLayoutProperty(item.colorLayerId, 'visibility', visibility);
    if (item.shadeLayerId) map.setLayoutProperty(item.shadeLayerId, 'visibility', visibility);
  }
  document.getElementById('elevation-legend').hidden = selected !== 'surface' && selected !== 'basal';
  document.getElementById('hydraulic-legend').hidden = selected !== 'hydraulic-filled';
  document.getElementById('correction-legend').hidden = selected !== 'hydraulic-correction';
  const legend = document.getElementById('custom-legend');
  legend.hidden = !custom;
  if (custom) {
    document.getElementById('custom-legend-title').textContent = `${custom.label} · ${custom.unit}`;
    document.getElementById('custom-colorbar').src = custom.colorbar;
    const [minimum, maximum] = custom.range;
    const labels = legend.querySelectorAll('.custom-colorbar-labels span');
    labels.forEach((item, index) => {
      item.textContent = new Intl.NumberFormat('es-CL', {maximumFractionDigits: 2}).format(minimum + (maximum - minimum) * index / 3);
    });
  }
  updateLabels();
}

function applyOutlines() {
  if (!mapReady) return;
  const satelliteVisible = document.getElementById('show-satellite').checked;
  map.setLayoutProperty('satellite-imagery', 'visibility', satelliteVisible ? 'visible' : 'none');
  if (!satelliteVisible && message.textContent.startsWith('No se pudo cargar la imagen satelital')) message.classList.add('hidden');
  const rgiVisibility = document.getElementById('show-rgi').checked ? 'visible' : 'none';
  map.setLayoutProperty('glacier-casing', 'visibility', rgiVisibility);
  map.setLayoutProperty('glacier-outlines', 'visibility', rgiVisibility);
  const gradientVisibility = document.getElementById('show-gradient').checked ? 'visible' : 'none';
  map.setLayoutProperty('gradient-casing', 'visibility', gradientVisibility);
  map.setLayoutProperty('gradient-outlines', 'visibility', gradientVisibility);
  for (const item of customGeometries) {
    const visibility = item.input.checked ? 'visible' : 'none';
    if (item.input.checked && !item.loaded) {
      map.getSource(item.sourceId).setData(item.geojson);
      item.loaded = true;
    }
    item.layerIds.forEach(id => map.setLayoutProperty(id, 'visibility', visibility));
  }
  for (const item of customOverlays) {
    map.setLayoutProperty(item.colorLayerId, 'visibility', item.input.checked ? 'visible' : 'none');
    item.legend.hidden = !item.input.checked;
  }
}

function expandedBounds(extent) {
  const [west, south, east, north] = extent;
  const centerX = (west + east) / 2;
  const centerY = (south + north) / 2;
  const halfWidth = Math.max((east - west) / 2, 0.01);
  const halfHeight = Math.max((north - south) / 2, 0.01);
  return [[centerX - halfWidth, centerY - halfHeight], [centerX + halfWidth, centerY + halfHeight]];
}

function layerControl(item, kind) {
  const label = document.createElement('label');
  label.className = kind === 'surface' ? 'layer-row' : 'layer-row layer-toggle';
  const swatch = document.createElement('span');
  if (kind !== 'geometry') {
    swatch.className = 'swatch';
    swatch.style.background = `url("${item.colorbar}") center / cover`;
  } else {
    swatch.className = 'outline-swatch';
    swatch.style.borderColor = item.color;
  }
  const title = document.createElement('span');
  title.textContent = item.label;
  const subtitle = document.createElement('small');
  subtitle.textContent = item.description || (kind === 'geometry' ? `${item.featureCount} geometrías` : `Variable · ${item.unit}`);
  title.appendChild(subtitle);
  const input = document.createElement('input');
  input.type = kind === 'surface' ? 'radio' : 'checkbox';
  if (kind === 'surface') {
    input.name = 'terrain';
    input.value = item.id;
    input.addEventListener('change', surfaceChanged);
  } else {
    input.checked = item.visible;
    input.setAttribute('aria-label', `Mostrar ${item.label}`);
    input.addEventListener('change', () => {
      applyOutlines();
      if (input.checked) {
        focusedBounds = expandedBounds(item.bounds);
        const current = map.getBounds();
        const [southWest, northEast] = focusedBounds;
        if (!current.contains(southWest) || !current.contains(northEast)) reset();
      }
    });
  }
  label.append(swatch, title, input);
  return {label, input};
}

async function loadCustomLayers() {
  const response = await fetch('./terrain/custom-layers.json', {cache: 'no-store'});
  if (!response.ok) throw new Error(`catálogo HTTP ${response.status}`);
  const manifest = await response.json();
  if (!Array.isArray(manifest.surfaces) || !Array.isArray(manifest.geometries) || (manifest.overlays !== undefined && !Array.isArray(manifest.overlays))) {
    throw new Error('catálogo generado inválido');
  }
  for (const item of manifest.surfaces) {
    const prefix = `custom-${item.id}`;
    item.demSourceId = `${prefix}-dem`;
    item.colorSourceId = `${prefix}-color-source`;
    item.colorLayerId = `${prefix}-color`;
    item.shadeLayerId = `${prefix}-shade`;
    if (item.display !== 'relief') {
      map.addSource(item.demSourceId, {
        type: 'raster-dem', tiles: [item.demTiles], tileSize: 256, encoding: 'terrarium',
        minzoom: item.minzoom, maxzoom: item.maxzoom, bounds: item.bounds,
        attribution: item.label
      });
      customSourceIds.add(item.demSourceId);
    }
    map.addSource(item.colorSourceId, {
      type: 'raster', tiles: [item.colorTiles], tileSize: 256,
      minzoom: item.minzoom, maxzoom: item.maxzoom, bounds: item.bounds
    });
    customSourceIds.add(item.colorSourceId);
    map.addLayer({
      id: item.colorLayerId, type: 'raster', source: item.colorSourceId,
      layout: {visibility: 'none'}, paint: {'raster-fade-duration': 0}
    }, 'surface-shade');
    if (item.display !== 'relief') {
      map.addLayer({
        id: item.shadeLayerId, type: 'hillshade', source: item.demSourceId,
        layout: {visibility: 'none'}, paint: {
          'hillshade-illumination-direction': 315,
          'hillshade-shadow-color': 'rgba(22, 35, 33, 0.32)',
          'hillshade-highlight-color': 'rgba(255, 255, 255, 0.22)',
          'hillshade-accent-color': 'rgba(22, 35, 33, 0.12)'
        }
      }, 'satellite-imagery');
    } else {
      item.shadeLayerId = null;
    }
    customSurfaces.push(item);
    document.getElementById('custom-surfaces').appendChild(layerControl(item, 'surface').label);
  }
  for (const item of manifest.overlays || []) {
    item.colorSourceId = `custom-${item.id}-overlay-source`;
    item.colorLayerId = `custom-${item.id}-overlay`;
    map.addSource(item.colorSourceId, {
      type: 'raster', tiles: [item.colorTiles], tileSize: 256,
      minzoom: item.minzoom, maxzoom: item.maxzoom, bounds: item.bounds
    });
    customSourceIds.add(item.colorSourceId);
    map.addLayer({
      id: item.colorLayerId, type: 'raster', source: item.colorSourceId,
      layout: {visibility: item.visible ? 'visible' : 'none'},
      paint: {'raster-fade-duration': 0, 'raster-opacity': 0.78}
    }, 'satellite-imagery');
    const control = layerControl(item, 'overlay');
    item.input = control.input;
    document.getElementById('custom-overlays').appendChild(control.label);
    const legend = document.createElement('section');
    legend.className = 'legend';
    legend.hidden = !item.visible;
    const heading = document.createElement('h2');
    heading.textContent = `${item.label} · ${item.unit}`;
    const bar = document.createElement('img');
    bar.className = 'custom-colorbar';
    bar.src = item.colorbar;
    bar.alt = `Escala de color para ${item.label}`;
    const values = document.createElement('div');
    values.className = 'custom-colorbar-labels';
    const format = new Intl.NumberFormat('es-CL', {maximumFractionDigits: 2});
    for (let index = 0; index < 4; index++) {
      const span = document.createElement('span');
      span.textContent = format.format(item.range[0] + (item.range[1] - item.range[0]) * index / 3);
      values.appendChild(span);
    }
    legend.append(heading, bar, values);
    item.legend = legend;
    document.getElementById('overlay-legends').appendChild(legend);
    customOverlays.push(item);
  }
  for (const item of manifest.geometries) {
    const sourceId = `custom-${item.id}-geometry`;
    const geometryTypes = new Set((item.geometryTypes || []).map(type => type.toUpperCase()));
    const hasPolygons = !geometryTypes.size || geometryTypes.has('POLYGON') || geometryTypes.has('MULTIPOLYGON');
    const hasLines = !geometryTypes.size || hasPolygons || geometryTypes.has('LINESTRING') || geometryTypes.has('MULTILINESTRING');
    const hasPoints = !geometryTypes.size || geometryTypes.has('POINT') || geometryTypes.has('MULTIPOINT');
    item.sourceId = sourceId;
    item.loaded = item.visible;
    map.addSource(sourceId, {
      type: 'geojson',
      data: item.visible ? item.geojson : {type: 'FeatureCollection', features: []}
    });
    customSourceIds.add(sourceId);
    item.layerIds = [];
    const visibility = item.visible ? 'visible' : 'none';
    if (item.fillOpacity > 0 && hasPolygons) {
      const fillId = `${sourceId}-fill`;
      map.addLayer({id: fillId, type: 'fill', source: sourceId, layout: {visibility}, paint: {
        'fill-color': item.color, 'fill-opacity': item.fillOpacity
      }});
      item.layerIds.push(fillId);
    }
    if (hasLines) {
      const lineId = `${sourceId}-line`;
      map.addLayer({id: lineId, type: 'line', source: sourceId, layout: {visibility}, paint: {
        'line-color': item.color, 'line-width': item.width
      }});
      item.layerIds.push(lineId);
    }
    if (hasPoints) {
      const pointId = `${sourceId}-point`;
      map.addLayer({id: pointId, type: 'circle', source: sourceId, layout: {visibility}, paint: {
        'circle-color': item.color, 'circle-radius': item.radius,
        'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1
      }});
      item.layerIds.push(pointId);
    }
    const control = layerControl(item, 'geometry');
    item.input = control.input;
    customGeometries.push(item);
    document.getElementById('custom-geometries').appendChild(control.label);
  }
}

function surfaceChanged() {
  applyTerrain();
  const selected = document.querySelector('input[name="terrain"]:checked').value;
  const custom = customSurfaces.find(item => item.id === selected);
  focusedBounds = custom ? expandedBounds(custom.bounds) : bounds;
  focusedPitch = custom ? 65 : 58;
}

document.querySelectorAll('input[name="terrain"]').forEach(input => input.addEventListener('change', surfaceChanged));
document.getElementById('vertical-exaggeration').addEventListener('input', event => {
  const selected = document.querySelector('input[name="terrain"]:checked').value;
  if (customSurfaces.some(item => item.id === selected)) {
    exaggerationByLayer.set(selected, Number(event.target.value));
    applyTerrain();
  }
});
document.getElementById('show-satellite').addEventListener('change', applyOutlines);
document.getElementById('show-rgi').addEventListener('change', applyOutlines);
document.getElementById('show-gradient').addEventListener('change', applyOutlines);

document.getElementById('reset-view').addEventListener('click', reset);
document.getElementById('zoom-in').addEventListener('click', () => map.zoomIn());
document.getElementById('zoom-out').addEventListener('click', () => map.zoomOut());
document.getElementById('rotate-view').addEventListener('click', () => map.easeTo({bearing: map.getBearing() + 45}));
