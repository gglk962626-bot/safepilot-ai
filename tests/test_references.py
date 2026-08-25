# SafePilot AI 안전정보 Reference 단위 테스트 — API 키 불필요
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import prompts
import safety_references as sr
from models import WorkInput

passed = []
failed = []


def check(name, cond):
    (passed if cond else failed).append(name)
    print(("PASS" if cond else "FAIL"), "-", name)


def W(**kw):
    return WorkInput(**kw)


def ids(selected):
    return [s["reference"]["reference_id"] for s in selected]


FOOD = W(
    name="식품 제조공장 컨베이어·절단기 라인 정비 및 세척 작업",
    location="OO식품 제조공장 가공라인",
    description="벨트 컨베이어로 이송되는 원료를 절단기로 절단·가공하고, "
                "당일 작업 종료 후 컨베이어와 절단기 내부를 정비·세척한다.",
    equipment="벨트 컨베이어, 식품용 절단기, 고압 세척기",
    workers="작업자 3명",
    notes="야간에 설비 내부 청소와 정비를 병행한다.",
)
WELD = W(name="탱크 내부 배관 용접", location="제2도크 블록 내부",
         description="밀폐공간인 탱크 내부에서 배관 연결부를 용접한다.")
CALL = W(name="콜센터 고객상담", location="본사 고객센터 상담실",
         description="헤드셋으로 전화상담 및 민원 응대를 수행한다. 고객 폭언 발생 가능.")

# ---------------------------------------------------------------------------
# [1] 데이터 무결성 — 실존 확인 자료만, 필수 필드 완비
# ---------------------------------------------------------------------------
# 도장·세척 4건 추가로 15~16건 (식품4 + 조선4 + 도장·세척4 + 콜센터4)
check("[1] Reference 15~16건 수록", 15 <= len(sr.REFERENCES) <= 16)
required = ["reference_id", "title", "source", "document_type", "official_url",
            "applicable_keywords", "summary", "safety_points", "usage_note"]
check("[1] 모든 자료에 필수 필드 존재",
      all(all(k in r and r[k] for k in required) for r in sr.REFERENCES))
check("[1] official_url은 KOSHA 공식 도메인",
      all("kosha.or.kr" in r["official_url"] for r in sr.REFERENCES))
check("[1] reference_id 중복 없음",
      len({r["reference_id"] for r in sr.REFERENCES}) == len(sr.REFERENCES))

# ---------------------------------------------------------------------------
# [2] 키워드 매칭·관련도 점수
# ---------------------------------------------------------------------------
text = sr._combined_text(FOOD)
conv = sr.get_reference("conveyor-safety")
s_conv, m_conv = sr.score_reference(text, conv)
check("[2] 핵심 키워드 일치 시 높은 점수", s_conv >= sr._CORE_WEIGHT and "컨베이어" in m_conv)
s_weld, _ = sr.score_reference(text, sr.get_reference("welding-fire-prevention"))
check("[2] 무관한 자료는 핵심 점수 미달", s_weld < sr._MIN_SCORE)
check("[2] 핵심(10) > 관련(3) 가중치", sr._CORE_WEIGHT > sr._RELATED_WEIGHT)

# ---------------------------------------------------------------------------
# [3] 상위 3건 제한 / 중복 제거 / 관련 없음 → 빈 목록
# ---------------------------------------------------------------------------
sel_food = sr.select_references(FOOD)
check("[3] 상위 최대 3건 제한", 1 <= len(sel_food) <= 3)
check("[3] 동일 자료 중복 선택 없음", len(set(ids(sel_food))) == len(sel_food))
check("[3] 점수 내림차순 정렬",
      all(sel_food[i]["score"] >= sel_food[i+1]["score"] for i in range(len(sel_food)-1)))
sel_none = sr.select_references(W(name="사무실 서류 정리", location="본관 3층",
                                  description="보관 문서를 분류하여 서가에 정리한다."))
check("[3] 관련 자료 없으면 빈 목록", sel_none == [])
check("[3] 빈 입력 → 빈 목록", sr.select_references(W()) == [])

# ---------------------------------------------------------------------------
# [4] 식품 제조 신규 입력 — 관련 자료 선정
# ---------------------------------------------------------------------------
food_ids = ids(sel_food)
check("[4] 식품 입력 → 컨베이어·식품기계·LOTO 계열 선정",
      "conveyor-safety" in food_ids and "loto-energy-isolation" in food_ids)
check("[4] 식품 입력에 콜센터·용접 자료 미선정",
      not any(i in food_ids for i in
              ["welding-fire-prevention", "emotional-labor-health-guide",
               "callcenter-stress-ops"]))

# ---------------------------------------------------------------------------
# [5] 조선소 입력 / 콜센터 입력
# ---------------------------------------------------------------------------
weld_ids = ids(sr.select_references(WELD))
check("[5] 조선소 입력 → 용접 화재예방 + 밀폐공간 선정",
      "welding-fire-prevention" in weld_ids and "confined-space-program" in weld_ids)
call_ids = ids(sr.select_references(CALL))
check("[5] 콜센터 입력 → 감정노동·콜센터 자료 선정",
      "emotional-labor-health-guide" in call_ids and "callcenter-stress-ops" in call_ids)
check("[5] 콜센터 입력에 기계·화기 자료 미선정",
      not any(i in call_ids for i in ["conveyor-safety", "welding-fire-prevention"]))

# ---------------------------------------------------------------------------
# [6] fail-open — 데이터 오류에도 평가 생성 흐름을 막지 않음
# ---------------------------------------------------------------------------
_orig = sr.REFERENCES
try:
    sr.REFERENCES = _orig + [{"reference_id": "broken", "applicable_keywords": None},
                             {"title": "필드 누락 자료"}]
    sel_broken = sr.select_references(FOOD)
    check("[6] 일부 자료 필드 누락에도 정상 선정", 1 <= len(sel_broken) <= 3
          and "broken" not in ids(sel_broken))
    sr.REFERENCES = "완전히 잘못된 타입"
    check("[6] 데이터 전체 오류 → 빈 목록 (fail-open)", sr.select_references(FOOD) == [])
    check("[6] 오류 상태에서도 프롬프트 블록은 빈 문자열", sr.build_prompt_block(None) == "")
finally:
    sr.REFERENCES = _orig

# ---------------------------------------------------------------------------
# [7] 1차 프롬프트 전달 / 2차 프롬프트 미전달
# ---------------------------------------------------------------------------
block = sr.build_prompt_block(sel_food)
check("[7] 프롬프트 블록에 자료명·출처·요약·핵심 안전정보 포함",
      "[참고 안전자료]" in block and "자료명:" in block and "출처:" in block
      and "핵심 안전정보:" in block)
check("[7] 블록에 점수 미결정 원칙 명시", "위험도 점수" in block and "결정하지 않는다" in block)
p1 = prompts.build_first_pass_user(FOOD, block)
check("[7] 1차 프롬프트에 참고 안전자료 전달됨", "[참고 안전자료]" in p1
      and sel_food[0]["reference"]["title"] in p1)
p1_none = prompts.build_first_pass_user(FOOD, "")
check("[7] 블록 없으면 1차 프롬프트는 기존과 동일 구조", "[참고 안전자료]" not in p1_none)
p2 = prompts.build_review_user(FOOD, "{\"hazards\": []}")
check("[7] 2차 프롬프트에 Reference 원문 미전달", "[참고 안전자료]" not in p2
      and "핵심 안전정보" not in p2)

# ---------------------------------------------------------------------------
# [8] Reference 0건/1건이어도 흐름 정상
# ---------------------------------------------------------------------------
check("[8] 0건 → 빈 블록 → 프롬프트 무변화", sr.build_prompt_block([]) == "")
one = sel_food[:1]
b1 = sr.build_prompt_block(one)
check("[8] 1건만 선정돼도 블록 정상 생성", "1. 자료명:" in b1 and "2. 자료명:" not in b1)

# ---------------------------------------------------------------------------
# [11] 도장·세척 Reference (신규 4건)
# ---------------------------------------------------------------------------
PAINT_DEMO = W(
    name="선박 블록 내부 도장 및 세척·정비 작업",
    location="OO조선소 제3도크",
    description="블록 내부에서 도장작업 후 도장설비 및 작업구역을 세척하고, 설비 정비를 수행한다.",
    equipment="스프레이건, 환기설비, 세척장비, 전동공구",
    workers="도장공 2명, 보조 1명",
    notes="유기용제 및 세척제를 사용하며 블록 내부에서 작업한다.",
)
u11 = ids(sr.select_references(PAINT_DEMO))
check("[11] 도장·세척 데모 입력 → 도장 화재·폭발 규정 선정", "painting-fire-explosion" in u11)
check("[11] 선박 블록 내부 도장 → 선박 도장 지침 선정", "ship-painting-safety" in u11)
check("[11] 세척제 사용 → 세척작업 OPS 선정", "cleaning-3-measures-ops" in u11)
check("[11] 상위 3건 = 도장·선박도장·세척 (관련도순)", len(u11) == 3)

paint_only = ids(sr.select_references(
    W(name="건물 외벽 도장 작업", location="본관 외벽",
      description="스프레이로 외벽 도장을 실시한다.", equipment="스프레이건, 도료")))
check("[11] 일반 도장 입력 → 도장 규정 선정, 선박 지침 미선정",
      "painting-fire-explosion" in paint_only and "ship-painting-safety" not in paint_only)

clean_only = ids(sr.select_references(
    W(name="부품 세척 작업", location="세척실",
      description="세척조에서 세척제로 금속 부품을 탈지·세척한다.")))
check("[11] 세척 입력 → 세척 OPS 선정", "cleaning-3-measures-ops" in clean_only)

msds_in = ids(sr.select_references(
    W(name="화학물질 취급 전 MSDS 확인", location="자재창고",
      description="신규 입고된 화학물질의 물질안전보건자료(MSDS)를 확인하고 경고표지를 부착한다.")))
check("[11] MSDS·화학물질 입력 → 화학물질정보 시스템 선정 가능", "kosha-msds-info" in msds_in)

PLAIN_WORK = W(name="사무실 서류 정리", location="본관 3층",
               description="보관 문서를 분류하여 서가에 정리한다.")
check("[11] 무관 작업(서류 정리)에 신규 자료 미선정",
      not any(i in ids(sr.select_references(PLAIN_WORK)) for i in
              ["painting-fire-explosion", "ship-painting-safety",
               "cleaning-3-measures-ops", "kosha-msds-info"]))

# 기존 시나리오 보호: 식품 상위 3건에 신규 자료가 억지 진입하지 않음
food_after = ids(sr.select_references(FOOD))
check("[11] 기존 식품 입력 상위 3건 유지 (컨베이어·LOTO 계열)",
      "conveyor-safety" in food_after and "loto-energy-isolation" in food_after
      and "painting-fire-explosion" not in food_after)
call_after = ids(sr.select_references(CALL))
check("[11] 기존 콜센터 입력에 신규 자료 미선정",
      not any(i in call_after for i in
              ["painting-fire-explosion", "ship-painting-safety",
               "cleaning-3-measures-ops", "kosha-msds-info"]))
# G-117 보건관리 제외 원칙: usage_note가 화재·폭발/작업관리 범위로 한정되고 중독 표현 없음
g117 = sr.get_reference("ship-painting-safety")
check("[11] G-117 usage_note에 중독·건강장해 표현 없음",
      "중독" not in g117["usage_note"] and "건강장해" not in g117["usage_note"]
      and "화재" in g117["usage_note"])
# MSDS 표현 과장 금지
msds_ref = sr.get_reference("kosha-msds-info")
_msds_blob = msds_ref["summary"] + msds_ref["usage_note"] + " ".join(msds_ref["safety_points"])
check("[11] MSDS 자료에 '실시간 분석' 등 과장 표현 없음",
      "실시간" not in _msds_blob and "자동 산정" not in _msds_blob
      and msds_ref["document_type"] == "화학물질정보 시스템")

# ---------------------------------------------------------------------------
# [9] Reference 매칭 경로에 AI 호출 없음
# ---------------------------------------------------------------------------
src = open(os.path.join(os.path.dirname(__file__), "..", "safety_references.py"),
           encoding="utf-8").read()
check("[9] safety_references에 Gemini/AI 임포트 없음",
      "genai" not in src and "import ai_service" not in src
      and "generate_content" not in src)

# ---------------------------------------------------------------------------
# [10] FullResult 하위 호환 — reference_ids 없는 기존 데이터
# ---------------------------------------------------------------------------
from models import FullResult, AssessmentResult, ReviewResult
fr = FullResult(work_input=FOOD, first=AssessmentResult(), review=ReviewResult())
check("[10] reference_ids 미지정 시 빈 목록 기본값", fr.reference_ids == [])
check("[10] getattr 방어 호환", getattr(fr, "reference_ids", []) == [])
import demo_data
check("[10] 기존 데모 JSON에 reference_ids 없어도 오류 없음",
      isinstance(demo_data.get_demo_reference_ids("welding"), list))

print()
print(f"결과: {len(passed)} PASS / {len(failed)} FAIL")
sys.exit(1 if failed else 0)
