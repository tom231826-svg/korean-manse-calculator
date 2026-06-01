#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -S -m py_compile scripts/calculate_manse.py scripts/build_kasi_cache.py scripts/validate_caches.py
"$PYTHON_BIN" -S scripts/validate_caches.py --start-year 1950 --end-year 2030 >/tmp/korean_manse_v07_validate.json
"$PYTHON_BIN" - <<'PY'
import json, subprocess
import os
from pathlib import Path
root=Path.cwd()
python_bin=os.environ.get('PYTHON_BIN', 'python3')

def run(date, time, calendar='solar'):
    cp=subprocess.run([python_bin,'-S','scripts/calculate_manse.py','--date',date,'--time',time,'--calendar',calendar,'--format','json'],cwd=root,text=True,capture_output=True,check=False)
    data=json.loads(cp.stdout)
    return cp.returncode, data

# 외부 기준 케이스 검증 A: 보정 후 22:58, 입력일 일진 병인 유지
code,r=run('1990-01-01','23:30')
assert code==0 and r['status']=='ok'
assert r['summary']=='己巳년 丙子월 丙寅일 己亥시'
assert r['calendar_data']['solar_date_for_day_pillar']=='1990-01-01'
assert r['normalized_time']['basis_time_kst']=='1990-01-01T22:58:00+09:00'

# 외부 기준 케이스 검증 B: 보정 후 전날 23:58 子시, 그래도 입력일 정묘 일주 유지
code,r=run('1990-01-02','00:30')
assert code==0 and r['status']=='ok'
assert r['summary']=='己巳년 丙子월 丁卯일 庚子시'
assert r['calendar_data']['solar_date_for_day_pillar']=='1990-01-02'
assert r['calendar_data']['time_corrected_date_for_year_month_and_hour']=='1990-01-01'
assert r['pillars']['hour']['branch']=='子'

# Skyfield 보완 영역
code,r=run('1965-07-07','16:00')
assert code==0 and r['summary']=='乙巳년 壬午월 壬戌일 戊申시'

# 기존 자시 정책 보존: 23시대 子시라도 다음날 일주로 넘기지 않음
code,r=run('2020-12-25','23:40')
assert code==0 and r['summary']=='庚子년 戊子월 壬寅일 庚子시'

# 시간 미상은 00:00으로 가정하지 않음
code,r=run('2015-08-15','unknown')
assert code==0 and r['pillars']['hour'] is None
assert r['normalized_time']['basis_time_kst'] is None
assert any(w['code']=='hour_unknown' for w in r['warnings'])

# 미지원/범위 외
code,r=run('2001-09-30','12:00','lunar')
assert code==2 and r['status']=='unsupported_calendar'
code,r=run('2031-01-01','10:00')
assert code==2 and r['status']=='error' and r['error']['reason']=='year_out_of_range'
print('smoke ok')
PY
