# Changelog

All notable public changes to this project are documented here.

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
