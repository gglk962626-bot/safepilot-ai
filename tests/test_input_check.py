# SafePilot AI 입력정보 확인(추가 확인 권장) 단위 테스트 — API 키 불필요
# 구조: 작업 특성 감지 → 권장 항목 목록 → 현재 입력과 비교 → 미확인 항목만 표시
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


def unconfirmed(work):
    return [it for t in input_check.get_recommended_input_info(work) for it in t["items"]]


def confirmed(work):
    return [it for t in input_check.get_recommended_input_info(work) for it in t["confirmed"]]


def is_ready(review):
    """✅ 완료 메시지 표시 조건 (app.py와 동일한 판정)."""
    return (review["has_input"]
            and review["unconfirmed_count"] == 0
            and not review["general"])


# ---------------------------------------------------------------------------
# 테스트 1 — 프레스 작업 예시: 입력에서 확인된 항목은 제외, 미확인만 표시
# ---------------------------------------------------------------------------
press = W(
    name="금속판 프레스 성형 작업",
    location="금속제품 제조공장 생산라인",
    description="작업자 2명이 프레스 기계를 이용해 금속판을 반복 성형하고 제품을 꺼낸다.",
    equipment="프레스 기계, 금속판, 집게",
    workers="2명",
    notes="생산량이 많아 동일 작업을 장시간 반복한다.",
)
check("[1] 프레스 특성 탐지", "machine_press" in trait_keys(press))
u1, c1 = unconfirmed(press), confirmed(press)
check("[1] 이미 입력된 정보(장소·인원·장비·반복작업)는 확인됨으로 제외",
      {"작업 장소", "작업 인원", "사용 장비", "반복·장시간 작업 여부"} <= set(c1))
check("[1] 미확인 항목만 표시 (방호장치·금형·에너지차단·손끼임 4건)",
      set(u1) == {"방호장치 및 안전장치 종류·작동 상태", "금형 교체·조정 작업 여부",
                  "정비·청소 시 에너지 차단 방법", "손 끼임 방지 작업방법"})
r1 = input_check.review_input(press)
check("[1] 미확인 4건 → 완료 메시지 미표시", not is_ready(r1) and r1["unconfirmed_count"] == 4)

# ---------------------------------------------------------------------------
# 테스트 2 — 입력정보가 일부 빠진 프레스 작업: 빠진 항목이 미확인으로 표시
# ---------------------------------------------------------------------------
press_partial = W(name="프레스 성형 작업", location="생산라인",
                  description="프레스 기계로 금속판을 성형한다.")
u2 = unconfirmed(press_partial)
check("[2] 장비·인원 미입력 → 해당 항목 미확인으로 표시",
      "사용 장비" in u2 and "작업 인원" in u2)
check("[2] 반복작업 언급 없음 → 반복·장시간 작업 여부도 미확인",
      "반복·장시간 작업 여부" in u2)
check("[2] 전체 입력보다 미확인 항목이 많음", len(u2) > len(unconfirmed(press)))

# ---------------------------------------------------------------------------
# 테스트 3 — 정보 보완 후 권장 항목이 실제로 줄어드는지
# ---------------------------------------------------------------------------
press_sup = press.model_copy(update={
    "notes": press.notes + " 광전자식 방호장치 설치, 금형 교체 시 전원 차단 및 잠금장치 적용"})
u3 = unconfirmed(press_sup)
check("[3] 보완된 항목(방호장치·금형·에너지차단) 자동 제거",
      "방호장치 및 안전장치 종류·작동 상태" not in u3
      and "금형 교체·조정 작업 여부" not in u3
      and "정비·청소 시 에너지 차단 방법" not in u3)
check("[3] 실제 미확인 항목만 남음 (손 끼임 방지 1건)", u3 == ["손 끼임 방지 작업방법"])
check("[3] 미확인 1건 남음 → 아직 완료 메시지 미표시",
      not is_ready(input_check.review_input(press_sup)))

# ---------------------------------------------------------------------------
# 테스트 4 — 콜센터 작업
# ---------------------------------------------------------------------------
cc = W(name="콜센터 고객상담", location="본사 고객센터 상담실",
       description="헤드셋으로 전화상담 및 민원 응대를 수행한다.")
check("[4] 콜센터 특성 탐지", "callcenter" in trait_keys(cc))
u4, c4 = unconfirmed(cc), confirmed(cc)
check("[4] 입력에서 확인된 항목(응대 방식·헤드셋) 제외",
      "전화·대면 응대 방식" in c4 and "헤드셋 사용 여부" in c4)
check("[4] 미확인 항목(폭언·폭력, 반복·장시간, 휴게)만 표시",
      set(u4) == {"폭언·폭력 발생 가능성", "반복·장시간 작업 여부", "휴게 및 업무전환 방식"})

# ---------------------------------------------------------------------------
# 테스트 5 — 용접 + 밀폐공간 작업 (복수 특성 + 중복 제거 + 보완 반영)
# ---------------------------------------------------------------------------
weld = W(name="탱크 내부 용접", location="제2도크 블록 내부",
         description="탱크 내부에서 배관 연결부를 용접한다.")
k5 = trait_keys(weld)
check("[5] 용접 + 밀폐공간 동시 탐지", {"hot_work", "confined"} <= k5)
rec5 = input_check.get_recommended_input_info(weld)
all5 = [it for t in rec5 for it in t["items"] + t["confirmed"]]
u5 = unconfirmed(weld)
check("[5] 중복 항목('환기 방법') 1회만 취급", all5.count("환기 방법") == 1)
check("[5] 미확인 항목에 화재감시자·산소측정 포함",
      "화재감시자 배치 여부" in u5 and "산소·유해가스 측정 여부" in u5)
weld_sup = weld.model_copy(update={
    "notes": "이동식 배기팬으로 환기 실시, 산소농도 측정기 배치, 화재감시자 1명 배치"})
u5b = unconfirmed(weld_sup)
check("[5] 보완 후 환기·산소측정·화재감시자 항목 자동 제거",
      "환기 방법" not in u5b and "산소·유해가스 측정 여부" not in u5b
      and "화재감시자 배치 여부" not in u5b)
check("[5] 보완해도 남은 미확인 항목은 유지 (예: 가연물 존재 여부)",
      "가연물 존재 여부" in u5b)

# ---------------------------------------------------------------------------
# 테스트 6 — 미확인 항목이 하나도 없을 때만 완료 메시지
# ---------------------------------------------------------------------------
press_full = press_sup.model_copy(update={
    "notes": press_sup.notes + " 손 끼임 방지를 위해 밀대와 안전수공구 사용"})
r6 = input_check.review_input(press_full)
check("[6] 모든 권장 항목 확인 → 완료 메시지 표시", is_ready(r6))
check("[6] 확인된 항목 수 집계", r6["confirmed_count"] == 8 and r6["unconfirmed_count"] == 0)
plain = W(name="사무실 서류 정리 및 문서고 이관", location="본관 3층 문서고",
          description="보관 연한이 지난 문서를 분류하여 지하 문서고로 옮기고 서가에 정리한다.")
check("[6] 특성 미감지 + 일반 안내 없음 → 완료 메시지 표시",
      is_ready(input_check.review_input(plain)))
check("[6] 미확인 항목이 있으면 완료 메시지 미표시 (프레스 기본 입력)",
      not is_ready(input_check.review_input(press)))

# ---------------------------------------------------------------------------
# 테스트 7 — 부정 표현: 특성 감지에서만 예외 처리
# ---------------------------------------------------------------------------
w7 = W(name="배관 점검", location="기계실", description="배관 상태를 점검한다. 용접 작업을 하지 않음")
check("[7] '용접 작업을 하지 않음' → 용접 특성 미감지", "hot_work" not in trait_keys(w7))
w7b = W(name="설비 점검", location="옥외", description="밀폐공간 출입 없음. 외부에서 육안 점검만 수행")
check("[7] '밀폐공간 출입 없음' → 밀폐공간 특성 미감지", "confined" not in trait_keys(w7b))
w7c = W(name="용접 보수", location="공장동", description="어제는 용접 작업을 하지 않음. 금일 배관 용접 실시")
check("[7] 부정+긍정 혼재 시에는 감지 유지", "hot_work" in trait_keys(w7c))
# 권장 항목 확인 판정에는 부정 예외를 적용하지 않음 — 부정형 언급도 '확인된 정보'
w7d = W(name="탱크 내부 배관 용접", location="제2도크",
        description="탱크 내부 용접. 가연물 없음 확인, 화재감시자 배치하지 않음")
u7d = unconfirmed(w7d)
check("[7] 권장 항목의 부정형 언급('가연물 없음')도 확인된 정보로 제외",
      "가연물 존재 여부" not in u7d and "화재감시자 배치 여부" not in u7d)

# ---------------------------------------------------------------------------
# 테스트 8 — 기타 특성(화학물질·고소·중장비) 미확인 추출
# ---------------------------------------------------------------------------
w8a = W(name="부품 세척 작업", location="세척실",
        description="유기용제 세척제로 금속 부품을 세척한다.")
u8a = unconfirmed(w8a)
check("[8] 화학물질: 물질명·노출 경로 미확인 표시", "물질명" in u8a and "노출 경로" in u8a)
w8b = W(name="지붕 보수", location="창고동",
        description="사다리와 비계를 이용해 지붕 패널을 교체한다.")
u8b = unconfirmed(w8b)
check("[8] 고소작업: 추락방지·안전대 미확인 표시",
      "추락방지시설" in u8b and "안전대 사용 여부" in u8b)
w8c = W(name="자재 하역", location="야적장",
        description="크레인으로 중량물을 인양하여 하역한다.")
u8c = unconfirmed(w8c)
check("[8] 중장비: 신호수·작업반경·취급 중량 미확인 표시",
      "신호수 배치 여부" in u8c and "작업반경" in u8c and "취급 중량" in u8c)
w8d = w8c.model_copy(update={"notes": "신호수 1명 배치, 작업반경 내 출입금지 조치"})
u8d = unconfirmed(w8d)
check("[8] 중장비 보완 후 신호수·작업반경·통제 항목 제거",
      "신호수 배치 여부" not in u8d and "작업반경" not in u8d
      and "작업구역 통제 여부" not in u8d)

# ---------------------------------------------------------------------------
# 안내 전용·빈 상태·API 미호출 보장
# ---------------------------------------------------------------------------
w9 = W(name="용접", location="", description="")
r9 = input_check.review_input(w9)
check("[9] '용접' 한 단어에도 안내 표시 (차단 정보 없음)",
      r9["has_input"] and r9["unconfirmed_count"] > 0
      and "block" not in r9 and "disabled" not in r9)
check("[9] 특성 감지된 짧은 입력에 길이 안내 없음 (길이는 보조 기준)",
      not any("짧습니다" in n for n in input_check.check_input_completeness(
          W(name="x", location="제2도크", description="탱크 내부 용접"))))
r_empty = input_check.review_input(W())
check("[9] 필수 3개 모두 빈 초기 상태 → 영역 미표시", r_empty["has_input"] is False)
check("[9] 선택 필드만 입력해도 필수 3개가 비면 미표시",
      input_check.review_input(W(equipment="크레인"))["has_input"] is False)
n9 = input_check.check_input_completeness(W(name="정리", location="공장", description="정리함"))
check("[9] 짧고 일반적인 입력 → 길이·장소 일반 안내", len(n9) >= 2)

# ---------------------------------------------------------------------------
# 테스트 10 — 유사 단어 오탐 방지 (다른 단어의 일부로 등장하는 키워드)
# ---------------------------------------------------------------------------
check("[10] '소화기 점검' → 화기작업 미감지",
      "hot_work" not in trait_keys(W(name="사무실 정리",
                                     description="사무실 소화기 위치 점검 및 비품 정리")))
w10a = W(name="전화상담", description="전화기 헤드셋으로 고객응대 상담 업무")
check("[10] '전화기' → 화기작업 미감지 + 콜센터는 감지",
      trait_keys(w10a) == {"callcenter"})
check("[10] '전화기' 언급도 응대 방식 확인으로 인정",
      "전화·대면 응대 방식" in confirmed(w10a))
check("[10] '가스켓 교체 후 용접' → 사용 가스 정보는 여전히 미확인",
      "사용 가스 또는 장비" in unconfirmed(
          W(name="배관 용접", description="배관 플랜지 가스켓 교체 후 용접")))
check("[10] '철골 구조물' 언급 → 구조·구출 방법은 여전히 미확인",
      "구조·구출 방법" in unconfirmed(
          W(name="탱크 점검", description="탱크 내부 철골 구조물 점검")))
check("[10] '피스톤 인양' → 취급 중량은 여전히 미확인",
      "취급 중량" in unconfirmed(
          W(name="엔진 정비", description="크레인으로 엔진 피스톤 인양 작업")))
check("[10] '정지상태 확인 후 용접' → 작업 높이는 여전히 미확인",
      "작업 높이" in unconfirmed(
          W(name="용접", description="설비 정지상태 확인 후 용접 작업")))
check("[10] '피트니스 센터 청소' → 밀폐공간 미감지",
      "confined" not in trait_keys(W(name="청소", description="피트니스 센터 바닥 청소 작업")))
check("[10] '이용제한 안내문 부착' → 화학물질 미감지",
      "chemical" not in trait_keys(W(name="안내문 부착",
                                     description="출입 이용제한 안내문 부착 작업")))
check("[10] '작업대기 후 하역' → 고소작업 미감지",
      "height" not in trait_keys(W(name="하역", description="화물차 도착까지 작업대기 후 하역")))
check("[10] 절 경계 부정('크레인, 신호수 없음')은 크레인 감지 유지",
      "heavy" in trait_keys(W(name="자재 인양", description="크레인 사용, 신호수 없음")))
check("[10] 소문자 'loto 절차 적용'도 에너지 차단 확인으로 인정",
      "정비·청소 시 에너지 차단 방법" in confirmed(
          W(name="프레스 정비", description="프레스 정비 시 loto 절차 적용")))

src = open(os.path.join(os.path.dirname(__file__), "..", "input_check.py"), encoding="utf-8").read()
check("[11] input_check에 Gemini/AI 서비스 임포트 없음",
      "genai" not in src and "import ai_service" not in src and "generate_content" not in src)

print()
print(f"결과: {len(passed)} PASS / {len(failed)} FAIL")
sys.exit(1 if failed else 0)
