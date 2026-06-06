import type { CityTwinSettingKey, CityTwinSettings } from "@/lib/cityTwinMap";

export const DEFAULT_SETTINGS: CityTwinSettings = {
  density: 64,
  green: 35,
  parking: 18,
  street: 35,
  alignment: 72,
  height: 58,
};

export const AUTO_TIMING = {
  londonOverviewMs: 1600,
  pauseAfterOverviewMs: 450,
  vertexRevealMs: 900,
  fitToZoneMs: 1200,
  waitForInitialPlanTimeoutMs: 12000,
  parameterStepMs: 320,
  waitForImprovedPlanTimeoutMs: 8000,
  orbitMoveMs: 8500,
};

export const SETTING_CONTROLS: {
  key: CityTwinSettingKey;
  label: string;
  min: number;
  max: number;
  hint: string;
}[] = [
  {
    key: "density",
    label: "Housing density",
    min: 5,
    max: 100,
    hint: "Homes per built block",
  },
  {
    key: "green",
    label: "Green space target",
    min: 5,
    max: 80,
    hint: "Share reserved as parks",
  },
  {
    key: "parking",
    label: "Parking pressure",
    min: 0,
    max: 80,
    hint: "Surface parking demand",
  },
  {
    key: "street",
    label: "Road fill",
    min: 0,
    max: 100,
    hint: "Boundary anchors connected",
  },
  {
    key: "alignment",
    label: "Road alignment",
    min: 0,
    max: 100,
    hint: "How straight corridors run",
  },
  {
    key: "height",
    label: "Height ambition",
    min: 0,
    max: 100,
    hint: "Massing of tall buildings",
  },
];

const SETTING_LIMITS = Object.fromEntries(
  SETTING_CONTROLS.map(({ key, min, max }) => [key, { min, max }]),
) as Record<CityTwinSettingKey, { min: number; max: number }>;

const randomInt = (min: number, max: number) =>
  Math.floor(min + Math.random() * (max - min + 1));

export const clampSetting = (key: CityTwinSettingKey, value: number) => {
  const limit = SETTING_LIMITS[key];
  return Math.max(limit.min, Math.min(limit.max, value));
};

export const buildRandomGreenerSettings = (
  current: CityTwinSettings,
): CityTwinSettings => ({
  density: clampSetting("density", randomInt(58, 88)),
  green: clampSetting(
    "green",
    Math.max(current.green + randomInt(18, 32), randomInt(62, 78)),
  ),
  parking: clampSetting("parking", randomInt(4, 16)),
  street: clampSetting("street", randomInt(46, 74)),
  alignment: clampSetting("alignment", randomInt(54, 86)),
  height: clampSetting("height", randomInt(48, 82)),
});
