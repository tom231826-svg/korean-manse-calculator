# Test Plan v0.8

## 필수 검증 명령

```bash
python3 scripts/validate_caches.py --start-year 1950 --end-year 2030
bash tests/smoke_test.sh
```

## 데이터 검증

- 일진: 1950~2030 전체 29,585일 존재.
- 일진: JDN fallback 비교 mismatch 0.
- 절기 reference: 81개 연도 파일 존재.
- 절기 reference: 각 연도 24개 절기 존재.
- 절기 cache: 1,944 entries 존재.
- 절기: `name`과 `sunLongitude` 불일치 없음. 불일치 시 황경 fallback으로 정규화.
- source: `kasi` 또는 `skyfield_de421` 계열이어야 함.
- 음력 변환 cache: 1950-01-01~2030-12-31 양력 날짜 29,585일이 음력 key로 역인덱싱되어야 함.

## Ground truth 케이스

| ID | 입력 | 기대 |
|---|---|---|
| T01_reference_A | 1990-01-01 23:30 | 己巳 / 丙子 / 丙寅 / 己亥 |
| T02_reference_B | 1990-01-02 00:30 | 己巳 / 丙子 / 丁卯 / 庚子 |
| T03_junseok | 2001-11-19 12:00 | 辛巳 / 己亥 / 丙戌 / 甲午 |
| T04_skyfield | 1995-05-15 14:30 | 乙亥 / 辛巳 / 丙午 / 乙未 |
| T05_ipchun_before | 2024-02-04 16:00 | 癸卯 / 乙丑 / 戊戌 / 庚申 |
| T06_ipchun_after | 2024-02-04 18:00 | 甲辰 / 丙寅 / 戊戌 / 辛酉 |
| T10_old_skyfield | 1965-07-07 16:00 | 乙巳 / 壬午 / 壬戌 / 戊申 |

## 자시/일주 정책 검증

- `1990-01-02 00:30`은 -32분 보정 후 전날 23:58이지만 일주는 입력일 `1990-01-02`의 丁卯를 유지해야 한다.
- `2020-12-25 23:40`은 보정 후 子시이지만 다음날 일주로 넘기지 않는다.

## 시간 미상

시간 미상은 00:00으로 가정하지 않는다.

- `basis_time_kst = null`
- `pillars.hour = null`
- `warnings`에 `hour_unknown` 포함

## 에러 케이스

- `calendar`가 `solar|lunar` 외 값: `unsupported_calendar`
- 평달/윤달 후보가 모두 있는데 `lunar_leap=auto`: `ambiguous_lunar_date`
- cache에 없는 음력 날짜: `invalid_lunar_date`
- 음력 변환 cache 파일 누락: `lunar_conversion_missing`
- 1949 이하 또는 2031 이상: `year_out_of_range`
