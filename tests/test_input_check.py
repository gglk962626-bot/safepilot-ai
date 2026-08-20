# SafePilot AI 입력정보 확인(추가 확인 권장) 단위 테스트 — API 키 불필요
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import input_check
from models import WorkInput

passed = []
failed = []


def check(name, cond):
    (passed if cond else failed).append(name)
    print(("PASS" if cond else "FAIL"), "-", name)


def W(**kw):
    return WorkInput(**kw)


def trait_keys(work):
    return {r["key"] for r in input_check.detect_work_traits(work)}


# ---------------------------------------------------------------------------
# 테스트 1 — 일반적인 충분한 입력: 권장 없음 + 생성 가능 상태
# ---------------------------------------------------------------------------
w1 = W(name="사무실 서류 정리 및 문서고 이관", location="본관 3층 문서고",
       description="보관 연한이 지난 문서를 분류하여 지하 문서고로 옮기고 서가에 정리한다.")
r1 = input_check.review_input(w1)
check("[1] 특성 미감지 시 권장 정보 없음", r1["has_input"] and not r1["traits"])
check("[1] 일반 안내도 없음 (충분한 입력)", not r1["general"])

# ---------------------------------------------------------------------------
# 테스트 2 — 용접 + 밀폐공간 (탱크 내부 용접)
# ---------------------------------------------------------------------------
w2 = W(name="탱크 내부 용접", location="제2도크", description="탱크 내부에서 배관 용접")
k2 = trait_keys(w2)
check("[2] 용접 규칙 탐지", "hot_work" in k2)
check("[2] 밀폐공간 규칙 탐지", "confined" in k2)
rec2 = input_check.get_recommended_input_info(w2)
all_items2 = [it for t in rec2 for it in t["items"]]
check("[2] 관련 권장정보 생성 (화재감시자·산소측정 포함)",
      "화재감시자 배치 여부" in all_items2 and "산소·유해가스 측정 여부" in all_items2)

# ---------------------------------------------------------------------------
# 테스트 3 — 화학물질
# ---------------------------------------------------------------------------
w3 = W(name="부품 세척 작업", location="세척실", description="유기용제 세척제로 금속 부품을 세척한다.")
check("[3] 화학물질 규칙 탐지", "chemical" in trait_keys(w3))
rec3 = [it for t in input_check.get_recommended_input_info(w3) for it in t["items"]]
check("[3] 화학물질 권장정보 (물질명·노출 경로)", "물질명" in rec3 and "노출 경로" in rec3)

# ---------------------------------------------------------------------------
# 테스트 4 — 고소작업 / 중장비
# ---------------------------------------------------------------------------
w4a = W(name="지붕 보수", location="창고동", description="사다리와 비계를 이용해 지붕 패널을 교체한다.")
check("[4] 고소작업 규칙 탐지", "height" in trait_keys(w4a))
rec4a = [it for t in input_check.get_recommended_input_info(w4a) for it in t["items"]]
check("[4] 고소작업 권장정보 (추락방지·안전대)",
      "추락방지시설" in rec4a and "안전대 사용 여부" in rec4a)

w4b = W(name="자재 하역", location="야적장", description="크레인으로 중량물을 인양하여 하역한다.")
check("[4] 중장비 규칙 탐지", "heavy" in trait_keys(w4b))
rec4b = [it for t in input_check.get_recommended_input_info(w4b) for it in t["items"]]
check("[4] 중장비 권장정보 (신호수·작업반경)",
      "신호수 배치 여부" in rec4b and "작업반경" in rec4b)

# ---------------------------------------------------------------------------
# 테스트 5 — 콜센터·고객응대
# ---------------------------------------------------------------------------
w5 = W(name="콜센터 고객상담", location="상담실", description="헤드셋으로 전화상담 및 민원 응대")
check("[5] 콜센터 규칙 탐지", "callcenter" in trait_keys(w5))
rec5 = [it for t in input_check.get_recommended_input_info(w5) for it in t["items"]]
check("[5] 콜센터 권장정보 (폭언·폭력, 헤드셋, 휴게)",
      "폭언·폭력 발생 가능성" in rec5 and "헤드셋 사용 여부" in rec5
      and "휴게 및 업무전환 방식" in rec5)

# ---------------------------------------------------------------------------
# 테스트 6 — 매우 짧은 입력: 안내만 하고 차단하지 않음
# ---------------------------------------------------------------------------
w6 = W(name="용접", location="", description="")
r6 = input_check.review_input(w6)
check("[6] '용접' 한 단어에도 안내 표시", r6["has_input"] and len(r6["traits"]) >= 1)
check("[6] 필수값 검증은 기존 로직 그대로 (input_check는 차단 정보를 반환하지 않음)",
      "block" not in r6 and "disabled" not in r6)
check("[6] 특성 감지된 짧은 입력에 길이 안내 없음 (길이는 보조 기준)",
      not any("짧습니다" in n for n in
              input_check.check_input_completeness(
                  W(name="x", location="제2도크", description="탱크 내부 용접"))))

# ---------------------------------------------------------------------------
# 테스트 7 — 부정 표현: 과도한 안내 방지
# ---------------------------------------------------------------------------
w7 = W(name="배관 점검", location="기계실", description="배관 상태를 점검한다. 용접 작업을 하지 않음")
check("[7] '용접 작업을 하지 않음' → 용접 권장정보 미표시", "hot_work" not in trait_keys(w7))
w7b = W(name="설비 점검", location="옥외", description="밀폐공간 출입 없음. 외부에서 육안 점검만 수행")
check("[7] '밀폐공간 출입 없음' → 밀폐공간 권장정보 미표시", "confined" not in trait_keys(w7b))
# 부정과 긍정이 함께 있으면 감지 유지 (한 번이라도 부정 없이 등장)
w7c = W(name="용접 보수", location="공장동", description="어제는 용접 작업을 하지 않음. 금일 배관 용접 실시")
check("[7] 부정+긍정 혼재 시에는 감지 유지", "hot_work" in trait_keys(w7c))

# ---------------------------------------------------------------------------
# 테스트 8 — 복수 특성 + 중복 항목 제거
# ---------------------------------------------------------------------------
w8 = W(name="탱크 내부 용접", location="제2도크 블록 내부",
       description="탱크 내부에서 배관 연결부를 용접한다.")
rec8 = input_check.get_recommended_input_info(w8)
labels8 = [t["label"] for t in rec8]
all8 = [it for t in rec8 for it in t["items"]]
check("[8] 용접 + 밀폐공간 안내 동시 표시",
      "용접·절단·화기작업" in labels8 and "밀폐공간" in labels8)
check("[8] 중복 항목('환기 방법') 1회만 표시", all8.count("환기 방법") == 1)
check("[8] 전체 항목 중복 없음", len(all8) == len(set(all8)))

# ---------------------------------------------------------------------------
# 빈 입력 상태 / 일반 안내 / API 미호출 보장
# ---------------------------------------------------------------------------
r_empty = input_check.review_input(W())
check("[9] 필수 3개 모두 빈 초기 상태 → 영역 미표시", r_empty["has_input"] is False)
check("[9] 선택 필드만 입력해도 필수 3개가 비면 미표시",
      input_check.review_input(W(equipment="크레인"))["has_input"] is False)

n10 = input_check.check_input_completeness(W(name="정리", location="공장", description="정리함"))
check("[10] 짧고 일반적인 입력 → 길이·장소 안내", len(n10) >= 2)
n10b = input_check.check_input_completeness(
    W(name="용접", location="A동 2층", description="철골 보강재 용접", equipment=""))
check("[10] 화기작업 + 장비 미입력 → 장비 안내", any("사용 장비" in n for n in n10b))

# API 미호출 보장: 모듈 소스에 AI 관련 임포트가 없어야 함
src = open(os.path.join(os.path.dirname(__file__), "..", "input_check.py"), encoding="utf-8").read()
check("[15] input_check에 Gemini/AI 서비스 임포트 없음",
      "genai" not in src and "import ai_service" not in src and "generate_content" not in src)

print()
print(f"결과: {len(passed)} PASS / {len(failed)} FAIL")
sys.exit(1 if failed else 0)
