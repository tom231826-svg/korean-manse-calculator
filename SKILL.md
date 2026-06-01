---
name: korean-manse-calculator-v0.8
version: 0.8.0
description: |
  사주/Four Pillars 에이전트가 호출하는 계산 전용 만세력 스킬. 국내/서울 기본값 기준 양력 또는 한국 음력 생년월일시를 받아
  음력은 먼저 양력으로 변환한 뒤 한국 표준시 변동·서머타임·서울 경도 보정 -32분을 적용하고,
  1950~2030 24절기 lookup과 양력 일진 lookup으로 년주·월주·일주·시주를 산출한다.
  일주는 외부 기준 케이스 검증과 동일하게 계산 기준 양력 일자의 일진을 그대로 사용한다.
  LLM은 직접 계산하지 않고 내부 계산 엔진 결과만 전달한다.
---

# Korean Manse Calculator v0.8

## 역할

이 스킬은 사주/Four Pillars 에이전트의 **계산 레이어**다. 사주 풀이, 성격 해석, 궁합, 운세 문장 생성은 하지 않는다. 사용자의 생년월일시를 구조화하고 `scripts/calculate_manse.py` 실행 결과를 그대로 사주 에이전트에 전달한다.

계산 결과의 표준 인터페이스는 `schemas/manse-output.schema.json`이다.

## v0.8 고정 정책

```yaml
profile: seoul_corrected_manse_v0.8
calendar: solar_or_korean_lunar_via_offline_cache
country_scope: KR_only
birthplace_input: false
birthplace_assumption: Seoul

# 시간 처리
timezone_baseline: Korea_legal_clock_time
standard_time_history: auto_by_zoneinfo_Asia_Seoul
summer_time: auto_by_zoneinfo_Asia_Seoul
longitude_correction: true
longitude_correction_minutes: -32
longitude_correction_basis: Seoul_local_mean_time_style_longitude_correction
apparent_solar_time: false
true_solar_time: false
equation_of_time: false

# 4기둥 결정 기준
year_pillar_boundary: ipchun_exact_corrected_time
month_pillar_boundary: 12_solar_term_exact_corrected_time
day_pillar_basis: input_solar_date_or_converted_solar_date
zi_hour_method: reference_case_midnight_boundary
zi_hour_range: "23:00-00:59"
zi_hour_changes_day_pillar: false
hour_pillar_basis: corrected_time_for_hour_branch + input_date_day_stem

lunar_calendar: supported_by_offline_lunar_to_solar_cache_v0.8
overseas_birth: unsupported
user_birthplace_input: unsupported
interpretation_inside_skill: forbidden
```

## 입력

필수/선택 입력:

```yaml
required:
  date: "YYYY-MM-DD"          # calendar=solar이면 양력, calendar=lunar이면 음력

optional:
  time: "HH:MM" | "unknown"  # 출생시각. 모르면 unknown
  gender: "male" | "female" | "unknown"
  calendar: "solar" | "lunar"
  lunar_leap: "auto" | "true" | "false"
```

`calendar=lunar`이면 `date`는 음력 날짜로 해석한다. `lunar_leap=auto`에서 같은 음력일에 평달/윤달 후보가 모두 있으면 `ambiguous_lunar_date`를 반환한다. 해외 출생이나 출생지 입력은 받지 않는다.

## 계산 단계

### Step 0 — 입력 사전 처리

| 케이스 | 반환 |
|---|---|
| `calendar`가 `solar|lunar` 외 값 | `unsupported_calendar` |
| 음력 변환 cache 파일 누락 | `lunar_conversion_missing` |
| `lunar_leap=auto`이고 평달/윤달 후보 모두 존재 | `ambiguous_lunar_date` |
| 음력 날짜가 cache에서 찾을 수 없음 | `invalid_lunar_date` |
| 출생연도 < 1950 또는 > 2030 | `error.reason = year_out_of_range` |
| 출생시간 미상 | 시주는 `null`, 시간 보정은 적용하지 않음 |
| 날짜 포맷 비정상 | `error` |

음력 입력은 이 단계에서 양력으로 변환하고, 이후 계산 단계는 변환된 양력 날짜를 사용한다.

### Step 1 — 시간 보정

1. 사용자가 입력한 시각을 당시 대한민국 법정 시계 시간으로 본다.
2. `zoneinfo:Asia/Seoul`로 과거 표준시와 서머타임을 fixed KST(+09:00) 기준으로 환산한다.
3. 서울 기본값 경도 보정 `-32분`을 적용한다.
4. 이후 **년주·월주·시주는 보정시각 기준**으로 판정한다.
5. 단, **일주는 보정시각으로 날짜를 바꾸지 않고 입력 양력 일자의 일진을 그대로 사용**한다.

서울 -32분은 경도 보정 성격이다. 진태양시/시태양시/균시차 보정은 적용하지 않는다.

### Step 2 — 일주(日柱): 외부 기준 케이스 검증 자정경계 방식

- 일주 결정 일자 = 양력 입력일 또는 음력에서 변환된 양력 일자.
- 보정시각이 전날/다음날로 넘어가도 일주 날짜는 바꾸지 않는다.
- 子시여도 다음날 일주로 넘기지 않는다.
- `data/day_ganzhi_by_year/{YYYY}.json` 또는 `references/ilju/{YYYY}.json`의 입력일 lookup을 사용한다.

외부 기준 케이스 직접 검증으로 확인한 기준 케이스:

| 입력 | 보정시각 | 일주 |
|---|---:|---|
| 1990-01-01 23:30 | 1990-01-01 22:58 | 병인, 1월 1일 일진 |
| 1990-01-02 00:30 | 1990-01-01 23:58 | 정묘, 1월 2일 일진 |

### Step 3 — 년주(年柱): 입춘 분 단위 기준

- `data/solar_terms_cache.json` 또는 `references/jeolgi/{YYYY}.json`에서 입춘 시각을 찾는다.
- 보정시각 < 입춘시각이면 전년도 간지.
- 보정시각 >= 입춘시각이면 해당년도 간지.
- 1984년 = 갑자(甲子), `(year_used - 1984) mod 60`.

### Step 4 — 월주(月柱): 12절 분 단위 기준

월주 경계에는 24절기 중 아래 12개 절기만 직접 사용한다.

| 월지 | 시작 절기 |
|---|---|
| 寅 | 입춘 |
| 卯 | 경칩 |
| 辰 | 청명 |
| 巳 | 입하 |
| 午 | 망종 |
| 未 | 소서 |
| 申 | 입추 |
| 酉 | 백로 |
| 戌 | 한로 |
| 亥 | 입동 |
| 子 | 대설 |
| 丑 | 소한 |

보정시각 이전의 가장 가까운 월 경계 절기를 찾고, 연간 기준 월간표로 월주를 산출한다.

### Step 5 — 황경 Fallback 규칙

24절기 entry의 `name`과 `sunLongitude`가 모순되면 **sunLongitude를 우선 신뢰**한다. 이 규칙은 KASI/distbe 계열 라벨 오류를 방어하기 위한 필수 규칙이다.

| 황경 | 절기 | 황경 | 절기 | 황경 | 절기 |
|---:|---|---:|---|---:|---|
| 0° | 춘분 | 120° | 대서 | 240° | 소설 |
| 15° | 청명 | 135° | 입추 | 255° | 대설 |
| 30° | 곡우 | 150° | 처서 | 270° | 동지 |
| 45° | 입하 | 165° | 백로 | 285° | 소한 |
| 60° | 소만 | 180° | 추분 | 300° | 대한 |
| 75° | 망종 | 195° | 한로 | 315° | 입춘 |
| 90° | 하지 | 210° | 상강 | 330° | 우수 |
| 105° | 소서 | 225° | 입동 | 345° | 경칩 |

### Step 6 — 시주(時柱)

- 출생시간이 `unknown`이면 `pillars.hour = null`.
- 시지: 보정시각 기준. 子시는 23:00~00:59.
- 시주 천간: Step 2의 입력 양력일 일간을 기준으로 오자둔 표를 적용한다.
- 子시여도 일간을 다음날 일간으로 바꾸지 않는다.

## 24절기 데이터 v0.8

`references/jeolgi/{YYYY}.json` 1950~2030 총 81개 파일을 포함한다. 각 파일 구조:

```json
{
  "year": 1990,
  "source_summary": {"kasi": 0, "skyfield": 24},
  "jeolgi": [
    {"name":"소한", "hanja":"小寒", "date":"1990-01-05", "kst":"1990-01-05 23:33", "sun_longitude":285, "source":"skyfield_de421"}
  ]
}
```

데이터 출처/방법론:

- 2000~2027: KASI 특일정보 API `SpcdeInfoService/get24DivisionsInfo`.
- 1950~1999, 2028~2030: skyfield + NASA/JPL DE421 ephemeris.
- skyfield 재현 시 반드시 `ecliptic_latlon('date')`를 사용한다. 기본 J2000 frame을 쓰면 평균분점 기준 오차가 커져 절입시각이 크게 틀어진다.
- reference generation 방법론 기준 KASI ground truth 615개와 cross-validation 99.5% (612개) 1분 이내 일치.

반영된 정정/검토 이력:

- 2007-12-07: KASI/distbe 원본 `대서` 라벨 오류 → `대설` 정정 (`sunLongitude=255°`).
- 2019-01-20: KASI `17:60` 비정상 시각 표기 → `18:00` 정규화.
- 2011-01-21 대한: KASI 1일 typo 의심 → skyfield 결과 `2011-01-20 19:18`로 교체.
- 2011-11-08 입동: KASI vs skyfield 6시간 차이 → skyfield 결과 `2011-11-08 03:34`로 교체.
- 2015 하지: KASI vs skyfield 20분 차이, KASI 채택 후 `review_note` 표시.
- v0.7 통합 검증 중 `2000년 우수 누락/입춘 날짜 오염`을 추가 발견하여 runtime cache와 reference를 보정했다. 이 보정은 `references/jeolgi/2000.json`에 기록되어 있다.

## 데이터 파일

| 파일 | 용도 |
|---|---|
| `scripts/calculate_manse.py` | 결정론적 계산 엔진 |
| `scripts/build_kasi_cache.py` | KASI + skyfield 또는 bundled reference 기반 24절기 cache 재생성 |
| `scripts/validate_caches.py` | 일진/절기 데이터 무결성 검증 |
| `data/solar_terms_cache.json` | 엔진용 1950~2030 24절기 cache, 1,944 entries |
| `data/day_ganzhi_by_year/{YYYY}.json` | 엔진용 1950~2030 일진 lookup |
| `references/jeolgi/{YYYY}.json` | reference generation 구조 기반 24절기 reference |
| `references/ilju/{YYYY}.json` | 일진 reference |
| `references/conversion.json` | 60갑자, 월주표, 시주표, 시간 보정 규칙 |
| `schemas/manse-output.schema.json` | 사주 에이전트 연동 출력 schema |

## 사용법

```bash
python3 scripts/calculate_manse.py --date 1990-01-01 --time 23:30 --format json
python3 scripts/calculate_manse.py --date 1990-01-02 --time 00:30 --format json
python3 scripts/calculate_manse.py --date 1965-07-07 --time 16:00 --format md
```

데이터 검증:

```bash
python3 scripts/validate_caches.py --start-year 1950 --end-year 2030
```

reference에서 cache 재생성:

```bash
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --from-bundled-references
```

KASI + skyfield로 재현 생성:

```bash
KASI_SPCDE_SERVICE_KEY="<your-data-go-kr-service-key>" \
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --skyfield-data-dir ./skyfield-data
```

## 절대 금지

- LLM이 직접 JDN, 월주, 시주를 암산하지 않는다.
- 출생지를 사용자에게 묻지 않는다.
- 서울 -32분 보정을 사용자별 지역 보정처럼 설명하지 않는다. v0.8은 서울 기본값 고정이다.
- 진태양시/시태양시/균시차까지 적용했다고 말하지 않는다.
- 子시라는 이유로 일주를 다음날로 넘기지 않는다.
- 보정시각이 전날/다음날이 되었다는 이유로 일주를 바꾸지 않는다.
- 음력/윤달 변환을 LLM이 임의로 수행하지 않는다. 반드시 `data/lunar_to_solar_by_year` cache 결과를 사용한다.

## 사주 에이전트 연동 규칙

사주 에이전트는 이 스킬의 JSON 결과에서 아래 필드만 계산 근거로 신뢰한다.

- `pillars.year/month/day/hour`
- `normalized_time`
- `calendar_data.day_pillar_policy`
- `solar_terms`
- `warnings`
- `policies`

해석 문장, 말투, 상담 흐름은 본체가 담당한다.
