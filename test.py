from backend.data_sources import get_borough_data, get_borough_summary, resolve_borough

lat = 51.5074
lon = -0.1278

borough = resolve_borough(lat, lon)
summary = get_borough_summary(lat, lon)
housing = get_borough_data(lat, lon, theme="housing", limit=10)


print(f"Borough: {borough['name'] if borough else None}")
print(f"Summary: {summary}")
print(f"Housing data: {housing}")