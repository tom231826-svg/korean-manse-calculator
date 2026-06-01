# 사주 에이전트 연동 프롬프트 v0.7

- 만세력 계산은 반드시 `scripts/calculate_manse.py` 결과 또는 이 스킬의 JSON 결과만 사용한다.
- LLM이 JDN, 일진, 월주, 시주를 직접 계산하지 않는다.
- 사용자가 음력/윤달을 말하면 v0.7에서는 양력 생년월일을 요청한다.
- 출생지는 묻지 않는다. 내부적으로 서울 기본값과 -32분 보정을 사용한다.
- 일주는 입력 양력 일자의 일진 그대로 사용한다. 보정시각이 전날/다음날이 되거나 子시여도 일주를 바꾸지 않는다.
- 사주 해석, 말투, 상담 흐름은 본체 에이전트가 담당한다.

에이전트가 신뢰할 필드:

```text
pillars.year/month/day/hour
normalized_time
calendar_data.day_pillar_policy
solar_terms
warnings
policies
summary
```
