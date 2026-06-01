# Data Sources

This repository includes generated reference/cache files for Korean manse calculation over 1950-2030.

## KASI / Data.go.kr

For 2000-2027 solar-term references, the generation workflow can use the Korea Astronomy and Space Science Institute public data APIs exposed through data.go.kr:

- `SpcdeInfoService/get24DivisionsInfo` for 24 solar terms
- `LrsrCldInfoService/getLunCalInfo` as an optional day-ganzhi fallback

API keys are not included in this repository. Use local environment variables when regenerating data.

## Skyfield / NASA JPL DE421

For years outside the KASI direct range, the reference workflow uses Skyfield with NASA JPL DE421 ephemeris data. Downloaded ephemeris files are not committed.

## Notes

The bundled data is intended to make calculation reproducible without requiring live API access. If you regenerate or redistribute derived datasets, review the applicable KASI/data.go.kr and NASA/JPL data terms for your use case.
