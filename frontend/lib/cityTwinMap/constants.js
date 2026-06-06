export const EMPTY = { type: "FeatureCollection", features: [] };
export const LONDON_CENTER = [-0.1276, 51.5072];
export const AUTO_IMPROVEMENT_CENTER_BBOX = [-0.22, 51.475, -0.035, 51.535];
export const AUTO_IMPROVEMENT_OVERVIEW_CAMERA = {
  center: LONDON_CENTER,
  zoom: 10.65,
  pitch: 48,
  bearing: -12,
  duration: 1600,
};
export const AUTO_IMPROVEMENT_FIT_MAX_ZOOM = 14.65;
export const AUTO_ORBIT_ZOOM_MIN = 12.75;
export const AUTO_ORBIT_ZOOM_MAX = 14.15;
export const AUTO_ORBIT_DURATION_MS = 8500;

// Coarse Greater London administrative outline (lng/lat), kept slightly inside
// the real GLA boundary so auto-picked zones never spill into the home counties
// or the sea. Used to constrain the "Auto" zone picker.
export const GREATER_LONDON_RING = [
  [-0.3, 51.66],
  [-0.07, 51.69],
  [0.04, 51.66],
  [0.28, 51.6],
  [0.3, 51.53],
  [0.17, 51.46],
  [0.06, 51.31],
  [-0.06, 51.3],
  [-0.2, 51.33],
  [-0.31, 51.36],
  [-0.45, 51.45],
  [-0.51, 51.51],
  [-0.48, 51.6],
  [-0.3, 51.66],
];

export const MAP_STYLES = {
  dark: "https://tiles.openfreemap.org/styles/dark",
  light: "https://tiles.openfreemap.org/styles/positron",
};

export const OVERPASS_ENDPOINTS = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.private.coffee/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
];

export const EARTH_RADIUS_METERS = 6371008.8;
export const DEG_TO_RAD = Math.PI / 180;
export const RAD_TO_DEG = 180 / Math.PI;

export const CONNECTABLE_HIGHWAYS = new Set([
  "primary",
  "primary_link",
  "secondary",
  "secondary_link",
  "tertiary",
  "tertiary_link",
  "unclassified",
  "residential",
  "living_street",
  "service",
  "pedestrian",
]);

export const VECTOR_CONTEXT_SOURCE_LAYERS = {
  road: ["transportation", "transportation_name", "roads", "road"],
  water: ["water", "waterway", "physical_line"],
  building: ["building", "buildings"],
  park: ["park", "landcover", "landuse", "landuse_p", "physical_point"],
};

export const CUSTOM_LAYER_PREFIXES = [
  "selection-",
  "context-",
  "generated-",
  "anchor-",
];

export const MIN_POLYGON_VERTICES = 4;
export const WATER_POLYGON_EXCLUSION_KM = 0.038;
export const WATER_RIVER_LINE_EXCLUSION_KM = 0.15;
export const WATER_CANAL_LINE_EXCLUSION_KM = 0.08;
export const WATER_MINOR_LINE_EXCLUSION_KM = 0.05;
export const WATER_DEFAULT_LINE_EXCLUSION_KM = 0.075;
export const MAX_WATER_OBSTACLES = 400;
export const CONTEXT_CACHE_MAX = 8;
export const OVERPASS_COOLDOWN_MS = 90_000;
export const OVERPASS_BBOX_CACHE_MAX = 12;
export const CONTEXT_FETCH_DEBOUNCE_MS = 520;

// Per-kind caps for fetched context. A single flat cap let dense road counts
// (tens of thousands in central London) starve water/building/park down to zero,
// which removed the river masks and let the plan build over the Thames.
export const CONTEXT_KIND_BUDGETS = {
  road: 1200,
  water: 500,
  building: 600,
  park: 250,
};

export const WATER_CONTEXT_READY_STATES = new Set(["vector", "osm", "partial"]);

// Backend that estimates population for the selected polygon. Overridable at
// build time (NEXT_PUBLIC_* is inlined by Next, even with output: "export").
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "https://api.urbanflux.london";

export const POPULATION_FETCH_DEBOUNCE_MS = 600;
export const IMPACT_FETCH_DEBOUNCE_MS = 600;
