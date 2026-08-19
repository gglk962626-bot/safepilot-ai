# 실제 Gemini API 종단 점검 스크립트 (수동 실행용 — API 키 필요, 회귀 테스트와 별개)
# 실행: PYTHONUTF8=1 py tests/api_e2e_check.py
import sys, time
sys.stdout.reconfigure(encoding="utf-8")
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import ai_service
from models import WorkInput, CONTROL_TYPES, FullResult, uncovered_steps, apply_threshold
import pdf_service

work = WorkInput(
    name="사다리를 이용한 사무실 천장 형광등 교체",
    location="본관 3층 사무실",
    description="A형 사다리(1.8m)를 설치하고 올라가 천장 매입형 형광등을 탈거 후 새 LED 등기구로 교체한다. 교체 전 분전반에서 해당 회로 차단.",
    equipment="A형 사다리, 절연장갑, LED 등기구, 드라이버",
    workers="전기원 1명, 보조 1명",
    notes="사무실 근무자가 있는 시간대 작업",
)

def with_retry(fn, name, tries=4, wait=45):
    for i in range(tries):
        try:
            return fn()
        except ai_service.AIServiceError as e:
            msg = str(e)
            if "503" in msg or "서버 오류" in msg or "한도" in msg:
                print(f"[{name}] 시도 {i+1} 실패({msg[:40]}...) — {wait}초 후 재시도")
                time.sleep(wait)
                continue
            raise
    raise SystemExit(f"[{name}] {tries}회 재시도 실패")

first = with_retry(lambda: ai_service.run_first_pass(work), "1차")
print("1차:", len(first.work_steps), "단계 /", len(first.hazards), "위험요인 / no_hazard", len(first.no_hazard_steps))
print("  residual<=before:", all(h.residual_score <= h.risk_score for h in first.hazards),
      "| basis all:", all(h.basis_likelihood.strip() and h.basis_severity.strip() for h in first.hazards),
      "| types valid:", all(m.control_type in CONTROL_TYPES for h in first.hazards for m in h.measures),
      "| uncovered:", uncovered_steps(first), "| TBM고정:", any("근로자 의견 청취" in t for t in first.tbm))

review = with_retry(lambda: ai_service.run_review_pass(work, first), "2차")
final = review.final
cats = [f.category for f in review.findings]
print("2차: findings", len(review.findings), "/ changes", len(review.changes), "/ final", len(final.hazards))
print("  신규3범주 점검:", all(c in cats for c in ["감정노동·심리사회적 위험", "폭력·상해 위험", "생물학적 위험"]),
      "| residual<=before:", all(h.residual_score <= h.risk_score for h in final.hazards),
      "| uncovered:", uncovered_steps(final),
      "| needs_review:", sum(1 for h in final.hazards if h.needs_review))
apply_threshold(final, 4)
print("  기준초과(4점):", final.improvement_required_count, "/", len(final.hazards),
      "| basis all:", all(h.basis_likelihood.strip() and h.basis_severity.strip() for h in final.hazards),
      "| TBM고정:", any("근로자 의견 청취" in t for t in final.tbm))
res = FullResult(work_input=work, first=first, review=review, is_demo=False,
                 generated_at="2026-08-18", threshold=4)
print("PDF bytes:", len(pdf_service.build_pdf(res)))
print("OK-ALL")
