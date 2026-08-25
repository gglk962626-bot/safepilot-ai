"""SafePilot AI - KOSHA MSDS 로컬 캐시 및 화학물질 식별

지원 범위와 한계:
- 아래 6종은 한국산업안전보건공단 화학물질정보(msds.kosha.or.kr)의 MSDS 상세
  원문을 직접 확인하여 핵심 정보만 요약 수록한 것이다 (chem_id·개정일 포함).
- 식별은 동의어 사전 기반의 순수 로컬 문자열 매칭이다. AI가 물질을 추정하지
  않으며, '신너'·'도료' 등 성분을 알 수 없는 표현은 어떤 물질로도 매핑하지 않는다.
- MSDS 정보는 1차 AI의 위험요인·안전대책 작성 '참고자료'로만 전달되며,
  위험도 점수(가능성×심각도) 계산에는 어떤 방식으로도 개입하지 않는다.
- 이 모듈이 실패해도 위험성평가 생성은 정상 진행된다 (fail-open).
- Gemini API를 호출하지 않는다.
"""

from __future__ import annotations

from typing import List

MSDS_SEARCH_URL = "https://msds.kosha.or.kr/MSDSInfo/kcic/msdssearchMsds.do"

# 각 항목의 classification / signal / hazard_statements / precautions 는
# KOSHA MSDS 상세 페이지(2번 유해성·위험성, 7번 취급·저장, 8번 노출방지 및
# 개인보호구 항목) 원문에서 추출·요약한 것이다.
MSDS_CHEMICALS: List[dict] = [
    {
        "name": "톨루엔",
        "cas": "108-88-3",
        "chem_id": "001032",
        "revision": "2025-08-08",
        "synonyms": ["톨루엔", "toluene", "톨루올"],
        "signal": "위험",
        "classification": [
            "인화성 액체 구분2", "피부 자극성 구분2", "생식독성 구분2",
            "특정표적장기 독성(1회 노출) 구분3(마취영향)",
            "특정표적장기 독성(반복 노출) 구분2", "흡인 유해성 구분1",
        ],
        "hazard_statements": [
            "H225 고인화성 액체 및 증기",
            "H304 삼켜서 기도로 유입되면 치명적일 수 있음",
            "H336 졸음 또는 현기증을 일으킬 수 있음",
            "H361 태아 또는 생식능력에 손상을 일으킬 것으로 의심됨",
            "H373 장기간·반복 노출 시 장기에 손상을 일으킬 수 있음",
        ],
        "precautions": [
            "점화원 격리, 방폭형 전기·환기·조명 설비 사용, 정전기 방지 조치",
            "증기 흡입을 피하고 환기가 잘 되는 곳에서만 취급",
            "유기물질용 정화통을 장착한 호흡보호구(고농도 시 송기마스크) 착용",
            "보안경 또는 고글, 내화학성 보호장갑 착용",
        ],
    },
    {
        "name": "크실렌",
        "cas": "1330-20-7",
        "chem_id": "001077",
        "revision": "2025-12-10",
        "synonyms": ["크실렌", "xylene", "자일렌"],
        "signal": "위험",
        "classification": [
            "인화성 액체 구분3", "피부 자극성 구분2", "눈 자극성 구분2",
            "생식독성 구분2", "특정표적장기 독성(1회 노출) 구분3(호흡기 자극·마취영향)",
            "특정표적장기 독성(반복 노출) 구분2",
        ],
        "hazard_statements": [
            "H226 인화성 액체 및 증기",
            "H304 삼켜서 기도로 유입되면 치명적일 수 있음",
            "H315 피부에 자극을 일으킴",
            "H332 흡입하면 유해함",
            "H335 호흡기 자극을 일으킬 수 있음",
            "H361 태아 또는 생식능력에 손상을 일으킬 것으로 의심됨",
        ],
        "precautions": [
            "점화원 격리와 환기 확보, 증기 흡입 회피",
            "유기물질용 정화통을 장착한 호흡보호구(고농도 시 송기마스크) 착용",
            "보안경 또는 고글, 내화학성 보호장갑 착용",
        ],
    },
    {
        "name": "아세톤",
        "cas": "67-64-1",
        "chem_id": "001067",
        "revision": "2026-04-17",
        "synonyms": ["아세톤", "acetone"],
        "signal": "위험",
        "classification": [
            "인화성 액체 구분2", "눈 자극성 구분2", "생식독성 구분2",
            "특정표적장기 독성(1회 노출) 구분3(마취영향)",
            "특정표적장기 독성(반복 노출) 구분1",
        ],
        "hazard_statements": [
            "H225 고인화성 액체 및 증기",
            "H319 눈에 심한 자극을 일으킴",
            "H336 졸음 또는 현기증을 일으킬 수 있음",
            "H372 장기간·반복 노출 시 장기에 손상을 일으킴",
        ],
        "precautions": [
            "방폭형 전기·환기·조명 설비 사용, 스파크 비발생 도구 사용, 정전기 방지",
            "증기 흡입을 피하고 환기가 잘 되는 곳에서만 취급",
            "유기물질용 정화통을 장착한 호흡보호구 착용",
            "보안경 또는 고글 착용, 긴급세척시설 인접 배치",
        ],
    },
    {
        "name": "디클로로메탄",
        "cas": "75-09-2",
        "chem_id": "001024",
        "revision": "2025-09-17",
        "synonyms": ["디클로로메탄", "dichloromethane", "염화메틸렌",
                     "메틸렌클로라이드", "메틸렌 클로라이드"],
        "signal": "위험",
        "classification": [
            "피부 자극성 구분2", "눈 자극성 구분2", "생식세포 변이원성 구분2",
            "발암성 구분1B", "특정표적장기 독성(1회 노출) 구분3(마취영향)",
            "특정표적장기 독성(반복 노출) 구분2",
        ],
        "hazard_statements": [
            "H336 졸음 또는 현기증을 일으킬 수 있음",
            "H341 유전적인 결함을 일으킬 것으로 의심됨",
            "H350 암을 일으킬 수 있음",
            "H373 장기간·반복 노출 시 장기에 손상을 일으킬 수 있음",
        ],
        "precautions": [
            "증기 흡입을 피하고 옥외 또는 환기가 잘 되는 곳에서만 취급",
            "밀폐공간·세척조 내부 사용 시 고농도 증기 축적에 특히 주의",
            "유기물질용 정화통을 장착한 호흡보호구(고농도 시 송기마스크) 착용",
            "보안경 또는 고글, 내화학성 보호장갑 착용",
        ],
    },
    {
        "name": "이소프로필 알코올",
        "cas": "67-63-0",
        "chem_id": "001065",
        "revision": "2025-08-08",
        "synonyms": ["이소프로필 알코올", "이소프로필알코올", "이소프로판올",
                     "isopropyl alcohol", "isopropanol", "IPA"],
        "signal": "위험",
        "classification": [
            "인화성 액체 구분2", "눈 자극성 구분2",
            "특정표적장기 독성(1회 노출) 구분3(마취영향)", "흡인 유해성 구분2",
        ],
        "hazard_statements": [
            "H225 고인화성 액체 및 증기",
            "H319 눈에 심한 자극을 일으킴",
            "H336 졸음 또는 현기증을 일으킬 수 있음",
        ],
        "precautions": [
            "방폭 설비 사용, 스파크 비발생 도구 사용, 정전기 방지 조치",
            "증기 흡입을 피하고 환기가 잘 되는 곳에서만 취급",
            "유기물질용 정화통을 장착한 호흡보호구 착용, 보안경 착용",
        ],
    },
    {
        "name": "메틸 에틸 케톤",
        "cas": "78-93-3",
        "chem_id": "001080",
        "revision": "2025-08-08",
        "synonyms": ["메틸 에틸 케톤", "메틸에틸케톤", "methyl ethyl ketone",
                     "MEK", "2-부타논"],
        "signal": "위험",
        "classification": [
            "인화성 액체 구분2", "눈 자극성 구분2",
            "특정표적장기 독성(1회 노출) 구분3(호흡기 자극)",
        ],
        "hazard_statements": [
            "H225 고인화성 액체 및 증기",
            "H319 눈에 심한 자극을 일으킴",
            "H335 호흡기 자극을 일으킬 수 있음",
        ],
        "precautions": [
            "방폭 설비 사용, 스파크 비발생 도구 사용, 정전기 방지 조치",
            "증기 흡입을 피하고 환기가 잘 되는 곳에서만 취급",
            "유기물질용 정화통을 장착한 호흡보호구 착용, 보안경 착용",
        ],
    },
]


def identify_chemicals(work) -> List[dict]:
    """작업정보 6개 필드에서 지원 물질을 동의어 매칭으로 식별한다.

    - 명확한 물질명·동의어가 텍스트에 있을 때만 반환한다 (AI 추정 없음).
    - '신너'·'도료' 등 성분 불명 표현은 매핑하지 않는다 (동의어 사전에 없음).
    - 어떤 오류가 나도 빈 목록을 반환한다 (fail-open).
    """
    try:
        parts = [getattr(work, f, "") or "" for f in
                 ("name", "location", "description", "equipment", "workers", "notes")]
        text = " ".join(str(p) for p in parts).lower()
        found = []
        for chem in MSDS_CHEMICALS:
            if any(s.lower() in text for s in chem["synonyms"]):
                found.append(chem)
        return found
    except Exception:
        return []


def get_chemical(name: str) -> dict | None:
    """물질명으로 캐시 항목을 조회한다 (표시 단계 방어용)."""
    for chem in MSDS_CHEMICALS:
        if chem["name"] == name:
            return chem
    return None


def build_msds_block(chemicals: List[dict]) -> str:
    """식별된 물질의 MSDS 요약을 1차 AI 프롬프트용 블록으로 구성한다.

    빈 목록이면 빈 문자열(프롬프트 불변). 오류 시에도 빈 문자열 (fail-open).
    """
    try:
        if not chemicals:
            return ""
        lines = ["[화학물질 MSDS 참고정보 — 한국산업안전보건공단 화학물질정보]"]
        for i, c in enumerate(chemicals, 1):
            lines.append(f"{i}. {c['name']} (CAS {c['cas']}, KOSHA MSDS 개정 {c['revision']})")
            lines.append(f"   신호어: {c['signal']} / 분류: {', '.join(c['classification'])}")
            lines.append(f"   유해·위험문구: {'; '.join(c['hazard_statements'])}")
            lines.append(f"   예방·보호조치: {' / '.join(c['precautions'])}")
        lines.append(
            "위 정보는 작업정보에서 확인된 물질의 KOSHA 공식 MSDS 요약이다. 해당 물질과 관련된 "
            "위험요인·원인·감소대책·판단 근거를 작성할 때 참고하라. MSDS에 없는 내용을 MSDS가 "
            "제시했다고 쓰지 말고, 확인되지 않은 다른 물질을 추정하지 마라. "
            "이 정보는 위험도 점수·등급을 직접 결정하지 않는다.")
        return "\n".join(lines)
    except Exception:
        return ""
