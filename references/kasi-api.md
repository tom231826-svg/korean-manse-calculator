# KASI / Skyfield 데이터 소스 메모 v0.7

## 사용 API

### 특일정보 API

- Service: `SpcdeInfoService/get24DivisionsInfo`
- 용도: 24절기 날짜, `kst` 절입시각, `sunLongitude` 수집
- v0.7 재현 정책상 KASI 직접 구간: 2000~2027
- 환경변수: `KASI_SPCDE_SERVICE_KEY` 또는 공통 `KASI_SERVICE_KEY`

### 음양력정보 API

- Service: `LrsrCldInfoService/getLunCalInfo`
- v0.7에서는 일진 live fallback 용도만 남겨둔다.
- 음력/윤달 변환은 v1.x backlog.
- 환경변수: `KASI_LRSR_SERVICE_KEY` 또는 공통 `KASI_SERVICE_KEY`

## 24절기 보완

- 1950~1999, 2028~2030은 skyfield + NASA/JPL DE421 ephemeris를 사용한다.
- skyfield 계산 시 `ecliptic_latlon('date')`를 반드시 사용한다.
- 기본 J2000 frame은 평균분점 기준이라 절입시각이 크게 틀어질 수 있다.

## 정정 이력

- 2007-12-07: 대서 라벨 오류 → 대설 정정 (`sunLongitude=255`).
- 2019-01-20: `17:60` → `18:00`.
- 2011-01-21 대한: KASI 1일 typo 의심 → skyfield `2011-01-20 19:18`.
- 2011-11-08 입동: KASI vs skyfield 6시간 차이 → skyfield `2011-11-08 03:34`.
- 2015 하지: KASI vs skyfield 20분 차이, KASI 채택 및 `review_note`.
- 2000 입춘/우수: v0.7 통합 검증 중 우수 누락/입춘 날짜 오염 발견, 보정.

## 캐시 재생성

번들 reference에서 생성:

```bash
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --from-bundled-references
```

KASI + skyfield로 재현 생성:

```bash
KASI_SPCDE_SERVICE_KEY="<your-data-go-kr-service-key>" \
python3 scripts/build_kasi_cache.py --start-year 1950 --end-year 2030 --skyfield-data-dir ./skyfield-data
```
