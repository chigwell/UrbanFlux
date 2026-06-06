THEMES = {
    "planning_land",
    "housing",
    "socioeconomic",
    "health",
    "environment",
    "transport",
    "safety",
    "demographics",
    "other",
}

METADATA_TEXT_SQL = (
    "lower(coalesce(ds.title,'') || ' ' || coalesce(cf.title,'') || ' ' || "
    "coalesce(ds.description,'') || ' ' || coalesce(cf.description,''))"
)

THEME_CASE_SQL = f"""
CASE
  WHEN {METADATA_TEXT_SQL} LIKE '%brownfield%'
    OR {METADATA_TEXT_SQL} LIKE '%land use%'
    OR {METADATA_TEXT_SQL} LIKE '%planning%'
    OR {METADATA_TEXT_SQL} LIKE '%development%'
    OR {METADATA_TEXT_SQL} LIKE '%industrial%'
    OR {METADATA_TEXT_SQL} LIKE '%opportunity area%'
    OR {METADATA_TEXT_SQL} LIKE '%land assets%'
    THEN 'planning_land'
  WHEN {METADATA_TEXT_SQL} LIKE '%crime%'
    OR {METADATA_TEXT_SQL} LIKE '%police%'
    OR {METADATA_TEXT_SQL} LIKE '%collision%'
    OR {METADATA_TEXT_SQL} LIKE '%fire brigade%'
    OR {METADATA_TEXT_SQL} LIKE '%incidents attended%'
    THEN 'safety'
  WHEN {METADATA_TEXT_SQL} LIKE '%transport%'
    OR {METADATA_TEXT_SQL} LIKE '%commuting%'
    OR {METADATA_TEXT_SQL} LIKE '%cycle%'
    OR {METADATA_TEXT_SQL} LIKE '%bus%'
    OR {METADATA_TEXT_SQL} LIKE '%underground%'
    OR {METADATA_TEXT_SQL} LIKE '%ptal%'
    OR {METADATA_TEXT_SQL} LIKE '%public transport accessibility%'
    THEN 'transport'
  WHEN {METADATA_TEXT_SQL} LIKE '%pollution%'
    OR {METADATA_TEXT_SQL} LIKE '%environment%'
    OR {METADATA_TEXT_SQL} LIKE '%footprint%'
    OR {METADATA_TEXT_SQL} LIKE '%flood%'
    OR {METADATA_TEXT_SQL} LIKE '%waste%'
    OR {METADATA_TEXT_SQL} LIKE '%pm2.5%'
    THEN 'environment'
  WHEN {METADATA_TEXT_SQL} LIKE '%health%'
    OR {METADATA_TEXT_SQL} LIKE '%life expectancy%'
    OR {METADATA_TEXT_SQL} LIKE '%mental%'
    OR {METADATA_TEXT_SQL} LIKE '%fertility%'
    OR {METADATA_TEXT_SQL} LIKE '%blind%'
    OR {METADATA_TEXT_SQL} LIKE '%deaf%'
    OR {METADATA_TEXT_SQL} LIKE '%birth%'
    OR {METADATA_TEXT_SQL} LIKE '%death rate%'
    THEN 'health'
  WHEN {METADATA_TEXT_SQL} LIKE '%empty home%'
    OR {METADATA_TEXT_SQL} LIKE '%dwelling%'
    OR {METADATA_TEXT_SQL} LIKE '%house price%'
    OR {METADATA_TEXT_SQL} LIKE '%house prices%'
    OR {METADATA_TEXT_SQL} LIKE '%property price%'
    OR {METADATA_TEXT_SQL} LIKE '%affordable housing%'
    OR {METADATA_TEXT_SQL} LIKE '%housing%'
    OR {METADATA_TEXT_SQL} LIKE '%tenure%'
    OR {METADATA_TEXT_SQL} LIKE '%council tax%'
    THEN 'housing'
  WHEN {METADATA_TEXT_SQL} LIKE '%deprivation%'
    OR {METADATA_TEXT_SQL} LIKE '%income%'
    OR {METADATA_TEXT_SQL} LIKE '%employment%'
    OR {METADATA_TEXT_SQL} LIKE '%jobs%'
    OR {METADATA_TEXT_SQL} LIKE '%economic%'
    OR {METADATA_TEXT_SQL} LIKE '%qualification%'
    OR {METADATA_TEXT_SQL} LIKE '%poverty%'
    THEN 'socioeconomic'
  WHEN {METADATA_TEXT_SQL} LIKE '%population%'
    OR {METADATA_TEXT_SQL} LIKE '%census%'
    OR {METADATA_TEXT_SQL} LIKE '%ethnic%'
    OR {METADATA_TEXT_SQL} LIKE '% age %'
    OR {METADATA_TEXT_SQL} LIKE '%age-specific%'
    OR {METADATA_TEXT_SQL} LIKE '%age group%'
    OR {METADATA_TEXT_SQL} LIKE '%age structure%'
    OR {METADATA_TEXT_SQL} LIKE '%single year of age%'
    OR {METADATA_TEXT_SQL} LIKE '%religion%'
    OR {METADATA_TEXT_SQL} LIKE '%migration%'
    THEN 'demographics'
  ELSE 'other'
END
"""
