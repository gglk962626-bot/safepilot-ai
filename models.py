"""SafePilot AI - 데이터 모델 정의 (Pydantic)

AI가 반환한 JSON을 검증하고, 위험도 점수를 Python에서 직접 계산한다.
- likelihood(발생 가능성), severity(피해 심각도)는 1~5만 허용
- risk_score = likelihood x severity (AI 값은 신뢰하지 않고 여기서 재계산)
- 개선 후(잔여) 위험도: residual_score = residual_likelihood x residual_severity (역시 코드 계산)
- improvement_required / needs_review 는 AI 출력이 아니라 코드가 산정하는 상태값이다.
"""

from __future__ import annotations

import math
import re
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator, model_validator

# 위험도 구간 정의: (구간 상한, 등급명)
RISK_BANDS = [
    (4, "낮음"),
    (9, "보통"),
    (16, "높음"),
    (25, "매우 높음"),
]

# 등급별 색상 (화면/PDF 공용)
RISK_COLORS = {
    "낮음": "#2e7d32",       # 녹색
    "보통": "#f9a825",       # 노랑
    "높음": "#ef6c00",       # 주황
    "매우 높음": "#c62828",  # 빨강
}

# 2차 AI가 반드시 점검해야 하는 검토 범주 (20개)
REVIEW_CATEGORIES = [
    "추락", "낙하 및 비래", "협착 및 끼임", "충돌", "전도", "감전",
    "화재 및 폭발", "유해가스 및 화학물질", "소음 및 진동", "근골격계 부담",
    "고온 및 저온", "차량 및 중장비", "밀폐공간", "작업자 간 의사소통",
    "작업구역 통제", "작업허가", "개인보호구",
    "감정노동·심리사회적 위험", "폭력·상해 위험", "생물학적 위험",
]
CATEGORY_COUNT = len(REVIEW_CATEGORIES)  # 20

# 최종 위험성 판단 기준 기본값 (SafePilot 기본 설정값 — 법정 기준 아님)
DEFAULT_RISK_THRESHOLD = 4

# 감소대책 위계 (Hierarchy of Controls) — 데이터 계층은 영문 snake_case,
# 표시 계층은 한국어 라벨 매핑을 사용한다.
CONTROL_TYPES = ["elimination", "substitution", "engineering", "administrative", "ppe"]
CONTROL_TYPE_LABELS = {
    "elimination": "제거",
    "substitution": "대체",
    "engineering": "공학적",
    "administrative": "관리적",
    "ppe": "PPE",
}
_LABEL_TO_CONTROL = {v: k for k, v in CONTROL_TYPE_LABELS.items()}
# 심각도 하향을 허용하는 상위 수준 대책
HIGHER_CONTROLS = {"elimination", "substitution", "engineering"}

# TBM에 코드가 항상 고정 삽입하는 항목 (2차 AI가 삭제할 수 없음)
FIXED_TBM_ITEM = "본 위험성평가 결과에 대한 근로자 의견 청취"


def compute_risk_score(likelihood: int, severity: int) -> int:
    """위험도 점수 = 발생 가능성 x 피해 심각도 (Python에서 직접 계산)."""
    return int(likelihood) * int(severity)


def risk_level_from_score(score: int) -> str:
    """점수를 위험도 등급으로 변환한다."""
    for upper, name in RISK_BANDS:
        if score <= upper:
            return name
    return "매우 높음"


def _clamp_1_to_5(value) -> int:
    """AI가 범위를 벗어난 값을 주더라도 1~5 사이로 보정한다."""
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        v = 3  # 해석 불가 시 중간값
    return max(1, min(5, v))


class WorkInput(BaseModel):
    """사용자가 입력한 작업 정보."""

    name: str = ""            # 작업명
    location: str = ""        # 작업 장소
    description: str = ""     # 작업 내용
    equipment: str = ""       # 사용 장비
    workers: str = ""         # 작업 인원
    notes: str = ""           # 특이사항

    def missing_required(self) -> List[str]:
        """필수 입력값 중 비어 있는 항목명을 반환한다."""
        missing = []
        if not self.name.strip():
            missing.append("작업명")
        if not self.location.strip():
            missing.append("작업 장소")
        if not self.description.strip():
            missing.append("작업 내용")
        return missing


class ControlMeasure(BaseModel):
    """감소대책 1건 (Hierarchy of Controls 유형 포함)."""

    control_type: str = Field(default="administrative", description="대책 위계 유형")
    description: str = Field(default="", description="대책 내용")

    @model_validator(mode="before")
    @classmethod
    def _accept_plain_string(cls, v):
        # 구버전 데이터/편집 입력 호환: 문자열이면 "[라벨] 내용" 접두를 해석한다.
        if isinstance(v, str):
            text = v.strip()
            m = re.match(r"^\[([^\]]{1,10})\]\s*(.*)$", text)
            if m and m.group(1).strip() in _LABEL_TO_CONTROL:
                return {"control_type": _LABEL_TO_CONTROL[m.group(1).strip()],
                        "description": m.group(2).strip()}
            return {"control_type": "administrative", "description": text}
        return v

    @field_validator("control_type", mode="before")
    @classmethod
    def _normalize_type(cls, v):
        s = str(v or "").strip().lower()
        if s in CONTROL_TYPES:
            return s
        # 한국어 라벨로 들어온 경우 매핑
        if str(v or "").strip() in _LABEL_TO_CONTROL:
            return _LABEL_TO_CONTROL[str(v).strip()]
        return "administrative"  # 허용 외 값은 관리적 대책으로 보정

    @property
    def label(self) -> str:
        return CONTROL_TYPE_LABELS.get(self.control_type, "관리적")

    @property
    def display(self) -> str:
        return f"[{self.label}] {self.description}"


class HazardItem(BaseModel):
    """위험요인 1건."""

    step: str = Field(default="", description="작업 단계")
    category: str = Field(default="기타", description="위험 분류")
    hazard: str = Field(default="", description="위험요인")
    cause: str = Field(default="", description="원인")
    damage: str = Field(default="", description="예상 피해")
    likelihood: int = Field(default=3, description="발생 가능성 (1~5)")
    severity: int = Field(default=3, description="피해 심각도 (1~5)")
    measures: List[ControlMeasure] = Field(default_factory=list, description="감소대책")
    ppe: List[str] = Field(default_factory=list, description="개인보호구")
    # --- 개선 후(잔여) 위험성: AI 생성 (1~5) ---
    residual_likelihood: int = Field(default=3, description="개선 후 발생 가능성 (1~5)")
    residual_severity: int = Field(default=3, description="개선 후 피해 심각도 (1~5)")
    # --- 판단 근거: AI 생성 (각 1문장) ---
    basis_likelihood: str = Field(default="", description="발생 가능성 판단 근거 (개선 전)")
    basis_severity: str = Field(default="", description="피해 심각도 판단 근거 (개선 전)")
    residual_basis_likelihood: str = Field(default="", description="개선 후 발생 가능성 판단 근거")
    residual_basis_severity: str = Field(default="", description="개선 후 피해 심각도 판단 근거")
    # --- 코드 산정 상태값: AI 응답 스키마에서 제외되며 코드가 세팅한다 ---
    improvement_required: bool = Field(default=False, description="기준 초과 여부 (코드 산정)")
    needs_review: bool = Field(default=False, description="AI 검증 미통과 — 수동 검토 필요 (코드 산정)")
    needs_review_reason: str = Field(default="", description="검수 필요 사유 (코드 기록)")

    @model_validator(mode="before")
    @classmethod
    def _default_residuals(cls, data):
        # AI가 residual 값을 누락하면 '개선 없음(=개선 전과 동일)'으로 간주한다.
        # (기본값 3을 쓰면 개선 전보다 커질 수 있어 규칙 위반이 생기므로 여기서 보정)
        # 편집 모드의 빈 셀은 pandas NaN 으로 들어오므로 NaN 도 누락으로 취급한다.
        def _missing(v):
            return v is None or v == "" or (isinstance(v, float) and math.isnan(v))

        if isinstance(data, dict):
            if _missing(data.get("residual_likelihood")):
                data["residual_likelihood"] = data.get("likelihood", 3)
            if _missing(data.get("residual_severity")):
                data["residual_severity"] = data.get("severity", 3)
        return data

    @field_validator("likelihood", "severity", "residual_likelihood", "residual_severity", mode="before")
    @classmethod
    def _validate_scale(cls, v):
        return _clamp_1_to_5(v)

    @field_validator("measures", mode="before")
    @classmethod
    def _ensure_measures(cls, v):
        if v is None:
            return []
        if isinstance(v, (str, dict)):
            return [v]
        return list(v)

    @field_validator("ppe", mode="before")
    @classmethod
    def _ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return list(v)

    # --- 개선 전 위험도 (코드 계산) ---
    @property
    def risk_score(self) -> int:
        return compute_risk_score(self.likelihood, self.severity)

    @property
    def risk_level(self) -> str:
        return risk_level_from_score(self.risk_score)

    # --- 개선 후 잔여 위험도 (코드 계산) ---
    @property
    def residual_score(self) -> int:
        return compute_risk_score(self.residual_likelihood, self.residual_severity)

    @property
    def residual_level(self) -> str:
        return risk_level_from_score(self.residual_score)

    def only_admin_ppe(self) -> bool:
        """감소대책이 관리적·PPE 유형으로만 구성되었는지 (상위 수준 대책 검토 필요 표시용)."""
        if not self.measures:
            return False
        return all(m.control_type not in HIGHER_CONTROLS for m in self.measures)

    def rule_violations(self, enforce_severity_rule: bool = True) -> List[str]:
        """코드 레벨 검증 규칙 위반 목록을 반환한다 (없으면 빈 리스트)."""
        v: List[str] = []
        if self.residual_score > self.risk_score:
            v.append("개선 후 위험도 점수가 개선 전보다 높음")
        if enforce_severity_rule and self.residual_severity < self.severity:
            if not any(m.control_type in HIGHER_CONTROLS for m in self.measures):
                v.append("제거·대체·공학적 대책 없이 심각도를 하향함")
        return v


class NoHazardStep(BaseModel):
    """유의미한 위험요인이 없는 작업단계 (사유 포함)."""

    step: str = Field(default="", description="작업 단계")
    reason: str = Field(default="", description="사유")


class AssessmentResult(BaseModel):
    """1차 AI 위험성평가 결과 (또는 검토 후 최종 결과)."""

    work_overview: str = Field(default="", description="작업 개요 요약")
    work_steps: List[str] = Field(default_factory=list, description="작업 세부 단계")
    hazards: List[HazardItem] = Field(default_factory=list, description="위험요인 목록")
    no_hazard_steps: List[NoHazardStep] = Field(default_factory=list,
                                                description="유의미한 위험요인 없음 단계")
    ppe_list: List[str] = Field(default_factory=list, description="전체 개인보호구")
    tbm: List[str] = Field(default_factory=list, description="작업 전 TBM 항목")
    checklist: List[str] = Field(default_factory=list, description="작업 전 체크리스트")

    @field_validator("work_steps", "ppe_list", "tbm", "checklist", mode="before")
    @classmethod
    def _ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return list(v)

    @field_validator("no_hazard_steps", mode="before")
    @classmethod
    def _ensure_nhs(cls, v):
        if v is None:
            return []
        return list(v)

    @property
    def max_risk_score(self) -> int:
        return max((h.risk_score for h in self.hazards), default=0)

    @property
    def max_risk_level(self) -> str:
        return risk_level_from_score(self.max_risk_score) if self.hazards else "-"

    def count_by_level(self) -> dict:
        counts = {"낮음": 0, "보통": 0, "높음": 0, "매우 높음": 0}
        for h in self.hazards:
            counts[h.risk_level] = counts.get(h.risk_level, 0) + 1
        return counts

    @property
    def needs_review_count(self) -> int:
        return sum(1 for h in self.hazards if h.needs_review)

    @property
    def improvement_required_count(self) -> int:
        return sum(1 for h in self.hazards if h.improvement_required)


class HazardPatch(BaseModel):
    """검증 실패 항목 재생성 응답 (AI → 코드)."""

    hazards: List[HazardItem] = Field(default_factory=list)
    no_hazard_steps: List[NoHazardStep] = Field(default_factory=list)


class ReviewFinding(BaseModel):
    """2차 AI 검토 결과 - 범주별 점검 내용."""

    category: str = Field(default="", description="검토 범주")
    status: str = Field(default="적정", description="적정 / 보완 / 해당없음")
    comment: str = Field(default="", description="검토 의견")

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v):
        s = str(v or "").strip()
        if "보완" in s or "누락" in s or "수정" in s:
            return "보완"
        if "해당" in s or "무관" in s:
            return "해당없음"
        return "적정"


class ChangeItem(BaseModel):
    """검토 전후 변경사항 1건."""

    action: str = Field(default="추가", description="추가 / 수정")
    target: str = Field(default="", description="변경 대상 영역")
    description: str = Field(default="", description="변경 내용 설명")


# ---------------------------------------------------------------------------
# 변경사항(changes) 표시 정제
# - 2차 AI가 시스템 자동 계산 필드의 정리 작업을 '변경사항'으로 보고하는 경우가
#   있어, 사용자에게 무의미한 항목은 제거하고 내부 필드명은 한국어로 치환한다.
# - 위험성평가 내용 자체(hazards·근거·대책 등)는 건드리지 않는다.
# ---------------------------------------------------------------------------

# 코드가 자체 계산·관리하는 필드 (AI가 정리했다고 보고해도 사용자에게 무의미)
_SYSTEM_FIELD_TOKENS = [
    "risk_score", "risk_level", "residual_score", "residual_level",
    "improvement_required", "needs_review_reason", "needs_review",
    "needs_review_count", "improvement_required_count",
    "max_risk_score", "max_risk_level", "reference_ids",
]
# 필드 '정리 작업' 서술을 나타내는 표현 (시스템 필드 토큰과 함께 나오면 제거)
_FIELD_CLEANUP_HINTS = ["필드", "키", "스키마", "자동 계산", "자체 계산", "시스템", "속성"]

# 내부 필드명 → 사용자용 한국어 표현 (제거가 아닌 치환 대상)
_FIELD_LABELS = {
    "no_hazard_steps": "위험요인 없는 단계",
    "work_steps": "작업 단계",
    "hazards": "위험요인 목록",
    "residual_basis_likelihood": "개선 후 가능성 판단 근거",
    "residual_basis_severity": "개선 후 심각도 판단 근거",
    "basis_likelihood": "가능성 판단 근거",
    "basis_severity": "심각도 판단 근거",
    "residual_likelihood": "개선 후 발생 가능성",
    "residual_severity": "개선 후 피해 심각도",
    "likelihood": "발생 가능성",
    "severity": "피해 심각도",
    "control_type": "대책 유형",
    "measures": "감소대책",
    "checklist": "체크리스트",
    "damage": "예상 피해",
    "hazard": "위험요인",
    "cause": "원인",
    "category": "위험 분류",
    "ppe": "개인보호구",
    "tbm": "TBM",
    "step": "작업 단계",
    # 시스템 필드가 '치환' 경로로 남는 경우의 안전망
    "risk_score": "위험도 점수",
    "risk_level": "위험도 등급",
    "residual_score": "개선 후 위험도 점수",
    "residual_level": "개선 후 위험도 등급",
    "improvement_required": "개선 필요 여부",
    "needs_review_reason": "검수 필요 사유",
    "needs_review": "검수 필요 여부",
}


def _replace_field_names(text: str) -> str:
    """텍스트 안의 내부 필드명을 한국어 표현으로 치환한다 (긴 이름 우선)."""
    for key in sorted(_FIELD_LABELS, key=len, reverse=True):
        if key in text:
            text = text.replace(key, _FIELD_LABELS[key])
    return text


def sanitize_changes(changes: List["ChangeItem"]) -> List["ChangeItem"]:
    """사용자에게 무의미한 시스템 필드 정리 항목을 제거하고, 남는 항목의
    내부 필드명은 한국어로 치환한다. 실패 시 원본을 그대로 반환한다 (fail-open).
    """
    try:
        out: List[ChangeItem] = []
        for c in changes or []:
            blob = f"{c.target} {c.description}"
            has_system = any(t in blob for t in _SYSTEM_FIELD_TOKENS)
            has_cleanup = any(h in blob for h in _FIELD_CLEANUP_HINTS)
            if has_system and has_cleanup:
                continue  # 시스템 계산 필드 정리 보고 → 사용자 표시에서 제외
            new_target = _replace_field_names(c.target)
            new_desc = _replace_field_names(c.description)
            if new_target != c.target or new_desc != c.description:
                c = ChangeItem(action=c.action, target=new_target, description=new_desc)
            out.append(c)
        return out
    except Exception:
        return changes if isinstance(changes, list) else []

    @field_validator("action", mode="before")
    @classmethod
    def _normalize_action(cls, v):
        s = str(v or "").strip()
        return "수정" if "수정" in s or "변경" in s else "추가"


class ReviewResult(BaseModel):
    """2차 AI 교차검토 결과 전체."""

    findings: List[ReviewFinding] = Field(default_factory=list)
    changes: List[ChangeItem] = Field(default_factory=list)
    final: AssessmentResult = Field(default_factory=AssessmentResult)


class FullResult(BaseModel):
    """앱에서 사용하는 최종 묶음 결과."""

    work_input: WorkInput
    first: AssessmentResult          # 1차 생성 결과
    review: ReviewResult             # 2차 검토 결과 (final 포함)
    is_demo: bool = False            # 데모 모드 여부
    generated_at: str = ""           # 생성 일시 문자열
    edited: bool = False             # 책임자가 결과를 직접 수정했는지 여부
    threshold: int = DEFAULT_RISK_THRESHOLD  # 최종 위험성 판단 기준 (사용자 설정)
    # 1차 AI에 실제 전달된 참고 안전자료 id (없으면 빈 목록 — 위험도 계산과 무관)
    reference_ids: List[str] = Field(default_factory=list)
    # 작업정보에서 식별되어 MSDS 요약이 1차 AI에 전달된 물질명 (위험도 계산과 무관)
    detected_chemicals: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 최종 위험성 판단 기준 적용 (코드 산정)
# ---------------------------------------------------------------------------

def apply_threshold(result: AssessmentResult, threshold: int) -> None:
    """개선 후 위험도가 기준을 초과하면 improvement_required=True 로 코드가 세팅한다.

    AI가 이 값을 출력하더라도 여기서 무조건 덮어쓴다.
    """
    for h in result.hazards:
        h.improvement_required = h.residual_score > int(threshold)


# ---------------------------------------------------------------------------
# 작업단계 번호 유틸리티 (완전성 검증·번호 연속성)
# ---------------------------------------------------------------------------

_STEP_PREFIX_RE = re.compile(r"^\s*(\d+(?:\s*[~\-,]\s*\d+)*)\s*[.)]?\s*")


def parse_step_numbers(step_text: str) -> List[int]:
    """작업단계 문자열에서 참조하는 단계 번호 목록을 파싱한다.

    "1. 준비" → [1] / "3~4. 용접·사상" → [3, 4] / "2, 5" → [2, 5]
    번호가 없으면 빈 리스트.
    """
    m = _STEP_PREFIX_RE.match(str(step_text or ""))
    if not m:
        return []
    nums: List[int] = []
    token = m.group(1)
    for part in re.split(r"[,]", token):
        part = part.strip()
        rng = re.split(r"[~\-]", part)
        try:
            if len(rng) == 2:
                a, b = int(rng[0]), int(rng[1])
                if a <= b and b - a <= 30:
                    nums.extend(range(a, b + 1))
            else:
                nums.append(int(rng[0]))
        except ValueError:
            continue
    return sorted(set(nums))


def strip_step_prefix(step_text: str) -> str:
    """작업단계 문자열에서 앞의 번호 표기를 제거한다."""
    return _STEP_PREFIX_RE.sub("", str(step_text or "")).strip()


def _renumber_text(text: str, mapping: dict) -> str:
    """문자열 안의 'N단계' 및 선두 번호 참조를 매핑에 따라 갱신한다 (베스트에포트)."""
    def _rep(m):
        n = int(m.group(1))
        return f"{mapping.get(n, n)}단계"
    return re.sub(r"(\d+)\s*단계", _rep, str(text or ""))


def normalize_steps(result: AssessmentResult, review: Optional[ReviewResult] = None) -> dict:
    """작업단계 번호를 1..N 연속으로 재정렬하고 관련 참조를 일괄 갱신한다.

    - work_steps: 목록 순서대로 1..N 번호를 다시 부여
    - hazards.step / no_hazard_steps.step: 원본 번호 → 새 번호 매핑으로 갱신
    - review(선택): findings.comment / changes.description 안의 'N단계' 참조 갱신
    반환: 원본 번호 → 새 번호 매핑 dict
    """
    mapping: dict = {}
    new_steps: List[str] = []
    bodies: List[str] = []
    for i, s in enumerate(result.work_steps, 1):
        olds = parse_step_numbers(s)
        if olds:
            # 중복 원본 번호는 첫 등장만 유지 (덮어쓰면 참조가 어긋남)
            mapping.setdefault(olds[0], i)
        body = strip_step_prefix(s)
        bodies.append(body)
        new_steps.append(f"{i}. {body}" if body else f"{i}.")
    result.work_steps = new_steps

    identity = all(k == v for k, v in mapping.items())

    def _rescue_unnumbered(step_text: str) -> str:
        """번호 없는 step 을 단계 본문 텍스트 매칭으로 복원한다 (유일 매칭일 때만)."""
        body_h = strip_step_prefix(step_text)
        if not body_h:
            return step_text
        matches = [i for i, b in enumerate(bodies, 1)
                   if b and (b in body_h or body_h in b)]
        if len(matches) == 1:
            return f"{matches[0]}. {body_h}"
        return step_text

    def _remap_step_field(step_text: str) -> str:
        nums = parse_step_numbers(step_text)
        body = strip_step_prefix(step_text)
        if not nums:
            # 번호가 없는 참조("전 과정" 등)는 본문 매칭으로 복원 시도
            return _rescue_unnumbered(step_text)
        new_nums = sorted({mapping.get(n, n) for n in nums})
        # 연속 구간은 a~b, 아니면 콤마 나열
        if len(new_nums) == 1:
            prefix = f"{new_nums[0]}"
        elif new_nums == list(range(new_nums[0], new_nums[-1] + 1)):
            prefix = f"{new_nums[0]}~{new_nums[-1]}"
        else:
            prefix = ", ".join(str(n) for n in new_nums)
        return f"{prefix}. {body}" if body else f"{prefix}."

    for h in result.hazards:
        h.step = _remap_step_field(h.step)
    for ns in result.no_hazard_steps:
        ns.step = _remap_step_field(ns.step)

    if review is not None and not identity:
        for f in review.findings:
            f.comment = _renumber_text(f.comment, mapping)
        for c in review.changes:
            c.description = _renumber_text(c.description, mapping)
    return mapping


def covered_step_numbers(result: AssessmentResult) -> set:
    """위험요인이 커버하는 단계 번호 집합을 반환한다.

    번호가 없는 step("전 과정" 등, 본문 매칭 복원도 실패한 경우)은
    전 단계를 포괄하는 것으로 보수적으로 간주한다 — 잘못된 '위험요인 없음' 행과
    불필요한 AI 재생성 호출을 막기 위함.
    """
    covered: set = set()
    all_steps = set(range(1, len(result.work_steps) + 1))
    for h in result.hazards:
        nums = parse_step_numbers(h.step)
        covered.update(nums if nums else all_steps)
    return covered


def uncovered_steps(result: AssessmentResult) -> List[Tuple[int, str]]:
    """위험요인이 1건도 매핑되지 않은 작업단계 목록을 반환한다.

    no_hazard_steps 로 이미 '유의미한 위험요인 없음' 처리된 단계는 제외한다.
    반환: [(단계 번호, 단계 문자열), ...]
    """
    covered = covered_step_numbers(result)
    for ns in result.no_hazard_steps:
        covered.update(parse_step_numbers(ns.step))
    out: List[Tuple[int, str]] = []
    for i, s in enumerate(result.work_steps, 1):
        if i not in covered:
            out.append((i, s))
    return out


def prune_no_hazard_steps(result: AssessmentResult) -> None:
    """위험요인이 존재하는 단계를 가리키는 no_hazard_steps 항목을 제거한다.

    (편집으로 위험요인이 추가되거나 AI 패치가 같은 단계에 둘 다 반환한 경우의
    '위험요인 행 + 유의미한 위험요인 없음 행' 동시 표시 모순 방지)
    """
    covered = covered_step_numbers(result)
    kept, seen = [], set()
    for ns in result.no_hazard_steps:
        nums = tuple(parse_step_numbers(ns.step))
        if set(nums) & covered:
            continue  # 이미 위험요인이 커버하는 단계
        if nums and nums in seen:
            continue  # 중복 제거
        seen.add(nums)
        kept.append(ns)
    result.no_hazard_steps = kept
