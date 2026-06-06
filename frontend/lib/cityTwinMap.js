import maplibregl from "maplibre-gl";

const EMPTY = { type: "FeatureCollection", features: [] };
const LONDON_CENTER = [-0.1276, 51.5072];
const DARK_STYLE = "https://tiles.openfreemap.org/styles/dark";
const LIGHT_STYLE = "https://tiles.openfreemap.org/styles/positron";
const MIN_VERTICES = 4;
const EARTH_RADIUS = 6371008.8;
const OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter";

const DEMO_ZONE = [
  [-0.1312, 51.5069],
  [-0.1198, 51.5075],
  [-0.1158, 51.5015],
  [-0.1268, 51.4987],
  [-0.1355, 51.5018],
];

const sliderIds = ["density", "green", "parking", "street", "alignment", "height"];

export function initCityTwinMap() {
  if (typeof window === "undefined" || window.__urbanFluxMap) {
    return () => {};
  }

  const dom = {
    progressBar: byId("progressBar"),
    statusText: byId("statusText"),
    roadsPill: byId("roadsPill"),
    waterPill: byId("waterPill"),
    anchorsPill: byId("anchorsPill"),
    areaMetric: byId("areaMetric"),
    homesMetric: byId("homesMetric"),
    linksMetric: byId("linksMetric"),
    waterMetric: byId("waterMetric"),
    buildingsMetric: byId("buildingsMetric"),
    parkingMetric: byId("parkingMetric"),
    scenarioLabel: byId("scenarioLabel"),
    reportText: byId("reportText"),
    toast: byId("toast"),
    themeToggle: byId("themeToggle"),
    allowWaterToggle: byId("allowWaterToggle"),
  };

  const state = {
    vertices: [],
    markers: [],
    midpointMarkers: [],
    theme: "dark",
    allowWater: false,
    context: { roads: [], water: [], buildings: [], parks: [] },
    contextKey: "",
    generationTimer: 0,
    contextTimer: 0,
  };

  const map = new maplibregl.Map({
    container: "map",
    style: DARK_STYLE,
    center: LONDON_CENTER,
    zoom: 12.45,
    pitch: 57,
    bearing: -18,
    attributionControl: false,
  });

  window.__urbanFluxMap = map;
  map.addControl(new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }), "bottom-right");

  map.once("load", () => {
    initialiseLayers(map);
    wireUi(map, state, dom);
    loadDemoZone(map, state, dom, false);
    setStatus(dom, 100, "Demo zone loaded. Drag points or tune sliders to regenerate.");
  });

  map.on("style.load", () => {
    initialiseLayers(map);
    refreshSources(map, state);
    setThemePaint(map, state.theme);
  });

  map.on("click", (event) => {
    if (event.originalEvent.target.closest(".maplibregl-marker")) {
      return;
    }
    addVertex(map, state, dom, [event.lngLat.lng, event.lngLat.lat]);
  });

  return () => {
    window.__urbanFluxMap = null;
    clearTimeout(state.generationTimer);
    clearTimeout(state.contextTimer);
    state.markers.forEach((marker) => marker.remove());
    state.midpointMarkers.forEach((marker) => marker.remove());
    map.remove();
  };
}

function wireUi(map, state, dom) {
  byId("demoButton")?.addEventListener("click", () => loadDemoZone(map, state, dom, true));
  byId("undoButton")?.addEventListener("click", () => {
    state.vertices.pop();
    syncAfterGeometryChange(map, state, dom);
  });
  byId("clearButton")?.addEventListener("click", () => {
    state.vertices = [];
    state.context = { roads: [], water: [], buildings: [], parks: [] };
    state.contextKey = "";
    syncAfterGeometryChange(map, state, dom);
    setSource(map, "context", EMPTY);
    setSource(map, "generated", EMPTY);
    setStatus(dom, 0, "Cleared. Click four or more points to define a regeneration zone.");
    updateMetrics(dom);
  });
  byId("fitButton")?.addEventListener("click", () => fitToZone(map, state));

  dom.themeToggle?.addEventListener("change", () => {
    state.theme = dom.themeToggle.checked ? "light" : "dark";
    document.body.dataset.theme = state.theme;
    map.setStyle(state.theme === "light" ? LIGHT_STYLE : DARK_STYLE, { diff: false });
  });

  dom.allowWaterToggle?.addEventListener("change", () => {
    state.allowWater = dom.allowWaterToggle.checked;
    showToast(dom, state.allowWater ? "Water override enabled." : "Water protection enabled.");
    scheduleGeneration(map, state, dom);
  });

  sliderIds.forEach((id) => {
    const input = byId(id);
    const output = byId(`${id}Out`);
    input?.addEventListener("input", () => {
      output.textContent = input.value;
      scheduleGeneration(map, state, dom);
    });
  });
}

function initialiseLayers(map) {
  addSource(map, "selection", EMPTY);
  addSource(map, "context", EMPTY);
  addSource(map, "generated", EMPTY);
  addSource(map, "anchors", EMPTY);

  addLayer(map, {
    id: "selection-fill",
    type: "fill",
    source: "selection",
    paint: { "fill-color": "#33e4f2", "fill-opacity": 0.14 },
    filter: ["==", ["geometry-type"], "Polygon"],
  });
  addLayer(map, {
    id: "selection-line",
    type: "line",
    source: "selection",
    paint: { "line-color": "#33e4f2", "line-width": 3, "line-dasharray": [1.4, 0.7] },
  });
  addLayer(map, {
    id: "context-water",
    type: "fill",
    source: "context",
    filter: ["==", ["get", "kind"], "water"],
    paint: { "fill-color": "#2878ff", "fill-opacity": 0.34 },
  });
  addLayer(map, {
    id: "context-water-lines",
    type: "line",
    source: "context",
    filter: ["==", ["get", "kind"], "water-line"],
    paint: { "line-color": "#2878ff", "line-width": 4, "line-opacity": 0.62 },
  });
  addLayer(map, {
    id: "context-parks",
    type: "fill",
    source: "context",
    filter: ["==", ["get", "kind"], "park"],
    paint: { "fill-color": "#5dde75", "fill-opacity": 0.24 },
  });
  addLayer(map, {
    id: "context-buildings",
    type: "fill",
    source: "context",
    filter: ["==", ["get", "kind"], "building"],
    paint: { "fill-color": "#9e7bff", "fill-opacity": 0.18 },
  });
  addLayer(map, {
    id: "context-roads",
    type: "line",
    source: "context",
    filter: ["==", ["get", "kind"], "road"],
    paint: { "line-color": "#70a8ff", "line-width": 1.7, "line-opacity": 0.72 },
  });
  addLayer(map, {
    id: "generated-parks",
    type: "fill",
    source: "generated",
    filter: ["==", ["get", "kind"], "park"],
    paint: { "fill-color": "#6bf49a", "fill-opacity": 0.58 },
  });
  addLayer(map, {
    id: "generated-parking",
    type: "fill",
    source: "generated",
    filter: ["==", ["get", "kind"], "parking"],
    paint: { "fill-color": "#ffce55", "fill-opacity": 0.54 },
  });
  addLayer(map, {
    id: "generated-buildings",
    type: "fill-extrusion",
    source: "generated",
    filter: ["==", ["get", "kind"], "building"],
    paint: {
      "fill-extrusion-color": "#ff5dbb",
      "fill-extrusion-height": ["get", "height"],
      "fill-extrusion-base": 0,
      "fill-extrusion-opacity": 0.72,
    },
  });
  addLayer(map, {
    id: "generated-roads",
    type: "line",
    source: "generated",
    filter: ["==", ["get", "kind"], "road"],
    paint: { "line-color": "#33e4f2", "line-width": 4, "line-opacity": 0.94 },
  });
  addLayer(map, {
    id: "anchors",
    type: "circle",
    source: "anchors",
    paint: {
      "circle-color": "#ffffff",
      "circle-stroke-color": "#33e4f2",
      "circle-stroke-width": 2,
      "circle-radius": 4,
    },
  });
}

function setThemePaint(map, theme) {
  if (!map.getLayer("selection-line")) {
    return;
  }
  map.setPaintProperty("selection-line", "line-color", theme === "light" ? "#009db8" : "#33e4f2");
}

function addSource(map, id, data) {
  if (!map.getSource(id)) {
    map.addSource(id, { type: "geojson", data });
  }
}

function addLayer(map, layer) {
  if (!map.getLayer(layer.id)) {
    map.addLayer(layer);
  }
}

function setSource(map, id, data) {
  const source = map.getSource(id);
  if (source) {
    source.setData(data);
  }
}

function addVertex(map, state, dom, coord) {
  state.vertices.push(coord);
  syncAfterGeometryChange(map, state, dom);
}

function insertVertex(map, state, dom, index, coord) {
  state.vertices.splice(index + 1, 0, coord);
  syncAfterGeometryChange(map, state, dom);
}

function syncAfterGeometryChange(map, state, dom) {
  renderMarkers(map, state, dom);
  updateSelection(map, state);
  scheduleContext(map, state, dom);
  scheduleGeneration(map, state, dom);
}

function renderMarkers(map, state, dom) {
  state.markers.forEach((marker) => marker.remove());
  state.midpointMarkers.forEach((marker) => marker.remove());
  state.markers = [];
  state.midpointMarkers = [];

  state.vertices.forEach((coord, index) => {
    const element = document.createElement("div");
    element.className = "vertex-marker";
    element.title = "Drag vertex. Double-click to remove.";
    element.addEventListener("dblclick", (event) => {
      event.stopPropagation();
      state.vertices.splice(index, 1);
      syncAfterGeometryChange(map, state, dom);
    });
    const marker = new maplibregl.Marker({ element, draggable: true, anchor: "center" })
      .setLngLat(coord)
      .addTo(map);
    marker.on("drag", () => {
      const lngLat = marker.getLngLat();
      state.vertices[index] = [lngLat.lng, lngLat.lat];
      updateSelection(map, state);
      scheduleGeneration(map, state, dom);
    });
    marker.on("dragend", () => syncAfterGeometryChange(map, state, dom));
    state.markers.push(marker);
  });

  if (state.vertices.length < 2) {
    return;
  }

  const edgeCount = state.vertices.length >= MIN_VERTICES ? state.vertices.length : state.vertices.length - 1;
  for (let index = 0; index < edgeCount; index += 1) {
    const next = (index + 1) % state.vertices.length;
    const coord = midpoint(state.vertices[index], state.vertices[next]);
    const element = document.createElement("div");
    element.className = "midpoint-marker";
    element.title = "Add point";
    element.addEventListener("click", (event) => {
      event.stopPropagation();
      insertVertex(map, state, dom, index, coord);
    });
    state.midpointMarkers.push(new maplibregl.Marker({ element, anchor: "center" }).setLngLat(coord).addTo(map));
  }
}

function updateSelection(map, state) {
  if (state.vertices.length === 0) {
    setSource(map, "selection", EMPTY);
    return;
  }
  const features = [
    {
      type: "Feature",
      properties: { kind: "outline" },
      geometry: { type: "LineString", coordinates: outlineCoordinates(state.vertices) },
    },
  ];
  if (state.vertices.length >= MIN_VERTICES) {
    features.push({
      type: "Feature",
      properties: { kind: "selected" },
      geometry: { type: "Polygon", coordinates: [outlineCoordinates(state.vertices)] },
    });
  }
  setSource(map, "selection", { type: "FeatureCollection", features });
}

function loadDemoZone(map, state, dom, userTriggered) {
  state.vertices = DEMO_ZONE.map((coord) => [...coord]);
  syncAfterGeometryChange(map, state, dom);
  fitToZone(map, state);
  if (userTriggered) {
    showToast(dom, "Demo zone restored.");
  }
}

function fitToZone(map, state) {
  if (state.vertices.length < 2) {
    map.easeTo({ center: LONDON_CENTER, zoom: 12.45, pitch: 57, bearing: -18, duration: 700 });
    return;
  }
  const bounds = state.vertices.reduce(
    (box, coord) => box.extend(coord),
    new maplibregl.LngLatBounds(state.vertices[0], state.vertices[0]),
  );
  map.fitBounds(bounds, { padding: 140, pitch: 57, bearing: -18, duration: 700 });
}

function scheduleContext(map, state, dom) {
  clearTimeout(state.contextTimer);
  if (state.vertices.length < MIN_VERTICES) {
    return;
  }
  state.contextTimer = window.setTimeout(() => fetchContext(map, state, dom), 260);
}

async function fetchContext(map, state, dom) {
  const key = bbox(state.vertices).map((value) => value.toFixed(4)).join(":");
  if (key === state.contextKey) {
    return;
  }
  state.contextKey = key;
  setStatus(dom, 36, "Reading OSM roads, buildings, parks and water near the selected zone...");
  try {
    const response = await fetch(OVERPASS_ENDPOINT, {
      method: "POST",
      body: buildOverpassQuery(bbox(state.vertices)),
      headers: { "Content-Type": "text/plain;charset=UTF-8" },
    });
    if (!response.ok) {
      throw new Error(`Overpass ${response.status}`);
    }
    const data = await response.json();
    state.context = parseOverpass(data);
    setSource(map, "context", contextCollection(state.context));
    setStatus(dom, 68, `Loaded ${state.context.roads.length} roads and ${state.context.water.length} water masks. Generating scenario...`);
    scheduleGeneration(map, state, dom);
  } catch {
    state.context = fallbackContext(state.vertices);
    setSource(map, "context", contextCollection(state.context));
    setStatus(dom, 62, "OSM fetch unavailable. Using generated basemap context fallback.");
    scheduleGeneration(map, state, dom);
  }
}

function buildOverpassQuery(box) {
  const [west, south, east, north] = box;
  const region = `${south},${west},${north},${east}`;
  return `
    [out:json][timeout:18];
    (
      way["highway"~"primary|secondary|tertiary|residential|service|unclassified"](${region});
      way["building"](${region});
      way["natural"="water"](${region});
      way["waterway"~"river|canal"](${region});
      way["leisure"="park"](${region});
      way["landuse"~"grass|recreation_ground|meadow"](${region});
    );
    out body geom;
  `;
}

function parseOverpass(data) {
  const context = { roads: [], water: [], buildings: [], parks: [] };
  for (const element of data.elements || []) {
    if (element.type !== "way" || !Array.isArray(element.geometry) || element.geometry.length < 2) {
      continue;
    }
    const coords = element.geometry.map((point) => [point.lon, point.lat]);
    const tags = element.tags || {};
    if (tags.highway) {
      context.roads.push(lineFeature(coords, { kind: "road" }));
    } else if (tags.waterway) {
      context.water.push(lineFeature(coords, { kind: "water-line" }));
    } else if (tags.natural === "water") {
      context.water.push(polygonFeature(coords, { kind: "water" }));
    } else if (tags.building) {
      context.buildings.push(polygonFeature(coords, { kind: "building" }));
    } else if (tags.leisure === "park" || tags.landuse) {
      context.parks.push(polygonFeature(coords, { kind: "park" }));
    }
  }
  return context;
}

function fallbackContext(vertices) {
  const [west, south, east, north] = bbox(vertices);
  const roads = [];
  const water = [];
  const buildings = [];
  const parks = [];
  for (let i = 1; i <= 4; i += 1) {
    const t = i / 5;
    roads.push(lineFeature([[lerp(west, east, t), south], [lerp(west, east, t + 0.03), north]], { kind: "road" }));
  }
  water.push(lineFeature([[west, lerp(south, north, 0.34)], [east, lerp(south, north, 0.42)]], { kind: "water-line" }));
  parks.push(rectFeature([lerp(west, east, 0.72), lerp(south, north, 0.72)], 0.0012, 0.0008, { kind: "park" }));
  buildings.push(rectFeature([lerp(west, east, 0.25), lerp(south, north, 0.62)], 0.0007, 0.0005, { kind: "building" }));
  return { roads, water, buildings, parks };
}

function scheduleGeneration(map, state, dom) {
  clearTimeout(state.generationTimer);
  state.generationTimer = window.setTimeout(() => generateScenario(map, state, dom), 120);
}

function generateScenario(map, state, dom) {
  if (state.vertices.length < MIN_VERTICES) {
    setSource(map, "generated", EMPTY);
    setSource(map, "anchors", EMPTY);
    updateMetrics(dom);
    setStatus(dom, Math.min(state.vertices.length * 18, 72), `${Math.max(0, MIN_VERTICES - state.vertices.length)} more point(s) needed for a valid polygon.`);
    return;
  }

  const controls = readControls();
  const area = polygonAreaHectares(state.vertices);
  const center = centroid(state.vertices);
  const random = seededRandom(`${state.vertices.flat().map((value) => value.toFixed(5)).join(",")}:${Object.values(controls).join(":")}:${state.allowWater}`);
  const anchors = boundaryAnchors(state.vertices, controls.street);
  const roads = createRoads(center, anchors, controls.alignment);
  const obstacles = state.allowWater ? [] : state.context.water;
  const parks = createParks(state.vertices, controls.green, random, obstacles);
  const parking = createParking(state.vertices, controls.parking, random, obstacles);
  const buildings = createBuildings(state.vertices, controls, random, obstacles, parks.concat(parking));
  const features = [...parks, ...parking, ...buildings, ...roads];

  setSource(map, "generated", { type: "FeatureCollection", features });
  setSource(map, "anchors", {
    type: "FeatureCollection",
    features: anchors.map((coord) => pointFeature(coord, { kind: "anchor" })),
  });

  const homes = Math.round(area * controls.density * (0.9 + controls.height / 180));
  const parkingSpaces = Math.round(area * controls.parking * 1.8);
  updateMetrics(dom, {
    area,
    homes,
    links: roads.length,
    water: state.context.water.length,
    buildings: buildings.length,
    parking: parkingSpaces,
    anchors: anchors.length,
    roads: state.context.roads.length,
  });
  setStatus(dom, 100, `Generated ${buildings.length} footprints, ${roads.length} road links and ${parks.length} green zones.`);
  dom.reportText.textContent = state.allowWater
    ? "Water override is active. The plan maximises buildable capacity and may cross mapped river or basin geometry."
    : "Water protection is active. Generated homes, parks and parking avoid mapped water features where context is available.";
  dom.scenarioLabel.textContent = `${homes.toLocaleString()} homes`;
}

function createRoads(center, anchors, alignment) {
  const roads = anchors.map((anchor, index) => {
    const bendAmount = (50 - alignment) / 80000;
    const bend = index % 2 === 0 ? bendAmount : -bendAmount;
    return lineFeature([anchor, [lerp(anchor[0], center[0], 0.52) + bend, lerp(anchor[1], center[1], 0.52) - bend], center], {
      kind: "road",
    });
  });
  if (anchors.length >= 4) {
    roads.push(lineFeature([anchors[0], center, anchors[Math.floor(anchors.length / 2)]], { kind: "road" }));
  }
  return roads;
}

function createParks(vertices, green, random, obstacles) {
  const count = clamp(Math.round(green / 20), 1, 4);
  const result = [];
  for (let i = 0; i < count; i += 1) {
    const point = randomPointInPolygon(vertices, random, obstacles);
    if (point) {
      result.push(rectFeature(point, 0.00075 + green / 200000, 0.00055 + green / 260000, { kind: "park" }));
    }
  }
  return result;
}

function createParking(vertices, parking, random, obstacles) {
  const count = Math.round(parking / 22);
  const result = [];
  for (let i = 0; i < count; i += 1) {
    const point = randomPointInPolygon(vertices, random, obstacles);
    if (point) {
      result.push(rectFeature(point, 0.00042, 0.00028, { kind: "parking" }));
    }
  }
  return result;
}

function createBuildings(vertices, controls, random, obstacles, reserved) {
  const area = polygonAreaHectares(vertices);
  const count = clamp(Math.round(area * (controls.density / 4.2)), 8, 90);
  const result = [];
  for (let i = 0; i < count; i += 1) {
    const point = randomPointInPolygon(vertices, random, obstacles);
    if (!point || reserved.some((feature) => pointInPolygon(point, feature.geometry.coordinates[0]))) {
      continue;
    }
    const width = 0.00025 + random() * 0.00032;
    const height = 0.00018 + random() * 0.00028;
    const floors = Math.round(3 + (controls.height / 100) * 15 + random() * 5);
    result.push(rectFeature(point, width, height, { kind: "building", height: floors * 3.2 }));
  }
  return result;
}

function readControls() {
  return Object.fromEntries(sliderIds.map((id) => [id, Number(byId(id)?.value || 0)]));
}

function updateMetrics(dom, values = null) {
  dom.areaMetric.textContent = values ? values.area.toFixed(1) : "-";
  dom.homesMetric.textContent = values ? values.homes.toLocaleString() : "-";
  dom.linksMetric.textContent = values ? values.links.toLocaleString() : "-";
  dom.waterMetric.textContent = values ? values.water.toLocaleString() : "-";
  dom.buildingsMetric.textContent = values ? values.buildings.toLocaleString() : "-";
  dom.parkingMetric.textContent = values ? values.parking.toLocaleString() : "-";
  dom.roadsPill.textContent = values ? values.roads.toLocaleString() : "-";
  dom.waterPill.textContent = values ? values.water.toLocaleString() : "-";
  dom.anchorsPill.textContent = values ? values.anchors.toLocaleString() : "-";
  if (!values) {
    dom.scenarioLabel.textContent = "No scenario yet";
    dom.reportText.textContent = "Waiting for a valid polygon. Click four or more points, or use the demo zone.";
  }
}

function setStatus(dom, progress, text) {
  dom.progressBar.style.width = `${clamp(progress, 0, 100)}%`;
  dom.statusText.textContent = text;
}

function showToast(dom, text) {
  dom.toast.textContent = text;
  dom.toast.classList.add("visible");
  window.setTimeout(() => dom.toast.classList.remove("visible"), 1700);
}

function contextCollection(context) {
  return {
    type: "FeatureCollection",
    features: [...context.parks, ...context.water, ...context.buildings, ...context.roads],
  };
}

function boundaryAnchors(vertices, roadFill) {
  const anchors = [];
  const step = Math.max(1, Math.round(4 - roadFill / 34));
  vertices.forEach((coord, index) => {
    const next = vertices[(index + 1) % vertices.length];
    anchors.push(coord);
    if (index % step === 0) {
      anchors.push(midpoint(coord, next));
    }
  });
  return anchors;
}

function randomPointInPolygon(vertices, random, obstacles) {
  const box = bbox(vertices);
  for (let tries = 0; tries < 180; tries += 1) {
    const point = [lerp(box[0], box[2], random()), lerp(box[1], box[3], random())];
    if (pointInPolygon(point, vertices) && !touchesAny(point, obstacles)) {
      return point;
    }
  }
  return centroid(vertices);
}

function touchesAny(point, features) {
  return features.some((feature) => {
    if (feature.geometry.type === "Polygon") {
      return pointInPolygon(point, feature.geometry.coordinates[0]);
    }
    if (feature.geometry.type === "LineString") {
      return distanceToLine(point, feature.geometry.coordinates) < 0.00035;
    }
    return false;
  });
}

function distanceToLine(point, line) {
  let min = Infinity;
  for (let i = 0; i < line.length - 1; i += 1) {
    min = Math.min(min, distanceToSegment(point, line[i], line[i + 1]));
  }
  return min;
}

function distanceToSegment(point, a, b) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const length = dx * dx + dy * dy || 1;
  const t = clamp(((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length, 0, 1);
  return Math.hypot(point[0] - (a[0] + dx * t), point[1] - (a[1] + dy * t));
}

function rectFeature(center, width, height, properties) {
  const coords = [
    [center[0] - width / 2, center[1] - height / 2],
    [center[0] + width / 2, center[1] - height / 2],
    [center[0] + width / 2, center[1] + height / 2],
    [center[0] - width / 2, center[1] + height / 2],
    [center[0] - width / 2, center[1] - height / 2],
  ];
  return { type: "Feature", properties, geometry: { type: "Polygon", coordinates: [coords] } };
}

function polygonFeature(coords, properties) {
  return {
    type: "Feature",
    properties,
    geometry: { type: "Polygon", coordinates: [outlineCoordinates(coords)] },
  };
}

function lineFeature(coords, properties) {
  return { type: "Feature", properties, geometry: { type: "LineString", coordinates: coords } };
}

function pointFeature(coord, properties) {
  return { type: "Feature", properties, geometry: { type: "Point", coordinates: coord } };
}

function polygonAreaHectares(vertices) {
  const origin = vertices[0];
  const meters = vertices.map((coord) => toMeters(coord, origin));
  let sum = 0;
  for (let i = 0; i < meters.length; i += 1) {
    const a = meters[i];
    const b = meters[(i + 1) % meters.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum / 2) / 10000;
}

function toMeters(coord, origin) {
  const lat = (coord[1] * Math.PI) / 180;
  const originLat = (origin[1] * Math.PI) / 180;
  return {
    x: ((coord[0] - origin[0]) * Math.PI * EARTH_RADIUS * Math.cos((lat + originLat) / 2)) / 180,
    y: ((coord[1] - origin[1]) * Math.PI * EARTH_RADIUS) / 180,
  };
}

function pointInPolygon(point, polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const xi = polygon[i][0];
    const yi = polygon[i][1];
    const xj = polygon[j][0];
    const yj = polygon[j][1];
    const intersects = yi > point[1] !== yj > point[1] && point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi || 1e-12) + xi;
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
}

function centroid(vertices) {
  const total = vertices.reduce((acc, coord) => [acc[0] + coord[0], acc[1] + coord[1]], [0, 0]);
  return [total[0] / vertices.length, total[1] / vertices.length];
}

function bbox(vertices) {
  const lngs = vertices.map((coord) => coord[0]);
  const lats = vertices.map((coord) => coord[1]);
  const pad = 0.003;
  return [Math.min(...lngs) - pad, Math.min(...lats) - pad, Math.max(...lngs) + pad, Math.max(...lats) + pad];
}

function outlineCoordinates(vertices) {
  if (vertices.length === 0) {
    return [];
  }
  const first = vertices[0];
  const last = vertices[vertices.length - 1];
  return first[0] === last[0] && first[1] === last[1] ? vertices : [...vertices, first];
}

function midpoint(a, b) {
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function seededRandom(seed) {
  let value = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    value ^= seed.charCodeAt(i);
    value = Math.imul(value, 16777619);
  }
  return () => {
    value += 0x6d2b79f5;
    let t = value;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function byId(id) {
  return document.getElementById(id);
}
