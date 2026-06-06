// Type surface for the vanilla CityTwin engine (lib/cityTwinMap.js).
// The engine owns MapLibre + geometry/generation; React drives it through this
// bridge: callbacks for every output, a handle for every input.

export type CityTwinTheme = "light" | "dark";

export type CityTwinSettingKey =
  | "density"
  | "green"
  | "parking"
  | "street"
  | "alignment"
  | "height";

export type CityTwinSettings = Record<CityTwinSettingKey, number>;

export type AutoImprovementMode =
  | "idle"
  | "overview"
  | "selecting"
  | "waiting-initial-plan"
  | "tuning"
  | "waiting-improved-plan"
  | "orbiting";

export interface AutoImprovementZoneOptions {
  signal?: AbortSignal;
  reveal?: boolean;
}

export interface WaitForPlanOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  minGeneratedFeatures?: number;
}

export interface ReplanningParams {
  housing_density: number;
  green_space_target: number;
  parking_pressure: number;
  road_fill: number;
  road_alignment: number;
  height_ambition: number;
}

/** Raw, unformatted metrics computed for the current scenario. */
export interface CityTwinRawMetrics {
  areaHa: number;
  homes: number;
  roadLinks: number;
  waterInsideHa: number;
  generatedBuildings: number;
  parkingSpaces: number;
  roadFill: number;
  roadAlignment: number;
  contextRoads: number;
  contextWater: number;
  waterProtected: boolean;
  waterConflictsRemoved: number;
}

/** Display-ready metric strings (already localized/rounded by the engine). */
export interface CityTwinMetrics {
  raw: CityTwinRawMetrics;
  area: string;
  homes: string;
  links: string;
  water: string;
  buildings: string;
  parking: string;
}

export interface CityTwinPills {
  roads: number;
  water: number;
  anchors: number;
}

/** Approximate population for the selected area, fetched from the backend. */
export interface CityTwinPopulation {
  status: "loading" | "ready" | "error";
  /** Raw endpoint count. Present when `status` is "ready". */
  approximatePopulation?: number;
  /** Formatted count, e.g. "12,480". Present when `status` is "ready". */
  population?: string;
  lsoaCount?: number;
  areaKm2?: number;
  note?: string;
}

/** A single replanning impact metric returned by the backend `/impact` endpoint. */
export interface CityTwinImpactMetric {
  metric: string;
  value: string;
  delta: string;
  /** Primary London Datastore dataset/resource URL, or empty when unavailable. */
  source: string;
  /** Optional external methodology URL, e.g. TfL or WHO. */
  methodologySource?: string;
  /** Short explanation of the data/method basis for the estimate. */
  basis?: string;
}

/** Replanning impact for the selected area + chosen params, from the backend. */
export interface CityTwinImpact {
  status: "loading" | "ready" | "error";
  metrics?: CityTwinImpactMetric[];
  note?: string;
}

export interface CityTwinOptions {
  /** Element id string or the element itself for the MapLibre container. */
  container: string | HTMLElement;
  initialTheme?: CityTwinTheme;
  initialAllowWater?: boolean;
  initialSettings?: Partial<CityTwinSettings>;
  /** Progress bar value (0-100) + status line text. */
  onStatus?: (progress: number, text: string) => void;
  /** Metric tiles; `null` clears them to em dashes. */
  onMetrics?: (metrics: CityTwinMetrics | null) => void;
  /** Scenario subtitle label. */
  onScenario?: (label: string) => void;
  /** Planning report paragraph. */
  onReport?: (text: string) => void;
  /** Contextual map hint line. */
  onHint?: (text: string) => void;
  /** Live context counts (existing roads / water masks / boundary anchors). */
  onPills?: (pills: CityTwinPills) => void;
  /** Approximate population for the selected area; `null` clears it. */
  onPopulation?: (population: CityTwinPopulation | null) => void;
  /** Replanning impact metrics for the selected area + params; `null` clears them. */
  onImpact?: (impact: CityTwinImpact | null) => void;
  /** Transient toast message. */
  onToast?: (text: string) => void;
  /** Fired when direct map/marker/camera input should cancel guided auto mode. */
  onAutoInterrupted?: () => void;
}

export interface CityTwinHandle {
  setSetting: (key: CityTwinSettingKey, value: number) => void;
  setTheme: (theme: CityTwinTheme) => void;
  setAllowWater: (on: boolean) => void;
  loadDemo: () => void;
  /** Compatibility alias for the previous random zone picker. */
  autoZone: () => void;
  flyToLondonOverview: (options?: { signal?: AbortSignal }) => Promise<void>;
  pickAutoImprovementZone: (
    options?: AutoImprovementZoneOptions,
  ) => Promise<void>;
  waitForPlanRender: (options?: WaitForPlanOptions) => Promise<boolean>;
  startAutoOrbit: (options?: { signal?: AbortSignal }) => void;
  stopAutoOrbit: () => void;
  clearZone: () => void;
  undo: () => void;
  fit: () => void;
  destroy: () => void;
}

export function cityTwinSettingsToReplanningParams(settings: CityTwinSettings): ReplanningParams;

export function initCityTwinMap(options: CityTwinOptions): CityTwinHandle;
