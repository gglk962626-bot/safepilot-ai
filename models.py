"""SafePilot AI - 데이터 모델 정의 (Pydantic)

AI가 반환한 JSON을 검증하고, 위험도 점수를 Python에서 직접 계산한다.
- likelihood(발생 가능성), severity(피해 심각도)는 1~5만 허용
- risk_score = likelihood x severity (AI 값은 신뢰하지 않고 여기서 재계산)
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, field_validator

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

# 2차 AI가 반드시 점검해야 하는 검토 범주
REVIEW_CATEGORIES = [
    "추락", "낙하 및 비래", "협착 및 끼임", "충돌", "전도", "감전",
    "화재 및 폭발", "유해가스 및 화학물질", "소음 및 진동", "근골격계 부담",
    "고온 및 저온", "차량 및 중장비", "밀폐공간", "작업자 간 의사소통",
    "작업구역 통제", "작업허가", "개인보호구",
]


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


class HazardItem(BaseModel):
    """위험요인 1건."""

    step: str = Field(default="", description="작업 단계")
    category: str = Field(default="기타", description="위험 분류")
    hazard: str = Field(default="", description="위험요인")
    cause: str = Field(default="", description="원인")
    damage: str = Field(default="", description="예상 피해")
    likelihood: int = Field(default=3, description="발생 가능성 (1~5)")
    severity: int = Field(default=3, description="피해 심각도 (1~5)")
    measures: List[str] = Field(default_factory=list, description="예방대책")
    ppe: List[str] = Field(default_factory=list, description="개인보호구")

    @field_validator("likelihood", "severity", mode="before")
    @classmethod
    def _validate_scale(cls, v):
        return _clamp_1_to_5(v)

    @field_validator("measures", "ppe", mode="before")
    @classmethod
    def _ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return list(v)

    @property
    def risk_score(self) -> int:
        return compute_risk_score(self.likelihood, self.severity)

    @property
    def risk_level(self) -> str:
        return risk_level_from_score(self.risk_score)


class AssessmentResult(BaseModel):
    """1차 AI 위험성평가 결과 (또는 검토 후 최종 결과)."""

    work_overview: str = Field(default="", description="작업 개요 요약")
    work_steps: List[str] = Field(default_factory=list, description="작업 세부 단계")
    hazards: List[HazardItem] = Field(default_factory=list, description="위험요인 목록")
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
