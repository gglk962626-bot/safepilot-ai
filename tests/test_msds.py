# SafePilot AI 화학물질 MSDS 캐시·식별 단위 테스트 — API 키 불필요
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import input_check
import msds_data
import prompts
from models import WorkInput, FullResult, AssessmentResult, ReviewResult

passed = []
failed = []


def check(name, cond):
    (passed if cond else failed).append(name)
    print(("PASS" if cond else "FAIL"), "-", name)


def W(**kw):
    return WorkInput(**kw)


def names(work):
    return [c["name"] for c in msds_data.identify_chemicals(work)]


# ---------------------------------------------------------------------------
# [1] 캐시 무결성 — KOSHA 실측 검증값과 일치
# ---------------------------------------------------------------------------
check("[1] 지원 물질 6종 수록", len(msds_data.MSDS_CHEMICALS) == 6)
_expected_cas = {"톨루엔": "108-88-3", "크실렌": "1330-20-7", "아세톤": "67-64-1",
                 "디클로로메탄": "75-09-2", "이소프로필 알코올": "67-63-0",
                 "메틸 에틸 케톤": "78-93-3"}
check("[1] CAS 번호가 KOSHA 검증값과 일치",
      all(msds_data.get_chemical(n)["cas"] == cas for n, cas in _expected_cas.items()))
_required = ["name", "cas", "chem_id", "revision", "synonyms", "signal",
             "classification", "hazard_statements", "precautions"]
check("[1] 전 물질 필수 필드 완비",
      all(all(k in c and c[k] for k in _required) for c in msds_data.MSDS_CHEMICALS))
check("[1] 디클로로메탄 발암성 1B 원문 반영",
      any("발암성 구분1B" in x for x in msds_data.get_chemical("디클로로메탄")["classification"]))

# ---------------------------------------------------------------------------
# [2] 식별 — 명확한 물질명에서만 (AI 추정 없음)
# ---------------------------------------------------------------------------
w_ac = W(name="설비 세척", location="세척실", description="아세톤과 IPA를 사용하여 세척함")
check("[2] '아세톤과 IPA 사용' → 2종 식별",
      set(names(w_ac)) == {"아세톤", "이소프로필 알코올"})
check("[2] 소문자 영문 동의어 식별", "아세톤" in names(
    W(name="세척", location="실험실", description="acetone으로 부품을 닦는다")))
check("[2] 염화메틸렌 동의어 → 디클로로메탄 식별", "디클로로메탄" in names(
    W(name="탈지", location="세척조", description="염화메틸렌 세척제를 사용한다")))

# ---------------------------------------------------------------------------
# [3] 성분 불명 표현은 특정 물질로 추정하지 않음
# ---------------------------------------------------------------------------
w_paint = W(name="선박 블록 도장 작업", location="제3도크",
            description="에어리스 스프레이를 이용한 도장 작업", notes="주변 작업자 출입 통제")
check("[3] '도장'만 입력 → 식별 0 (임의 추정 없음)", names(w_paint) == [])
check("[3] '도료와 신너를 사용' → 식별 0 (혼합물 미확정)", names(
    W(name="도장", location="공장", description="도료와 신너를 사용함")) == [])
check("[3] 무관 작업 → 식별 0", names(
    W(name="서류 정리", location="사무실", description="문서를 분류한다")) == [])

# ---------------------------------------------------------------------------
# [4] 부족 정보 알림 — MSDS 단어 없이 작업 맥락만으로 안내
# ---------------------------------------------------------------------------
r_paint = input_check.review_input(w_paint)
check("[4] 도장 작업 → 화학물질 확인 고정 안내 표시",
      any("실제 사용하는 화학물질" in n for n in r_paint["general"]))
check("[4] 도장 특성 규칙 감지",
      any(t["key"] == "painting" for t in input_check.detect_work_traits(w_paint)
          if isinstance(t, dict)) or
      "painting" in [t["key"] for t in input_check.detect_work_traits(w_paint)])
w_paint2 = w_paint.model_copy(update={"notes": w_paint.notes + " 아세톤과 IPA를 사용함"})
r_paint2 = input_check.review_input(w_paint2)
check("[4] 물질명 입력 후 → 고정 안내 소멸 (식별로 전환)",
      not any("실제 사용하는 화학물질" in n for n in r_paint2["general"]))
check("[4] 콜센터 입력 → 화학물질 안내 없음",
      not any("실제 사용하는 화학물질" in n for n in input_check.review_input(
          W(name="콜센터 상담", location="상담실", description="전화상담 업무"))["general"]))

# ---------------------------------------------------------------------------
# [5] 1차 전달 / 2차 미전달 / 위험도 불개입
# ---------------------------------------------------------------------------
chems = msds_data.identify_chemicals(w_ac)
block = msds_data.build_msds_block(chems)
check("[5] MSDS 블록에 물질·CAS·유해문구·예방조치 포함",
      "아세톤" in block and "67-64-1" in block and "H225" in block and "예방·보호조치" in block)
check("[5] 블록에 점수 미결정·추정 금지 지시 포함",
      "위험도 점수" in block and "결정하지 않는다" in block and "추정하지 마라" in block)
p1 = prompts.build_first_pass_user(w_ac, block)
check("[5] 1차 프롬프트에 MSDS 참고정보 전달", "[화학물질 MSDS 참고정보" in p1)
p2 = prompts.build_review_user(w_ac, "{}")
check("[5] 2차 프롬프트에 MSDS 원문 미전달", "MSDS 참고정보" not in p2)
check("[5] 식별 0 → 빈 블록 (프롬프트 불변)", msds_data.build_msds_block([]) == "")
src = open(os.path.join(os.path.dirname(__file__), "..", "msds_data.py"), encoding="utf-8").read()
check("[5] msds_data에 Gemini/AI 임포트 없음",
      "genai" not in src and "import ai_service" not in src)
check("[5] 캐시에 위험도 점수 산정 로직 없음",
      "risk_score" not in src and "likelihood" not in src and "severity" not in src)

# ---------------------------------------------------------------------------
# [6] fail-open · 하위 호환
# ---------------------------------------------------------------------------
check("[6] 잘못된 입력 → 빈 목록", msds_data.identify_chemicals(None) == [])
check("[6] 블록 오류 입력 → 빈 문자열", msds_data.build_msds_block(None) == "")
fr = FullResult(work_input=w_ac, first=AssessmentResult(), review=ReviewResult())
check("[6] detected_chemicals 기본값 빈 목록 (기존 데이터 호환)",
      fr.detected_chemicals == [] and getattr(fr, "detected_chemicals", []) == [])

# ---------------------------------------------------------------------------
# [7] 기존 데모 4종 무영향 (식별 0 → 카드·전달 없음)
# ---------------------------------------------------------------------------
import demo_data
for key in ("welding", "callcenter", "food"):
    w = demo_data.get_sample_input(key)
    check(f"[7] {key} 데모 샘플 → 물질 식별 0 (결과 불변)", names(w) == [])
# 도장·세척 데모는 특이사항에 아세톤을 명시 → MSDS 카드 시연용으로 식별됨
check("[7] painting 데모 샘플 → 아세톤 식별 (MSDS 카드 표시)",
      names(demo_data.get_sample_input("painting")) == ["아세톤"])

print()
print(f"결과: {len(passed)} PASS / {len(failed)} FAIL")
sys.exit(1 if failed else 0)
