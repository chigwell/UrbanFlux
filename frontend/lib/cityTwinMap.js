import maplibregl from "maplibre-gl";
import turfBbox from "@turf/bbox";
import turfBuffer from "@turf/buffer";
import turfBooleanIntersects from "@turf/boolean-intersects";
import turfArea from "@turf/area";
import turfCentroid from "@turf/centroid";
import {
  API_BASE_URL,
  AUTO_IMPROVEMENT_CENTER_BBOX,
  AUTO_IMPROVEMENT_FIT_MAX_ZOOM,
  AUTO_IMPROVEMENT_OVERVIEW_CAMERA,
  AUTO_ORBIT_DURATION_MS,
  AUTO_ORBIT_ZOOM_MAX,
  AUTO_ORBIT_ZOOM_MIN,
  CONNECTABLE_HIGHWAYS,
  CONTEXT_CACHE_MAX,
  CONTEXT_FETCH_DEBOUNCE_MS,
  CONTEXT_KIND_BUDGETS,
  CUSTOM_LAYER_PREFIXES,
  DEG_TO_RAD,
  EARTH_RADIUS_METERS,
  EMPTY,
  GREATER_LONDON_RING,
  IMPACT_FETCH_DEBOUNCE_MS,
  LONDON_CENTER,
  MAP_STYLES,
  MAX_WATER_OBSTACLES,
  MIN_POLYGON_VERTICES,
  OVERPASS_BBOX_CACHE_MAX,
  OVERPASS_COOLDOWN_MS,
  OVERPASS_ENDPOINTS,
  POPULATION_FETCH_DEBOUNCE_MS,
  RAD_TO_DEG,
  VECTOR_CONTEXT_SOURCE_LAYERS,
  WATER_CANAL_LINE_EXCLUSION_KM,
  WATER_CONTEXT_READY_STATES,
  WATER_DEFAULT_LINE_EXCLUSION_KM,
  WATER_MINOR_LINE_EXCLUSION_KM,
  WATER_POLYGON_EXCLUSION_KM,
  WATER_RIVER_LINE_EXCLUSION_KM,
} from "./cityTwinMap/constants";
import { abortError, sleep, throwIfAborted } from "./cityTwinMap/async";
import { cityTwinSettingsToReplanningParams } from "./cityTwinMap/settings";
export { cityTwinSettingsToReplanningParams } from "./cityTwinMap/settings";

export function initCityTwinMap(options = {}) {
  // View bridge: the engine no longer reaches into the DOM by id. React passes
  // callbacks for every output and drives every input through the returned handle.
  const noop = () => {};
  const emit = {
    onStatus: options.onStatus || noop,
    onMetrics: options.onMetrics || noop,
    onScenario: options.onScenario || noop,
    onReport: options.onReport || noop,
    onHint: options.onHint || noop,
    onPills: options.onPills || noop,
    onPopulation: options.onPopulation || noop,
    onImpact: options.onImpact || noop,
    onToast: options.onToast || noop,
    onAutoInterrupted: options.onAutoInterrupted || noop,
  };

  const initialTheme = options.initialTheme === "light" ? "light" : "dark";
  const defaultSettings = {
    density: 64,
    green: 35,
    parking: 18,
    street: 35,
    alignment: 72,
    height: 58,
  };

  const state = {
    theme: initialTheme,
    allowWater: Boolean(options.initialAllowWater),
    vertices: [],
    vertexMarkers: [],
    midpointMarkers: [],
    contextFeatures: [],
    contextKey: "",
    contextStatus: "empty",
    contextFetchController: null,
    overpassEndpointIndex: 0,
    generationRaf: null,
    contextTimer: null,
    populationTimer: null,
    populationController: null,
    populationKey: "",
    impactTimer: null,
    impactController: null,
    impactKey: "",
    statsCache: null,
    contextCache: new Map(),
    overpassCooldownUntil: 0,
    overpassBBoxCache: new Map(),
    settledContextTimer: null,
    lastGeneratedFeatures: [],
    toastTimer: null,
    autoOrbitTimer: null,
    autoOrbitAbortController: null,
    renderVersion: 0,
    lastSuccessfulRenderVersion: 0,
    lastSuccessfulRenderFeatureCount: 0,
    mapReady: false,
    layersReady: false,
    settings: { ...defaultSettings, ...(options.initialSettings || {}) },
    latestStats: createEmptyContextStats(),
  };

  const map = new maplibregl.Map({
    container: options.container || "map",
    style: MAP_STYLES[initialTheme],
    center: LONDON_CENTER,
    zoom: 12.4,
    pitch: 57,
    bearing: -18,
    maxPitch: 74,
    attributionControl: true,
  });

  map.addControl(
    new maplibregl.NavigationControl({
      showCompass: true,
      visualizePitch: true,
    }),
    "bottom-right",
  );

  map.on("style.load", () => {
    initialiseMapLayers();
    refreshAllSources();
    if (state.vertices.length < MIN_POLYGON_VERTICES) {
      return;
    }
    // Invalidate the theme-scoped cache key but keep in-memory context/features on
    // screen until the new basemap tiles are rendered and we can re-extract safely.
    state.contextKey = "";
    state.statsCache = null;
    scheduleMapSettledContextFetch();
  });

  map.once("load", () => {
    state.mapReady = true;
    loadDemoZone();
    showToast(
      "Demo zone loaded. Road fill controls how many boundary anchors are connected; road alignment controls how straight the corridors are.",
    );
  });

  map.on("click", (event) => {
    const target = event.originalEvent.target;
    if (target instanceof Element && target.closest(".maplibregl-marker")) {
      return;
    }
    emit.onAutoInterrupted();
    addVertex([event.lngLat.lng, event.lngLat.lat]);
  });

  map.on("dragstart", stopAutoOnUserCameraInput);
  map.on("zoomstart", stopAutoOnUserCameraInput);
  map.on("rotatestart", stopAutoOnUserCameraInput);
  map.on("pitchstart", stopAutoOnUserCameraInput);

  function setAllowWater(on) {
    const next = Boolean(on);
    if (state.allowWater === next) {
      return;
    }
    state.allowWater = next;
    setStatus(
      state.allowWater ? 70 : 78,
      state.allowWater
        ? "Water override enabled. Roads and buildings may cross mapped rivers and basins."
        : "Water override disabled. Rivers and basins are hard masks for generated roads and buildings.",
    );
    scheduleGeneration();
  }

  function setSetting(key, value) {
    if (!(key in state.settings)) {
      return;
    }
    state.settings[key] = Number(value);
    scheduleGeneration();
    scheduleImpactFetch();
  }

  function setTheme(theme) {
    if (state.theme === theme) {
      return;
    }
    state.theme = theme;
    map.setStyle(MAP_STYLES[theme], { diff: false });
    setStatus(
      74,
      `${theme === "light" ? "Light" : "Dark"} theme loaded. Restoring generated layers...`,
    );
  }

  function stopAutoOnUserCameraInput(event) {
    if (!event.originalEvent) {
      return;
    }

    const hadOrbit =
      state.autoOrbitTimer !== null || state.autoOrbitAbortController !== null;
    if (hadOrbit) {
      stopAutoOrbit();
      emit.onToast("Auto improvement paused because you moved the map.");
    }
    emit.onAutoInterrupted();
  }

  function initialiseMapLayers() {
    state.layersReady = false;

    addSourceIfMissing("selection", EMPTY);
    addSourceIfMissing("context", EMPTY);
    addSourceIfMissing("generated", EMPTY);

    const p = palette();

    addLayerIfMissing({
      id: "selection-fill",
      type: "fill",
      source: "selection",
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: {
        "fill-color": p.selectionFill,
        "fill-opacity": 0.17,
      },
    });
    addLayerIfMissing({
      id: "selection-line-halo",
      type: "line",
      source: "selection",
      filter: ["==", ["geometry-type"], "Polygon"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": p.selectionHalo,
        "line-width": 9,
        "line-opacity": 0.24,
      },
    });
    addLayerIfMissing({
      id: "selection-line",
      type: "line",
      source: "selection",
      filter: ["==", ["geometry-type"], "Polygon"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": p.selectionLine,
        "line-width": 2.4,
        "line-opacity": 0.98,
      },
    });

    addLayerIfMissing({
      id: "context-water-fill",
      type: "fill",
      source: "context",
      filter: [
        "all",
        ["==", ["get", "kind"], "water"],
        ["==", ["geometry-type"], "Polygon"],
      ],
      paint: {
        "fill-color": p.contextWater,
        "fill-opacity": 0.34,
      },
    });
    addLayerIfMissing({
      id: "context-water-line",
      type: "line",
      source: "context",
      filter: [
        "all",
        ["==", ["get", "kind"], "water"],
        ["==", ["geometry-type"], "LineString"],
      ],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": p.contextWater,
        "line-width": ["interpolate", ["linear"], ["zoom"], 11, 2.4, 16, 12],
        "line-opacity": 0.48,
      },
    });
    addLayerIfMissing({
      id: "context-park-fill",
      type: "fill",
      source: "context",
      filter: [
        "all",
        ["==", ["get", "kind"], "park"],
        ["==", ["geometry-type"], "Polygon"],
      ],
      paint: {
        "fill-color": p.contextPark,
        "fill-opacity": 0.2,
      },
    });
    addLayerIfMissing({
      id: "context-building-fill",
      type: "fill",
      source: "context",
      filter: [
        "all",
        ["==", ["get", "kind"], "building"],
        ["==", ["geometry-type"], "Polygon"],
      ],
      paint: {
        "fill-color": p.contextBuilding,
        "fill-opacity": 0.3,
      },
    });
    addLayerIfMissing({
      id: "context-road-casing",
      type: "line",
      source: "context",
      filter: ["==", ["get", "kind"], "road"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": p.contextRoadCasing,
        "line-width": ["interpolate", ["linear"], ["zoom"], 11, 2.4, 16, 13],
        "line-opacity": 0.72,
      },
    });
    addLayerIfMissing({
      id: "context-road",
      type: "line",
      source: "context",
      filter: ["==", ["get", "kind"], "road"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": [
          "match",
          ["get", "highway"],
          "primary",
          p.contextRoadMajor,
          "primary_link",
          p.contextRoadMajor,
          "secondary",
          p.contextRoadMajor,
          "secondary_link",
          p.contextRoadMajor,
          "tertiary",
          p.contextRoadMid,
          "tertiary_link",
          p.contextRoadMid,
          "service",
          p.contextRoadMinor,
          p.contextRoad,
        ],
        "line-width": [
          "interpolate",
          ["linear"],
          ["zoom"],
          11,
          [
            "match",
            ["get", "highway"],
            "primary",
            2.4,
            "secondary",
            2.2,
            "tertiary",
            1.9,
            1.35,
          ],
          16,
          [
            "match",
            ["get", "highway"],
            "primary",
            8.4,
            "secondary",
            7.4,
            "tertiary",
            6.3,
            "service",
            3.8,
            5.2,
          ],
        ],
        "line-opacity": 0.9,
      },
    });

    addLayerIfMissing({
      id: "generated-park",
      type: "fill",
      source: "generated",
      filter: [
        "all",
        ["==", ["get", "kind"], "park"],
        ["==", ["geometry-type"], "Polygon"],
      ],
      paint: {
        "fill-color": p.generatedPark,
        "fill-opacity": 0.74,
      },
    });
    addLayerIfMissing({
      id: "generated-parking",
      type: "fill",
      source: "generated",
      filter: [
        "all",
        ["==", ["get", "kind"], "parking"],
        ["==", ["geometry-type"], "Polygon"],
      ],
      paint: {
        "fill-color": p.generatedParking,
        "fill-opacity": 0.7,
      },
    });
    addLayerIfMissing({
      id: "generated-building",
      type: "fill-extrusion",
      source: "generated",
      filter: [
        "all",
        ["==", ["get", "kind"], "building"],
        ["==", ["geometry-type"], "Polygon"],
      ],
      paint: {
        "fill-extrusion-color": [
          "interpolate",
          ["linear"],
          ["get", "height"],
          8,
          p.buildingLow,
          55,
          p.buildingMid,
          130,
          p.buildingHigh,
          260,
          p.buildingTower,
          420,
          p.buildingSupertall,
        ],
        "fill-extrusion-height": ["get", "height"],
        "fill-extrusion-base": 0,
        "fill-extrusion-opacity": 0.78,
      },
    });
    addLayerIfMissing({
      id: "generated-road-casing",
      type: "line",
      source: "generated",
      filter: ["==", ["get", "kind"], "road"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": p.generatedRoadCasing,
        "line-width": [
          "interpolate",
          ["linear"],
          ["zoom"],
          11,
          [
            "match",
            ["get", "roadClass"],
            "gateway",
            9.8,
            "connector",
            7.8,
            "primary",
            7.2,
            "cycle",
            2.5,
            5.5,
          ],
          16,
          [
            "match",
            ["get", "roadClass"],
            "gateway",
            24,
            "connector",
            19,
            "primary",
            17,
            "cycle",
            6,
            13,
          ],
        ],
        "line-opacity": [
          "match",
          ["get", "roadClass"],
          "gateway",
          0.95,
          "connector",
          0.92,
          0.76,
        ],
        "line-blur": [
          "match",
          ["get", "roadClass"],
          "gateway",
          0.3,
          "connector",
          0.2,
          0,
        ],
      },
    });
    addLayerIfMissing({
      id: "generated-road",
      type: "line",
      source: "generated",
      filter: ["==", ["get", "kind"], "road"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": [
          "match",
          ["get", "roadClass"],
          "gateway",
          p.generatedGateway,
          "connector",
          p.generatedConnector,
          "primary",
          p.generatedPrimary,
          "cycle",
          p.generatedCycle,
          p.generatedStreet,
        ],
        "line-width": [
          "interpolate",
          ["linear"],
          ["zoom"],
          11,
          [
            "match",
            ["get", "roadClass"],
            "gateway",
            5.6,
            "connector",
            4.7,
            "primary",
            4.0,
            "cycle",
            1.25,
            2.8,
          ],
          16,
          [
            "match",
            ["get", "roadClass"],
            "gateway",
            13,
            "connector",
            11,
            "primary",
            9.5,
            "cycle",
            3.0,
            6.5,
          ],
        ],
        "line-opacity": 0.98,
      },
    });
    addLayerIfMissing({
      id: "anchor-halo",
      type: "circle",
      source: "generated",
      filter: ["==", ["get", "kind"], "anchor"],
      paint: {
        "circle-color": p.anchorHalo,
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 8, 16, 17],
        "circle-opacity": 0.25,
        "circle-blur": 0.55,
      },
    });
    addLayerIfMissing({
      id: "anchor-dot",
      type: "circle",
      source: "generated",
      filter: ["==", ["get", "kind"], "anchor"],
      paint: {
        "circle-color": p.anchorDot,
        "circle-stroke-color": p.anchorStroke,
        "circle-stroke-width": 2,
        "circle-radius": [
          "interpolate",
          ["linear"],
          ["zoom"],
          11,
          3.2,
          16,
          6.2,
        ],
        "circle-opacity": 0.98,
      },
    });

    state.layersReady = true;
  }

  function palette() {
    if (state.theme === "light") {
      return {
        selectionFill: "#06b6d4",
        selectionHalo: "#0891b2",
        selectionLine: "#0284c7",
        contextWater: "#2e91ff",
        contextPark: "#27a844",
        contextBuilding: "#64748b",
        contextRoadCasing: "#ffffff",
        contextRoad: "#4b5563",
        contextRoadMajor: "#c2410c",
        contextRoadMid: "#d97706",
        contextRoadMinor: "#64748b",
        generatedPark: "#22c55e",
        generatedParking: "#f59e0b",
        buildingLow: "#67e8f9",
        buildingMid: "#60a5fa",
        buildingHigh: "#a855f7",
        buildingTower: "#f472b6",
        buildingSupertall: "#facc15",
        generatedRoadCasing: "#ffffff",
        generatedGateway: "#06b6d4",
        generatedConnector: "#0891b2",
        generatedPrimary: "#0ea5e9",
        generatedStreet: "#38bdf8",
        generatedCycle: "#16a34a",
        anchorHalo: "#06b6d4",
        anchorDot: "#00d5ff",
        anchorStroke: "#ffffff",
      };
    }
    return {
      selectionFill: "#53f7ff",
      selectionHalo: "#53f7ff",
      selectionLine: "#9dfcff",
      contextWater: "#3b82f6",
      contextPark: "#40e36d",
      contextBuilding: "#9ca3af",
      contextRoadCasing: "#020617",
      contextRoad: "#ffe8b0",
      contextRoadMajor: "#ffb86b",
      contextRoadMid: "#ffd166",
      contextRoadMinor: "#d6e4ff",
      generatedPark: "#7dff9f",
      generatedParking: "#ffd166",
      buildingLow: "#53f7ff",
      buildingMid: "#7aa7ff",
      buildingHigh: "#b66dff",
      buildingTower: "#ff7ab6",
      buildingSupertall: "#fff08a",
      generatedRoadCasing: "#020617",
      generatedGateway: "#ffffff",
      generatedConnector: "#9dfcff",
      generatedPrimary: "#53f7ff",
      generatedStreet: "#c8ffff",
      generatedCycle: "#7dff9f",
      anchorHalo: "#53f7ff",
      anchorDot: "#53f7ff",
      anchorStroke: "#ffffff",
    };
  }

  function addSourceIfMissing(id, data) {
    if (!map.getSource(id)) {
      map.addSource(id, { type: "geojson", data });
    }
  }

  function addLayerIfMissing(layer) {
    if (!map.getLayer(layer.id)) {
      map.addLayer(layer);
    }
  }

  function refreshAllSources() {
    if (
      !map.getSource("selection") ||
      !map.getSource("context") ||
      !map.getSource("generated")
    ) {
      return;
    }
    updateSelectionSource();
    setSourceData("context", {
      type: "FeatureCollection",
      features: state.contextFeatures,
    });
    // Re-render immediately after a style swap — debounced generation would briefly
    // clear output when contextStatus was previously set to "stale".
    generateScenario();
  }

  function setSourceData(sourceId, data) {
    const source = map.getSource(sourceId);
    if (source && typeof source.setData === "function") {
      source.setData(data);
    }
  }

  function addVertex(coord) {
    state.vertices.push(coord);
    renderVertexMarkers();
    updateSelectionSource();
    scheduleGeneration();
    scheduleContextFetch();
    schedulePopulationFetch();
    scheduleImpactFetch();
  }

  function undoVertex() {
    if (state.vertices.length === 0) {
      return;
    }
    state.vertices.pop();
    renderVertexMarkers();
    updateSelectionSource();
    scheduleGeneration();
    scheduleContextFetch();
    schedulePopulationFetch();
    scheduleImpactFetch();
  }

  function clearZone() {
    state.vertices = [];
    state.contextFeatures = [];
    state.contextKey = "";
    state.contextStatus = "empty";
    state.latestStats = createEmptyContextStats();
    state.lastSuccessfulRenderFeatureCount = 0;
    renderVertexMarkers();
    setSourceData("selection", EMPTY);
    setSourceData("context", EMPTY);
    setSourceData("generated", EMPTY);
    updateMetrics(null);
    clearPopulation();
    clearImpact();
    setStatus(
      20,
      "Zone cleared. Click four or more points to start a new scenario.",
    );
  }

  function loadDemoZone(showMessage = false) {
    state.vertices = [
      [-0.1399, 51.5077],
      [-0.1216, 51.5094],
      [-0.1148, 51.5024],
      [-0.1264, 51.4966],
      [-0.1448, 51.5009],
    ];
    renderVertexMarkers();
    updateSelectionSource();
    fitToZone({ animated: showMessage });
    queueInitialContextFetch();
    schedulePopulationFetch();
    scheduleImpactFetch();
    if (showMessage) {
      showToast(
        "Demo zone restored. Water override is off by default, so mapped rivers are excluded from generation.",
      );
    }
  }

  // Ray-casting point-in-polygon against a single closed ring of [lng, lat] pairs.
  function pointInRing(point, ring) {
    const [x, y] = point;
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
      const [xi, yi] = ring[i];
      const [xj, yj] = ring[j];
      const intersects =
        yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
      if (intersects) {
        inside = !inside;
      }
    }
    return inside;
  }

  function prefersReducedMotion() {
    return (
      window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true
    );
  }

  function easeToAsync(camera, signal) {
    return new Promise((resolve, reject) => {
      if (signal?.aborted) {
        reject(abortError());
        return;
      }

      let settled = false;
      let safetyTimer = null;

      const cleanup = () => {
        map.off("moveend", onMoveEnd);
        signal?.removeEventListener("abort", onAbort);
        window.clearTimeout(safetyTimer);
      };

      const finish = () => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        resolve();
      };

      const onMoveEnd = () => finish();

      const onAbort = () => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        map.stop();
        reject(abortError());
      };

      signal?.addEventListener("abort", onAbort, { once: true });
      map.once("moveend", onMoveEnd);
      map.easeTo(camera);

      safetyTimer = window.setTimeout(
        finish,
        Math.max(100, Number(camera.duration || 0) + 250),
      );
    });
  }

  async function flyToLondonOverview(options = {}) {
    const signal = options.signal;
    throwIfAborted(signal);

    setStatus(
      24,
      "Flying to a London overview before choosing an improvement area...",
    );

    await easeToAsync(
      {
        ...AUTO_IMPROVEMENT_OVERVIEW_CAMERA,
        duration: prefersReducedMotion()
          ? 0
          : AUTO_IMPROVEMENT_OVERVIEW_CAMERA.duration,
      },
      signal,
    );
  }

  function buildRandomAutoImprovementVertices(random = Math.random) {
    const [minLng, minLat, maxLng, maxLat] =
      AUTO_IMPROVEMENT_CENTER_BBOX;

    for (let attempt = 0; attempt < 100; attempt += 1) {
      const center = [
        randomRange(random, minLng, maxLng),
        randomRange(random, minLat, maxLat),
      ];

      if (!pointInRing(center, GREATER_LONDON_RING)) {
        continue;
      }

      const vertexCount = Math.floor(randomRange(random, 5, 8.999)); // 5..8
      const baseRadiusKm = randomRange(random, 0.42, 0.82);
      const rotation = randomRange(random, 0, Math.PI * 2);
      const metersPerDegLat = 111320;
      const metersPerDegLng =
        111320 * Math.cos((center[1] * Math.PI) / 180);

      const vertices = [];
      let valid = true;

      for (let i = 0; i < vertexCount; i += 1) {
        const angle =
          rotation +
          (i / vertexCount) * Math.PI * 2 +
          randomRange(random, -0.28, 0.28);

        const radiusKm = baseRadiusKm * randomRange(random, 0.68, 1.28);
        const dx = Math.cos(angle) * radiusKm * 1000;
        const dy = Math.sin(angle) * radiusKm * 1000;

        const vertex = [
          center[0] + dx / metersPerDegLng,
          center[1] + dy / metersPerDegLat,
        ];

        if (!pointInRing(vertex, GREATER_LONDON_RING)) {
          valid = false;
          break;
        }

        vertices.push(vertex);
      }

      if (!valid) {
        continue;
      }

      const areaSqm = turfArea(polygonFeature(vertices));
      const areaKm2 = areaSqm / 1_000_000;

      if (areaKm2 < 0.35 || areaKm2 > 2.4) {
        continue;
      }

      return vertices;
    }

    return [
      [-0.1399, 51.5077],
      [-0.1216, 51.5094],
      [-0.1148, 51.5024],
      [-0.1264, 51.4966],
      [-0.1448, 51.5009],
    ];
  }

  async function pickAutoImprovementZone(options = {}) {
    const signal = options.signal;
    const reveal = options.reveal !== false;
    throwIfAborted(signal);

    const vertices = buildRandomAutoImprovementVertices(Math.random);

    state.contextKey = "";
    state.statsCache = null;
    state.lastGeneratedFeatures = [];
    state.contextFeatures = [];
    state.contextStatus = "empty";
    state.lastSuccessfulRenderFeatureCount = 0;
    setSourceData("context", EMPTY);
    setSourceData("generated", EMPTY);

    setStatus(
      30,
      "Choosing a random central London neighbourhood boundary...",
    );

    if (reveal && !prefersReducedMotion()) {
      state.vertices = [];
      renderVertexMarkers();
      updateSelectionSource();

      for (let index = 0; index < vertices.length; index += 1) {
        throwIfAborted(signal);
        state.vertices = vertices.slice(0, index + 1);
        renderVertexMarkers();
        updateSelectionSource();
        await sleep(900 / vertices.length, signal);
      }
    } else {
      state.vertices = vertices;
      renderVertexMarkers();
      updateSelectionSource();
    }

    fitToZone({
      animated: !prefersReducedMotion(),
      durationMs: prefersReducedMotion() ? 0 : 1200,
      maxZoom: AUTO_IMPROVEMENT_FIT_MAX_ZOOM,
    });

    const stopFitOnAbort = () => map.stop();
    signal?.addEventListener("abort", stopFitOnAbort, { once: true });
    try {
      await sleep(prefersReducedMotion() ? 0 : 1250, signal);
    } finally {
      signal?.removeEventListener("abort", stopFitOnAbort);
    }

    queueInitialContextFetch();
    schedulePopulationFetch();
    scheduleImpactFetch();

    showToast("Auto improvement selected a neighbourhood-scale London area.");
  }

  // Compatibility path for the old autoZone handle. The guided React flow calls
  // pickAutoImprovementZone instead.
  function loadAutoZone() {
    state.vertices = buildRandomAutoImprovementVertices(Math.random);
    state.contextKey = "";
    state.statsCache = null;
    state.lastGeneratedFeatures = [];
    state.contextFeatures = [];
    state.contextStatus = "empty";
    state.lastSuccessfulRenderFeatureCount = 0;
    setSourceData("context", EMPTY);
    setSourceData("generated", EMPTY);
    renderVertexMarkers();
    updateSelectionSource();
    fitToZone({
      animated: true,
      maxZoom: AUTO_IMPROVEMENT_FIT_MAX_ZOOM,
    });
    queueInitialContextFetch();
    schedulePopulationFetch();
    scheduleImpactFetch();
    showToast("Auto improvement selected a neighbourhood-scale London area.");
  }

  function fitPadding() {
    const { clientWidth: width, clientHeight: height } = map.getContainer();
    const isNarrow = width < 768;
    const peek = Math.min(120, Math.round(height * 0.14));

    const padding = isNarrow
      ? { top: 56, bottom: peek + 24, left: 20, right: 20 }
      : { top: 94, bottom: 92, left: 380, right: 440 };

    // MapLibre fitBounds breaks when padding exceeds the canvas.
    const maxH = Math.floor(width * 0.45);
    const maxV = Math.floor(height * 0.45);
    return {
      top: Math.min(padding.top, maxV),
      bottom: Math.min(padding.bottom, maxV),
      left: Math.min(padding.left, maxH),
      right: Math.min(padding.right, maxH),
    };
  }

  function fitToZone(options = {}) {
    const animated = options.animated === true;
    const durationMs = Number.isFinite(options.durationMs)
      ? options.durationMs
      : animated
        ? 760
        : 0;
    const maxZoom = Number.isFinite(options.maxZoom)
      ? options.maxZoom
      : 15.2;
    map.resize();
    if (state.vertices.length === 0) {
      map.easeTo({
        center: LONDON_CENTER,
        zoom: 12.4,
        pitch: 57,
        bearing: -18,
        duration: Number.isFinite(options.durationMs)
          ? options.durationMs
          : animated
            ? 700
            : 0,
      });
      return;
    }
    const bounds = state.vertices.reduce(
      (box, coord) => box.extend(coord),
      new maplibregl.LngLatBounds(state.vertices[0], state.vertices[0]),
    );
    map.fitBounds(bounds, {
      padding: fitPadding(),
      pitch: 57,
      bearing: -18,
      duration: durationMs,
      maxZoom,
    });
  }

  function renderVertexMarkers() {
    for (const marker of state.vertexMarkers) {
      marker.remove();
    }
    for (const marker of state.midpointMarkers) {
      marker.remove();
    }
    state.vertexMarkers = [];
    state.midpointMarkers = [];

    state.vertices.forEach((coord, index) => {
      const element = document.createElement("div");
      element.className = "vertex-marker";
      element.title = "Drag to reshape. Double-click or right-click to remove.";
      const marker = new maplibregl.Marker({
        element,
        draggable: true,
        anchor: "center",
      })
        .setLngLat(coord)
        .addTo(map);

      marker.on("dragstart", () => {
        emit.onAutoInterrupted();
      });
      marker.on("drag", () => {
        const lngLat = marker.getLngLat();
        state.vertices[index] = [lngLat.lng, lngLat.lat];
        updateSelectionSource();
      });
      marker.on("dragend", () => {
        const lngLat = marker.getLngLat();
        state.vertices[index] = [lngLat.lng, lngLat.lat];
        updateSelectionSource();
        renderVertexMarkers();
        scheduleGeneration();
        scheduleContextFetch();
        schedulePopulationFetch();
        scheduleImpactFetch();
      });

      element.addEventListener("dblclick", (event) => {
        event.preventDefault();
        event.stopPropagation();
        emit.onAutoInterrupted();
        removeVertex(index);
      });
      element.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        event.stopPropagation();
        emit.onAutoInterrupted();
        removeVertex(index);
      });

      state.vertexMarkers.push(marker);
    });

    renderMidpointMarkersOnly();
  }

  function renderMidpointMarkersOnly() {
    for (const marker of state.midpointMarkers) {
      marker.remove();
    }
    state.midpointMarkers = [];
    if (state.vertices.length < 2) {
      return;
    }

    const edgeCount =
      state.vertices.length >= MIN_POLYGON_VERTICES
        ? state.vertices.length
        : state.vertices.length - 1;
    for (let index = 0; index < edgeCount; index += 1) {
      const nextIndex = (index + 1) % state.vertices.length;
      const coord = midpointLngLat(
        state.vertices[index],
        state.vertices[nextIndex],
      );
      const element = document.createElement("div");
      element.className = "midpoint-marker";
      element.title = "Click to add a vertex here.";
      element.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        emit.onAutoInterrupted();
        state.vertices.splice(nextIndex, 0, coord);
        renderVertexMarkers();
        updateSelectionSource();
        scheduleGeneration();
        scheduleContextFetch();
        schedulePopulationFetch();
        scheduleImpactFetch();
      });
      const marker = new maplibregl.Marker({ element, anchor: "center" })
        .setLngLat(coord)
        .addTo(map);
      state.midpointMarkers.push(marker);
    }
  }

  function removeVertex(index) {
    if (state.vertices.length <= 1) {
      clearZone();
      return;
    }
    state.vertices.splice(index, 1);
    renderVertexMarkers();
    updateSelectionSource();
    scheduleGeneration();
    scheduleContextFetch();
    schedulePopulationFetch();
    scheduleImpactFetch();
  }

  function midpointLngLat(a, b) {
    return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  }

  function updateSelectionSource() {
    if (state.vertices.length < MIN_POLYGON_VERTICES) {
      setSourceData("selection", EMPTY);
      return;
    }
    setSourceData("selection", {
      type: "FeatureCollection",
      features: [polygonFeature(state.vertices)],
    });
  }

  function polygonFeature(vertices) {
    const closed = [...vertices, vertices[0]];
    return {
      type: "Feature",
      properties: { kind: "selection" },
      geometry: { type: "Polygon", coordinates: [closed] },
    };
  }

  function verticesKey(vertices) {
    return vertices
      .map((coord) => `${coord[0].toFixed(5)},${coord[1].toFixed(5)}`)
      .join("|");
  }

  function schedulePopulationFetch() {
    if (state.vertices.length < MIN_POLYGON_VERTICES) {
      return;
    }
    window.clearTimeout(state.populationTimer);
    state.populationTimer = window.setTimeout(
      fetchPopulation,
      POPULATION_FETCH_DEBOUNCE_MS,
    );
  }

  function clearPopulation() {
    window.clearTimeout(state.populationTimer);
    state.populationController?.abort();
    state.populationController = null;
    state.populationKey = "";
    emit.onPopulation(null);
  }

  async function fetchPopulation() {
    if (state.vertices.length < MIN_POLYGON_VERTICES) {
      return;
    }
    // The estimate depends only on the polygon, so skip refetching an unchanged shape.
    const key = verticesKey(state.vertices);
    if (key === state.populationKey) {
      return;
    }

    state.populationController?.abort();
    const controller = new AbortController();
    state.populationController = controller;
    emit.onPopulation({ status: "loading" });

    try {
      const response = await fetch(`${API_BASE_URL}/population`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          polygon: polygonFeature(state.vertices).geometry,
        }),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(`Population request failed: ${response.status}`);
      }
      const data = await response.json();
      state.populationKey = key;
      const approximatePopulation = Number(data.approximate_population);
      emit.onPopulation({
        status: "ready",
        approximatePopulation,
        population: approximatePopulation.toLocaleString(),
        lsoaCount: data.lsoa_count,
        areaKm2: data.area_km2,
        note: data.note,
      });
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
      // Surface the failure (the card shows an error) and allow a later retry.
      state.populationKey = "";
      emit.onPopulation({ status: "error" });
    } finally {
      if (state.populationController === controller) {
        state.populationController = null;
      }
    }
  }

  function scheduleImpactFetch() {
    if (state.vertices.length < MIN_POLYGON_VERTICES) {
      return;
    }
    window.clearTimeout(state.impactTimer);
    state.impactTimer = window.setTimeout(
      fetchImpact,
      IMPACT_FETCH_DEBOUNCE_MS,
    );
  }

  function clearImpact() {
    window.clearTimeout(state.impactTimer);
    state.impactController?.abort();
    state.impactController = null;
    state.impactKey = "";
    emit.onImpact(null);
  }

  async function fetchImpact() {
    if (state.vertices.length < MIN_POLYGON_VERTICES) {
      return;
    }
    // Impact depends on both the polygon and the slider params, so key on both.
    const params = cityTwinSettingsToReplanningParams(state.settings);
    const key = `${verticesKey(state.vertices)}|${JSON.stringify(params)}`;
    if (key === state.impactKey) {
      return;
    }

    state.impactController?.abort();
    const controller = new AbortController();
    state.impactController = controller;
    emit.onImpact({ status: "loading" });

    try {
      const response = await fetch(`${API_BASE_URL}/impact`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          polygon: polygonFeature(state.vertices).geometry,
          params,
        }),
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(`Impact request failed: ${response.status}`);
      }
      const data = await response.json();
      console.info("[UrbanFlux] Impact calculation engine", {
        engine: data.calculation_engine || "unknown",
        reason: data.calculation_reason || "unknown",
        note: data.note || "",
      });
      state.impactKey = key;
      emit.onImpact({
        status: "ready",
        note: data.note,
        calculationEngine: data.calculation_engine,
        calculationReason: data.calculation_reason,
        metrics: (data.metrics || []).map((metric) => ({
          metric: metric.improved_metric,
          value: metric.improved_value,
          delta: metric.delta,
          source: metric.source,
          methodologySource: metric.methodology_source,
          basis: metric.basis,
        })),
      });
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
      // Surface the failure (the card shows an error) and allow a later retry.
      state.impactKey = "";
      emit.onImpact({ status: "error" });
    } finally {
      if (state.impactController === controller) {
        state.impactController = null;
      }
    }
  }

  function scheduleGeneration() {
    if (state.generationRaf !== null) {
      cancelAnimationFrame(state.generationRaf);
    }
    state.generationRaf = requestAnimationFrame(() => {
      state.generationRaf = null;
      generateScenario();
    });
  }

  function scheduleContextFetch(options = {}) {
    if (state.vertices.length < MIN_POLYGON_VERTICES) {
      return;
    }
    window.clearTimeout(state.contextTimer);
    const delay = options.urgent ? 0 : CONTEXT_FETCH_DEBOUNCE_MS;
    state.contextTimer = window.setTimeout(
      fetchContextForCurrentPolygon,
      delay,
    );
  }

  function queueInitialContextFetch() {
    window.clearTimeout(state.contextTimer);
    const run = () => {
      state.contextTimer = null;
      fetchContextForCurrentPolygon();
    };
    if (!map.isStyleLoaded() || map.isMoving()) {
      map.once("idle", run);
      return;
    }
    run();
  }

  function scheduleMapSettledContextFetch() {
    window.clearTimeout(state.settledContextTimer);
    const queue = () => {
      state.settledContextTimer = window.setTimeout(() => {
        if (state.vertices.length >= MIN_POLYGON_VERTICES) {
          scheduleContextFetch();
        }
      }, 280);
    };
    if (!map.isStyleLoaded() || map.isMoving()) {
      map.once("idle", queue);
      return;
    }
    queue();
  }

  function buildContextKey(bbox) {
    return `${state.theme}:${bbox.map((value) => value.toFixed(4)).join(",")}`;
  }

  function applyContextResult(status, features) {
    state.contextStatus = status;
    state.contextFeatures = features;
    state.statsCache = null;
    setSourceData("context", { type: "FeatureCollection", features });
  }

  function cacheContextResult(contextKey, status, features) {
    state.contextCache.set(contextKey, { status, features });
    while (state.contextCache.size > CONTEXT_CACHE_MAX) {
      const oldest = state.contextCache.keys().next().value;
      state.contextCache.delete(oldest);
    }
  }

  function cacheOverpassPayload(bboxKey, features) {
    state.overpassBBoxCache.set(bboxKey, features);
    while (state.overpassBBoxCache.size > OVERPASS_BBOX_CACHE_MAX) {
      const oldest = state.overpassBBoxCache.keys().next().value;
      state.overpassBBoxCache.delete(oldest);
    }
  }

  async function waitForMapSettled() {
    if (!map.isStyleLoaded() || map.isMoving()) {
      await new Promise((resolve) => map.once("idle", resolve));
    }
  }

  async function fetchContextForCurrentPolygon() {
    if (state.vertices.length < MIN_POLYGON_VERTICES) {
      return;
    }
    const polygon = polygonFeature(state.vertices);
    const bbox = expandBbox(turfBbox(polygon), 0.0062);
    const contextKey = buildContextKey(bbox);
    const cached = state.contextCache.get(contextKey);
    if (cached) {
      state.contextKey = contextKey;
      applyContextResult(cached.status, cached.features);
      generateScenario();
      return;
    }
    if (contextKey === state.contextKey && state.contextFeatures.length) {
      return;
    }
    state.contextKey = contextKey;
    state.statsCache = null;
    const previousContextStatus = state.contextStatus;

    if (state.contextFetchController) {
      state.contextFetchController.abort();
    }
    state.contextFetchController = new AbortController();
    state.contextStatus = "fetching";

    if (state.contextFeatures.length === 0) {
      await waitForMapSettled();
    }

    setStatus(
      34,
      "Reading vector basemap topology for roads, rivers, buildings and parks...",
    );
    let vectorFeatures = extractVectorTileContextFeatures({
      selectedPolygon: polygon,
      bbox,
    });
    if (
      !vectorContextLooksReady(vectorFeatures) &&
      state.contextFeatures.length > 0
    ) {
      state.contextStatus = WATER_CONTEXT_READY_STATES.has(
        previousContextStatus,
      )
        ? previousContextStatus
        : "vector";
      setSourceData("context", {
        type: "FeatureCollection",
        features: state.contextFeatures,
      });
      scheduleMapSettledContextFetch();
      generateScenario();
      return;
    }
    if (vectorFeatures.length > 0) {
      applyContextResult("vector", vectorFeatures);
      generateScenario();
      setStatus(
        54,
        `Loaded ${vectorFeatures.length.toLocaleString()} vector-tile features. Fetching raw OSM road graph for exact boundary anchors...`,
      );
    }

    // When the vector basemap already yields a rich road graph (and either water is
    // present or the user allowed building over water), the raw OSM refinement adds
    // little. Skipping it avoids a slow/flaky network round-trip plus a second full
    // generation. Sparse zones and water-gated zones still fall through to Overpass.
    if (vectorFeatures.length > 0 && vectorContextSufficient(vectorFeatures)) {
      cacheContextResult(contextKey, "vector", vectorFeatures);
      setStatus(
        82,
        `Vector basemap context is rich (${vectorFeatures.length.toLocaleString()} features). Skipping raw OSM fetch.`,
      );
      return;
    }

    const overpassBboxKey = bbox.map((value) => value.toFixed(3)).join(",");
    const overpassCached = state.overpassBBoxCache.get(overpassBboxKey);
    if (overpassCached) {
      const features = capContextFeaturesByKind(
        mergeContextFeatures(vectorFeatures, overpassCached),
      );
      applyContextResult("osm", features);
      cacheContextResult(contextKey, "osm", features);
      setStatus(
        78,
        `Merged ${features.length.toLocaleString()} basemap + cached OSM geometries. Rebuilding road-connected plan...`,
      );
      generateScenario();
      return;
    }

    if (Date.now() < state.overpassCooldownUntil) {
      if (vectorFeatures.length > 0) {
        applyContextResult("vector", vectorFeatures);
        cacheContextResult(contextKey, "vector", vectorFeatures);
        setStatus(68, "Overpass cooling down. Using vector-tile topology.");
        generateScenario();
      } else {
        state.contextStatus = WATER_CONTEXT_READY_STATES.has(
          previousContextStatus,
        )
          ? previousContextStatus
          : state.contextStatus;
      }
      return;
    }

    setStatus(
      62,
      "Fetching raw OSM roads, buildings, parks and water geometry around the selected boundary...",
    );
    const query = buildOverpassQuery(bbox);
    const endpoint =
      OVERPASS_ENDPOINTS[
        state.overpassEndpointIndex % OVERPASS_ENDPOINTS.length
      ];

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body: `data=${encodeURIComponent(query)}`,
        headers: {
          "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
        },
        signal: state.contextFetchController.signal,
      });
      if (!response.ok) {
        if (response.status === 429 || response.status >= 500) {
          state.overpassCooldownUntil = Date.now() + OVERPASS_COOLDOWN_MS;
        }
        throw new Error(`Overpass HTTP ${response.status}`);
      }
      const data = await response.json();
      const overpassFeatures = parseOverpassFeatures(data, polygon);
      cacheOverpassPayload(overpassBboxKey, overpassFeatures);
      const features = capContextFeaturesByKind(
        mergeContextFeatures(vectorFeatures, overpassFeatures),
      );
      applyContextResult("osm", features);
      cacheContextResult(contextKey, "osm", features);
      setStatus(
        78,
        `Merged ${features.length.toLocaleString()} basemap + raw OSM geometries. Rebuilding road-connected plan...`,
      );
      generateScenario();
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
      state.overpassEndpointIndex += 1;
      if (vectorFeatures.length > 0) {
        applyContextResult("partial", vectorFeatures);
        cacheContextResult(contextKey, "partial", vectorFeatures);
        setStatus(
          68,
          "Raw OSM fetch failed, but vector-tile topology is available. Using basemap-snapped road connectors.",
        );
        generateScenario();
        return;
      }
      console.warn("OSM context fetch failed with no vector fallback", error);
      state.contextStatus = "failed";
      state.contextFeatures = [];
      setSourceData("context", EMPTY);
      setStatus(
        42,
        "Live context failed. Water override is off, so the unsafe procedural fallback is blocked.",
      );
      generateScenario();
    }
  }

  function extractVectorTileContextFeatures({ selectedPolygon, bbox }) {
    if (!map.isStyleLoaded()) {
      return [];
    }

    const filterCtx = createContextFilterCtx(selectedPolygon);
    const layers = discoverBasemapContextLayers();
    const pixelBox = bboxToPixelQueryBox(bbox, 132);
    const features = [];

    features.push(
      ...queryRenderedContextFeatures(pixelBox, layers.road, "road", filterCtx),
      ...queryRenderedContextFeatures(
        pixelBox,
        layers.water,
        "water",
        filterCtx,
      ),
      ...queryRenderedContextFeatures(
        pixelBox,
        layers.building,
        "building",
        filterCtx,
      ),
      ...queryRenderedContextFeatures(pixelBox, layers.park, "park", filterCtx),
    );

    // queryRenderedFeatures is visually exact, but hidden/minor roads may be absent at some zooms.
    // querySourceFeatures fills that gap from currently loaded vector tiles. The layer list covers
    // OpenMapTiles/OpenFreeMap and common Protomaps-compatible source-layer names.
    if (
      features.filter((feature) => feature.properties.kind === "road").length <
      10
    ) {
      features.push(
        ...querySourceContextFeatureLayers(
          VECTOR_CONTEXT_SOURCE_LAYERS.road,
          "road",
          filterCtx,
        ),
      );
    }
    if (
      features.filter((feature) => feature.properties.kind === "water").length <
      4
    ) {
      features.push(
        ...querySourceContextFeatureLayers(
          VECTOR_CONTEXT_SOURCE_LAYERS.water,
          "water",
          filterCtx,
        ),
      );
    }
    if (
      features.filter((feature) => feature.properties.kind === "building")
        .length < 12
    ) {
      features.push(
        ...querySourceContextFeatureLayers(
          VECTOR_CONTEXT_SOURCE_LAYERS.building,
          "building",
          filterCtx,
        ),
      );
    }
    if (
      features.filter((feature) => feature.properties.kind === "park").length <
      6
    ) {
      features.push(
        ...querySourceContextFeatureLayers(
          VECTOR_CONTEXT_SOURCE_LAYERS.park,
          "park",
          filterCtx,
        ),
      );
    }

    return capContextFeaturesByKind(dedupeContextFeatures(features));
  }

  function discoverBasemapContextLayers() {
    const groups = { road: [], water: [], building: [], park: [] };
    const style = map.getStyle();
    for (const layer of style.layers || []) {
      if (
        !layer.id ||
        CUSTOM_LAYER_PREFIXES.some((prefix) => layer.id.startsWith(prefix))
      ) {
        continue;
      }
      const id = layer.id.toLowerCase();
      const sourceLayer = String(layer["source-layer"] || "").toLowerCase();
      const type = layer.type;

      if (
        type === "line" &&
        (["transportation", "transportation_name", "roads", "road"].includes(
          sourceLayer,
        ) ||
          /road|street|bridge|tunnel|path|highway/.test(id))
      ) {
        groups.road.push(layer.id);
        continue;
      }
      if (
        (type === "fill" || type === "line") &&
        (["water", "waterway", "physical_line"].includes(sourceLayer) ||
          /water|river|canal|dock/.test(id))
      ) {
        groups.water.push(layer.id);
        continue;
      }
      if (
        (type === "fill" || type === "fill-extrusion") &&
        (["building", "buildings"].includes(sourceLayer) || /building/.test(id))
      ) {
        groups.building.push(layer.id);
        continue;
      }
      if (
        (type === "fill" || type === "line") &&
        (/park|landcover|landuse|green|wood|grass/.test(id) ||
          ["park", "landcover", "landuse", "landuse_p"].includes(sourceLayer))
      ) {
        groups.park.push(layer.id);
      }
    }
    return groups;
  }

  function bboxToPixelQueryBox(bbox, padding) {
    const projected = [
      map.project([bbox[0], bbox[1]]),
      map.project([bbox[0], bbox[3]]),
      map.project([bbox[2], bbox[1]]),
      map.project([bbox[2], bbox[3]]),
    ];
    const xs = projected.map((point) => point.x);
    const ys = projected.map((point) => point.y);
    return [
      [Math.min(...xs) - padding, Math.min(...ys) - padding],
      [Math.max(...xs) + padding, Math.max(...ys) + padding],
    ];
  }

  function queryRenderedContextFeatures(pixelBox, layerIds, kind, filterCtx) {
    if (!layerIds.length) {
      return [];
    }
    try {
      return map
        .queryRenderedFeatures(pixelBox, { layers: layerIds })
        .flatMap((feature) =>
          normaliseMapFeature(feature, kind, filterCtx, "basemap-rendered"),
        );
    } catch (error) {
      console.warn(`Rendered ${kind} context query failed`, error);
      return [];
    }
  }

  function querySourceContextFeatureLayers(sourceLayers, kind, filterCtx) {
    return sourceLayers.flatMap((sourceLayer) =>
      querySourceContextFeatures(sourceLayer, kind, filterCtx),
    );
  }

  function querySourceContextFeatures(sourceLayer, kind, filterCtx) {
    const style = map.getStyle();
    const sourceIds = Object.entries(style.sources || {})
      .filter(([, source]) => source && source.type === "vector")
      .map(([sourceId]) => sourceId);
    const features = [];

    for (const sourceId of sourceIds) {
      try {
        features.push(
          ...map
            .querySourceFeatures(sourceId, { sourceLayer })
            .flatMap((feature) =>
              normaliseMapFeature(feature, kind, filterCtx, "basemap-source"),
            ),
        );
      } catch (_) {
        // Not every basemap source exposes every source-layer.
      }
    }
    return features;
  }

  function normaliseMapFeature(feature, kind, filterCtx, contextSource) {
    const geometry = feature.geometry;
    if (!geometry) {
      return [];
    }
    const props = feature.properties || {};
    const base = {
      kind,
      osmId: String(
        props.osm_id ||
          props.osmId ||
          props.id ||
          feature.id ||
          `${contextSource}/${kind}`,
      ),
      name: props.name || props.name_en || "",
      highway:
        kind === "road"
          ? normaliseHighway(
              props.highway || props.class || props.subclass || props.type,
            )
          : "",
      waterway:
        kind === "water"
          ? String(props.waterway || props.class || props.type || "")
          : "",
      water:
        kind === "water"
          ? String(props.water || props.natural || props.landuse || "")
          : "",
      height: parseBuildingHeight(props),
      contextSource,
    };

    if (kind === "road") {
      return flattenLineGeometry(geometry)
        .map((coordinates) => ({
          type: "Feature",
          properties: base,
          geometry: { type: "LineString", coordinates },
        }))
        .filter(
          (candidate) =>
            candidate.geometry.coordinates.length >= 2 &&
            shouldKeepContextFeature(candidate, filterCtx),
        );
    }

    if (
      kind === "water" &&
      (geometry.type === "LineString" || geometry.type === "MultiLineString")
    ) {
      return flattenLineGeometry(geometry)
        .map((coordinates) => ({
          type: "Feature",
          properties: base,
          geometry: { type: "LineString", coordinates },
        }))
        .filter(
          (candidate) =>
            candidate.geometry.coordinates.length >= 2 &&
            shouldKeepContextFeature(candidate, filterCtx),
        );
    }

    return flattenPolygonGeometry(geometry)
      .map((ring) => {
        if (ring.length < 4) {
          return null;
        }
        const polygon = {
          type: "Feature",
          properties: base,
          geometry: { type: "Polygon", coordinates: [closeRing(ring)] },
        };
        return shouldKeepContextFeature(polygon, filterCtx) ? polygon : null;
      })
      .filter(Boolean);
  }

  function flattenLineGeometry(geometry) {
    if (geometry.type === "LineString") {
      return coordinatesAreLngLat(geometry.coordinates)
        ? [geometry.coordinates]
        : [];
    }
    if (geometry.type === "MultiLineString") {
      return geometry.coordinates.filter(coordinatesAreLngLat);
    }
    return [];
  }

  function flattenPolygonGeometry(geometry) {
    if (geometry.type === "Polygon") {
      return coordinatesAreLngLat(geometry.coordinates[0])
        ? [geometry.coordinates[0]]
        : [];
    }
    if (geometry.type === "MultiPolygon") {
      return geometry.coordinates
        .map((polygon) => polygon[0])
        .filter(coordinatesAreLngLat);
    }
    return [];
  }

  function coordinatesAreLngLat(coordinates) {
    return (
      Array.isArray(coordinates) &&
      coordinates.length >= 2 &&
      coordinates.every(isValidCoord)
    );
  }

  function isValidCoord(coord) {
    return (
      Array.isArray(coord) &&
      coord.length >= 2 &&
      Number.isFinite(coord[0]) &&
      Number.isFinite(coord[1]) &&
      Math.abs(coord[0]) <= 180 &&
      Math.abs(coord[1]) <= 90
    );
  }

  function normaliseHighway(value) {
    const text = String(value || "").toLowerCase();
    if (/primary/.test(text)) return "primary";
    if (/secondary/.test(text)) return "secondary";
    if (/tertiary/.test(text)) return "tertiary";
    if (/living/.test(text)) return "living_street";
    if (/service|driveway|parking/.test(text)) return "service";
    if (/pedestrian|path|steps/.test(text)) return "pedestrian";
    if (/foot/.test(text)) return "footway";
    if (/cycle/.test(text)) return "cycleway";
    if (/minor|residential|street|road/.test(text)) return "residential";
    if (/trunk|motorway/.test(text)) return "primary";
    return text || "residential";
  }

  function mergeContextFeatures(primaryFeatures, secondaryFeatures) {
    return dedupeContextFeatures([...primaryFeatures, ...secondaryFeatures]);
  }

  function dedupeContextFeatures(features) {
    const seen = new Set();
    const result = [];
    for (const feature of features) {
      const key = contextFeatureKey(feature);
      if (!key || seen.has(key)) {
        continue;
      }
      seen.add(key);
      result.push(feature);
    }
    return result;
  }

  // Cap a mixed-kind feature list per kind instead of with a single flat slice, so
  // abundant roads can never crowd out water/building/park (which are appended after
  // roads). This keeps river masks available for water-aware replanning.
  function capContextFeaturesByKind(features, budgets = CONTEXT_KIND_BUDGETS) {
    const counts = {};
    const result = [];
    for (const feature of features) {
      const kind = feature.properties?.kind || "other";
      const budget = budgets[kind] ?? 150;
      const used = counts[kind] || 0;
      if (used >= budget) {
        continue;
      }
      counts[kind] = used + 1;
      result.push(feature);
    }
    return result;
  }

  function contextFeatureKey(feature) {
    const coordinates = firstAndLastCoordinates(feature.geometry);
    if (!coordinates) {
      return null;
    }
    const kind = feature.properties?.kind || "context";
    const source = feature.properties?.contextSource || "osm";
    const osmId = feature.properties?.osmId || "";
    const rounded = coordinates
      .flat()
      .map((value) => Number(value).toFixed(5))
      .join(":");
    return `${kind}:${source}:${osmId}:${rounded}`;
  }

  function firstAndLastCoordinates(geometry) {
    if (!geometry) {
      return null;
    }
    if (geometry.type === "LineString") {
      const first = geometry.coordinates[0];
      const last = geometry.coordinates[geometry.coordinates.length - 1];
      return isValidCoord(first) && isValidCoord(last) ? [first, last] : null;
    }
    if (geometry.type === "Polygon") {
      const ring = geometry.coordinates[0];
      if (!Array.isArray(ring) || ring.length < 2) {
        return null;
      }
      const first = ring[0];
      const last = ring[Math.max(0, ring.length - 2)];
      return isValidCoord(first) && isValidCoord(last) ? [first, last] : null;
    }
    return null;
  }

  function buildOverpassQuery(bbox) {
    const [west, south, east, north] = bbox;
    const bounds = `${south},${west},${north},${east}`;
    return `
[out:json][timeout:18];
(
  way["highway"~"^(primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|unclassified|residential|living_street|service|pedestrian|footway|cycleway|path)$"](${bounds});
  way["building"](${bounds});
  way["leisure"~"^(park|garden|playground|sports_centre|pitch)$"](${bounds});
  way["landuse"~"^(grass|recreation_ground|cemetery|forest|meadow|allotments|village_green|reservoir|basin)$"](${bounds});
  way["natural"~"^(water|wetland|wood|grassland)$"](${bounds});
  way["water"~"^(river|canal|lake|pond|dock|basin|reservoir)$"](${bounds});
  way["waterway"~"^(river|riverbank|canal|stream|dock|drain)$"](${bounds});
  relation["natural"="water"](${bounds});
  relation["water"~"^(river|canal|lake|pond|dock|basin|reservoir)$"](${bounds});
  relation["waterway"~"^(river|riverbank|canal|stream|dock|drain)$"](${bounds});
  relation["leisure"="park"](${bounds});
);
out body geom qt;
`.trim();
  }

  function parseOverpassFeatures(data, selectedPolygon) {
    const filterCtx = createContextFilterCtx(selectedPolygon);
    const features = [];
    for (const element of data.elements || []) {
      const elementFeatures = parseOverpassElement(element, filterCtx);
      for (const feature of elementFeatures) {
        features.push(feature);
      }
    }
    // Overpass returns highway ways first; a flat slice here dropped the water ways
    // that come later in the query. Cap per kind so rivers always survive.
    return capContextFeaturesByKind(features);
  }

  function parseOverpassElement(element, filterCtx) {
    const tags = element.tags || {};
    const features = [];

    if (element.type === "relation" && Array.isArray(element.members)) {
      for (const member of element.members) {
        if (!Array.isArray(member.geometry) || member.geometry.length < 2) {
          continue;
        }
        const coords = member.geometry.map((point) => [point.lon, point.lat]);
        const closed =
          coords.length >= 4 && sameCoord(coords[0], coords[coords.length - 1]);
        const kind = classifyOsm(tags, closed);
        if (!kind) {
          continue;
        }
        const feature = featureFromCoords(
          coords,
          kind,
          tags,
          `${element.type}/${element.id}/${member.ref || features.length}`,
        );
        if (feature && shouldKeepContextFeature(feature, filterCtx)) {
          features.push(feature);
        }
      }
      return features;
    }

    if (!Array.isArray(element.geometry) || element.geometry.length < 2) {
      return features;
    }
    const coords = element.geometry.map((point) => [point.lon, point.lat]);
    const closed =
      coords.length >= 4 && sameCoord(coords[0], coords[coords.length - 1]);
    const kind = classifyOsm(tags, closed);
    if (!kind) {
      return features;
    }
    const feature = featureFromCoords(
      coords,
      kind,
      tags,
      `${element.type}/${element.id}`,
    );
    if (feature && shouldKeepContextFeature(feature, filterCtx)) {
      features.push(feature);
    }
    return features;
  }

  function featureFromCoords(coords, kind, tags, osmId) {
    const properties = {
      kind,
      osmId,
      name: tags.name || "",
      highway: tags.highway || "",
      waterway: tags.waterway || "",
      water: tags.water || tags.natural || tags.landuse || "",
      height: parseBuildingHeight(tags),
      contextSource: "overpass",
    };
    const closed =
      coords.length >= 4 && sameCoord(coords[0], coords[coords.length - 1]);
    if (kind === "road" || (kind === "water" && !closed)) {
      return {
        type: "Feature",
        properties,
        geometry: { type: "LineString", coordinates: coords },
      };
    }
    if (!closed) {
      return null;
    }
    return {
      type: "Feature",
      properties,
      geometry: { type: "Polygon", coordinates: [coords] },
    };
  }

  function createContextFilterCtx(selectedPolygon) {
    const searchBbox = expandBbox(turfBbox(selectedPolygon), 0.0035);
    const coords = selectedPolygon.geometry.coordinates[0];
    const selectionRing =
      coords.length >= 4 && sameCoord(coords[0], coords[coords.length - 1])
        ? coords.slice(0, -1)
        : coords;
    return { searchBbox, selectionRing };
  }

  function featureLngLatBbox(feature) {
    const geometry = feature.geometry;
    if (!geometry) {
      return null;
    }
    let minLng = Infinity;
    let minLat = Infinity;
    let maxLng = -Infinity;
    let maxLat = -Infinity;
    const visit = (lng, lat) => {
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
        return;
      }
      minLng = Math.min(minLng, lng);
      maxLng = Math.max(maxLng, lng);
      minLat = Math.min(minLat, lat);
      maxLat = Math.max(maxLat, lat);
    };
    if (geometry.type === "LineString") {
      for (const coord of geometry.coordinates) {
        visit(coord[0], coord[1]);
      }
    } else if (geometry.type === "Polygon") {
      for (const coord of geometry.coordinates[0]) {
        visit(coord[0], coord[1]);
      }
    }
    if (!Number.isFinite(minLng)) {
      return null;
    }
    return [minLng, minLat, maxLng, maxLat];
  }

  function lngLatBboxesOverlap(a, b) {
    return a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];
  }

  function pointInLngLatRing(lng, lat, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
      const xi = ring[i][0];
      const yi = ring[i][1];
      const xj = ring[j][0];
      const yj = ring[j][1];
      const intersects =
        yi > lat !== yj > lat &&
        lng < ((xj - xi) * (lat - yi)) / (yj - yi || 1e-12) + xi;
      if (intersects) {
        inside = !inside;
      }
    }
    return inside;
  }

  function featureCentroidLngLat(feature) {
    const geometry = feature.geometry;
    if (geometry.type === "LineString") {
      let sumLng = 0;
      let sumLat = 0;
      for (const coord of geometry.coordinates) {
        sumLng += coord[0];
        sumLat += coord[1];
      }
      const count = geometry.coordinates.length;
      return count ? [sumLng / count, sumLat / count] : null;
    }
    if (geometry.type === "Polygon") {
      const ring = geometry.coordinates[0];
      const limit =
        ring.length >= 4 && sameCoord(ring[0], ring[ring.length - 1])
          ? ring.length - 1
          : ring.length;
      let sumLng = 0;
      let sumLat = 0;
      for (let index = 0; index < limit; index += 1) {
        sumLng += ring[index][0];
        sumLat += ring[index][1];
      }
      return limit ? [sumLng / limit, sumLat / limit] : null;
    }
    return null;
  }

  function shouldKeepContextFeature(feature, filterCtx) {
    const featureBbox = featureLngLatBbox(feature);
    if (
      !featureBbox ||
      !lngLatBboxesOverlap(featureBbox, filterCtx.searchBbox)
    ) {
      return false;
    }
    if (feature.properties.kind !== "building") {
      return true;
    }
    const centroid = featureCentroidLngLat(feature);
    if (!centroid) {
      return true;
    }
    return !pointInLngLatRing(
      centroid[0],
      centroid[1],
      filterCtx.selectionRing,
    );
  }

  function classifyOsm(tags, closed) {
    if (tags.highway) {
      return "road";
    }
    if (tags.building && closed) {
      return "building";
    }
    if (isWaterTags(tags)) {
      return "water";
    }
    if (
      tags.leisure === "park" ||
      tags.leisure === "garden" ||
      tags.leisure === "playground" ||
      tags.landuse === "grass" ||
      tags.landuse === "recreation_ground" ||
      tags.landuse === "cemetery" ||
      tags.landuse === "forest" ||
      tags.landuse === "meadow" ||
      tags.landuse === "allotments" ||
      tags.landuse === "village_green" ||
      tags.natural === "wood" ||
      tags.natural === "grassland"
    ) {
      return closed ? "park" : null;
    }
    return null;
  }

  function isWaterTags(tags) {
    return (
      tags.natural === "water" ||
      tags.natural === "wetland" ||
      tags.waterway === "river" ||
      tags.waterway === "riverbank" ||
      tags.waterway === "canal" ||
      tags.waterway === "stream" ||
      tags.waterway === "dock" ||
      tags.waterway === "drain" ||
      tags.water === "river" ||
      tags.water === "canal" ||
      tags.water === "lake" ||
      tags.water === "pond" ||
      tags.water === "dock" ||
      tags.water === "basin" ||
      tags.water === "reservoir" ||
      tags.landuse === "reservoir" ||
      tags.landuse === "basin"
    );
  }

  function parseBuildingHeight(tags) {
    const height = Number.parseFloat(
      String(tags.height || "").replace(/[a-zA-Z ]/g, ""),
    );
    if (Number.isFinite(height) && height > 1) {
      return clamp(height, 4, 180);
    }
    const levels = Number.parseFloat(tags["building:levels"] || "");
    if (Number.isFinite(levels) && levels > 0) {
      return clamp(levels * 3.2, 4, 180);
    }
    return 12;
  }

  function generateScenario() {
    if (state.vertices.length < MIN_POLYGON_VERTICES) {
      setSourceData("generated", EMPTY);
      updateMetrics(null);
      return;
    }

    const selectedPolygon = polygonFeature(state.vertices);
    const frame = createLocalFrame(selectedPolygon);
    const localPolygon = selectedPolygon.geometry.coordinates[0]
      .slice(0, -1)
      .map((coord) => lngLatToLocal(coord, frame));
    const centroid = polygonCentroidLocal(localPolygon);
    const random = seededRandom(
      hashString(
        state.vertices
          .map((coord) => coord.map((n) => n.toFixed(5)).join(":"))
          .join("|") +
          JSON.stringify(state.settings) +
          String(state.allowWater),
      ),
    );
    const statsKey = `${state.contextKey}|${state.theme}|${state.vertices
      .map((coord) => `${coord[0].toFixed(5)},${coord[1].toFixed(5)}`)
      .join("|")}`;
    let stats =
      state.statsCache?.key === statsKey ? state.statsCache.stats : null;
    if (!stats) {
      stats = buildContextStats({
        features: state.contextFeatures,
        selectedPolygon,
        frame,
        localPolygon,
      });
      state.statsCache = { key: statsKey, stats };
    }
    state.latestStats = stats;
    if (!state.allowWater && !waterContextReady()) {
      if (state.lastGeneratedFeatures.length > 0) {
        setSourceData("generated", {
          type: "FeatureCollection",
          features: state.lastGeneratedFeatures,
        });
        return;
      }
      setSourceData("generated", EMPTY);
      updateMetrics(null);
      updatePills(stats);
      emit.onReport(
        "Waiting for vector-tile or raw OSM water masks before generating. Water override is off, so the fallback layout is blocked instead of guessing across rivers.",
      );
      emit.onHint(
        "Water protection is on. Waiting for river and waterbody masks before drawing generated roads/buildings.",
      );
      setStatus(
        46,
        "Water protection is enabled. Waiting for river and waterbody masks before generating the plan...",
      );
      return;
    }

    const generated = generateUrbanLayout({
      selectedPolygon,
      frame,
      localPolygon,
      centroid,
      stats,
      random,
      settings: state.settings,
      allowWater: state.allowWater,
    });

    state.lastGeneratedFeatures = generated.features;
    setSourceData("generated", {
      type: "FeatureCollection",
      features: generated.features,
    });
    state.renderVersion += 1;
    state.lastSuccessfulRenderVersion = state.renderVersion;
    state.lastSuccessfulRenderFeatureCount = generated.features.length;
    window.dispatchEvent(
      new CustomEvent("urbanflux:plan-rendered", {
        detail: {
          version: state.renderVersion,
          featureCount: generated.features.length,
        },
      }),
    );
    updateMetrics(generated.metrics);
    updatePills(stats);
    setStatus(
      generated.metrics.roadFill === 0
        ? 88
        : stats.anchors.length > 0
          ? 92
          : 56,
      generated.metrics.roadFill === 0
        ? "Road fill is 0%. Road generation is disabled; zoning still respects water and the selected boundary."
        : stats.anchors.length > 0
          ? `Connected ${generated.metrics.roadLinks} boundary road anchors with a sparse, one-pass road network. Drag any point to see live replanning.`
        : "No connectable OSM roads found near this boundary yet. Try expanding the polygon or wait for the context layer.",
    );
  }

  function waitForPlanRender(options = {}) {
    const signal = options.signal;
    const timeoutMs = options.timeoutMs ?? 10000;
    const minGeneratedFeatures = options.minGeneratedFeatures ?? 1;
    const startVersion = state.lastSuccessfulRenderVersion;

    return new Promise((resolve, reject) => {
      if (signal?.aborted) {
        reject(abortError());
        return;
      }

      if (
        options.allowExisting === true &&
        state.lastSuccessfulRenderFeatureCount >= minGeneratedFeatures
      ) {
        resolve(true);
        return;
      }

      let settled = false;

      const cleanup = () => {
        window.removeEventListener("urbanflux:plan-rendered", onRendered);
        signal?.removeEventListener("abort", onAbort);
        window.clearTimeout(timeout);
      };

      const finish = (value) => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        resolve(value);
      };

      const onRendered = (event) => {
        const detail = event.detail || {};
        if (
          detail.version > startVersion &&
          detail.featureCount >= minGeneratedFeatures
        ) {
          finish(true);
        }
      };

      const onAbort = () => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        reject(abortError());
      };

      const timeout = window.setTimeout(() => finish(false), timeoutMs);

      window.addEventListener("urbanflux:plan-rendered", onRendered);
      signal?.addEventListener("abort", onAbort, { once: true });
    });
  }

  function selectedZoneCenter() {
    if (state.vertices.length >= MIN_POLYGON_VERTICES) {
      return turfCentroid(polygonFeature(state.vertices)).geometry.coordinates;
    }

    return LONDON_CENTER;
  }

  function startAutoOrbit(options = {}) {
    stopAutoOrbit();

    const signal = options.signal;
    const controller = new AbortController();
    state.autoOrbitAbortController = controller;

    signal?.addEventListener(
      "abort",
      () => {
        controller.abort();
        stopAutoOrbit();
      },
      { once: true },
    );

    if (prefersReducedMotion()) {
      setStatus(
        96,
        "Auto improvement complete. Reduced-motion mode keeps the improved scenario still.",
      );
      return;
    }

    const orbitOnce = () => {
      if (controller.signal.aborted) {
        return;
      }

      const nextBearing = map.getBearing() + 26;
      const currentZoom = map.getZoom();
      const nextZoom =
        currentZoom > (AUTO_ORBIT_ZOOM_MIN + AUTO_ORBIT_ZOOM_MAX) / 2
          ? AUTO_ORBIT_ZOOM_MIN
          : AUTO_ORBIT_ZOOM_MAX;

      map.easeTo({
        center: selectedZoneCenter(),
        bearing: nextBearing,
        pitch: 60,
        zoom: nextZoom,
        duration: AUTO_ORBIT_DURATION_MS,
        easing: (t) => t * (2 - t),
      });

      state.autoOrbitTimer = window.setTimeout(
        orbitOnce,
        AUTO_ORBIT_DURATION_MS + 250,
      );
    };

    setStatus(
      96,
      "Auto improvement complete. Slowly orbiting the greener scenario...",
    );
    orbitOnce();
  }

  function stopAutoOrbit() {
    const hadOrbit =
      state.autoOrbitTimer !== null || state.autoOrbitAbortController !== null;

    window.clearTimeout(state.autoOrbitTimer);
    state.autoOrbitTimer = null;

    const controller = state.autoOrbitAbortController;
    state.autoOrbitAbortController = null;
    controller?.abort();

    if (hadOrbit) {
      map.stop();
    }
  }

  function waterContextReady() {
    if (WATER_CONTEXT_READY_STATES.has(state.contextStatus)) {
      return true;
    }
    // Keep generating from in-memory context during style swaps, zoom/pan tile
    // reloads, and background refetches — only block when context truly failed.
    return state.contextFeatures.length > 0 && state.contextStatus !== "failed";
  }

  function countContextKinds(features) {
    const counts = { road: 0, water: 0, building: 0, park: 0 };
    for (const feature of features) {
      const kind = feature.properties?.kind;
      if (kind in counts) {
        counts[kind] += 1;
      }
    }
    return counts;
  }

  // "Sufficient" = enough road geometry for solid boundary anchors, plus either
  // real water masks already present or water protection disabled. This keeps the
  // Overpass skip safe: zones that still need water masks fall through and fetch.
  function vectorContextSufficient(vectorFeatures) {
    const counts = countContextKinds(vectorFeatures);
    const roadsRich = counts.road >= 80;
    const waterSafe = state.allowWater || counts.water >= 2;
    return roadsRich && waterSafe;
  }

  function vectorContextLooksReady(vectorFeatures) {
    if (vectorFeatures.length === 0) {
      return false;
    }
    if (state.contextFeatures.length === 0) {
      return true;
    }
    // queryRenderedFeatures returns little/nothing until vector tiles paint after setStyle.
    return (
      vectorFeatures.length >= Math.max(24, state.contextFeatures.length * 0.3)
    );
  }

  function buildContextStats({
    features,
    selectedPolygon,
    frame,
    localPolygon,
  }) {
    const roads = [];
    const water = [];
    const buildings = [];
    const parks = [];

    for (const feature of features) {
      if (feature.properties.kind === "road") {
        roads.push(feature);
      } else if (feature.properties.kind === "water") {
        water.push(feature);
      } else if (feature.properties.kind === "building") {
        buildings.push(feature);
      } else if (feature.properties.kind === "park") {
        parks.push(feature);
      }
    }

    const waterObstacles = buildWaterObstacles({
      water,
      selectedPolygon,
      frame,
    });
    const anchors = findRoadAnchors({ roads, localPolygon, frame });
    const medianBuildingArea = estimateMedianBuildingArea(buildings, frame);
    return {
      roads,
      water,
      buildings,
      parks,
      waterObstacles,
      anchors,
      medianBuildingArea,
    };
  }

  function createEmptyContextStats() {
    return {
      roads: [],
      water: [],
      buildings: [],
      parks: [],
      waterObstacles: [],
      anchors: [],
      medianBuildingArea: 210,
    };
  }

  function buildWaterObstacles({ water, selectedPolygon, frame }) {
    const obstacles = [];
    for (const feature of water) {
      try {
        for (const mask of createWaterMasks(feature)) {
          if (!mask || !turfBooleanIntersects(mask, selectedPolygon)) {
            continue;
          }
          for (const ring of collectPolygonRings(mask)) {
            const localRing = closeLocalRing(
              ring.map((coord) => lngLatToLocal(coord, frame)),
            );
            if (Math.abs(polygonSignedArea(localRing)) > 20) {
              ensureObstacleBounds(localRing);
              obstacles.push(localRing);
            }
          }
        }
      } catch (error) {
        console.warn("Failed to create water obstacle", error);
      }
    }
    return dedupeWaterObstacles(obstacles).slice(0, MAX_WATER_OBSTACLES);
  }

  // The buffered mask is in lng/lat and depends only on the water feature itself,
  // not on the drawn polygon or local frame. Cache it on the feature object so a
  // drag replan reuses it; a context refetch creates fresh feature objects, which
  // naturally invalidates the cache.
  function createWaterMasks(feature) {
    if (!feature?.geometry) {
      return [];
    }
    if (feature._waterMasks) {
      return feature._waterMasks;
    }
    const masks = computeWaterMasks(feature);
    Object.defineProperty(feature, "_waterMasks", {
      value: masks,
      enumerable: false,
      writable: true,
      configurable: true,
    });
    return masks;
  }

  function computeWaterMasks(feature) {
    const geometryType = feature.geometry.type;
    if (geometryType === "LineString" || geometryType === "MultiLineString") {
      const buffered = turfBuffer(feature, waterMaskWidthKm(feature), {
        units: "kilometers",
        steps: 12,
      });
      return buffered ? [buffered] : [];
    }
    if (geometryType === "Polygon" || geometryType === "MultiPolygon") {
      const buffered = turfBuffer(feature, WATER_POLYGON_EXCLUSION_KM, {
        units: "kilometers",
        steps: 12,
      });
      return buffered ? [buffered] : [feature];
    }
    return [];
  }

  function waterMaskWidthKm(feature) {
    const props = feature.properties || {};
    const waterText =
      `${props.waterway || ""} ${props.water || ""} ${props.class || ""} ${props.type || ""} ${props.name || ""}`.toLowerCase();
    if (/river|riverbank|thames|wide/.test(waterText)) {
      return WATER_RIVER_LINE_EXCLUSION_KM;
    }
    if (/canal|dock|basin|reservoir/.test(waterText)) {
      return WATER_CANAL_LINE_EXCLUSION_KM;
    }
    if (/stream|drain|ditch/.test(waterText)) {
      return WATER_MINOR_LINE_EXCLUSION_KM;
    }
    return WATER_DEFAULT_LINE_EXCLUSION_KM;
  }

  function dedupeWaterObstacles(obstacles) {
    const result = [];
    const seen = new Set();
    for (const obstacle of obstacles) {
      const bounds = localBounds(obstacle);
      const key = [bounds.minX, bounds.minY, bounds.maxX, bounds.maxY]
        .map((value) => Math.round(value / 3))
        .join(":");
      if (!seen.has(key)) {
        seen.add(key);
        result.push(obstacle);
      }
    }
    return result;
  }

  function closeLocalRing(points) {
    if (!points.length) {
      return points;
    }
    return sameLocalPoint(points[0], points[points.length - 1])
      ? points
      : [...points, points[0]];
  }

  function closeRing(ring) {
    if (!ring.length) {
      return ring;
    }
    return sameCoord(ring[0], ring[ring.length - 1])
      ? ring
      : [...ring, ring[0]];
  }

  function collectPolygonRings(feature) {
    if (!feature || !feature.geometry) {
      return [];
    }
    if (feature.geometry.type === "Polygon") {
      return [feature.geometry.coordinates[0]];
    }
    if (feature.geometry.type === "MultiPolygon") {
      return feature.geometry.coordinates
        .map((polygon) => polygon[0])
        .filter(Boolean);
    }
    return [];
  }

  function estimateMedianBuildingArea(buildings, frame) {
    const areas = [];
    for (const building of buildings.slice(0, 220)) {
      if (building.geometry.type !== "Polygon") {
        continue;
      }
      const ring = building.geometry.coordinates[0].map((coord) =>
        lngLatToLocal(coord, frame),
      );
      const area = Math.abs(polygonSignedArea(ring));
      if (area > 18 && area < 6000) {
        areas.push(area);
      }
    }
    if (areas.length === 0) {
      return 220;
    }
    areas.sort((a, b) => a - b);
    return areas[Math.floor(areas.length / 2)];
  }

  function findRoadAnchors({ roads, localPolygon, frame }) {
    if (!localPolygon.length) {
      return [];
    }
    const edges = polygonEdges(localPolygon);
    const centroid = polygonCentroidLocal(localPolygon);
    const rawAnchors = [];

    for (const road of roads) {
      const highway = road.properties.highway || "residential";
      const sourceBias =
        road.properties.contextSource === "overpass"
          ? -0.38
          : road.properties.contextSource === "basemap-source"
            ? -0.14
            : 0.04;
      if (!CONNECTABLE_HIGHWAYS.has(highway)) {
        continue;
      }
      const coords = road.geometry.coordinates;
      if (!Array.isArray(coords) || coords.length < 2) {
        continue;
      }
      const localLine = coords.map((coord) => lngLatToLocal(coord, frame));

      for (let index = 0; index < localLine.length - 1; index += 1) {
        const a = localLine[index];
        const b = localLine[index + 1];
        const length = distanceLocal(a, b);
        if (length < 3) {
          continue;
        }
        const direction = normalizeVector({ x: b.x - a.x, y: b.y - a.y });
        const aInside = pointInPolygon(a, localPolygon);
        const bInside = pointInPolygon(b, localPolygon);
        let segmentCreatedIntersection = false;

        for (let edgeIndex = 0; edgeIndex < edges.length; edgeIndex += 1) {
          const edge = edges[edgeIndex];
          const hit = segmentIntersection(a, b, edge.a, edge.b);
          if (!hit) {
            continue;
          }
          segmentCreatedIntersection = true;
          const before = interpolateLocal(
            a,
            b,
            Math.max(0, hit.t - Math.min(0.34, 28 / length)),
          );
          const after = interpolateLocal(
            a,
            b,
            Math.min(1, hit.t + Math.min(0.34, 28 / length)),
          );
          let outside = !pointInPolygon(before, localPolygon) ? before : after;
          if (pointInPolygon(outside, localPolygon)) {
            outside = aInside ? b : a;
          }
          if (pointInPolygon(outside, localPolygon)) {
            outside = moveAwayFromCentroid(hit.point, centroid, 38);
          }
          rawAnchors.push(
            makeAnchor({
              local: hit.point,
              outside,
              direction,
              road,
              highway,
              frame,
              source: "intersects-boundary",
              priority: highwayWeight(highway) + sourceBias,
              distanceToRoad: 0,
              edgeIndex,
              segmentIndex: index,
              outsideTrace: buildOutsideTrace(
                localLine,
                index,
                hit.point,
                hit.point,
                localPolygon,
              ),
            }),
          );
        }

        const radius = roadSearchRadiusMeters(highway);
        if (!segmentCreatedIntersection && (!aInside || !bInside)) {
          let best = null;
          let bestEdgeIndex = -1;
          for (let edgeIndex = 0; edgeIndex < edges.length; edgeIndex += 1) {
            const edge = edges[edgeIndex];
            const candidate = nearestSegmentPair(a, b, edge.a, edge.b);
            if (!best || candidate.distance < best.distance) {
              best = candidate;
              bestEdgeIndex = edgeIndex;
            }
          }
          if (
            best &&
            best.distance <= radius &&
            !pointInPolygon(best.onFirst, localPolygon)
          ) {
            rawAnchors.push(
              makeAnchor({
                local: best.onSecond,
                outside: best.onFirst,
                direction,
                road,
                highway,
                frame,
                source: "near-boundary",
                priority:
                  highwayWeight(highway) + sourceBias + best.distance / 90,
                distanceToRoad: best.distance,
                edgeIndex: bestEdgeIndex,
                segmentIndex: index,
                outsideTrace: buildOutsideTrace(
                  localLine,
                  index,
                  best.onFirst,
                  best.onSecond,
                  localPolygon,
                ),
              }),
            );
          }
        }
      }
    }

    return dedupeAnchors(rawAnchors, localPolygon).slice(0, 22);
  }

  function makeAnchor(options) {
    const {
      local,
      outside,
      direction,
      road,
      highway,
      frame,
      source,
      priority,
      distanceToRoad,
      edgeIndex,
      segmentIndex,
      outsideTrace,
    } = options;
    const trace = Array.isArray(outsideTrace)
      ? outsideTrace.filter(isFinitePoint)
      : [];
    // Prefer the real road's first outside vertex as the connection point; fall back
    // to the synthetic lead-in only when the road has no usable outside geometry.
    const leadIn = trace.length
      ? trace[0]
      : chooseLeadInPoint({
          outside,
          local,
          direction,
          localPolygonCentroid: null,
        });
    return {
      id: `${road.properties.osmId}-${edgeIndex}-${segmentIndex}-${source}`,
      local,
      coord: localToLngLat(local, frame),
      outside,
      outsideCoord: localToLngLat(outside, frame),
      outsideTrace: trace,
      leadIn,
      leadInCoord: localToLngLat(leadIn, frame),
      direction,
      highway,
      source,
      priority,
      distanceToRoad,
      edgeIndex,
      osmId: road.properties.osmId,
    };
  }

  // Walk the existing road's own vertices outward from the boundary crossing,
  // collecting the real outside geometry (ordered far -> nearest boundary) so a
  // generated corridor can overlap and continue the actual street instead of a
  // synthetic straight stub. Returns [] for degenerate roads (caller falls back).
  function buildOutsideTrace(
    localLine,
    segmentIndex,
    boundaryPoint,
    anchorLocal,
    localPolygon,
    maxLen = 110,
  ) {
    if (!Array.isArray(localLine) || localLine.length < 2) {
      return [];
    }
    const collect = (startIndex, stepDir) => {
      const points = [];
      let accumulated = 0;
      let previous = boundaryPoint;
      for (let i = startIndex; i >= 0 && i < localLine.length; i += stepDir) {
        const vertex = localLine[i];
        if (!isFinitePoint(vertex) || pointInPolygon(vertex, localPolygon)) {
          break;
        }
        accumulated += distanceLocal(previous, vertex);
        if (accumulated > maxLen) {
          break;
        }
        points.push(vertex);
        previous = vertex;
      }
      return points;
    };

    // One side is outside for boundary crossings; both may be outside for
    // near-boundary roads, so pick the branch reaching farthest from the boundary.
    const downward = collect(segmentIndex, -1);
    const upward = collect(segmentIndex + 1, 1);
    const reach = (points) =>
      points.length
        ? distanceLocal(points[points.length - 1], anchorLocal)
        : -1;
    const chosen = reach(downward) >= reach(upward) ? downward : upward;
    if (chosen.length === 0) {
      return [];
    }
    // chosen is nearest -> far; reverse to far -> nearest for path prepending.
    return chosen.slice().reverse();
  }

  function chooseLeadInPoint({ outside, local, direction }) {
    const d1 = {
      x: outside.x + direction.x * 52,
      y: outside.y + direction.y * 52,
    };
    const d2 = {
      x: outside.x - direction.x * 52,
      y: outside.y - direction.y * 52,
    };
    return distanceLocal(d1, local) >= distanceLocal(d2, local) ? d1 : d2;
  }

  function dedupeAnchors(anchors, localPolygon) {
    const centroid = polygonCentroidLocal(localPolygon);
    const sorted = anchors
      .filter(
        (anchor) =>
          isFinitePoint(anchor.local) &&
          isFinitePoint(anchor.outside) &&
          distanceLocal(anchor.local, anchor.outside) < 260,
      )
      .map((anchor) => ({
        ...anchor,
        radialDistance: distanceLocal(anchor.local, centroid),
      }))
      .sort((a, b) => {
        if (a.priority !== b.priority) {
          return a.priority - b.priority;
        }
        return a.distanceToRoad - b.distanceToRoad;
      });

    const selected = [];
    for (const anchor of sorted) {
      const tooClose = selected.some((existing) => {
        const sameRoadPenalty = existing.osmId === anchor.osmId ? 115 : 0;
        return (
          distanceLocal(existing.local, anchor.local) < 72 + sameRoadPenalty
        );
      });
      if (!tooClose) {
        selected.push(anchor);
      }
      if (selected.length >= 28) {
        break;
      }
    }
    return selected;
  }

  function highwayWeight(highway) {
    if (highway.includes("primary")) {
      return 0;
    }
    if (highway.includes("secondary")) {
      return 0.15;
    }
    if (highway.includes("tertiary")) {
      return 0.32;
    }
    if (highway === "residential" || highway === "unclassified") {
      return 0.62;
    }
    if (highway === "living_street" || highway === "pedestrian") {
      return 0.75;
    }
    return 1;
  }

  function roadSearchRadiusMeters(highway) {
    if (highway.includes("primary") || highway.includes("secondary")) {
      return 185;
    }
    if (highway.includes("tertiary")) {
      return 155;
    }
    if (highway === "service") {
      return 104;
    }
    return 150;
  }

  function generateUrbanLayout({
    selectedPolygon,
    frame,
    localPolygon,
    centroid,
    stats,
    random,
    settings,
    allowWater,
  }) {
    const features = [];
    const localBbox = localBounds(localPolygon);
    const areaSqm = turfArea(selectedPolygon);
    const areaHa = areaSqm / 10000;
    const density = settings.density / 100;
    const green = settings.green / 100;
    const parking = settings.parking / 100;
    const street = settings.street / 100;
    const waterInsideArea = estimateWaterAreaInside(
      stats.waterObstacles,
      selectedPolygon,
      frame,
    );
    const obstacles = allowWater ? [] : stats.waterObstacles;
    const availableAreaSqm = allowWater
      ? areaSqm
      : Math.max(areaSqm - waterInsideArea, areaSqm * 0.08);
    const preparedAnchors = prepareAnchors(
      stats.anchors,
      localPolygon,
      centroid,
      settings,
    );
    const anchors = selectAnchorsForRoadFill(preparedAnchors, street, centroid);
    const alignment = clamp((settings.alignment ?? 72) / 100, 0, 1);
    const blockSpacing = clamp(240 - density * 42 - street * 30, 120, 260);
    const sampleStep = clamp(blockSpacing / 8, 12, 24);
    const roadNetwork = buildSparseRoadNetwork({
      anchors,
      centroid,
      localPolygon,
      obstacles,
      random,
      frame,
      blockSpacing,
      sampleStep,
      roadFill: street,
      alignment,
    });
    features.push(...roadNetwork.features);

    const connectorCount = roadNetwork.connectorCount;
    const gatewayRoutes = roadNetwork.gatewayRoutes;

    const zoning = generateZoning({
      localPolygon,
      frame,
      localBbox,
      obstacles,
      random,
      settings,
      areaSqm: availableAreaSqm,
      medianBuildingArea: stats.medianBuildingArea,
      anchors,
      blockSpacing,
    });
    features.push(...zoning.features);

    const protectedFeatures = allowWater
      ? features
      : filterGeneratedFeaturesAgainstWater(features, frame, obstacles);
    const featureSummary = summariseGeneratedFeatures(protectedFeatures);
    const homes = estimateHomesCapacity(featureSummary, settings);
    const parkingSpaces = Math.round(featureSummary.parkingArea / 18);

    return {
      features: protectedFeatures,
      metrics: {
        areaHa,
        homes,
        roadLinks: featureSummary.roadLinks,
        gatewayLinks: featureSummary.gatewayRoutes,
        roadFill: Math.round(street * 100),
        roadAlignment: Math.round(alignment * 100),
        waterInsideArea,
        waterInsideHa: waterInsideArea / 10000,
        waterProtected: !allowWater && waterInsideArea > 100,
        waterConflictsRemoved: allowWater
          ? 0
          : Math.max(0, features.length - protectedFeatures.length),
        generatedBuildings: featureSummary.buildingCount,
        generatedRoads: featureSummary.roadCount,
        parkingSpaces,
        greenRatio:
          availableAreaSqm > 0
            ? featureSummary.greenArea / availableAreaSqm
            : 0,
        contextRoads: stats.roads.length,
        contextWater: stats.water.length,
        anchors: stats.anchors.length,
      },
    };
  }

  function filterGeneratedFeaturesAgainstWater(features, frame, obstacles) {
    if (!obstacles.length) {
      return features;
    }
    return features.filter((feature) =>
      generatedFeatureAvoidsWater(feature, frame, obstacles),
    );
  }

  function generatedFeatureAvoidsWater(feature, frame, obstacles) {
    if (!feature?.geometry || !feature.properties) {
      return false;
    }
    if (feature.properties.kind === "anchor") {
      return true;
    }
    if (feature.geometry.type === "LineString") {
      const points = feature.geometry.coordinates
        .map((coord) => lngLatToLocal(coord, frame))
        .filter(isFinitePoint);
      return points.length >= 2 && !lineIntersectsAnyPolygon(points, obstacles);
    }
    if (feature.geometry.type === "Polygon") {
      const ring = closeLocalRing(
        feature.geometry.coordinates[0]
          .map((coord) => lngLatToLocal(coord, frame))
          .filter(isFinitePoint),
      );
      return ring.length >= 4 && !polygonIntersectsAnyPolygon(ring, obstacles);
    }
    return true;
  }

  function summariseGeneratedFeatures(features) {
    const roadConnectionIds = new Set();
    const summary = {
      buildingCount: 0,
      buildingFootprintArea: 0,
      buildingFloorArea: 0,
      parkingArea: 0,
      greenArea: 0,
      roadCount: 0,
      roadLinks: 0,
      gatewayRoutes: 0,
    };

    for (const feature of features) {
      const kind = feature.properties?.kind;
      if (kind === "building") {
        const footprintArea = Number(feature.properties.footprintArea || 0);
        const levels = Number(feature.properties.levels || 1);
        summary.buildingCount += 1;
        summary.buildingFootprintArea += footprintArea;
        summary.buildingFloorArea += footprintArea * Math.max(levels, 1);
      } else if (kind === "parking") {
        summary.parkingArea += Number(feature.properties.area || 0);
      } else if (kind === "park") {
        summary.greenArea += Number(feature.properties.area || 0);
      } else if (kind === "road") {
        summary.roadCount += 1;
        const connectionId = String(
          feature.properties.connectionId || `road-${summary.roadCount}`,
        );
        if (!roadConnectionIds.has(connectionId)) {
          roadConnectionIds.add(connectionId);
          if (feature.properties.roadClass === "gateway") {
            summary.gatewayRoutes += 1;
            summary.roadLinks += Number(
              feature.properties.connectionCount || 2,
            );
          } else {
            summary.roadLinks += Number(
              feature.properties.connectionCount || 1,
            );
          }
        }
      }
    }
    return summary;
  }

  function estimateHomesCapacity(featureSummary, settings) {
    if (featureSummary.buildingCount <= 0) {
      return 0;
    }

    const homesPerBlock = clamp(Number(settings.density) || 0, 5, 100);
    const heightAmbition = clamp(Number(settings.height ?? 58) / 100, 0, 1);
    const averageLevels =
      featureSummary.buildingFootprintArea > 0
        ? featureSummary.buildingFloorArea / featureSummary.buildingFootprintArea
        : 1;
    const heightMultiplier = clamp(0.75 + heightAmbition * 1.15, 0.75, 1.9);
    const towerMultiplier = clamp(
      0.85 + Math.log2(Math.max(averageLevels, 1)) / 5,
      0.85,
      2.1,
    );

    return Math.round(
      featureSummary.buildingCount *
        homesPerBlock *
        heightMultiplier *
        towerMultiplier,
    );
  }

  function prepareAnchors(anchors, localPolygon, centroid, settings) {
    const roadFill = clamp((settings.street ?? 35) / 100, 0, 1);
    const maxAnchors =
      roadFill >= 0.995 ? anchors.length : Math.min(anchors.length, 24);
    return anchors.slice(0, maxAnchors).map((anchor, index) => {
      let local = anchor.local;
      if (!pointInPolygonLoose(local, localPolygon, 3)) {
        local = nearestPointOnPolygonBoundary(local, localPolygon).point;
      }
      const outside = anchor.outside;
      const toCenter = normalizeVector({
        x: centroid.x - local.x,
        y: centroid.y - local.y,
      });
      let inward = normalizeVector({
        x: local.x - outside.x,
        y: local.y - outside.y,
      });
      if (!isFinitePoint(inward) || vectorLength(inward) < 0.001) {
        inward = toCenter;
      }
      if (dot(inward, toCenter) < 0) {
        inward = { x: -inward.x, y: -inward.y };
      }
      inward = normalizeVector({
        x: inward.x * 0.78 + toCenter.x * 0.22,
        y: inward.y * 0.78 + toCenter.y * 0.22,
      });
      return {
        ...anchor,
        index,
        local,
        inward,
      };
    });
  }

  function selectAnchorsForRoadFill(anchors, roadFill, centroid) {
    if (!anchors.length || roadFill <= 0) {
      return [];
    }
    const fill = clamp(roadFill, 0, 1);
    const targetCount =
      fill >= 0.995
        ? anchors.length
        : Math.max(1, Math.ceil(anchors.length * fill));
    if (targetCount >= anchors.length) {
      return anchors
        .slice()
        .sort((a, b) => anchorAngle(a, centroid) - anchorAngle(b, centroid));
    }

    const candidates = anchors.map((anchor) => ({
      anchor,
      angle: anchorAngle(anchor, centroid),
    }));
    const selected = [];
    const used = new Set();
    const priorityOrdered = candidates
      .slice()
      .sort((a, b) => a.anchor.priority - b.anchor.priority);

    selected.push(priorityOrdered[0]);
    used.add(priorityOrdered[0].anchor.id);

    while (selected.length < targetCount) {
      let best = null;
      for (const candidate of candidates) {
        if (used.has(candidate.anchor.id)) {
          continue;
        }
        const nearestAngleGap = Math.min(
          ...selected.map((item) =>
            circularAngleDistance(candidate.angle, item.angle),
          ),
        );
        const priorityPenalty = candidate.anchor.priority * 0.42;
        const score = nearestAngleGap - priorityPenalty;
        if (!best || score > best.score) {
          best = { ...candidate, score };
        }
      }
      if (!best) {
        break;
      }
      selected.push(best);
      used.add(best.anchor.id);
    }

    return selected
      .map((item) => item.anchor)
      .sort((a, b) => anchorAngle(a, centroid) - anchorAngle(b, centroid));
  }

  function buildSparseRoadNetwork({
    anchors,
    centroid,
    localPolygon,
    obstacles,
    random,
    frame,
    blockSpacing,
    sampleStep,
    roadFill,
    alignment,
  }) {
    const features = [];
    const localRoadSegments = [];
    const gatewayRoutes = [];
    const usedAnchorIds = new Set();
    let connectorCount = 0;

    if (!anchors.length || roadFill <= 0) {
      return { features, localRoadSegments, gatewayRoutes, connectorCount };
    }

    const pairedRoutes = buildSparseGatewayRoutes({
      anchors,
      centroid,
      random,
      alignment,
      roadFill,
      obstacles,
      localPolygon,
    });
    for (const route of pairedRoutes) {
      const segments = constrainedLineSegments(route.points, {
        localPolygon,
        obstacles,
        allowOutside: true,
        step: sampleStep,
      });
      let rendered = false;
      for (const segment of segments) {
        if (polylineLength(segment) < 30) {
          continue;
        }
        features.push(
          localLineFeature(segment, frame, {
            kind: "road",
            roadClass: "gateway",
            connectorType: "paired-osm-anchors",
            connectionId: route.id,
            connectionCount: route.anchorIds.length,
          }),
        );
        localRoadSegments.push(segment);
        rendered = true;
      }
      if (!rendered) {
        continue;
      }
      gatewayRoutes.push(route);
      for (const anchorId of route.anchorIds) {
        if (!usedAnchorIds.has(anchorId)) {
          usedAnchorIds.add(anchorId);
          connectorCount += 1;
        }
      }
    }

    for (const anchor of anchors) {
      if (usedAnchorIds.has(anchor.id)) {
        continue;
      }
      const target = findConnectorTarget({
        anchor,
        centroid,
        localRoadSegments,
        localPolygon,
        obstacles,
        blockSpacing,
      });
      const path = buildAlignedConnectorPath(
        anchor,
        target,
        centroid,
        random,
        alignment,
        obstacles,
        localPolygon,
      );
      const segments = constrainedLineSegments(path, {
        localPolygon,
        obstacles,
        allowOutside: true,
        step: sampleStep,
      });
      const usableSegments = segments.filter(
        (segment) => polylineLength(segment) > 22,
      );
      if (usableSegments.length > 0) {
        usedAnchorIds.add(anchor.id);
        connectorCount += 1;
      }
      for (const segment of usableSegments) {
        features.push(
          localLineFeature(segment, frame, {
            kind: "road",
            roadClass: "connector",
            connectorType: anchor.source,
            connectionId: anchor.id,
            connectionCount: 1,
            highway: anchor.highway,
          }),
        );
        localRoadSegments.push(segment);
      }
    }

    for (const anchor of anchors) {
      features.push(
        localPointFeature(anchor.local, frame, {
          kind: "anchor",
          anchorType: "boundary",
          highway: anchor.highway,
        }),
      );
      features.push(
        localPointFeature(anchor.outside, frame, {
          kind: "anchor",
          anchorType: "osm-road",
          highway: anchor.highway,
        }),
      );
    }

    return { features, localRoadSegments, gatewayRoutes, connectorCount };
  }

  function buildSparseGatewayRoutes({
    anchors,
    centroid,
    random,
    alignment,
    roadFill,
    obstacles = [],
    localPolygon = [],
  }) {
    const routes = [];
    const used = new Set();
    const routeLimit = Math.round(
      clamp(roadFill * 2.1, roadFill >= 0.55 ? 1 : 0, 2),
    );
    if (routeLimit <= 0) {
      return routes;
    }
    const orderedAnchors = anchors
      .slice()
      .sort(
        (a, b) =>
          a.priority - b.priority ||
          anchorAngle(a, centroid) - anchorAngle(b, centroid),
      );
    const maxRoutes = Math.round(clamp(roadFill * 3, 0, 3));

    for (const anchor of orderedAnchors) {
      if (routes.length >= maxRoutes) {
        break;
      }
      if (routes.length >= routeLimit || used.has(anchor.id)) {
        continue;
      }
      let best = null;
      for (const candidate of orderedAnchors) {
        if (candidate.id === anchor.id || used.has(candidate.id)) {
          continue;
        }
        const angleGap = circularAngleDistance(
          anchorAngle(anchor, centroid),
          anchorAngle(candidate, centroid),
        );
        const oppositePenalty = Math.abs(Math.PI - angleGap);
        const distance = distanceLocal(anchor.local, candidate.local);
        if (distance < 140 && roadFill < 0.86) {
          continue;
        }
        // Never pair anchors that sit on opposite sides of a river/water body: the
        // straight corridor between them would cross water and be split into stubs.
        if (
          obstacles.length > 0 &&
          lineIntersectsAnyPolygon([anchor.local, candidate.local], obstacles)
        ) {
          continue;
        }
        const score =
          oppositePenalty * 2.8 -
          Math.min(distance, 1200) * 0.001 +
          highwayWeight(candidate.highway) * 0.22;
        if (!best || score < best.score) {
          best = { anchor: candidate, score, oppositePenalty };
        }
      }
      if (!best) {
        continue;
      }
      if (best.oppositePenalty > 1.34 && roadFill < 0.82) {
        continue;
      }
      used.add(anchor.id);
      used.add(best.anchor.id);
      routes.push({
        id: `${anchor.id}--${best.anchor.id}`,
        anchorIds: [anchor.id, best.anchor.id],
        points: buildAlignedGatewayPath(
          anchor,
          best.anchor,
          centroid,
          random,
          alignment,
          obstacles,
          localPolygon,
        ),
      });
    }

    return routes;
  }

  function buildAlignedGatewayPath(
    a,
    b,
    centroid,
    random,
    alignment,
    obstacles = [],
    localPolygon = [],
  ) {
    const straightness = clamp(alignment, 0, 1);
    const distance = distanceLocal(a.local, b.local);
    const shoulderLength = Math.min(160, distance * 0.28);
    const aShoulder = {
      x: a.local.x + a.inward.x * shoulderLength,
      y: a.local.y + a.inward.y * shoulderLength,
    };
    const bShoulder = {
      x: b.local.x + b.inward.x * shoulderLength,
      y: b.local.y + b.inward.y * shoulderLength,
    };
    const midpoint = interpolateLocal(a.local, b.local, 0.5);
    const centerBias = clamp(0.12 + (1 - straightness) * 0.42, 0.1, 0.56);
    const core = lerpPoint(midpoint, centroid, centerBias);
    const axis = normalizeVector({
      x: b.local.x - a.local.x,
      y: b.local.y - a.local.y,
    });
    const perpendicular = { x: -axis.y, y: axis.x };
    const wobble = clamp(distance * 0.08 * (1 - straightness), 0, 90);
    const coreOffset = randomRange(random, -wobble, wobble);
    let corePoint = {
      x: core.x + perpendicular.x * coreOffset,
      y: core.y + perpendicular.y * coreOffset,
    };
    // When the zone centroid is over water, the corridor bend can land on the
    // river; pull it back onto dry land so the gateway stays buildable.
    if (obstacles.length > 0 && pointInAnyPolygon(corePoint, obstacles)) {
      corePoint = nearestInteriorPoint(
        corePoint,
        centroid,
        localPolygon,
        obstacles,
      );
    }

    const aPrefix = anchorOutsidePrefix(a);
    const bSuffix = anchorOutsideSuffix(b);

    if (straightness >= 0.78) {
      return [...aPrefix, aShoulder, corePoint, bShoulder, ...bSuffix];
    }

    const bend = wobble * 0.55;
    return [
      ...aPrefix,
      aShoulder,
      {
        x:
          aShoulder.x +
          (corePoint.x - aShoulder.x) * 0.46 +
          perpendicular.x * randomRange(random, -bend, bend),
        y:
          aShoulder.y +
          (corePoint.y - aShoulder.y) * 0.46 +
          perpendicular.y * randomRange(random, -bend, bend),
      },
      corePoint,
      {
        x:
          corePoint.x +
          (bShoulder.x - corePoint.x) * 0.58 +
          perpendicular.x * randomRange(random, -bend, bend),
        y:
          corePoint.y +
          (bShoulder.y - corePoint.y) * 0.58 +
          perpendicular.y * randomRange(random, -bend, bend),
      },
      bShoulder,
      ...bSuffix,
    ];
  }

  // Lead the path in from the real outside road geometry when available, else from
  // the synthetic lead-in. Prefix runs far -> boundary -> inside (anchor.local).
  function anchorOutsidePrefix(anchor) {
    return anchor.outsideTrace?.length
      ? [...anchor.outsideTrace, anchor.outside, anchor.local]
      : [anchor.leadIn, anchor.outside, anchor.local];
  }

  // Mirror of anchorOutsidePrefix for the far end of a gateway: inside -> boundary -> far.
  function anchorOutsideSuffix(anchor) {
    return anchor.outsideTrace?.length
      ? [anchor.local, anchor.outside, ...anchor.outsideTrace.slice().reverse()]
      : [anchor.local, anchor.outside, anchor.leadIn];
  }

  function buildAlignedConnectorPath(
    anchor,
    target,
    centroid,
    random,
    alignment,
    obstacles = [],
    localPolygon = [],
  ) {
    const straightness = clamp(alignment, 0, 1);
    const distance = distanceLocal(anchor.local, target);
    const shoulder = {
      x: anchor.local.x + anchor.inward.x * Math.min(96, distance * 0.36),
      y: anchor.local.y + anchor.inward.y * Math.min(96, distance * 0.36),
    };
    const midpoint = interpolateLocal(anchor.local, target, 0.5);
    const centerBias = clamp((1 - straightness) * 0.24, 0, 0.24);
    const core = lerpPoint(midpoint, centroid, centerBias);
    const axis = normalizeVector({
      x: target.x - anchor.local.x,
      y: target.y - anchor.local.y,
    });
    const perpendicular = { x: -axis.y, y: axis.x };
    const bend = clamp(distance * 0.14 * (1 - straightness), 0, 76);
    let corePoint = {
      x: core.x + perpendicular.x * randomRange(random, -bend, bend),
      y: core.y + perpendicular.y * randomRange(random, -bend, bend),
    };
    if (obstacles.length > 0 && pointInAnyPolygon(corePoint, obstacles)) {
      corePoint = nearestInteriorPoint(
        corePoint,
        centroid,
        localPolygon,
        obstacles,
      );
    }

    const prefix = anchorOutsidePrefix(anchor);

    if (straightness >= 0.82) {
      return [...prefix, shoulder, target];
    }

    return [...prefix, shoulder, corePoint, target];
  }

  function anchorAngle(anchor, centroid) {
    return Math.atan2(anchor.local.y - centroid.y, anchor.local.x - centroid.x);
  }

  function circularAngleDistance(a, b) {
    const difference = Math.abs(a - b) % (Math.PI * 2);
    return difference > Math.PI ? Math.PI * 2 - difference : difference;
  }

  function lerpPoint(a, b, t) {
    return {
      x: a.x + (b.x - a.x) * t,
      y: a.y + (b.y - a.y) * t,
    };
  }

  function findConnectorTarget({
    anchor,
    centroid,
    localRoadSegments,
    localPolygon,
    obstacles,
    blockSpacing,
  }) {
    const pull = clamp(blockSpacing * 1.45, 118, 360);
    const preferred = {
      x: anchor.local.x + anchor.inward.x * pull,
      y: anchor.local.y + anchor.inward.y * pull,
    };
    const snapped = nearestPointOnRoadSegments(preferred, localRoadSegments);
    let target =
      snapped && snapped.distance < pull * 0.92 ? snapped.point : preferred;

    if (!pointAllowedInside(target, localPolygon, obstacles)) {
      const alternatives = [
        rotateVector(anchor.inward, 24 * DEG_TO_RAD),
        rotateVector(anchor.inward, -24 * DEG_TO_RAD),
        rotateVector(anchor.inward, 48 * DEG_TO_RAD),
        rotateVector(anchor.inward, -48 * DEG_TO_RAD),
        normalizeVector({
          x: centroid.x - anchor.local.x,
          y: centroid.y - anchor.local.y,
        }),
      ];
      for (const direction of alternatives) {
        const candidate = {
          x: anchor.local.x + direction.x * pull,
          y: anchor.local.y + direction.y * pull,
        };
        if (pointAllowedInside(candidate, localPolygon, obstacles)) {
          target = candidate;
          break;
        }
      }
    }

    if (!pointInPolygonLoose(target, localPolygon, 4)) {
      return nearestInteriorPoint(
        anchor.local,
        centroid,
        localPolygon,
        obstacles,
      );
    }
    return target;
  }

  function constrainedLineSegments(points, options) {
    const { localPolygon, obstacles, allowOutside, step } = options;
    const effectiveStep =
      obstacles.length > 0 ? Math.min(step || 14, 5) : step || 14;
    const samples = samplePolyline(points, effectiveStep);
    const segments = [];
    let current = [];

    for (const sample of samples) {
      const insideSelection = pointInPolygonLoose(sample, localPolygon, 0.2);
      const withinAllowedExtent = insideSelection || Boolean(allowOutside);
      const sampleAllowed =
        withinAllowedExtent && !pointInAnyPolygon(sample, obstacles);
      const previous = current[current.length - 1];
      const crossesWaterMask =
        Boolean(previous) &&
        segmentIntersectsAnyPolygon(previous, sample, obstacles);

      if (sampleAllowed && !crossesWaterMask) {
        if (!previous || distanceLocal(previous, sample) > 0.35) {
          current.push(sample);
        }
        continue;
      }

      if (current.length >= 2) {
        segments.push(current);
      }
      current = sampleAllowed ? [sample] : [];
    }

    if (current.length >= 2) {
      segments.push(current);
    }
    return segments.filter(
      (segment) => !lineIntersectsAnyPolygon(segment, obstacles),
    );
  }

  function samplePolyline(points, step) {
    const samples = [];
    for (let index = 0; index < points.length - 1; index += 1) {
      const a = points[index];
      const b = points[index + 1];
      const length = distanceLocal(a, b);
      const count = Math.max(2, Math.ceil(length / step));
      for (let i = 0; i <= count; i += 1) {
        if (index > 0 && i === 0) {
          continue;
        }
        samples.push(interpolateLocal(a, b, i / count));
      }
    }
    return samples;
  }

  function generateZoning({
    localPolygon,
    frame,
    localBbox,
    obstacles,
    random,
    settings,
    areaSqm,
    medianBuildingArea,
    anchors,
    blockSpacing,
  }) {
    const features = [];
    let buildingCount = 0;
    let buildingArea = 0;
    let greenArea = 0;
    let parkingArea = 0;
    const density = settings.density / 100;
    const green = settings.green / 100;
    const parking = settings.parking / 100;
    const heightAmbition = settings.height / 100;
    const towerIntensity = clamp((heightAmbition - 0.78) / 0.22, 0, 1);
    const skyscraperIntensity = clamp((heightAmbition - 0.9) / 0.1, 0, 1);
    const baseCell = clamp(
      Math.sqrt(Math.max(120, medianBuildingArea)) * (2.4 - density * 0.6),
      34,
      84,
    );
    const stepX = clamp(baseCell * 2.15, 56, 140);
    const stepY = clamp(baseCell * 1.85, 52, 132);
    const anchorInfluence = anchors.length > 0 ? 0.08 : 0;

    for (
      let y = localBbox.minY + stepY * 0.52;
      y < localBbox.maxY;
      y += stepY
    ) {
      for (
        let x = localBbox.minX + stepX * 0.52;
        x < localBbox.maxX;
        x += stepX
      ) {
        const jittered = {
          x: x + randomRange(random, -stepX * 0.16, stepX * 0.16),
          y: y + randomRange(random, -stepY * 0.16, stepY * 0.16),
        };
        if (!pointAllowedInside(jittered, localPolygon, obstacles)) {
          continue;
        }
        const roll = random();
        const parkChance = clamp(green * 0.48 + anchorInfluence, 0.08, 0.5);
        const parkingChance = clamp(parking * 0.28, 0.02, 0.28);
        const nearWater = pointDistanceToPolygons(jittered, obstacles, 60) < 60;

        if (roll < parkChance || nearWater) {
          const width = randomRange(random, stepX * 0.55, stepX * 1.26);
          const depth = randomRange(random, stepY * 0.55, stepY * 1.18);
          const poly = rectangleAround(
            jittered,
            width,
            depth,
            randomRange(random, -0.35, 0.35),
          );
          if (polygonAllowed(poly, localPolygon, obstacles)) {
            const area = Math.abs(polygonSignedArea(poly));
            greenArea += area;
            features.push(
              localPolygonFeature(poly, frame, { kind: "park", area }),
            );
          }
          continue;
        }

        if (roll < parkChance + parkingChance) {
          const width = randomRange(random, stepX * 0.42, stepX * 0.9);
          const depth = randomRange(random, stepY * 0.34, stepY * 0.72);
          const poly = rectangleAround(
            jittered,
            width,
            depth,
            randomRange(random, -0.25, 0.25),
          );
          if (polygonAllowed(poly, localPolygon, obstacles)) {
            const area = Math.abs(polygonSignedArea(poly));
            parkingArea += area;
            features.push(
              localPolygonFeature(poly, frame, { kind: "parking", area }),
            );
          }
          continue;
        }

        const lots =
          (random() > 0.72 && density > 0.42) ||
          (skyscraperIntensity > 0 && random() < skyscraperIntensity * 0.34)
            ? 2
            : 1;
        for (let lot = 0; lot < lots; lot += 1) {
          const offset = lots === 1 ? 0 : (lot - 0.5) * stepX * 0.34;
          const center = {
            x: jittered.x + offset,
            y: jittered.y + randomRange(random, -8, 8),
          };
          if (!pointAllowedInside(center, localPolygon, obstacles)) {
            continue;
          }
          const isSkyscraper =
            skyscraperIntensity > 0 && random() < 0.76 * skyscraperIntensity;
          const isLandmarkTower =
            isSkyscraper && skyscraperIntensity > 0.86 && random() < 0.16;
          const width = isSkyscraper
            ? randomRange(
                random,
                baseCell * 0.42,
                baseCell * (0.78 + density * 0.18),
              )
            : randomRange(
                random,
                baseCell * 0.72,
                baseCell * (1.35 + density * 0.35),
              );
          const depth = isSkyscraper
            ? randomRange(
                random,
                baseCell * 0.44,
                baseCell * (0.82 + density * 0.18),
              )
            : randomRange(
                random,
                baseCell * 0.7,
                baseCell * (1.26 + density * 0.25),
              );
          const poly = rectangleAround(
            center,
            width,
            depth,
            randomRange(random, -0.22, 0.22),
          );
          if (!polygonAllowed(poly, localPolygon, obstacles)) {
            continue;
          }
          const footprintArea = Math.abs(polygonSignedArea(poly));
          const levels = isLandmarkTower
            ? Math.round(randomRange(random, 86, 124))
            : isSkyscraper
              ? Math.round(
                  clamp(
                    34 +
                      density * 16 +
                      skyscraperIntensity * 44 +
                      randomRange(random, -8, 18),
                    30,
                    96,
                  ),
                )
              : Math.round(
                  clamp(
                    2 +
                      density * 7 +
                      heightAmbition * 14 +
                      towerIntensity * 12 +
                      randomRange(random, -2, 4),
                    2,
                    40,
                  ),
                );
          const height = levels * (isSkyscraper ? 3.45 : 3.25);
          buildingCount += 1;
          buildingArea += footprintArea * levels;
          features.push(
            localPolygonFeature(poly, frame, {
              kind: "building",
              height,
              levels,
              footprintArea,
              role: isLandmarkTower
                ? "landmark-tower"
                : isSkyscraper
                  ? "skyscraper"
                  : "building",
            }),
          );
        }
      }
    }

    const targetGreen = areaSqm * green;
    let extraParks = 0;
    while (greenArea < targetGreen * 0.78 && extraParks < 10) {
      const center = randomPointInPolygon(localPolygon, obstacles, random);
      if (!center) {
        break;
      }
      const radiusX = randomRange(
        random,
        blockSpacing * 0.34,
        blockSpacing * 0.68,
      );
      const radiusY = randomRange(
        random,
        blockSpacing * 0.28,
        blockSpacing * 0.58,
      );
      const park = organicBlob(center, radiusX, radiusY, random);
      if (polygonAllowed(park, localPolygon, obstacles)) {
        const area = Math.abs(polygonSignedArea(park));
        greenArea += area;
        features.push(
          localPolygonFeature(park, frame, {
            kind: "park",
            area,
            role: "target-green",
          }),
        );
      }
      extraParks += 1;
    }

    return { features, buildingCount, buildingArea, greenArea, parkingArea };
  }

  function pointAllowedInside(point, localPolygon, obstacles) {
    return (
      pointInPolygonLoose(point, localPolygon, 0.5) &&
      !pointInAnyPolygon(point, obstacles)
    );
  }

  function polygonAllowed(poly, localPolygon, obstacles) {
    const center = polygonCentroidLocal(poly);
    if (!pointAllowedInside(center, localPolygon, obstacles)) {
      return false;
    }
    let insideCorners = 0;
    for (const point of poly.slice(0, -1)) {
      if (pointAllowedInside(point, localPolygon, obstacles)) {
        insideCorners += 1;
      }
    }
    if (insideCorners < Math.max(3, poly.length - 2)) {
      return false;
    }
    return !polygonIntersectsAnyPolygon(poly, obstacles);
  }

  function estimateWaterAreaInside(obstacles, selectedPolygon, frame) {
    if (obstacles.length === 0) {
      return 0;
    }
    const selectedArea = turfArea(selectedPolygon);
    let area = 0;
    for (const obstacle of obstacles) {
      area += Math.abs(polygonSignedArea(obstacle));
    }
    return Math.min(area, selectedArea * 0.78);
  }

  function updateMetrics(metrics) {
    if (!metrics) {
      emit.onScenario("No scenario yet");
      emit.onMetrics(null);
      emit.onReport(
        "Waiting for a valid polygon. Click four or more points, or use the demo zone.",
      );
      emit.onHint(
        "Click at least four points. Drag vertices to reshape. Plus handles add new points.",
      );
      updatePills(createEmptyContextStats());
      return;
    }
    emit.onScenario(
      state.allowWater ? "Water override scenario" : "Water-protected scenario",
    );
    emit.onMetrics({
      raw: metrics,
      area: formatMetric(metrics.areaHa, 1),
      homes: metrics.homes.toLocaleString(),
      links: metrics.roadLinks.toLocaleString(),
      water:
        metrics.waterInsideHa > 0.05
          ? `${formatMetric(metrics.waterInsideHa, 1)} ha`
          : "0 ha",
      buildings: metrics.generatedBuildings.toLocaleString(),
      parking: metrics.parkingSpaces.toLocaleString(),
    });
    emit.onHint(
      metrics.roadFill === 0
        ? "Road fill is 0: no generated roads. Increase Road fill to connect boundary anchors."
        : metrics.roadLinks > 0
          ? "Connectors start on highlighted existing basemap/OSM roads; each selected anchor is used once."
          : "Move an edge closer to existing streets to create exact OSM road snaps.",
    );
    const waterSentence = metrics.waterProtected
      ? ` Water bodies inside the polygon are hard masks; ${metrics.waterConflictsRemoved} generated feature${metrics.waterConflictsRemoved === 1 ? "" : "s"} touching water were dropped before rendering.`
      : state.allowWater
        ? ` Water override is enabled, so generated zoning may cover rivers or basins.`
        : "";
    const roadSentence =
      metrics.roadFill === 0
        ? "Road fill is 0%, so generated roads are intentionally disabled."
        : `Road fill is ${metrics.roadFill}% and road alignment is ${metrics.roadAlignment}%, so the generator connects ${metrics.roadLinks} selected boundary anchors once instead of filling the whole polygon with a grid.`;
    emit.onReport(
      `The plan generated ${metrics.generatedBuildings} building footprints and ${metrics.parkingSpaces.toLocaleString()} parking spaces. ${roadSentence} It used ${metrics.contextRoads} nearby road geometries and ${metrics.contextWater} water features as context.${waterSentence}`,
    );
  }

  function updatePills(stats) {
    emit.onPills({
      roads: stats.roads.length,
      water: stats.water.length,
      anchors: stats.anchors.length,
    });
  }

  function setStatus(progress, text) {
    emit.onStatus(clamp(progress, 8, 100), text);
  }

  function showToast(text) {
    emit.onToast(text);
  }

  function localLineFeature(points, frame, properties) {
    return {
      type: "Feature",
      properties,
      geometry: {
        type: "LineString",
        coordinates: points.map((point) => localToLngLat(point, frame)),
      },
    };
  }

  function localPointFeature(point, frame, properties) {
    return {
      type: "Feature",
      properties,
      geometry: { type: "Point", coordinates: localToLngLat(point, frame) },
    };
  }

  function localPolygonFeature(points, frame, properties) {
    const ring =
      points[0] && sameLocalPoint(points[0], points[points.length - 1])
        ? points
        : [...points, points[0]];
    return {
      type: "Feature",
      properties,
      geometry: {
        type: "Polygon",
        coordinates: [ring.map((point) => localToLngLat(point, frame))],
      },
    };
  }

  function createLocalFrame(polygon) {
    const center = turfCentroid(polygon).geometry.coordinates;
    return {
      center,
      cosLat: Math.cos(center[1] * DEG_TO_RAD),
    };
  }

  function lngLatToLocal(coord, frame) {
    return {
      x:
        (coord[0] - frame.center[0]) *
        DEG_TO_RAD *
        EARTH_RADIUS_METERS *
        frame.cosLat,
      y: (coord[1] - frame.center[1]) * DEG_TO_RAD * EARTH_RADIUS_METERS,
    };
  }

  function localToLngLat(point, frame) {
    return [
      frame.center[0] +
        (point.x / (EARTH_RADIUS_METERS * frame.cosLat)) * RAD_TO_DEG,
      frame.center[1] + (point.y / EARTH_RADIUS_METERS) * RAD_TO_DEG,
    ];
  }

  function localBounds(points) {
    return points.reduce(
      (bounds, point) => ({
        minX: Math.min(bounds.minX, point.x),
        maxX: Math.max(bounds.maxX, point.x),
        minY: Math.min(bounds.minY, point.y),
        maxY: Math.max(bounds.maxY, point.y),
      }),
      { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity },
    );
  }

  function polygonEdges(points) {
    const edges = [];
    for (let index = 0; index < points.length; index += 1) {
      edges.push({
        a: points[index],
        b: points[(index + 1) % points.length],
        index,
      });
    }
    return edges;
  }

  function segmentIntersection(a, b, c, d) {
    const r = { x: b.x - a.x, y: b.y - a.y };
    const s = { x: d.x - c.x, y: d.y - c.y };
    const denominator = cross(r, s);
    if (Math.abs(denominator) < 1e-9) {
      return null;
    }
    const qMinusP = { x: c.x - a.x, y: c.y - a.y };
    const t = cross(qMinusP, s) / denominator;
    const u = cross(qMinusP, r) / denominator;
    if (t < -1e-7 || t > 1 + 1e-7 || u < -1e-7 || u > 1 + 1e-7) {
      return null;
    }
    return { point: interpolateLocal(a, b, t), t, u };
  }

  function nearestSegmentPair(a, b, c, d) {
    const hit = segmentIntersection(a, b, c, d);
    if (hit) {
      return { onFirst: hit.point, onSecond: hit.point, distance: 0 };
    }
    const candidates = [
      { onFirst: a, onSecond: nearestPointOnSegment(a, c, d) },
      { onFirst: b, onSecond: nearestPointOnSegment(b, c, d) },
      { onFirst: nearestPointOnSegment(c, a, b), onSecond: c },
      { onFirst: nearestPointOnSegment(d, a, b), onSecond: d },
    ];
    let best = null;
    for (const candidate of candidates) {
      const distance = distanceLocal(candidate.onFirst, candidate.onSecond);
      if (!best || distance < best.distance) {
        best = { ...candidate, distance };
      }
    }
    return best;
  }

  function nearestPointOnSegment(point, a, b) {
    const ab = { x: b.x - a.x, y: b.y - a.y };
    const ab2 = ab.x * ab.x + ab.y * ab.y;
    if (ab2 <= 1e-9) {
      return { ...a };
    }
    const t = clamp(
      ((point.x - a.x) * ab.x + (point.y - a.y) * ab.y) / ab2,
      0,
      1,
    );
    return interpolateLocal(a, b, t);
  }

  function nearestPointOnPolygonBoundary(point, polygon) {
    let best = null;
    for (const edge of polygonEdges(polygon)) {
      const candidate = nearestPointOnSegment(point, edge.a, edge.b);
      const distance = distanceLocal(point, candidate);
      if (!best || distance < best.distance) {
        best = { point: candidate, distance, edgeIndex: edge.index };
      }
    }
    return best;
  }

  function nearestPointOnRoadSegments(point, segments) {
    let best = null;
    for (const segment of segments) {
      for (let index = 0; index < segment.length - 1; index += 1) {
        const candidate = nearestPointOnSegment(
          point,
          segment[index],
          segment[index + 1],
        );
        const distance = distanceLocal(point, candidate);
        if (!best || distance < best.distance) {
          best = { point: candidate, distance };
        }
      }
    }
    return best;
  }

  function nearestInteriorPoint(start, centroid, localPolygon, obstacles) {
    const direction = normalizeVector({
      x: centroid.x - start.x,
      y: centroid.y - start.y,
    });
    for (let distance = 32; distance <= 420; distance += 24) {
      const candidate = {
        x: start.x + direction.x * distance,
        y: start.y + direction.y * distance,
      };
      if (pointAllowedInside(candidate, localPolygon, obstacles)) {
        return candidate;
      }
    }
    if (pointAllowedInside(centroid, localPolygon, obstacles)) {
      return centroid;
    }
    return firstDryFallbackPoint(localPolygon, obstacles) || centroid;
  }

  function firstDryFallbackPoint(localPolygon, obstacles) {
    const bounds = localBounds(localPolygon);
    const step = Math.max(
      18,
      Math.min(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY) / 18,
    );
    for (let y = bounds.minY; y <= bounds.maxY; y += step) {
      for (let x = bounds.minX; x <= bounds.maxX; x += step) {
        const candidate = { x, y };
        if (pointAllowedInside(candidate, localPolygon, obstacles)) {
          return candidate;
        }
      }
    }
    return null;
  }

  function pointInPolygon(point, polygon) {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
      const xi = polygon[i].x;
      const yi = polygon[i].y;
      const xj = polygon[j].x;
      const yj = polygon[j].y;
      const intersects =
        yi > point.y !== yj > point.y &&
        point.x < ((xj - xi) * (point.y - yi)) / (yj - yi || 1e-12) + xi;
      if (intersects) {
        inside = !inside;
      }
    }
    return inside;
  }

  function pointInPolygonLoose(point, polygon, toleranceMeters) {
    if (pointInPolygon(point, polygon)) {
      return true;
    }
    if (!toleranceMeters || toleranceMeters <= 0) {
      return false;
    }
    const nearest = nearestPointOnPolygonBoundary(point, polygon);
    return nearest && nearest.distance <= toleranceMeters;
  }

  function ensureObstacleBounds(obstacle) {
    if (!obstacle._bounds) {
      obstacle._bounds = localBounds(obstacle);
    }
    return obstacle._bounds;
  }

  function localBboxesOverlap(a, b, pad = 0) {
    return (
      a.minX - pad <= b.maxX + pad &&
      a.maxX + pad >= b.minX - pad &&
      a.minY - pad <= b.maxY + pad &&
      a.maxY + pad >= b.minY - pad
    );
  }

  function segmentLocalBbox(a, b, pad = 0) {
    return {
      minX: Math.min(a.x, b.x) - pad,
      maxX: Math.max(a.x, b.x) + pad,
      minY: Math.min(a.y, b.y) - pad,
      maxY: Math.max(a.y, b.y) + pad,
    };
  }

  function pointInAnyPolygon(point, polygons) {
    return polygons.some((polygon) => {
      const bounds = ensureObstacleBounds(polygon);
      if (
        point.x < bounds.minX - 0.4 ||
        point.x > bounds.maxX + 0.4 ||
        point.y < bounds.minY - 0.4 ||
        point.y > bounds.maxY + 0.4
      ) {
        return false;
      }
      return pointInPolygonLoose(point, polygon, 0.4);
    });
  }

  function lineIntersectsAnyPolygon(points, polygons) {
    if (polygons.length === 0 || points.length < 2) {
      return false;
    }
    if (points.some((point) => pointInAnyPolygon(point, polygons))) {
      return true;
    }
    for (let index = 0; index < points.length - 1; index += 1) {
      if (
        segmentIntersectsAnyPolygon(points[index], points[index + 1], polygons)
      ) {
        return true;
      }
    }
    return false;
  }

  function segmentIntersectsAnyPolygon(a, b, polygons) {
    const segmentBounds = segmentLocalBbox(a, b, 0.2);
    return polygons.some((polygon) => {
      const bounds = ensureObstacleBounds(polygon);
      if (!localBboxesOverlap(segmentBounds, bounds)) {
        return false;
      }
      return segmentIntersectsPolygon(a, b, polygon);
    });
  }

  function segmentIntersectsPolygon(a, b, polygon) {
    if (
      pointInPolygonLoose(a, polygon, 0.2) ||
      pointInPolygonLoose(b, polygon, 0.2)
    ) {
      return true;
    }
    return polygonEdges(polygon).some((edge) =>
      Boolean(segmentIntersection(a, b, edge.a, edge.b)),
    );
  }

  function polygonIntersectsAnyPolygon(poly, polygons) {
    if (polygons.length === 0 || poly.length === 0) {
      return false;
    }
    const polyBounds = localBounds(poly);
    return polygons.some((obstacle) => {
      const bounds = ensureObstacleBounds(obstacle);
      if (!localBboxesOverlap(polyBounds, bounds)) {
        return false;
      }
      return polygonsIntersect(poly, obstacle);
    });
  }

  function polygonsIntersect(a, b) {
    if (!a.length || !b.length) {
      return false;
    }
    if (
      pointInPolygonLoose(a[0], b, 0.2) ||
      pointInPolygonLoose(b[0], a, 0.2)
    ) {
      return true;
    }
    const edgesA = polygonEdges(a);
    const edgesB = polygonEdges(b);
    for (const edgeA of edgesA) {
      for (const edgeB of edgesB) {
        if (segmentIntersection(edgeA.a, edgeA.b, edgeB.a, edgeB.b)) {
          return true;
        }
      }
    }
    return false;
  }

  function pointDistanceToBoundsLowerBound(point, bounds) {
    const dx = Math.max(bounds.minX - point.x, 0, point.x - bounds.maxX);
    const dy = Math.max(bounds.minY - point.y, 0, point.y - bounds.maxY);
    return Math.hypot(dx, dy);
  }

  // `maxDistance` lets callers that only care about proximity (e.g. "is this within
  // 60 m of water?") cap the search so far-away obstacles are rejected by a cheap
  // bbox test before the O(edges) boundary scan. The bbox distance is always a
  // lower bound on the true boundary distance, so skipping never changes results.
  function pointDistanceToPolygons(point, polygons, maxDistance = Infinity) {
    if (polygons.length === 0) {
      return Infinity;
    }
    let best = maxDistance;
    for (const polygon of polygons) {
      const bounds = ensureObstacleBounds(polygon);
      if (pointDistanceToBoundsLowerBound(point, bounds) >= best) {
        continue;
      }
      const nearest = nearestPointOnPolygonBoundary(point, polygon);
      if (nearest && nearest.distance < best) {
        best = nearest.distance;
      }
    }
    return best;
  }

  function polygonCentroidLocal(points) {
    let area = 0;
    let cx = 0;
    let cy = 0;
    for (let i = 0, j = points.length - 1; i < points.length; j = i, i += 1) {
      const a = points[j];
      const b = points[i];
      const crossValue = a.x * b.y - b.x * a.y;
      area += crossValue;
      cx += (a.x + b.x) * crossValue;
      cy += (a.y + b.y) * crossValue;
    }
    area *= 0.5;
    if (Math.abs(area) < 1e-9) {
      const bounds = localBounds(points);
      return {
        x: (bounds.minX + bounds.maxX) / 2,
        y: (bounds.minY + bounds.maxY) / 2,
      };
    }
    return { x: cx / (6 * area), y: cy / (6 * area) };
  }

  function polygonSignedArea(points) {
    let area = 0;
    for (let i = 0; i < points.length; i += 1) {
      const a = points[i];
      const b = points[(i + 1) % points.length];
      area += a.x * b.y - b.x * a.y;
    }
    return area / 2;
  }

  function rectangleAround(center, width, height, angle) {
    const halfW = width / 2;
    const halfH = height / 2;
    const corners = [
      { x: -halfW, y: -halfH },
      { x: halfW, y: -halfH },
      { x: halfW, y: halfH },
      { x: -halfW, y: halfH },
    ].map((point) => ({
      x: center.x + point.x * Math.cos(angle) - point.y * Math.sin(angle),
      y: center.y + point.x * Math.sin(angle) + point.y * Math.cos(angle),
    }));
    corners.push(corners[0]);
    return corners;
  }

  function organicBlob(center, radiusX, radiusY, random) {
    const points = [];
    const count = 10;
    const angleOffset = randomRange(random, -0.35, 0.35);
    for (let index = 0; index < count; index += 1) {
      const angle = angleOffset + (Math.PI * 2 * index) / count;
      const scale = randomRange(random, 0.72, 1.14);
      points.push({
        x: center.x + Math.cos(angle) * radiusX * scale,
        y: center.y + Math.sin(angle) * radiusY * scale,
      });
    }
    points.push(points[0]);
    return points;
  }

  function randomPointInPolygon(localPolygon, obstacles, random) {
    const bounds = localBounds(localPolygon);
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const point = {
        x: randomRange(random, bounds.minX, bounds.maxX),
        y: randomRange(random, bounds.minY, bounds.maxY),
      };
      if (pointAllowedInside(point, localPolygon, obstacles)) {
        return point;
      }
    }
    return null;
  }

  function sameCoord(a, b) {
    return Math.abs(a[0] - b[0]) < 1e-10 && Math.abs(a[1] - b[1]) < 1e-10;
  }

  function sameLocalPoint(a, b) {
    return Math.abs(a.x - b.x) < 1e-6 && Math.abs(a.y - b.y) < 1e-6;
  }

  function expandBbox(bbox, amount) {
    return [
      bbox[0] - amount,
      bbox[1] - amount,
      bbox[2] + amount,
      bbox[3] + amount,
    ];
  }

  function interpolateLocal(a, b, t) {
    return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
  }

  function distanceLocal(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  function polylineLength(points) {
    let length = 0;
    for (let index = 0; index < points.length - 1; index += 1) {
      length += distanceLocal(points[index], points[index + 1]);
    }
    return length;
  }

  function vectorLength(vector) {
    return Math.hypot(vector.x, vector.y);
  }

  function normalizeVector(vector) {
    const length = vectorLength(vector);
    if (!Number.isFinite(length) || length < 1e-9) {
      return { x: 0, y: 0 };
    }
    return { x: vector.x / length, y: vector.y / length };
  }

  function moveAwayFromCentroid(point, centroid, distance) {
    const direction = normalizeVector({
      x: point.x - centroid.x,
      y: point.y - centroid.y,
    });
    return {
      x: point.x + direction.x * distance,
      y: point.y + direction.y * distance,
    };
  }

  function rotateVector(vector, angle) {
    return {
      x: vector.x * Math.cos(angle) - vector.y * Math.sin(angle),
      y: vector.x * Math.sin(angle) + vector.y * Math.cos(angle),
    };
  }

  function cross(a, b) {
    return a.x * b.y - a.y * b.x;
  }

  function dot(a, b) {
    return a.x * b.x + a.y * b.y;
  }

  function isFinitePoint(point) {
    return point && Number.isFinite(point.x) && Number.isFinite(point.y);
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function randomRange(random, min, max) {
    return min + (max - min) * random();
  }

  function seededRandom(seed) {
    let value = seed >>> 0;
    return () => {
      value += 0x6d2b79f5;
      let t = value;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function hashString(text) {
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  function formatMetric(value, digits = 0) {
    return Number(value).toLocaleString(undefined, {
      maximumFractionDigits: digits,
      minimumFractionDigits: digits,
    });
  }

  function destroy() {
    stopAutoOrbit();
    if (state.generationRaf !== null) {
      cancelAnimationFrame(state.generationRaf);
    }
    window.clearTimeout(state.contextTimer);
    window.clearTimeout(state.toastTimer);
    window.clearTimeout(state.populationTimer);
    window.clearTimeout(state.impactTimer);
    state.contextFetchController?.abort();
    state.populationController?.abort();
    state.impactController?.abort();
    for (const marker of state.vertexMarkers) {
      marker.remove();
    }
    for (const marker of state.midpointMarkers) {
      marker.remove();
    }
    map.remove();
  }

  return {
    setSetting,
    setTheme,
    setAllowWater,
    loadDemo: () => loadDemoZone(true),
    autoZone: loadAutoZone,
    flyToLondonOverview,
    pickAutoImprovementZone,
    waitForPlanRender,
    startAutoOrbit,
    stopAutoOrbit,
    clearZone,
    undo: undoVertex,
    fit: fitToZone,
    destroy,
  };
}
