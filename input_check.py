"""SafePilot AI - 입력정보 확인 (추가 확인 권장 안내)

작업정보 입력 단계에서 작업 특성상 추가로 확인하면 좋은 정보를 미리 안내하는
코드 기반 입력 안전장치.

원칙:
- Gemini API 를 호출하지 않는다. 순수 Python 로컬 규칙으로만 동작한다.
- 위험성평가 생성을 차단하지 않으며, 기존 평가 결과·위험도 계산에 관여하지 않는다.
- 키워드 탐지는 '안내용'일 뿐, 위험범주 분류나 위험도 판단 기능이 아니다.
"""

from __future__ import annotations

from typing import Dict, List

from models import WorkInput

# 키워드 뒤 일정 범위에 이 표현이 있으면 해당 매칭은 부정 표현으로 간주한다.
# (예: "용접 작업을 하지 않음") 복잡한 자연어 처리는 도입하지 않는다.
_NEGATION_TOKENS = ["하지 않", "하지않", "않음", "않는", "않고", "없음", "없다", "없는", "미실시", "제외"]
_NEGATION_WINDOW = 12  # 키워드 뒤 몇 글자까지 부정 표현을 살펴볼지

# 작업 특성별 탐지 규칙: 키워드는 작업명·장소·내용·장비·특이사항에서 찾는다.
INPUT_RULES: List[dict] = [
    {
        "key": "hot_work",
        "label": "용접·절단·화기작업",
        "keywords": ["용접", "용단", "절단", "화기", "불꽃", "그라인더"],
        "recommend": [
            "용접·절단 방식",
            "사용 가스 또는 장비",
            "환기 방법",
            "작업 높이",
            "가연물 존재 여부",
            "화재감시자 배치 여부",
        ],
    },
    {
        "key": "confined",
        "label": "밀폐공간",
        "keywords": ["탱크", "맨홀", "저장조", "피트", "밀폐공간", "배관 내부", "사일로"],
        "recommend": [
            "밀폐공간 해당 여부",
            "출입구 확보 상태",
            "환기 방법",
            "산소·유해가스 측정 여부",
            "감시인 배치 여부",
            "작업 인원",
            "구조·구출 방법",
        ],
    },
    {
        "key": "chemical",
        "label": "화학물질 취급",
        "keywords": ["화학물질", "용제", "세척제", "유기용제", "약품", "알칼리", "산성", "산세척"],
        "recommend": [
            "물질명",
            "취급량",
            "노출 경로",
            "환기 방법",
            "착용 보호구",
            "혼합·가열 여부",
        ],
    },
    {
        "key": "height",
        "label": "고소작업",
        "keywords": ["사다리", "비계", "고소", "높은 곳", "작업대", "지붕", "천장", "옥상"],
        "recommend": [
            "작업 높이",
            "작업발판 또는 비계 상태",
            "추락방지시설",
            "안전대 사용 여부",
            "작업구역 하부 통제 여부",
        ],
    },
    {
        "key": "heavy",
        "label": "중량물·중장비 작업",
        "keywords": ["크레인", "지게차", "굴착기", "중장비", "인양", "중량물", "호이스트"],
        "recommend": [
            "사용 장비",
            "취급 중량",
            "인양 방법",
            "작업반경",
            "신호수 배치 여부",
            "작업구역 통제 여부",
        ],
    },
    {
        "key": "callcenter",
        "label": "콜센터·고객응대",
        "keywords": ["콜센터", "상담", "고객응대", "민원", "전화상담", "고객센터", "감정노동"],
        "recommend": [
            "전화·대면 응대 방식",
            "폭언·폭력 발생 가능성",
            "헤드셋 사용 여부",
            "반복·장시간 작업 여부",
            "휴게 및 업무전환 방식",
        ],
    },
]

# 지나치게 일반적인 작업 장소 표현 (단독 입력 시 구체화 안내)
_GENERIC_LOCATIONS = {"현장", "공장", "사업장", "회사", "실내", "실외", "작업장"}


def _combined_text(work: WorkInput) -> str:
    """특성 탐지에 사용할 입력 텍스트 (작업명·장소·내용·장비·특이사항)."""
    return " ".join([work.name, work.location, work.description, work.equipment, work.notes])


def _keyword_hit(text: str, keyword: str) -> bool:
    """키워드가 부정 표현 없이 등장하는지 확인한다.

    키워드의 모든 등장 위치 뒤 일정 범위에 부정 표현이 있으면 매칭에서 제외한다.
    한 번이라도 부정 없이 등장하면 True.
    """
    start = 0
    while True:
        i = text.find(keyword, start)
        if i < 0:
            return False
        window = text[i + len(keyword): i + len(keyword) + _NEGATION_WINDOW]
        if not any(neg in window for neg in _NEGATION_TOKENS):
            return True
        start = i + len(keyword)


def detect_work_traits(work: WorkInput) -> List[dict]:
    """입력 텍스트에서 감지된 작업 특성 규칙 목록을 반환한다 (복수 감지 가능)."""
    text = _combined_text(work)
    return [rule for rule in INPUT_RULES
            if any(_keyword_hit(text, kw) for kw in rule["keywords"])]


def get_recommended_input_info(work: WorkInput) -> List[dict]:
    """감지된 특성별 추가 확인 권장 정보를 반환한다.

    반환: [{"key", "label", "items"}] — 여러 특성에 중복된 항목(예: '환기 방법')은
    먼저 감지된 특성에만 한 번 표시한다.
    """
    seen: set = set()
    out: List[dict] = []
    for rule in detect_work_traits(work):
        items = [it for it in rule["recommend"] if it not in seen]
        seen.update(items)
        if items:
            out.append({"key": rule["key"], "label": rule["label"], "items": items})
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

    # 특성상 장비 정보가 중요한 작업인데 사용 장비가 비어 있는 경우
    equip_needed = {"hot_work", "heavy", "chemical"}
    if not work.equipment.strip() and any(r["key"] in equip_needed for r in traits):
        notes.append("사용 장비가 비어 있습니다 — 장비를 입력하면 장비-보호구 적합성 "
                     "검토가 더 정확해집니다.")
    return notes


def review_input(work: WorkInput) -> Dict:
    """입력정보 확인 결과를 반환한다 (UI 표시용).

    - has_input: 필수 3개(작업명·장소·내용)가 모두 비어 있으면 False → 영역 미표시
    - traits: 특성별 추가 확인 권장 정보 (중복 제거)
    - general: 일반 확인 안내
    안내 전용이며 위험성평가 생성을 차단하지 않는다.
    """
    has_input = bool(work.name.strip() or work.location.strip() or work.description.strip())
    if not has_input:
        return {"has_input": False, "traits": [], "general": []}
    return {
        "has_input": True,
        "traits": get_recommended_input_info(work),
        "general": check_input_completeness(work),
    }
