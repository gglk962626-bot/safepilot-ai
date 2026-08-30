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
    # 교차검토 결과·변경사항·판단 근거는 화면 전용 검증 기록 — 보고서 미포함
    check("[보고서] PDF에서 교차검토·변경사항·판단 근거 섹션 제외",
          "20개 위험범주" not in text and "검토 전후 변경사항" not in text
          and "판단 근거" not in text)
    check("[보고서] PDF 섹션 번호 재정렬 (7 근로자 의견 / 8 책임자 확인)",
          "7. 근로자 의견" in text and "8. 현장 책임자 확인" in text)
    # 평가 기준표는 사이드바 '평가 설정'으로 이동 — PDF 부록에서 제거됨
    check("[부록] PDF에 평가 기준 부록 없음", "자체 평가 기준" not in text and "부록" not in text)
    check("[10] PDF에 근로자 의견 영역", "근로자 의견" in text and "참여 근로자" in text)
except ImportError:
    print("SKIP - pypdf 미설치: PDF 텍스트 검증 생략")
res.review.final.hazards[0].needs_review = False
res.review.final.hazards[0].needs_review_reason = ""

html = pdf_service.build_html_report(res)
check("[10] HTML 보고서: 개선 전·후/근로자 의견 포함, 평가 기준 부록 없음",
      "개선 후 위험성" in html and "근로자 의견" in html and "자체 평가 기준" not in html)
check("[보고서] HTML 보고서도 교차검토·변경사항·판단 근거 섹션 제외",
      "20개 위험범주" not in html and "검토 전후 변경사항" not in html
      and "판단 근거" not in html and "8. 현장 책임자 확인" in html)

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

# ---------------------------------------------------------------------------
# [정제] 변경사항(changes) 표시 정제 — 시스템 필드 정리 제거·내부 필드명 치환
# ---------------------------------------------------------------------------
from models import ChangeItem, sanitize_changes

_ch = sanitize_changes([
    ChangeItem(action="추가", target="평가 필드",
               description="시스템 자동 계산 필드(risk_score, improvement_required, needs_review)를 제거함"),
    ChangeItem(action="수정", target="no_hazard_steps",
               description="무위험 단계를 위험단계로 전환하여 안전대책을 신설함"),
    ChangeItem(action="수정", target="위험요인",
               description="밀폐공간 질식 위험의 원인 서술을 구체화함"),
])
check("[정제] 시스템 필드 정리 보고 항목 제거", len(_ch) == 2
      and all("risk_score" not in c.description for c in _ch))
check("[정제] 내부 필드명 target 한국어 치환", _ch[0].target == "위험요인 없는 단계")
check("[정제] 일반 변경 항목은 그대로 유지", _ch[1].target == "위험요인"
      and "구체화" in _ch[1].description)
check("[정제] 빈 목록·오류 입력 fail-open",
      sanitize_changes([]) == [] and isinstance(sanitize_changes(None), list))

# 데모 로드 경로에도 적용 (JSON 파일은 무수정, 메모리 정제만)
_food_ch = demo_data.get_demo_review("food").changes
check("[정제] 식품 데모의 시스템 필드 정리 항목 미표시",
      not any("improvement_required" in c.description or "risk_score" in c.description
              for c in _food_ch))
_paint_ch = demo_data.get_demo_review("painting").changes
check("[정제] 도장 데모 target 내부 필드명 치환",
      not any("no_hazard_steps" in (c.target + c.description) for c in _paint_ch))
import json as _json
check("[정제] 데모 JSON 파일 자체는 원본 유지",
      any("improvement_required" in c.get("description", "")
          for c in _json.load(open("assets/demo_food.json", encoding="utf-8"))["changes"]))

# 형식 정리(명칭·번호 표기) 항목 제거 + 실질 변화 항목 보존
_ch2 = sanitize_changes([
    ChangeItem(action="수정", target="작업 단계 명칭",
               description="혼재 단계 명칭 '4~5. 배관 연결부 아크용접 및 사상 작업'을 실제 작업 단계 "
                           "리스트와 일치하도록 수정하여 명확히 함"),
    ChangeItem(action="수정", target="위험요인",
               description="단계 명칭 변경에 맞춰 감전 위험요인의 대책을 보완함"),
])
check("[정제] 단계 명칭 표기 정리 항목 제거", len(_ch2) == 1)
check("[정제] 명칭 언급이라도 실질 변화(대책 보완)는 유지", "대책" in _ch2[0].description)

# TBM·체크리스트 번호 접두 정규화 (AI가 '1. '을 붙여도 중복 표기 방지)
from models import AssessmentResult as _AR
_ar = _AR(tbm=["1. 산소 농도를 측정한다", "2) 화기감시자를 배치한다", "번호 없는 항목"],
          checklist=["1. 1. 이중 번호 항목"])
check("[정제] TBM 선행 번호 제거", _ar.tbm[0] == "산소 농도를 측정한다"
      and _ar.tbm[1] == "화기감시자를 배치한다" and _ar.tbm[2] == "번호 없는 항목")
check("[정제] 이중 번호('1. 1.')도 제거", _ar.checklist[0] == "이중 번호 항목")

# ---------------------------------------------------------------------------
# [재시도] 5xx 서버 오류 자동 재시도 + 예비 모델 전환 (_generate_with_retry)
# ---------------------------------------------------------------------------
from google.genai.errors import ClientError, ServerError

_sleeps = []
_orig_sleep = ai_service.time.sleep
ai_service.time.sleep = lambda s: _sleeps.append(s)


class _FakeModels:
    """호출 계획(plan)대로 예외를 던지거나 응답을 돌려주는 가짜 모델 클라이언트."""

    def __init__(self, plan):
        self.plan = list(plan)
        self.calls = []  # 호출된 모델명 기록

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        step = self.plan.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class _FakeClient:
    def __init__(self, plan):
        self.models = _FakeModels(plan)


class _FakeResp:
    text = '{"ok": true}'
    candidates = []


def _err_503():
    return ServerError(503, {"error": {"message": "The model is overloaded."}})


# 1) 503 두 번 뒤 성공 → 같은 모델 안에서 재시도로 회복
_fc = _FakeClient([_err_503(), _err_503(), _FakeResp()])
_out = ai_service._call_model(_fc, "sys", "user")
check("[재시도] 503 2회 후 3번째 성공", _out == '{"ok": true}' and len(_fc.models.calls) == 3)
check("[재시도] 재시도 전 대기 (백오프 2s→4s)", _sleeps == [2.0, 4.0])
check("[재시도] 회복 시 기본 모델 유지", set(_fc.models.calls) == {ai_service.DEFAULT_MODEL})

# 2) 기본 모델 3회 모두 503 → 예비 모델로 전환해 성공
_sleeps.clear()
_fc2 = _FakeClient([_err_503(), _err_503(), _err_503(), _FakeResp()])
_out2 = ai_service._call_model(_fc2, "sys", "user")
check("[재시도] 기본 모델 소진 → 예비 모델로 성공",
      _out2 == '{"ok": true}' and _fc2.models.calls[-1] == ai_service.FALLBACK_MODEL)
check("[재시도] 예비 전환 시 총 호출 4회", len(_fc2.models.calls) == 4)

# 3) 전부 503 → 재시도 횟수가 명시된 한국어 오류
_fc3 = _FakeClient([_err_503() for _ in range(6)])
try:
    ai_service._call_model(_fc3, "sys", "user")
    check("[재시도] 전부 실패 → 오류", False)
except ai_service.AIServiceError as e:
    check("[재시도] 전부 실패 → 한국어 안내 (재시도 횟수 포함)",
          "혼잡" in str(e) and "6회" in str(e))
check("[재시도] 전부 실패 시 총 호출 6회 (무한 반복 없음)", len(_fc3.models.calls) == 6)

# 4) 429(한도)·401(키) 오류는 재시도 없이 즉시 한국어 오류 (기존 동작 유지)
for _code, _kw in [(429, "한도"), (401, "인증")]:
    _fce = _FakeClient([ClientError(_code, {"error": {"message": "x"}})])
    try:
        ai_service._call_model(_fce, "sys", "user")
        check(f"[재시도] {_code}는 즉시 오류", False)
    except ai_service.AIServiceError as e:
        check(f"[재시도] {_code}는 재시도 없이 즉시 한국어 오류",
              _kw in str(e) and len(_fce.models.calls) == 1)

ai_service.time.sleep = _orig_sleep

print()
print(f"결과: {len(passed)} PASS / {len(failed)} FAIL")
if key_present:
    print("(참고: .env에 API 키가 있어 '키 없음' 경로 테스트는 생략)")
sys.exit(1 if failed else 0)
