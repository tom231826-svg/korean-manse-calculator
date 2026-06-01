# Changelog

All notable public changes to this project are documented here.

## v0.8.0 - 2026-06-01

Adds Korean lunar calendar and leap-month input support while preserving the existing solar-date calculation engine.

### Added

- `--calendar lunar` input support.
- `--lunar-leap auto|true|false`, with `auto` as the default.
- Offline `data/lunar_to_solar_by_year/{YYYY}.json` conversion cache.
- `calendar_data` fields for original lunar input, selected leap-month flag, and converted solar date.
- KASI `LrsrCldInfoService/getLunCalInfo` regeneration path via `scripts/build_kasi_cache.py --include-lunar-conversion`.

### Validation

- Existing solar smoke tests remain unchanged in expected pillar results.
- Added smoke tests for regular lunar dates, leap-month dates, `auto` selection, ambiguous leap-month dates, invalid lunar dates, and missing conversion cache.
- Cache validation now checks that lunar conversion data reverse-indexes all 29,585 solar dates from 1950-01-01 through 2030-12-31.

### Data

- Bundled lunar conversion cache is generated from `korean-lunar-calendar` 0.3.1, an MIT-licensed offline package that states it follows KARI/KASI Korean lunar calendar data.
- KASI/data.go.kr remains the preferred source for official lunar cache regeneration when a valid `KASI_LRSR_SERVICE_KEY` is available.

### Limitations

- Runtime lunar conversion is cache-only; the calculator does not call KASI APIs during normal calculation.
- `--lunar-leap auto` returns `ambiguous_lunar_date` when both regular and leap-month candidates exist.
- Korea/Seoul default only; overseas birth and user-provided birthplace correction are not supported.

## v0.7.0 - 2026-06-01

Initial public release.

### Added

- Deterministic Korean manse / Four Pillars calculation engine for solar birth dates.
- CLI output in JSON and Markdown formats.
- JSON output schema for downstream agent or application integration.
- GitHub Actions CI workflow for validation and smoke tests.
- Example JSON output in `examples/sample-output.json`.

### Validation

- Validation for 29,585 day ganzhi entries from 1950-01-01 through 2030-12-31.
- Validation for 1,944 solar-term reference entries from 1950 through 2030.
- Smoke tests for late-night `子` hour handling, unknown birth time, old Skyfield-backed dates, unsupported lunar input, and out-of-range years.

### Data

- Bundled day ganzhi lookup data for 1950-2030.
- Bundled 24 solar-term references and runtime cache for 1950-2030.
- KASI / data.go.kr regeneration path for 2000-2027 solar terms.
- Skyfield / NASA JPL DE421 methodology for 1950-1999 and 2028-2030 solar terms.

### Limitations

- Solar-date input only.
- Korea/Seoul default only; overseas birth and user-provided birthplace correction are not supported.
- Lunar calendar and leap-month conversion are not supported.
- Apparent solar time, true solar time, and equation-of-time correction are not applied.
