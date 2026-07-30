# SafePilot AI 회귀 테스트 (API 키 불필요)
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ai_service
import demo_data
import pdf_service
from models import AssessmentResult, FullResult, ReviewResult, WorkInput

passed = []
failed = []


def check(name, cond):
    (passed if cond else failed).append(name)
    print(("PASS" if cond else "FAIL"), "-", name)


# 1. 데모 모드 데이터 검증 (기존 기능 회귀)
first = demo_data.get_demo_first()
review = demo_data.get_demo_review()
check("demo first: 6 hazards", len(first.hazards) == 6)
check("demo final: 8 hazards", len(review.final.hazards) == 8)
check("demo findings: 17 categories", len(review.findings) == 17)
check("risk score computed in python", review.final.max_risk_score == 15)

# 2. 위험도 규칙: AI가 준 risk_score는 무시되고 재계산되는지
h = AssessmentResult.model_validate({
    "hazards": [{"step": "s", "hazard": "h", "likelihood": 9, "severity": -2,
                 "risk_score": 999, "risk_level": "낮음"}]
}).hazards[0]
check("likelihood clamped to 5", h.likelihood == 5)
check("severity clamped to 1", h.severity == 1)
check("risk_score recomputed (5*1=5)", h.risk_score == 5)
check("risk_level from python (5=보통)", h.risk_level == "보통")

# 3. API 키 없음 → 데모 모드 정상 + 친절한 오류
check("no api key detected", ai_service.has_api_key() is False)
work = demo_data.SAMPLE_INPUT
try:
    ai_service.run_first_pass(work)
    check("run_first_pass w/o key raises", False)
except ai_service.AIServiceError as e:
    check("run_first_pass w/o key raises Korean error", "API 키" in str(e))

# 4. JSON 파싱 + 1회 재시도 로직 (모델 호출을 가짜 함수로 대체)
VALID = json.dumps(demo_data._FIRST, ensure_ascii=False)

calls = {"n": 0}
def fake_call_bad_then_good(client, system, user):
    calls["n"] += 1
    return "이것은 JSON이 아닙니다" if calls["n"] == 1 else VALID

orig_call = ai_service._call_model
orig_client = ai_service._get_client
ai_service._get_client = lambda: object()

ai_service._call_model = fake_call_bad_then_good
result = ai_service.run_first_pass(work)
check("retry: succeeds on 2nd attempt", len(result.hazards) == 6)
check("retry: exactly 2 calls made", calls["n"] == 2)

def fake_call_always_bad(client, system, user):
    return "{invalid json!!"
ai_service._call_model = fake_call_always_bad
try:
    ai_service.run_first_pass(work)
    check("both attempts fail -> error", False)
except ai_service.AIServiceError as e:
    check("both attempts fail -> Korean error", "해석하지 못했습니다" in str(e))

# 마크다운 코드블록으로 감싼 JSON도 파싱되는지
def fake_call_fenced(client, system, user):
    return "```json\n" + VALID + "\n```"
ai_service._call_model = fake_call_fenced
result = ai_service.run_first_pass(work)
check("fenced json parsed", len(result.hazards) == 6)

# 5. 2차 검토 파이프라인 (1차 결과 -> 검토 -> final)
REVIEW_VALID = json.dumps(
    {**demo_data._REVIEW, "final": demo_data._FINAL}, ensure_ascii=False)
ai_service._call_model = lambda c, s, u: REVIEW_VALID
rv = ai_service.run_review_pass(work, first)
check("review pass returns findings", len(rv.findings) == 17)
check("review pass returns final hazards", len(rv.final.hazards) == 8)

# final이 비어 있으면 1차 결과로 대체되는지
EMPTY_FINAL = json.dumps({"findings": [], "changes": [], "final": {}}, ensure_ascii=False)
ai_service._call_model = lambda c, s, u: EMPTY_FINAL
rv2 = ai_service.run_review_pass(work, first)
check("empty final falls back to first", len(rv2.final.hazards) == 6)

ai_service._call_model = orig_call
ai_service._get_client = orig_client

# 6. PDF/HTML 보고서 회귀
res = FullResult(work_input=work, first=first, review=review,
                 is_demo=True, generated_at="2026-07-30 16:00")
pdf = pdf_service.build_pdf(res)
check("pdf generated > 50KB", len(pdf) > 50000)
check("html report generated", "SafePilot AI" in pdf_service.build_html_report(res))

print()
print(f"결과: {len(passed)} PASS / {len(failed)} FAIL")
sys.exit(1 if failed else 0)
