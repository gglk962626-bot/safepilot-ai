"""SafePilot AI - 데모 모드 데이터

API 키가 없거나 API 장애 시에도 서비스 흐름을 그대로 체험할 수 있도록
미리 작성된 고품질 샘플 결과를 제공한다.

시나리오 데이터는 assets/demo_*.json 에 새 스키마(개선 전·후 위험도,
판단 근거, 대책 위계, 20개 위험범주)로 저장되어 있으며, 여기서 로드한다.

- 데모 1 (welding): 조선소 밀폐공간 용접
- 데모 2 (callcenter): 콜센터 상담 업무 (감정노동·폭력·상해 위험 분류 검증용)
"""

from __future__ import annotations

import json
import os

from models import AssessmentResult, ReviewResult, WorkInput, sanitize_changes

_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _load(filename: str) -> dict:
    path = os.path.join(_ASSET_DIR, filename)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"데모 데이터 파일이 없습니다: {path} — 배포 시 assets 폴더의 demo_*.json 이 "
            "저장소에 함께 포함되어야 합니다."
        ) from e


_SCENARIOS: dict[str, dict] = {
    "welding": _load("demo_welding.json"),
    "callcenter": _load("demo_callcenter.json"),
    # 실제 API 모드로 생성한 결과를 그대로 저장한 백업 데모 (reference_ids 포함)
    "food": _load("demo_food.json"),
    "painting": _load("demo_painting.json"),
}

SCENARIO_LABELS = {
    "welding": "조선소 밀폐공간 용접",
    "callcenter": "콜센터 상담 업무",
    "food": "식품 제조공장 설비 정비·세척",
    "painting": "선박 블록 도장·세척 작업",
}
DEFAULT_SCENARIO = "welding"


def get_sample_input(key: str = DEFAULT_SCENARIO) -> WorkInput:
    """시나리오의 샘플 작업 정보를 반환한다."""
    return WorkInput.model_validate(_SCENARIOS[key]["sample_input"])


def get_demo_first(key: str = DEFAULT_SCENARIO) -> AssessmentResult:
    """데모용 1차 결과를 Pydantic 모델로 반환한다."""
    return AssessmentResult.model_validate(_SCENARIOS[key]["first"])


def get_demo_review(key: str = DEFAULT_SCENARIO) -> ReviewResult:
    """데모용 2차 검토 결과를 Pydantic 모델로 반환한다.

    저장 당시 실제 API 산출물(JSON)은 그대로 두고, 표시 단계에서만
    시스템 필드 정리 항목 제거·내부 필드명 한국어 치환을 적용한다.
    """
    d = _SCENARIOS[key]
    review = ReviewResult.model_validate(
        {"findings": d["findings"], "changes": d["changes"], "final": d["final"]}
    )
    review.changes = sanitize_changes(review.changes)
    return review


def get_demo_reference_ids(key: str = DEFAULT_SCENARIO) -> list:
    """데모 JSON에 저장된 참고 안전자료 id 목록을 반환한다.

    생성 당시 실제 1차 AI에 전달된 reference_id를 그대로 담은 것이며,
    키가 없는 기존 JSON에서는 빈 목록을 반환한다 (하위 호환).
    """
    return list(_SCENARIOS.get(key, {}).get("reference_ids", []) or [])


# --- 하위 호환 (기존 코드·테스트가 참조하는 이름) ---
SAMPLE_INPUT = get_sample_input()
_FIRST = _SCENARIOS["welding"]["first"]
_REVIEW = {"findings": _SCENARIOS["welding"]["findings"],
           "changes": _SCENARIOS["welding"]["changes"]}
_FINAL = _SCENARIOS["welding"]["final"]
