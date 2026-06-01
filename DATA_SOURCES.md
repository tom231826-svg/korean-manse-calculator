# Data Sources

This repository includes generated reference/cache files for Korean manse calculation over 1950-2030.

## KASI / Data.go.kr

For 2000-2027 solar-term references, the generation workflow can use the Korea Astronomy and Space Science Institute public data APIs exposed through data.go.kr:

- `SpcdeInfoService/get24DivisionsInfo` for 24 solar terms
- `LrsrCldInfoService/getLunCalInfo` for day-ganzhi fallback and lunar-to-solar conversion cache regeneration

API keys are not included in this repository. Use local environment variables when regenerating data.

## Lunar Conversion Cache

Runtime lunar input uses bundled offline files under `data/lunar_to_solar_by_year/`.

- Cache key: `YYYY-MM-DD:regular` or `YYYY-MM-DD:leap`
- Cache value: converted solar date in `YYYY-MM-DD`
- Runtime behavior: lunar input is converted first, then the existing solar-date calculation engine is reused

The preferred regeneration source is KASI / data.go.kr `LrsrCldInfoService/getLunCalInfo`:

```bash
KASI_LRSR_SERVICE_KEY="<your-data-go-kr-service-key>" \
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --from-bundled-references --include-lunar-conversion
```

The current bundled v0.8 lunar conversion cache was generated from the MIT-licensed `korean-lunar-calendar` package, which states that it follows KARI/KASI Korean lunar calendar data and works offline. This was used because no valid KASI Lrsr API key is committed or available in the public repository. Regenerate with KASI before treating a new cache build as an official upstream refresh.

## Skyfield / NASA JPL DE421

For years outside the KASI direct range, the reference workflow uses Skyfield with NASA JPL DE421 ephemeris data. Downloaded ephemeris files are not committed.

## Notes

The bundled data is intended to make calculation reproducible without requiring live API access. If you regenerate or redistribute derived datasets, review the applicable KASI/data.go.kr, NASA/JPL, and third-party package license terms for your use case.
