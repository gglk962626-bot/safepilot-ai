"""SafePilot AI - 입력정보 확인 (추가 확인 권장 안내)

작업 특성별 '권장 확인 정보 목록'과 현재 입력정보를 비교하여,
아직 입력에서 확인되지 않은 항목만 안내하는 코드 기반 입력 안전장치.

동작 구조:
  작업 특성 감지 → 권장 항목 목록 → 현재 입력과 비교 → 미확인 항목만 표시
  (사용자가 정보를 보완하면 해당 항목은 자동으로 목록에서 빠진다)

원칙:
- Gemini API 를 호출하지 않는다. 순수 Python 로컬 규칙으로만 동작한다.
- 위험성평가 생성을 차단하지 않으며, 기존 평가 결과·위험도 계산에 관여하지 않는다.
- 키워드 탐지는 '안내용'일 뿐, 위험범주 분류나 위험도 판단 기능이 아니다.
"""

from __future__ import annotations

from typing import Dict, List

from models import WorkInput

# 키워드 뒤 일정 범위에 이 표현이 있으면 해당 매칭은 부정 표현으로 간주한다.
# (예: "용접 작업을 하지 않음") — 작업 특성 '감지'에만 적용한다.
# 권장 항목 '확인' 판정에는 적용하지 않는다: "화재감시자 배치 없음"처럼
# 부정형이라도 해당 정보가 입력에서 확인된 것이므로 항목은 해소된 것으로 본다.
_NEGATION_TOKENS = ["하지 않", "하지않", "않음", "않는", "않고", "없음", "없다", "없는", "미실시", "제외"]
_NEGATION_WINDOW = 12  # 키워드 뒤 몇 글자까지 부정 표현을 살펴볼지

# 권장 항목 1건: item(표시 문구) / keywords(입력 텍스트에 있으면 확인됨)
#               / fields(해당 입력 필드가 채워져 있으면 확인됨)
# keywords·fields 중 하나라도 충족되면 '이미 확인된 정보'로 보고 표시에서 제외한다.
INPUT_RULES: List[dict] = [
    {
        "key": "hot_work",
        "label": "용접·절단·화기작업",
        "keywords": ["용접", "용단", "절단", "화기", "불꽃", "그라인더"],
        "recommend": [
            {"item": "용접·절단 방식", "keywords": ["아크", "티그", "TIG", "미그", "MIG", "CO2", "가스용접", "산소절단", "플라즈마"]},
            {"item": "사용 가스 또는 장비", "keywords": ["가스", "LPG", "아세틸렌", "산소", "용접기"], "fields": ["equipment"]},
            {"item": "환기 방법", "keywords": ["환기", "배기", "송풍", "급기"]},
            {"item": "작업 높이", "keywords": ["높이", "미터", "고소"]},
            {"item": "가연물 존재 여부", "keywords": ["가연물", "가연성", "인화", "방화포", "불꽃받이", "도장"]},
            {"item": "화재감시자 배치 여부", "keywords": ["화재감시", "화기감시", "감시자"]},
        ],
    },
    {
        "key": "confined",
        "label": "밀폐공간",
        "keywords": ["탱크", "맨홀", "저장조", "피트", "밀폐공간", "배관 내부", "사일로"],
        "recommend": [
            {"item": "밀폐공간 해당 여부", "keywords": ["밀폐공간"]},
            {"item": "출입구 확보 상태", "keywords": ["출입구", "개구부", "맨홀 개방"]},
            {"item": "환기 방법", "keywords": ["환기", "배기", "송풍", "급기"]},
            {"item": "산소·유해가스 측정 여부", "keywords": ["산소농도", "가스농도", "농도 측정", "측정기", "산소 측정"]},
            {"item": "감시인 배치 여부", "keywords": ["감시인", "감시자", "화기감시"]},
            {"item": "작업 인원", "fields": ["workers"]},
            {"item": "구조·구출 방법",
             "keywords": ["구조 방법", "구출", "구조대", "구조 계획", "송기마스크", "비상 대응"]},
        ],
    },
    {
        "key": "chemical",
        "label": "화학물질 취급",
        "keywords": ["화학물질", "용제", "세척제", "유기용제", "약품", "알칼리", "산성", "산세척"],
        "recommend": [
            {"item": "물질명", "keywords": ["MSDS", "물질명", "톨루엔", "아세톤", "시너", "신너", "황산", "염산", "가성소다", "메탄올"]},
            {"item": "취급량", "keywords": ["취급량", "리터", "kg", "㎏", "톤"]},
            {"item": "노출 경로", "keywords": ["흡입", "피부", "노출 경로", "접촉"]},
            {"item": "환기 방법", "keywords": ["환기", "배기", "송풍", "급기"]},
            {"item": "착용 보호구", "keywords": ["보호구", "마스크", "장갑", "보안경", "방독", "앞치마"]},
            {"item": "혼합·가열 여부", "keywords": ["혼합", "가열", "희석"]},
        ],
    },
    {
        "key": "height",
        "label": "고소작업",
        "keywords": ["사다리", "비계", "고소", "높은 곳", "작업대", "지붕", "천장", "옥상"],
        "recommend": [
            {"item": "작업 높이", "keywords": ["높이", "미터", "1.8m", "2m", "3m"]},
            {"item": "작업발판 또는 비계 상태", "keywords": ["발판", "안전난간", "비계 설치", "아웃트리거"]},
            {"item": "추락방지시설", "keywords": ["추락방지", "안전난간", "안전망", "덮개"]},
            {"item": "안전대 사용 여부", "keywords": ["안전대", "안전벨트", "그네식", "부착설비"]},
            {"item": "작업구역 하부 통제 여부", "keywords": ["하부 통제", "출입 통제", "통제구역", "출입금지"]},
        ],
    },
    {
        "key": "heavy",
        "label": "중량물·중장비 작업",
        "keywords": ["크레인", "지게차", "굴착기", "중장비", "인양", "중량물", "호이스트"],
        "recommend": [
            {"item": "사용 장비", "fields": ["equipment"]},
            {"item": "취급 중량", "keywords": ["취급 중량", "톤", "kg", "㎏"]},
            {"item": "인양 방법", "keywords": ["줄걸이", "슬링", "와이어", "인양 방법", "체결", "결속"]},
            {"item": "작업반경", "keywords": ["작업반경", "반경", "선회"]},
            {"item": "신호수 배치 여부", "keywords": ["신호수", "유도자", "신호 체계"]},
            {"item": "작업구역 통제 여부", "keywords": ["통제", "출입금지", "구획", "펜스"]},
        ],
    },
    {
        "key": "machine_press",
        "label": "프레스·기계 끼임위험 작업",
        "keywords": ["프레스", "전단기", "절곡기", "사출성형", "롤러기", "성형기"],
        "recommend": [
            {"item": "작업 장소", "fields": ["location"]},
            {"item": "작업 인원", "fields": ["workers"]},
            {"item": "사용 장비", "fields": ["equipment"]},
            {"item": "반복·장시간 작업 여부", "keywords": ["반복", "장시간", "연속 작업"]},
            {"item": "방호장치 및 안전장치 종류·작동 상태",
             "keywords": ["방호장치", "안전장치", "광전자", "양수조작", "안전블록", "게이트가드", "덮개"]},
            {"item": "금형 교체·조정 작업 여부", "keywords": ["금형"]},
            {"item": "정비·청소 시 에너지 차단 방법",
             "keywords": ["전원 차단", "전원차단", "에너지 차단", "잠금장치", "LOTO", "기동장치 잠금"]},
            {"item": "손 끼임 방지 작업방법",
             "keywords": ["끼임 방지", "밀대", "안전수공구", "자동 이송", "자동 배출", "노터치"]},
        ],
    },
    {
        "key": "callcenter",
        "label": "콜센터·고객응대",
        "keywords": ["콜센터", "상담", "고객응대", "민원", "전화상담", "고객센터", "감정노동"],
        "recommend": [
            {"item": "전화·대면 응대 방식", "keywords": ["전화", "대면", "채팅", "비대면", "방문"]},
            {"item": "폭언·폭력 발생 가능성", "keywords": ["폭언", "폭력", "강성", "성희롱", "위협"]},
            {"item": "헤드셋 사용 여부", "keywords": ["헤드셋", "이어셋", "이어폰"]},
            {"item": "반복·장시간 작업 여부", "keywords": ["반복", "장시간", "8시간", "연속"]},
            {"item": "휴게 및 업무전환 방식", "keywords": ["휴게", "휴식", "업무전환", "교대"]},
        ],
    },
]

# 지나치게 일반적인 작업 장소 표현 (단독 입력 시 구체화 안내)
_GENERIC_LOCATIONS = {"현장", "공장", "사업장", "회사", "실내", "실외", "작업장"}

# 다른 단어의 일부로 흔히 등장해 오탐을 일으키는 표현 — 매칭 전에 가려낸다.
# (예: '소화기'의 '화기', '가스켓'의 '가스', '피스톤'의 '톤', '작업대기'의 '작업대')
_MASK_PATTERNS = [
    ("전화기", "전화■"),   # '화기' 오탐 방지 — '전화' 언급(콜센터 응대 방식)은 유지
    ("소화기", "■■■"),
    ("가스켓", "■■■"),
    ("피스톤", "■■■"),
    ("피트니스", "■■■■"),
    ("사용제한", "■■■■"),  # '용제' 오탐 방지
    ("이용제한", "■■■■"),
    ("작업대기", "■■■■"),
]

# 부정 표현 탐색 창은 문장·절 경계에서 끊는다 —
# "크레인, 신호수 없음"의 '없음'은 크레인이 아니라 신호수에 대한 부정이다.
_CLAUSE_STOPS = (",", ".", "。", ";", "\n")


def _combined_text(work: WorkInput) -> str:
    """탐지·확인에 사용할 입력 텍스트 (작업명·장소·내용·장비·인원·특이사항 전체).

    오탐 유발 표현을 가리고 소문자로 변환한다 (LOTO/loto, CO2/co2 등 대소문자 무관).
    """
    text = " ".join([work.name, work.location, work.description,
                     work.equipment, work.workers, work.notes])
    for src, dst in _MASK_PATTERNS:
        text = text.replace(src, dst)
    return text.lower()


def _keyword_hit(text: str, keyword: str) -> bool:
    """키워드가 부정 표현 없이 등장하는지 확인한다 (작업 특성 감지용).

    키워드의 모든 등장 위치 뒤 일정 범위(같은 절 안)에 부정 표현이 있으면
    매칭에서 제외한다. 한 번이라도 부정 없이 등장하면 True.
    """
    keyword = keyword.lower()
    start = 0
    while True:
        i = text.find(keyword, start)
        if i < 0:
            return False
        window = text[i + len(keyword): i + len(keyword) + _NEGATION_WINDOW]
        for stop in _CLAUSE_STOPS:
            cut = window.find(stop)
            if cut >= 0:
                window = window[:cut]
        if not any(neg in window for neg in _NEGATION_TOKENS):
            return True
        start = i + len(keyword)


def detect_work_traits(work: WorkInput) -> List[dict]:
    """입력 텍스트에서 감지된 작업 특성 규칙 목록을 반환한다 (복수 감지 가능)."""
    text = _combined_text(work)
    return [rule for rule in INPUT_RULES
            if any(_keyword_hit(text, kw) for kw in rule["keywords"])]


def _item_confirmed(work: WorkInput, text: str, spec: dict) -> bool:
    """권장 항목이 현재 입력에서 이미 확인되는지 판정한다.

    - keywords: 입력 텍스트에 하나라도 포함되면 확인 (부정형 언급도 '확인된 정보'로 본다)
    - fields: 해당 입력 필드가 채워져 있으면 확인
    """
    for kw in spec.get("keywords", []):
        if kw.lower() in text:
            return True
    for field in spec.get("fields", []):
        if str(getattr(work, field, "") or "").strip():
            return True
    return False


def get_recommended_input_info(work: WorkInput) -> List[dict]:
    """감지된 특성별 '아직 확인되지 않은' 권장 항목만 반환한다.

    반환: [{"key", "label", "items"(미확인), "confirmed"(확인된 항목명)}]
    여러 특성에 중복된 항목(예: '환기 방법')은 먼저 감지된 특성에만 한 번 표시한다.
    """
    text = _combined_text(work)
    seen: set = set()
    out: List[dict] = []
    for rule in detect_work_traits(work):
        unconfirmed, confirmed = [], []
        for spec in rule["recommend"]:
            item = spec["item"]
            if item in seen:
                continue
            seen.add(item)
            (confirmed if _item_confirmed(work, text, spec) else unconfirmed).append(item)
        if unconfirmed or confirmed:
            out.append({"key": rule["key"], "label": rule["label"],
                        "items": unconfirmed, "confirmed": confirmed})
    return out


def check_input_completeness(work: WorkInput) -> List[str]:
    """입력값에 대한 일반 확인 안내를 반환한다.

    문자 수는 보조 기준으로만 사용한다 — 특성 키워드가 감지된 짧은 입력
    (예: '탱크 내부 용접')은 구체적 정보로 보고 길이 안내를 하지 않는다.
    """
    notes: List[str] = []
    traits = detect_work_traits(work)

    desc = work.description.strip()
    if desc and len(desc) < 10 and not traits:
        notes.append("작업 내용이 짧습니다 — 작업 순서·방법을 조금 더 구체적으로 적으면 "
                     "평가의 현장 적합성이 높아집니다.")

    loc = work.location.strip()
    if loc and (loc in _GENERIC_LOCATIONS or len(loc) <= 2):
        notes.append("작업 장소가 일반적입니다 — 동·층·구역 등 구체적인 위치를 적으면 "
                     "장소 특성이 평가에 반영됩니다.")
    return notes


def review_input(work: WorkInput) -> Dict:
    """입력정보 확인 결과를 반환한다 (UI 표시용).

    - has_input: 필수 3개(작업명·장소·내용)가 모두 비어 있으면 False → 영역 미표시
    - traits: 특성별 권장 항목 비교 결과 (items=미확인만, confirmed=확인됨)
    - unconfirmed_count / confirmed_count: 전체 미확인·확인 항목 수
    - general: 일반 확인 안내
    미확인 항목이 하나도 없고 일반 안내도 없을 때만 '시작 가능' 상태로 표시한다.
    안내 전용이며 위험성평가 생성을 차단하지 않는다.
    """
    has_input = bool(work.name.strip() or work.location.strip() or work.description.strip())
    if not has_input:
        return {"has_input": False, "traits": [], "general": [],
                "unconfirmed_count": 0, "confirmed_count": 0}
    traits = get_recommended_input_info(work)
    general = check_input_completeness(work)
    return {
        "has_input": True,
        "traits": traits,
        "general": general,
        "unconfirmed_count": sum(len(t["items"]) for t in traits),
        "confirmed_count": sum(len(t["confirmed"]) for t in traits),
    }
