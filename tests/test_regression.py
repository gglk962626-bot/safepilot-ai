# SafePilot AI 회귀 테스트 (API 키 불필요)
# - 기존 기능 회귀 + 개선 전·후 위험성 관리 기능(명세 10절 12개 항목) 검증
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ai_service
import demo_data
import pdf_service
from models import (
    AssessmentResult, CONTROL_TYPES, CONTROL_TYPE_LABELS, CATEGORY_COUNT,
    ControlMeasure, FIXED_TBM_ITEM, FullResult, HazardItem, NoHazardStep,
    REVIEW_CATEGORIES, ReviewResult, WorkInput, apply_threshold,
    normalize_steps, parse_step_numbers, uncovered_steps,
)

passed = []
failed = []


def check(name, cond):
    (passed if cond else failed).append(name)
    print(("PASS" if cond else "FAIL"), "-", name)


PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ===========================================================================
# 0. 데모 데이터 로드 (두 시나리오)
# ===========================================================================
w_first = demo_data.get_demo_first("welding")
w_review = demo_data.get_demo_review("welding")
c_first = demo_data.get_demo_first("callcenter")
c_review = demo_data.get_demo_review("callcenter")
check("demo welding: first 6 / final 8", len(w_first.hazards) == 6 and len(w_review.final.hazards) == 8)
check("demo callcenter: first 4 / final 6", len(c_first.hazards) == 4 and len(c_review.final.hazards) == 6)

# ===========================================================================
# 1~2. 작업단계 완전성 + 번호 연속성
# ===========================================================================
for tag, res in [("welding.first", w_first), ("welding.final", w_review.final),
                 ("callcenter.first", c_first), ("callcenter.final", c_review.final)]:
    check(f"[1] {tag}: 모든 단계에 위험요인 매핑(또는 없음 표시)", not uncovered_steps(res))
    nums = [parse_step_numbers(s)[0] for s in res.work_steps]
    check(f"[2] {tag}: 단계 번호 연속(1..N)", nums == list(range(1, len(nums) + 1)))

# 번호 재정렬 + 교차검토 이력 참조 갱신
r = AssessmentResult(work_steps=["1. 준비", "3. 설치", "5. 용접"],
                     hazards=[HazardItem(step="3. 설치", hazard="협착"),
                              HazardItem(step="5. 용접", hazard="화상")])
rv = ReviewResult(findings=[], changes=[], final=r)
rv.changes = [type(rv).model_fields["changes"].annotation.__args__[0](
    action="추가", target="위험요인", description="5단계 용접에 위험요인 추가")] if False else rv.changes
from models import ChangeItem  # noqa: E402
rv.changes = [ChangeItem(action="추가", target="위험요인", description="5단계 용접에 위험요인 추가")]
mapping = normalize_steps(r, rv)
check("[2] 번호 재정렬 1,3,5→1,2,3", [parse_step_numbers(s)[0] for s in r.work_steps] == [1, 2, 3])
check("[2] 위험요인 step 참조 갱신 (5→3)", parse_step_numbers(r.hazards[1].step) == [3])
check("[2] 교차검토 이력 단계 참조 갱신", "3단계" in rv.changes[0].description)

# 미매핑 단계 → (재생성 불가 시) '유의미한 위험요인 없음' 처리
r2 = AssessmentResult(work_steps=["1. 준비", "2. 설치", "3. 마감"],
                      hazards=[HazardItem(step="1. 준비", hazard="x"), HazardItem(step="2. 설치", hazard="y")])
ai_service.postprocess_result(WorkInput(name="t"), r2, client=None, allow_regen=False)
check("[1] 미매핑 단계 → 유의미한 위험요인 없음 + 사유", len(r2.no_hazard_steps) == 1 and bool(r2.no_hazard_steps[0].reason))
check("[1] 처리 후 미매핑 없음", not uncovered_steps(r2))

# ===========================================================================
# 3~4. 개선 후 ≤ 개선 전 / 점수·등급 코드 계산
# ===========================================================================
all_h = w_first.hazards + w_review.final.hazards + c_first.hazards + c_review.final.hazards
check("[3] 모든 데모 항목: 개선 후 점수 <= 개선 전 점수",
      all(h.residual_score <= h.risk_score for h in all_h))
check("[4] 점수 = 가능성x심각도 / 잔여점수 = 잔여가능성x잔여심각도 (코드 계산)",
      all(h.risk_score == h.likelihood * h.severity and
          h.residual_score == h.residual_likelihood * h.residual_severity for h in all_h))
h = AssessmentResult.model_validate({"hazards": [{
    "step": "1. s", "hazard": "h", "likelihood": 9, "severity": -2,
    "residual_likelihood": 99, "residual_severity": 0,
    "risk_score": 999, "risk_level": "낮음"}]}).hazards[0]
check("[4] 범위 밖 값 보정: 가능성 9→5 / 심각도 -2→1", h.likelihood == 5 and h.severity == 1)
check("[4] AI가 준 risk_score 무시하고 재계산 (5x1=5, 보통)", h.risk_score == 5 and h.risk_level == "보통")

# 규칙 위반 검증: 개선 후 > 개선 전 / 상위 대책 없는 심각도 하향
bad1 = HazardItem(step="1", hazard="a", likelihood=2, severity=2, residual_likelihood=5, residual_severity=5)
check("[3] 위반 감지: 개선 후 > 개선 전", any("높음" in v for v in bad1.rule_violations()))
bad2 = HazardItem(step="1", hazard="b", likelihood=3, severity=4, residual_likelihood=3, residual_severity=2,
                  measures=[{"control_type": "ppe", "description": "보호구"}])
check("[3] 위반 감지: 상위 대책 없는 심각도 하향", any("심각도" in v for v in bad2.rule_violations()))
ok1 = HazardItem(step="1", hazard="c", likelihood=3, severity=4, residual_likelihood=3, residual_severity=2,
                 measures=[{"control_type": "engineering", "description": "설비 개선"}])
check("[3] 공학적 대책 있으면 심각도 하향 허용", not ok1.rule_violations())

# 재생성 한도(2회) 후 '검수 필요' 처리 — 무한 루프 금지
calls = {"n": 0}
STILL_BAD = json.dumps({"hazards": [{"step": "1. s", "hazard": "a", "likelihood": 2, "severity": 2,
                                     "residual_likelihood": 5, "residual_severity": 5}]}, ensure_ascii=False)
orig_call = ai_service._call_model
def _always_bad(client, system, user):
    calls["n"] += 1
    return STILL_BAD
ai_service._call_model = _always_bad
res_nr = AssessmentResult(work_steps=["1. s"], hazards=[bad1.model_copy(deep=True)])
ai_service.postprocess_result(WorkInput(name="t"), res_nr, client=object(), allow_regen=True)
ai_service._call_model = orig_call
check("[10] 2회 재생성 실패 → 검수 필요 상태", res_nr.hazards[0].needs_review and bool(res_nr.hazards[0].needs_review_reason))
check("[10] 재생성 호출이 2회로 제한됨 (무한 루프 없음)", calls["n"] == 2)

# ===========================================================================
# 5. improvement_required 는 코드 산정 (AI 출력 무시)
# ===========================================================================
res_thr = AssessmentResult.model_validate({"work_steps": ["1. s"], "hazards": [
    {"step": "1. s", "hazard": "低", "likelihood": 2, "severity": 2,
     "residual_likelihood": 1, "residual_severity": 2, "improvement_required": True},   # AI가 True 줘도
    {"step": "1. s", "hazard": "高", "likelihood": 4, "severity": 4,
     "residual_likelihood": 3, "residual_severity": 3, "improvement_required": False},  # AI가 False 줘도
]})
apply_threshold(res_thr, 4)
check("[5] improvement_required 코드 산정: 2점→False (AI True 무시)", res_thr.hazards[0].improvement_required is False)
check("[5] improvement_required 코드 산정: 9점>기준4 → True (AI False 무시)", res_thr.hazards[1].improvement_required is True)
apply_threshold(res_thr, 10)
check("[5] 기준 변경(10점) 시 재산정: 9점 → False", res_thr.hazards[1].improvement_required is False)

# ===========================================================================
# 6. 20개 위험범주 + "17개" 잔여 문구 없음
# ===========================================================================
check("[6] 위험범주 20개", CATEGORY_COUNT == 20 and len(REVIEW_CATEGORIES) == 20)
check("[6] 신규 3개 범주 포함",
      all(c in REVIEW_CATEGORIES for c in ["감정노동·심리사회적 위험", "폭력·상해 위험", "생물학적 위험"]))
leftover = []
for fn in ["app.py", "prompts.py", "pdf_service.py", "models.py", "demo_data.py"]:
    src = open(os.path.join(PROJ, fn), encoding="utf-8").read()
    if re.search(r"17\s*개", src):
        leftover.append(fn)
check("[6] '17개' 잔여 문구 없음 (앱 소스)", not leftover)
check("[6] 데모 findings 20개 범주 전수",
      [f.category for f in w_review.findings] == REVIEW_CATEGORIES
      and [f.category for f in c_review.findings] == REVIEW_CATEGORIES)

# ===========================================================================
# 7. 콜센터: 감정노동·폭력 위험 분류
# ===========================================================================
c_cats = {h.category for h in c_review.final.hazards}
emo = [h for h in c_review.final.hazards if h.category == "감정노동·심리사회적 위험"]
check("[7] 콜센터: 감정노동·심리사회적 위험 분류 존재(폭언·스트레스)", len(emo) >= 2)
check("[7] 콜센터: 폭력·상해 위험 분류 존재", "폭력·상해 위험" in c_cats)

# ===========================================================================
# 8. control_type 5개 영문 값 + 한국어 라벨
# ===========================================================================
check("[8] 데모 대책 control_type 전부 허용값",
      all(m.control_type in CONTROL_TYPES for h in all_h for m in h.measures))
check("[8] 한국어 라벨 매핑", CONTROL_TYPE_LABELS["elimination"] == "제거"
      and ControlMeasure(control_type="engineering", description="x").display == "[공학적] x")
check("[8] 허용 외 값 → administrative 보정",
      ControlMeasure.model_validate({"control_type": "magic", "description": "x"}).control_type == "administrative")
check("[8] '[제거] 내용' 문자열 해석 (편집 모드 호환)",
      ControlMeasure.model_validate("[제거] 유해공정 제거").control_type == "elimination")
check("[8] 관리·PPE만 구성 감지 (상위 수준 검토 문구용)",
      HazardItem(measures=[{"control_type": "ppe", "description": "x"}]).only_admin_ppe() is True
      and ok1.only_admin_ppe() is False)

# ===========================================================================
# 9. 판단 근거 생성 (개선 전 + 개선 후)
# ===========================================================================
check("[9] 데모 전 항목 basis_likelihood/severity 존재",
      all(h.basis_likelihood.strip() and h.basis_severity.strip() for h in all_h))
check("[9] 데모 전 항목 개선 후 판단 근거(residual_basis_*) 존재",
      all(getattr(h, "residual_basis_likelihood", "").strip()
          and getattr(h, "residual_basis_severity", "").strip() for h in all_h))
check("[9] AI 스키마에 개선 후 근거 필드 포함 (프롬프트)",
      "residual_basis_likelihood" in __import__("prompts").FIRST_PASS_SYSTEM)

# ===========================================================================
# 10~12. 검수 필요 표시·TBM 고정 항목·PDF 생성
# ===========================================================================
res = FullResult(work_input=demo_data.get_sample_input("welding"), first=w_first,
                 review=w_review, is_demo=True, generated_at="2026-08-18 10:00", threshold=4)
# 검수 필요 1건 강제 → PDF/HTML 표시 검증
res.review.final.hazards[0].needs_review = True
res.review.final.hazards[0].needs_review_reason = "테스트 사유"
pdf = pdf_service.build_pdf(res)
check("[12] PDF 생성 (용접, 가로형)", len(pdf) > 50000)
try:
    from pypdf import PdfReader
    import io
    text = "".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
    check("[10] PDF에 검수 필요 표시", "검수 필요" in text and "AI 검증 미통과" in text)
    check("[10] PDF 요약부에 검수 필요 건수", "검수 필요 항목: 1건" in text)
    check("[6] PDF에 20개 위험범주 문구", "20개 위험범주" in text)
    check("[부록] PDF에 평가 기준표", "자체 평가 기준" in text)
    check("[10] PDF에 근로자 의견 영역", "근로자 의견" in text and "참여 근로자" in text)
except ImportError:
    print("SKIP - pypdf 미설치: PDF 텍스트 검증 생략")
res.review.final.hazards[0].needs_review = False
res.review.final.hazards[0].needs_review_reason = ""

html = pdf_service.build_html_report(res)
check("[10] HTML 보고서: 개선 전·후/근로자 의견/기준표 포함",
      "개선 후 위험성" in html and "근로자 의견" in html and "자체 평가 기준" in html)

res_c = FullResult(work_input=demo_data.get_sample_input("callcenter"), first=c_first,
                   review=c_review, is_demo=True, generated_at="2026-08-18 10:00", threshold=4)
check("[12] PDF 생성 (콜센터)", len(pdf_service.build_pdf(res_c)) > 50000)

# --- 감사(audit)에서 발견된 엣지 케이스 회귀 방지 ---
# (a) 번호 없는 step("전 과정")은 전 단계 커버로 간주 → 가짜 '없음' 행·불필요 재생성 방지
r_un = AssessmentResult(work_steps=["1. 준비", "2. 용접"],
                        hazards=[HazardItem(step="전 과정", hazard="소음")])
ai_service.postprocess_result(WorkInput(name="t"), r_un, client=None, allow_regen=False)
check("[감사] 번호 없는 위험요인 → 미매핑 오탐 없음",
      not uncovered_steps(r_un) and len(r_un.no_hazard_steps) == 0)
# (a') 번호 없지만 본문이 단계와 유일 매칭되면 번호 복원
r_res = AssessmentResult(work_steps=["1. 준비", "2. 용접"],
                         hazards=[HazardItem(step="용접", hazard="화상")])
normalize_steps(r_res)
check("[감사] 번호 없는 step 본문 매칭 복원 (용접→2)", parse_step_numbers(r_res.hazards[0].step) == [2])
# (b) 중복 원본 번호 → 첫 등장 유지 (참조 어긋남 방지)
r_dup = AssessmentResult(work_steps=["1. 준비", "1. 설치", "2. 용접"],
                         hazards=[HazardItem(step="1. 준비", hazard="a"),
                                  HazardItem(step="2. 용접", hazard="b")])
normalize_steps(r_dup)
check("[감사] 중복 번호: 1번 참조가 첫 등장(준비)에 유지",
      parse_step_numbers(r_dup.hazards[0].step) == [1]
      and parse_step_numbers(r_dup.hazards[1].step) == [3])
# (c) NaN residual (편집 모드 빈 셀) → 개선 전과 동일로 보정 (허위 검수 필요 방지)
h_nan = HazardItem.model_validate({"step": "1. s", "hazard": "x", "likelihood": 2, "severity": 1,
                                   "residual_likelihood": float("nan"),
                                   "residual_severity": float("nan")})
check("[감사] NaN residual → 개선 전과 동일 보정 (위반 없음)",
      h_nan.residual_likelihood == 2 and h_nan.residual_severity == 1
      and not h_nan.rule_violations())
# (d) 위험요인이 생긴 단계의 기존 '없음' 행 제거 (모순 방지)
r_pr = AssessmentResult(work_steps=["1. 준비", "2. 마감"],
                        hazards=[HazardItem(step="1. 준비", hazard="a"),
                                 HazardItem(step="2. 마감", hazard="b")],
                        no_hazard_steps=[NoHazardStep(step="2. 마감", reason="이전 결과")])
ai_service.postprocess_result(WorkInput(name="t"), r_pr, client=None, allow_regen=False)
check("[감사] 커버된 단계의 '유의미한 위험요인 없음' 행 자동 제거", len(r_pr.no_hazard_steps) == 0)

# findings 누락 범주 자동 보정 (실 API에서 19/20 반환 사례 대응)
partial_rv = ReviewResult(findings=[{"category": c, "status": "적정", "comment": "ok"}
                                    for c in REVIEW_CATEGORIES[:19]])
ai_service._ensure_finding_coverage(partial_rv)
check("[6] findings 누락 범주 코드 보정 (19→20)", len(partial_rv.findings) == 20
      and partial_rv.findings[19].category == REVIEW_CATEGORIES[19]
      and "수동 확인" in partial_rv.findings[19].comment)
dup_rv = ReviewResult(findings=[{"category": REVIEW_CATEGORIES[0], "status": "적정", "comment": "a"},
                                {"category": REVIEW_CATEGORIES[0], "status": "보완", "comment": "b"}])
ai_service._ensure_finding_coverage(dup_rv)
check("[6] findings 중복 제거 + 순서 정렬", len(dup_rv.findings) == 20
      and [f.category for f in dup_rv.findings] == REVIEW_CATEGORIES)

# TBM 고정 항목: 데모 데이터 포함 + 코드 강제 삽입 확인
check("[11] 데모 TBM에 근로자 의견 청취 포함",
      any(FIXED_TBM_ITEM in t for t in w_review.final.tbm)
      and any(FIXED_TBM_ITEM in t for t in c_review.final.tbm))
r3 = AssessmentResult(work_steps=["1. s"], hazards=[HazardItem(step="1. s", hazard="x")],
                      tbm=["일반 항목"])
ai_service.postprocess_result(WorkInput(name="t"), r3, client=None, allow_regen=False)
check("[11] AI가 항목을 빼도 코드가 고정 삽입", any(FIXED_TBM_ITEM in t for t in r3.tbm))

# ===========================================================================
# 기존 기능 회귀 (JSON 재시도 / 오류 처리 / 폴백)
# ===========================================================================
key_present = ai_service.has_api_key()
work = demo_data.SAMPLE_INPUT
VALID = json.dumps(demo_data._FIRST, ensure_ascii=False)

calls2 = {"n": 0}
def fake_bad_then_good(client, system, user):
    calls2["n"] += 1
    return "이것은 JSON이 아닙니다" if calls2["n"] == 1 else VALID
orig_client = ai_service._get_client
ai_service._get_client = lambda: object()
ai_service._call_model = fake_bad_then_good
result = ai_service.run_first_pass(work)
check("회귀: JSON 실패 시 1회 재시도 후 성공", len(result.hazards) == 6)
check("회귀: 파싱 재시도 정확히 1회 (총 2호출)", calls2["n"] == 2)

ai_service._call_model = lambda c, s, u: "{invalid json!!"
try:
    ai_service.run_first_pass(work)
    check("회귀: 재시도까지 실패 → 오류", False)
except ai_service.AIServiceError as e:
    check("회귀: 재시도까지 실패 → 한국어 오류", "해석하지 못했습니다" in str(e))

REVIEW_VALID = json.dumps({**demo_data._REVIEW, "final": demo_data._FINAL}, ensure_ascii=False)
ai_service._call_model = lambda c, s, u: REVIEW_VALID
rvw = ai_service.run_review_pass(work, w_first)
check("회귀: 2차 검토 파이프라인 (findings 20 / final 8)",
      len(rvw.findings) == 20 and len(rvw.final.hazards) == 8)

EMPTY_FINAL = json.dumps({"findings": [], "changes": [], "final": {}}, ensure_ascii=False)
ai_service._call_model = lambda c, s, u: EMPTY_FINAL
rvw2 = ai_service.run_review_pass(work, w_first)
check("회귀: 빈 final → 1차 결과로 대체", len(rvw2.final.hazards) == 6)

ai_service._call_model = orig_call
ai_service._get_client = orig_client

print()
print(f"결과: {len(passed)} PASS / {len(failed)} FAIL")
if key_present:
    print("(참고: .env에 API 키가 있어 '키 없음' 경로 테스트는 생략)")
sys.exit(1 if failed else 0)
