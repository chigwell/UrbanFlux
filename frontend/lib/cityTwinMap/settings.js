export function cityTwinSettingsToReplanningParams(settings) {
  return {
    housing_density: Math.round(settings.density),
    green_space_target: Math.round(settings.green),
    parking_pressure: Math.round(settings.parking),
    road_fill: Math.round(settings.street),
    road_alignment: Math.round(settings.alignment),
    height_ambition: Math.round(settings.height),
  };
}
