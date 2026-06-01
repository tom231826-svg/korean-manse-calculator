# Korean Manse Calculator

[![CI](https://github.com/tom231826-svg/korean-manse-calculator/actions/workflows/ci.yml/badge.svg)](https://github.com/tom231826-svg/korean-manse-calculator/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/tom231826-svg/korean-manse-calculator?sort=semver)](https://github.com/tom231826-svg/korean-manse-calculator/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)](https://www.python.org/)

한국 만세력/Four Pillars 계산을 위한 결정론적(deterministic), 계산 전용(calculation-only), 재현 가능한(reproducible) 엔진입니다. 양력 또는 한국 음력 생년월일시를 입력받아 년주·월주·일주·시주를 구조화해 반환하며, 운세 해석·상담 문장·궁합 문장·예측 문장은 생성하지 않습니다.

## 왜 만들었나요?

LLM은 계산 결과를 설명하는 데는 유용하지만, 달력 계산 자체를 즉석에서 추론하면 틀릴 수 있습니다. 사주 만세력 계산에는 대한민국 법정시, 과거 서머타임, 24절기 경계, 일진 lookup, 자시/자정 정책처럼 명확한 규칙과 reference data가 필요합니다.

이 저장소는 해석 레이어와 계산 레이어를 분리하여, 에이전트나 애플리케이션이 반복 가능한 엔진 결과를 신뢰하도록 만드는 것을 목표로 합니다.

## 무엇을 하나요?

- 1950년부터 2030년까지 양력 생년월일시의 년주·월주·일주·시주를 계산합니다.
- `--calendar lunar` 입력을 지원하며, 음력/윤달은 먼저 양력으로 변환한 뒤 같은 계산 엔진을 사용합니다.
- `Asia/Seoul` 기준 대한민국 법정시와 과거 서머타임을 처리합니다.
- 서울 기준 고정 경도 보정 `-32분`을 적용합니다.
- 늦은 밤 `子`시 케이스에서도 일주는 입력 양력 날짜를 유지합니다.
- reference data, 검증 스크립트, smoke test, JSON 출력 스키마를 함께 제공합니다.

## 빠른 시작

```bash
python3 scripts/calculate_manse.py --date 1990-01-01 --time 23:30 --format json
python3 scripts/calculate_manse.py --date 1990-01-02 --time 00:30 --format json
python3 scripts/calculate_manse.py --date 1965-07-07 --time 16:00 --format md
python3 scripts/calculate_manse.py --calendar lunar --date 2001-08-14 --lunar-leap false --time 12:00 --format json
python3 scripts/calculate_manse.py --calendar lunar --date 2020-04-01 --lunar-leap true --time 12:00 --format json
```

번들 데이터 검증:

```bash
python3 scripts/validate_caches.py --start-year 1950 --end-year 2030
bash tests/smoke_test.sh
```

## 출력 예시

요약 출력:

```text
己巳년 丙子월 丙寅일 己亥시
```

짧은 JSON 형태:

```json
{
  "status": "ok",
  "summary": "己巳년 丙子월 丙寅일 己亥시",
  "pillars": {
    "year": {"ganzhi": "己巳", "ko": "기사"},
    "month": {"ganzhi": "丙子", "ko": "병자"},
    "day": {"ganzhi": "丙寅", "ko": "병인"},
    "hour": {"ganzhi": "己亥", "ko": "기해"}
  }
}
```

전체 JSON 예시는 [`examples/sample-output.json`](examples/sample-output.json)을 참고하세요.

## 정확도와 데이터 무결성

- 일진 lookup은 1950-01-01부터 2030-12-31까지 총 29,585일을 포함하며, 검증 기준 mismatch 0입니다.
- 24절기 reference는 81년 x 24개 = 1,944개 entry를 포함합니다.
- runtime solar-term cache 역시 1,944개 entry로 검증됩니다.
- 음력→양력 변환 cache는 1950-01-01부터 2030-12-31까지의 양력 날짜 29,585일을 역인덱싱합니다.
- CI는 push와 pull request마다 compile check, cache validation, smoke test를 실행합니다.
- LLM 직접 계산은 금지합니다. 호출자는 엔진 출력값을 계산의 source of truth로 사용해야 합니다.

자세한 내용은 [`docs/accuracy.md`](docs/accuracy.md)를 참고하세요.

## 제한 사항

- 음력 변환 cache는 런타임 API 호출 없이 번들 데이터를 사용합니다. cache에 없는 날짜는 계산하지 않습니다.
- `--lunar-leap auto`에서 평달/윤달 후보가 모두 있으면 `ambiguous_lunar_date`를 반환합니다.
- 해외 출생과 사용자 입력 출생지 보정은 지원하지 않습니다.
- 진태양시, 시태양시, 균시차 보정은 적용하지 않습니다.
- 현재는 early public release이며, 패키지 배포보다는 source-run CLI에 초점을 둡니다.

## 데이터 출처

일반 계산에는 저장소에 포함된 cache만으로 충분합니다. KASI/data.go.kr API 키는 upstream API에서 reference data를 재생성할 때만 필요합니다.

이 저장소에는 API 키가 포함되어 있지 않습니다. 필요하면 `.env.example`을 복사해 로컬 `.env` 파일을 만들고, 실제 키는 절대 커밋하지 마세요.

```bash
cp .env.example .env
```

번들 reference에서 cache 재생성:

```bash
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --from-bundled-references
```

KASI + Skyfield 기반 24절기 재생성:

```bash
KASI_SPCDE_SERVICE_KEY="<your-data-go-kr-service-key>" \
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --skyfield-data-dir ./skyfield-data
```

KASI 음양력정보 API 기반 음력 변환 cache 재생성:

```bash
KASI_LRSR_SERVICE_KEY="<your-data-go-kr-service-key>" \
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --from-bundled-references --include-lunar-conversion
```

데이터 출처와 재생성 정책은 [`DATA_SOURCES.md`](DATA_SOURCES.md)에 정리되어 있습니다.

## 로드맵

현재 우선순위는 #2: JSON schema 검증을 CI에 추가하고, 절기 경계 및 보정시각 경계 근처의 회귀 테스트를 확장하는 것입니다.

계획된 작업:

- #1: Python package 및 CLI 배포 워크플로 추가
- 음력 변환 cache의 KASI 재생성 결과와 현재 번들 cache를 교차 검증

## 기여하기

기여는 계산을 결정론적으로 유지하고, 해석 문장 생성을 계산 엔진에 섞지 않는 방향이어야 합니다. Pull request를 열기 전에 아래 검증을 실행해 주세요.

```bash
python3 -m json.tool examples/sample-output.json >/dev/null
python3 scripts/validate_caches.py --start-year 1950 --end-year 2030
bash tests/smoke_test.sh
```

자세한 내용은 [`CONTRIBUTING.md`](CONTRIBUTING.md), [`CHANGELOG.md`](CHANGELOG.md), [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)를 참고하세요.

## 라이선스

MIT. 자세한 내용은 [LICENSE](LICENSE)를 참고하세요.
