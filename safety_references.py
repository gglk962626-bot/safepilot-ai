"""SafePilot AI - 안전정보 Reference (KOSHA 공개 안전자료 로컬 매칭)

데이터 활용 흐름:
  사용자 작업정보 → 로컬 키워드 관련도 검색 (API 호출 없음)
  → 상위 관련 자료 최대 3건 선정 → 1차 AI 프롬프트에 요약 전달
  → 최종 결과에 출처·참고 이유 표시

원칙:
- 매칭은 순수 Python 로컬 규칙으로만 수행한다 (Gemini API 호출 0회).
- Reference는 1차 AI 생성의 '참고 정보'일 뿐, 위험도 점수·등급을 직접
  결정하지 않으며 법적 판단의 근거가 아니다.
- 이 모듈이 실패해도 위험성평가 생성은 정상 진행되어야 한다 (fail-open).
- 수록 자료는 전부 실존 여부(공식 페이지)를 확인한 한국산업안전보건공단
  공개 자료만 사용한다. 자료명·번호·URL을 추측으로 만들지 않는다.
"""

from __future__ import annotations

from typing import List

# ---------------------------------------------------------------------------
# Reference 데이터 (실존 확인된 KOSHA 공개 자료만 수록)
# 각 항목: reference_id / title / source / document_type / document_number(확인된
# 경우만) / official_url(실제 확인한 URL) / applicable_keywords(core=핵심,
# related=관련) / summary / safety_points / usage_note(결과 화면 한 줄 설명)
# ---------------------------------------------------------------------------

_GUIDE_URL = "https://portal.kosha.or.kr/archive/resources/tech-support/search/all/history?techGdlnNo="

REFERENCES: List[dict] = [
    # ---------------- 식품 제조 ----------------
    {
        "reference_id": "conveyor-safety",
        "title": "컨베이어의 안전에 관한 기술지원규정",
        "source": "한국산업안전보건공단",
        "document_type": "KOSHA GUIDE(기술지원규정)",
        "document_number": "B-M-33-2026",
        "official_url": _GUIDE_URL + "B-M-33-2026",
        "applicable_keywords": {
            "core": ["컨베이어", "벨트컨베이어", "벨트 컨베이어", "이송설비", "스크루컨베이어"],
            "related": ["끼임", "협착", "방호덮개", "비상정지", "이탈방지", "식품가공"],
        },
        "summary": "컨베이어와 부속장치의 설치·사용·점검·유지관리 전 과정의 안전조치를 정한 "
                   "현행 규정으로, 식품가공공장 벨트컨베이어의 방호·안전관리 사항을 포함한다.",
        "safety_points": [
            "청소·급유·점검·수리 등 정비 중에도 방호 연속성 유지, 개방 시 연동·잠금 등 동등 이상 조치",
            "낙하물·이탈 방지 조치와 비상정지장치 요건",
            "스크루컨베이어 투입구·점검구 방호조치",
            "방호장치 점검과 유지보수·대청소 후 확인 절차",
        ],
        "usage_note": "컨베이어 등 이송설비의 끼임 위험과 방호조치를 검토하기 위해 참고한 안전자료입니다.",
    },
    {
        "reference_id": "food-machine-safety",
        "title": "식품가공용기계의 안전작업에 관한 기술지원규정",
        "source": "한국산업안전보건공단",
        "document_type": "KOSHA GUIDE(기술지원규정)",
        "document_number": "B-M-6-2025",
        "official_url": _GUIDE_URL + "B-M-6-2025",
        "applicable_keywords": {
            "core": ["식품가공", "식품용", "분쇄기", "절단기", "혼합기", "파쇄기"],
            "related": ["제면기", "교반기", "끼임", "말림", "베임", "덮개", "연동장치"],
        },
        "summary": "분쇄기·파쇄기·절단기·혼합기 등 식품가공용 기계의 끼임·절단 재해 예방을 위한 "
                   "안전작업 방법과 방호조치를 정한 현행 규정이다.",
        "safety_points": [
            "위험 부위 덮개 설치, 가동 중 개방 시 가동정지·덮개 연동장치·감응형 방호장치 중 하나 이상 조치",
            "손 투입 분쇄 기계는 투입용 보조기구 사용으로 손 말림 방지",
            "잘 보이는 곳에 비상정지장치 설치",
            "식품가공용 파쇄·절단·혼합·제면기는 자율안전확인 표시 기계 사용",
        ],
        "usage_note": "절단기·분쇄기 등 식품가공 기계의 끼임·절단 위험을 검토하기 위해 참고한 안전자료입니다.",
    },
    {
        "reference_id": "loto-energy-isolation",
        "title": "에너지 차단장치의 잠금·표지에 관한 기술지원규정",
        "source": "한국산업안전보건공단",
        "document_type": "KOSHA GUIDE(기술지원규정)",
        "document_number": "B-M-25-2026",
        "applicable_keywords": {
            "core": ["정비", "청소", "LOTO", "잠금장치", "에너지 차단"],
            "related": ["수리", "점검", "불시가동", "기동장치", "전원 차단", "잔류에너지"],
        },
        "official_url": _GUIDE_URL + "B-M-25-2026",
        "summary": "기계·설비의 정비·보수·청소 작업 시 불시 가동 재해를 막기 위한 에너지 차단장치 "
                   "잠금·표지(LOTO) 절차를 정한 현행 규정이다.",
        "safety_points": [
            "정비·청소 전 운전정지 → 에너지 차단 → 잠금·표지 설치 → 잔류에너지 관리 순으로 실행",
            "잠금·표지 해제는 기기 점검과 작업자 전원 확인 후에만 실시",
            "협력업체 작업·단체작업·작업자 교대 시의 잠금·표지 절차 규정",
            "관계 근로자 교육훈련과 작업 전 알림 절차",
        ],
        "usage_note": "설비 정비·청소 과정의 불시 기동 및 에너지 차단(LOTO) 대책을 검토하기 위해 참고한 안전자료입니다.",
    },
    {
        "reference_id": "food-manufacturing-cardbook",
        "title": "식품제조작업 안전가이드(혼합기·절단기·분쇄기)",
        "source": "한국산업안전보건공단",
        "document_type": "안전보건 교육자료(카드북)",
        "document_number": "2023-교육혁신실-994",
        "official_url": "https://portal.kosha.or.kr/archive/cent-archive/master-arch",
        "applicable_keywords": {
            "core": ["식품제조", "식품 제조", "혼합기", "교반기"],
            "related": ["절단기", "분쇄기", "끼임", "청소", "임펠러", "투입구", "세척"],
        },
        "summary": "식품제조용 혼합기·절단기·분쇄기의 주요 위험요인과 작업 전 안전수칙, 실제 끼임 "
                   "재해사례를 정리한 KOSHA 교육자료다 (안전보건 자료실에서 '식품' 검색).",
        "safety_points": [
            "혼합기는 덮개 연동장치·비상정지장치·내부 안전망·동력전달부 방호덮개 설치",
            "청소·정비 시 운전정지 → 전원차단 → 잔류에너지 확인 → 잠금·표지 후 작업",
            "절단기 재료 투입 시 손 대신 투입봉 사용, 이물질 제거 시 동력 정지",
            "가동 중 내부 청소로 인한 임펠러 끼임 중대재해 사례 수록",
        ],
        "usage_note": "식품 제조설비 작업의 실제 끼임 재해사례와 안전수칙을 검토하기 위해 참고한 안전자료입니다.",
    },
    # ---------------- 조선·제조 ----------------
    {
        "reference_id": "welding-fire-prevention",
        "title": "용접·용단 작업 시 화재예방에 관한 기술지원규정",
        "source": "한국산업안전보건공단",
        "document_type": "KOSHA GUIDE(기술지원규정)",
        "document_number": "A-G-14-2026",
        "official_url": _GUIDE_URL + "A-G-14-2026",
        "applicable_keywords": {
            "core": ["용접", "용단", "화기작업"],
            "related": ["불티", "화재감시자", "방화포", "가연물", "그라인더", "절단"],
        },
        "summary": "용접·용단 등 불꽃·불티가 발생하는 화기작업의 화재·폭발 예방 조치와 작업 중 "
                   "관리사항을 정한 현행 규정이다.",
        "safety_points": [
            "화기작업 전 작업허가 절차와 주변 가연물 제거·격리",
            "불티 비산방지 덮개·용접방화포 설치와 화재감시자 배치",
            "탱크·배관 내부 화기작업은 인화성 가스 치환·농도 측정 후 실시",
            "작업 종료 후 잔불 확인과 일정 시간 감시",
        ],
        "usage_note": "용접·용단 등 화기작업의 화재·폭발 위험을 검토하기 위해 참고한 안전자료입니다.",
    },
    {
        "reference_id": "confined-space-program",
        "title": "밀폐공간 작업프로그램 수립 및 시행에 관한 기술지원규정",
        "source": "한국산업안전보건공단",
        "document_type": "KOSHA GUIDE(기술지원규정)",
        "document_number": "E-G-18-2026",
        "official_url": _GUIDE_URL + "E-G-18-2026",
        "applicable_keywords": {
            "core": ["밀폐공간", "질식", "산소결핍"],
            "related": ["유해가스", "환기", "송기마스크", "감시인", "탱크", "맨홀"],
        },
        "summary": "밀폐공간 질식·중독 재해 예방을 위해 사업장이 수립·시행해야 하는 밀폐공간 "
                   "작업프로그램의 구성 요소와 절차를 제시하는 현행 규정이다.",
        "safety_points": [
            "밀폐공간 사전 파악과 출입금지 표지·출입 통제",
            "작업 전 산소·유해가스 농도 측정으로 적정공기 확인 후 출입",
            "작업 전·작업 중 지속 환기 실시",
            "감시인 배치, 비상연락·구조체계, 구조 시 송기마스크 착용",
        ],
        "usage_note": "밀폐공간 작업의 질식 위험과 작업프로그램 요건을 검토하기 위해 참고한 안전자료입니다.",
    },
    {
        "reference_id": "crane-rigging-wire",
        "title": "크레인 달기기구 및 줄걸이 작업용 와이어로프의 작업에 관한 기술지원규정",
        "source": "한국산업안전보건공단",
        "document_type": "KOSHA GUIDE(기술지원규정)",
        "document_number": "B-M-12-2025",
        "official_url": _GUIDE_URL + "B-M-12-2025",
        "applicable_keywords": {
            "core": ["줄걸이", "크레인", "와이어로프", "달기기구"],
            "related": ["양중", "슬링", "인양", "중량물", "훅", "호이스트"],
        },
        "summary": "크레인 양중작업에 사용하는 달기기구와 줄걸이용 와이어로프의 선정·사용·점검 "
                   "기준을 제시해 중량물 낙하·협착 재해를 예방하기 위한 현행 규정이다.",
        "safety_points": [
            "와이어로프·달기기구의 폐기 기준과 사용 전 점검",
            "중량물 무게중심을 고려한 줄걸이 방법 선정",
            "인양 중 하부 출입 통제와 신호 체계 운영",
            "달기각도에 따른 장력 변화 고려",
        ],
        "usage_note": "중량물 인양·줄걸이 작업의 낙하·협착 위험을 검토하기 위해 참고한 안전자료입니다.",
    },
    {
        "reference_id": "portable-ladder",
        "title": "이동식 사다리의 사용에 관한 기술지원규정",
        "source": "한국산업안전보건공단",
        "document_type": "KOSHA GUIDE(기술지원규정)",
        "document_number": "A-G-4-2025",
        "official_url": _GUIDE_URL + "A-G-4-2025",
        "applicable_keywords": {
            "core": ["사다리", "이동식 사다리"],
            "related": ["추락", "고소작업", "A형 사다리", "전도방지", "작업발판", "안전대"],
        },
        "summary": "이동식 사다리 작업의 추락·전도 재해 예방을 위한 사다리의 선정, 설치, 사용 "
                   "방법과 금지사항을 정한 현행 규정이다.",
        "safety_points": [
            "사다리 설치 각도·전도방지 조치와 미끄럼 방지",
            "최상부 발판 작업 금지 등 사용 금지사항",
            "사다리 위 작업 시 안전모 등 보호구 착용",
            "손에 물건을 들고 오르내리는 행위 금지",
        ],
        "usage_note": "사다리 등 이동식 승강설비 작업의 추락 위험을 검토하기 위해 참고한 안전자료입니다.",
    },
    # ---------------- 도장·세척 (화학물질 안전정보) ----------------
    {
        "reference_id": "painting-fire-explosion",
        "title": "도장 공정에서의 화재·폭발위험방지에 관한 기술지원규정",
        "source": "한국산업안전보건공단",
        "document_type": "KOSHA GUIDE(기술지원규정)",
        "document_number": "B-E-17-2026",
        "official_url": _GUIDE_URL + "B-E-17-2026",
        "applicable_keywords": {
            "core": ["도장", "스프레이", "분무", "도장부스", "정전도장"],
            "related": ["페인트", "도료", "신너", "용제", "유기용제", "선박도장"],
        },
        "summary": "도장 공정(분무·담금·코팅)에서 인화성 액체의 증기·미스트에 의한 화재·폭발을 "
                   "방지하기 위한 현행 규정으로, 폭발위험장소 구분·방폭기기·배기 연동·접지를 규정한다.",
        "safety_points": [
            "분무부스 내부와 증기발생원 반경 1.5m 이내는 1종 폭발위험장소로 구분",
            "배기시스템 고장 시 도장설비가 자동 정지되도록 연동",
            "방폭구조 전기기기 선정, 분무지역에서 휴대용 전기기기 사용 금지",
            "정전도장기기는 환기 고장·누설전류 시 자동 전원차단 장치 구비",
            "페인트용기 등 도전성 물체 접지·본딩",
        ],
        "usage_note": "도장 공정의 화재·폭발 위험(폭발위험장소·방폭·환기 연동·접지)을 검토하기 위해 참고한 안전자료입니다.",
    },
    {
        "reference_id": "ship-painting-safety",
        "title": "선박내부에서 도장작업 시 안전에 관한 기술 지침",
        "source": "한국산업안전보건공단",
        "document_type": "KOSHA GUIDE(안전보건기술지침)",
        "document_number": "G-117-2014",
        "official_url": _GUIDE_URL + "G-117-2014",
        "applicable_keywords": {
            "core": ["선박 도장", "선박도장", "블록 내부 도장", "밀폐공간 도장"],
            "related": ["도장", "유기용제", "조선소", "블록", "밀폐공간", "신나"],
        },
        # 주의: 원문 적용범위가 보건관리를 제외하므로 화재·폭발 및 밀폐공간
        # 작업관리 범위로만 참고한다 (중독·건강장해의 근거로 사용 금지).
        "summary": "선박내부 도장작업 시 인화성 유기용제 증기에 의한 화재·폭발 예방을 위한 지침으로, "
                   "인화성 증기 농도 관리(LEL 기준)·환기·출입허가·점화원 관리를 규정한다 (보건관리는 적용 제외).",
        "safety_points": [
            "인화성 증기 농도 LEL 25% 이하 유지, 밀폐공간·인화점 27℃ 미만 물질은 LEL 10% 미만 (초과 시 작업 중지)",
            "밀폐공간 도장은 서면 출입허가, 급기 위주 강제환기, 가스검지기 연속 감시",
            "도장구역과 인접 블록에서 화기작업·비방폭 기기 금지, 접지·정전기 방지",
            "작업 종료 후에도 건조 완료까지 환기 지속",
            "용제 젖은 헝겊은 금속용기 보관, 소화기·방화포 비치",
        ],
        "usage_note": "선박 블록 내부 도장작업의 화재·폭발 위험과 밀폐공간 작업관리를 검토하기 위해 참고한 안전자료입니다.",
    },
    {
        "reference_id": "cleaning-3-measures-ops",
        "title": "세척작업 3대 핵심 안전보건 조치 OPS",
        "source": "한국산업안전보건공단",
        "document_type": "OPS(한장짜리 안전보건자료)",
        "document_number": "2023-산업보건실-141",
        "official_url": "https://portal.kosha.or.kr/archive/cent-archive/master-arch/master-list4/master-detail4?medSeq=44986",
        "applicable_keywords": {
            "core": ["세척", "세척제", "탈지", "세척조"],
            "related": ["화학물질", "유기용제", "청소", "세척공정"],
        },
        "summary": "세척제 화학물질에 의한 급성중독을 예방하기 위한 3대 핵심 조치(MSDS 확인·교육, "
                   "국소배기, 호흡보호구)를 정리한 KOSHA 공식 OPS 자료다.",
        "safety_points": [
            "MSDS로 세척제 성분·유해성을 확인하고 근로자에게 교육",
            "국소배기장치가 가동되는 상태에서만 세척작업 실시",
            "작업 시 방독마스크 착용",
            "세척조 내부 청소·수리 시 송기마스크 착용과 외부 감시인 배치",
            "어지러움·메스꺼움·두통 등 급성중독 증상 발생 시 즉시 진료",
        ],
        "usage_note": "세척제 취급 작업의 급성중독 위험과 3대 핵심 안전보건 조치를 검토하기 위해 참고한 안전자료입니다.",
    },
    {
        "reference_id": "kosha-msds-info",
        "title": "KOSHA 화학물질정보 (MSDS 검색)",
        "source": "한국산업안전보건공단",
        "document_type": "화학물질정보 시스템",
        "official_url": "https://msds.kosha.or.kr/MSDSInfo/kcic/msdssearchMsds.do",
        "applicable_keywords": {
            "core": ["MSDS", "물질안전보건자료", "화학물질"],
            "related": ["세척제", "도료", "신너", "유기용제", "CAS"],
        },
        "summary": "약 2만여 종 화학물질의 MSDS를 물질명 또는 CAS 번호로 검색할 수 있는 KOSHA 공식 "
                   "시스템이다. 톨루엔(108-88-3)·크실렌(1330-20-7)·아세톤(67-64-1)·디클로로메탄(75-09-2) 등 "
                   "도장·세척 작업에서 흔한 물질의 MSDS 확인 경로를 제공한다.",
        "safety_points": [
            "취급하는 도료·세척제의 물질명 또는 CAS 번호로 KOSHA MSDS를 검색해 유해성 확인",
            "MSDS의 유해성·응급조치·취급저장·노출방지 항목을 작업 전 확인",
            "확인한 유해성 정보를 근로자 교육과 보호구 선정에 반영",
        ],
        "usage_note": "KOSHA 화학물질정보에서 물질명 또는 CAS 번호로 MSDS를 확인할 수 있습니다.",
    },
    # ---------------- 콜센터·고객응대 ----------------
    {
        "reference_id": "emotional-labor-health-guide",
        "title": "감정노동 종사자 건강보호 가이드",
        "source": "한국산업안전보건공단",
        "document_type": "안전보건 가이드 책자",
        "document_number": "2021-사업총괄본부-694",
        "official_url": "https://portal.kosha.or.kr/archive/cent-archive/master-arch/master-list3/master-detail3?medSeq=43648",
        "applicable_keywords": {
            "core": ["감정노동", "고객응대", "콜센터", "폭언"],
            "related": ["상담", "민원", "직무스트레스", "트라우마", "건강장해", "고객센터"],
        },
        "summary": "산업안전보건법상 고객응대근로자 보호 의무 이행을 위한 KOSHA 공식 가이드로, "
                   "감정노동의 이해부터 예방·사후조치, 교육내용, 평가표까지 담고 있다.",
        "safety_points": [
            "폭언·폭력 고객 응대 시 업무 중단·전환 등 보호조치 절차",
            "감정노동 수준 평가와 고위험군 관리",
            "건강장해 발생 시 상담·치료 지원 등 사후조치",
            "고객응대 근로자 보호 문구 게시와 교육",
        ],
        "usage_note": "고객응대 업무의 감정노동·폭언 위험과 보호조치를 검토하기 위해 참고한 안전자료입니다.",
    },
    {
        "reference_id": "emotional-labor-assessment",
        "title": "고객응대 근로자의 감정노동 평가 지침",
        "source": "한국산업안전보건공단",
        "document_type": "KOSHA GUIDE(안전보건기술지침)",
        "document_number": "H-163-2021",
        "official_url": _GUIDE_URL + "H-163-2021",
        "applicable_keywords": {
            "core": ["감정노동", "고객응대"],
            "related": ["콜센터", "상담", "직무스트레스", "평가", "민원"],
        },
        "summary": "고객응대 업무 근로자의 감정노동 수준을 평가하기 위한 KOSHA 보건위생분야 "
                   "기술지침으로, 평가 결과를 건강보호 조치에 연계하도록 안내한다.",
        "safety_points": [
            "한국형 감정노동 평가도구를 활용한 수준 평가",
            "평가 결과에 따른 고위험 직무·근로자 파악",
            "감정노동 완화를 위한 작업환경·업무방식 개선 연계",
        ],
        "usage_note": "상담 업무의 감정노동 수준 평가 방법을 검토하기 위해 참고한 안전자료입니다.",
    },
    {
        "reference_id": "job-stress-prevention",
        "title": "직무스트레스로 인한 건강장해 예방에 관한 기술지원규정",
        "source": "한국산업안전보건공단",
        "document_type": "KOSHA GUIDE(기술지원규정)",
        "document_number": "E-G-2-2025",
        "official_url": _GUIDE_URL + "E-G-2-2025",
        "applicable_keywords": {
            "core": ["직무스트레스"],
            "related": ["감정노동", "정신건강", "고객응대", "콜센터", "야간작업", "교대근무"],
        },
        "summary": "직무스트레스로 인한 건강장해 예방 조치를 담은 2025년 제정 현행 규정으로, "
                   "종전 직무스트레스 관련 지침들을 통합했다.",
        "safety_points": [
            "직무스트레스 요인 평가와 개선 계획 수립",
            "업무량·근무시간 등 작업조건 개선",
            "근로자 상담·지원 체계 운영",
        ],
        "usage_note": "직무스트레스 요인 평가와 건강장해 예방 조치를 검토하기 위해 참고한 안전자료입니다.",
    },
    {
        "reference_id": "callcenter-stress-ops",
        "title": "고객 폭언 등으로 고통받는 콜센터 상담사의 직무스트레스 이렇게 관리하세요",
        "source": "한국산업안전보건공단",
        "document_type": "OPS(한장짜리 안전보건자료)",
        "document_number": "2022-산업보건실-101",
        "official_url": "https://portal.kosha.or.kr/archive/cent-archive/master-arch/master-list1/master-detail1?medSeq=43951",
        "applicable_keywords": {
            "core": ["콜센터", "폭언", "상담사", "전화상담"],
            "related": ["감정노동", "직무스트레스", "고객응대", "민원", "헤드셋"],
        },
        "summary": "고객 폭언에 노출되는 콜센터 상담사의 직무스트레스 관리방안을 한 장 분량으로 "
                   "정리한 KOSHA 공식 OPS 자료로, 사업장 게시·교육용으로 적합하다.",
        "safety_points": [
            "폭언 발생 시 응대 중단·전환 절차 마련",
            "휴게시간 보장과 심리 회복 지원",
            "상담사 보호 안내멘트 운영",
        ],
        "usage_note": "콜센터 상담사의 폭언 노출과 직무스트레스 관리방안을 검토하기 위해 참고한 안전자료입니다.",
    },
]


# ---------------------------------------------------------------------------
# 관련도 계산 (로컬 규칙)
# ---------------------------------------------------------------------------

_CORE_WEIGHT = 10      # 핵심 작업 키워드 일치
_RELATED_WEIGHT = 3    # 관련 작업 키워드 일치
_MIN_SCORE = _CORE_WEIGHT  # 핵심 키워드 1개 이상 일치해야 선정 (억지 매칭 방지)
MAX_REFERENCES = 3


def _combined_text(work) -> str:
    """작업정보 6개 필드를 하나의 검색 텍스트로 결합한다."""
    parts = [
        getattr(work, "name", "") or "",
        getattr(work, "location", "") or "",
        getattr(work, "description", "") or "",
        getattr(work, "equipment", "") or "",
        getattr(work, "workers", "") or "",
        getattr(work, "notes", "") or "",
    ]
    return " ".join(str(p) for p in parts).lower()


def score_reference(text: str, ref: dict) -> tuple[int, List[str]]:
    """검색 텍스트와 자료 하나의 관련도 점수·일치 키워드를 반환한다."""
    kw = ref.get("applicable_keywords", {}) or {}
    score = 0
    matched: List[str] = []
    for k in kw.get("core", []) or []:
        if k.lower() in text:
            score += _CORE_WEIGHT
            matched.append(k)
    for k in kw.get("related", []) or []:
        if k.lower() in text:
            score += _RELATED_WEIGHT
            matched.append(k)
    return score, matched


def select_references(work, limit: int = MAX_REFERENCES) -> List[dict]:
    """작업정보와 관련도가 높은 자료를 최대 limit건 선정한다.

    반환: [{"reference": dict, "score": int, "matched_keywords": [...]}]
    - 핵심 키워드가 하나도 일치하지 않는 자료는 선정하지 않는다.
    - 동일 자료는 중복 선정하지 않는다. 관련 자료가 없으면 빈 목록.
    - 어떤 오류가 나도 빈 목록을 반환한다 (fail-open — 평가 생성을 막지 않음).
    """
    try:
        text = _combined_text(work)
        if not text.strip():
            return []
        scored = []
        seen: set = set()
        for ref in REFERENCES:
            rid = ref.get("reference_id")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            score, matched = score_reference(text, ref)
            if score >= _MIN_SCORE:
                scored.append({"reference": ref, "score": score,
                               "matched_keywords": matched})
        scored.sort(key=lambda s: s["score"], reverse=True)
        return scored[: max(0, int(limit))]
    except Exception:
        return []


def get_reference(reference_id: str) -> dict | None:
    """reference_id로 자료를 조회한다 (없으면 None — 표시 단계 방어용)."""
    for ref in REFERENCES:
        if ref.get("reference_id") == reference_id:
            return ref
    return None


# ---------------------------------------------------------------------------
# 화학물질 취급 정황 감지 (MSDS 확인 경로 보조 안내용)
# - Top-3 Reference 선정과 완전히 분리된 표시 전용 판단이며,
#   선정 점수·순위·1차 AI 전달 내용에 일절 영향을 주지 않는다.
# - 화학물질 '자체'를 지시하는 단어만 사용한다: '세척'(물세척 가능)과
#   '용제' 단독('사용제한' 오탐)은 의도적으로 제외.
# ---------------------------------------------------------------------------

MSDS_REFERENCE_ID = "kosha-msds-info"

CHEMICAL_CONTEXT_KEYWORDS = [
    "화학물질", "MSDS", "물질안전보건자료", "세척제", "유기용제",
    "도료", "신너", "시너", "페인트", "도장", "약품", "산세척", "탈지",
]


def detect_chemical_context(work) -> List[str]:
    """작업정보에서 화학물질 취급 정황 단어를 찾아 반환한다 (없으면 빈 목록).

    어떤 오류가 나도 빈 목록을 반환한다 (fail-open — 안내 전용 기능이
    평가 생성·결과 표시를 막지 않는다).
    """
    try:
        text = _combined_text(work)
        return [k for k in CHEMICAL_CONTEXT_KEYWORDS if k.lower() in text]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 1차 AI 전달용 요약 블록 (원문이 아닌 최소 요약만 전달)
# ---------------------------------------------------------------------------

def build_prompt_block(selected: List[dict]) -> str:
    """선정된 자료를 1차 AI 프롬프트용 [참고 안전자료] 블록으로 구성한다.

    빈 목록이면 빈 문자열을 반환한다 (프롬프트는 기존과 동일해진다).
    어떤 오류가 나도 빈 문자열을 반환한다 (fail-open).
    """
    try:
        if not selected:
            return ""
        lines = ["[참고 안전자료]"]
        for i, item in enumerate(selected, 1):
            ref = item.get("reference", item) or {}
            points = " / ".join(ref.get("safety_points", [])[:5])
            lines.append(f"{i}. 자료명: {ref.get('title', '')}")
            lines.append(f"   출처: {ref.get('source', '')} ({ref.get('document_type', '')})")
            lines.append(f"   자료 요약: {ref.get('summary', '')}")
            lines.append(f"   핵심 안전정보: {points}")
        lines.append(
            "위 자료는 현재 작업의 위험요인·감소대책 작성 시 참고할 수 있는 안전정보다. "
            "그대로 복사하지 말고, 현재 작업정보와 결합하여 필요한 경우에만 원인·감소대책·"
            "판단 근거 작성에 참고하라. 자료에 없는 내용을 자료가 제시했다고 추정하지 마라. "
            "이 자료는 위험도 점수·등급을 직접 결정하지 않는다.")
        return "\n".join(lines)
    except Exception:
        return ""
