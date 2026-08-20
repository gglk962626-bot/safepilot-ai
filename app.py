"""SafePilot AI - 위험성평가 코파일럿 (Streamlit 앱)"""

from __future__ import annotations

import html
from datetime import datetime

import pandas as pd
import streamlit as st

import ai_service
import demo_data
import input_check
import pdf_service
from models import (
    AssessmentResult, CATEGORY_COUNT, DEFAULT_RISK_THRESHOLD, FullResult,
    RISK_COLORS, WorkInput, apply_threshold,
)

# ---------------------------------------------------------------------------
# 페이지 설정 및 스타일
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="SafePilot AI - 위험성평가 코파일럿",
    page_icon="🦺",
    layout="wide",
    initial_sidebar_state="expanded",  # 최종 위험성 판단 기준 설정이 바로 보이도록
)

# ---------------------------------------------------------------------------
# 사이드바: 최종 위험성 판단 기준 (법정 허용기준이 아님)
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 평가 설정")
    risk_threshold = st.number_input(
        "최종 위험성 판단 기준",
        min_value=1, max_value=25,
        value=DEFAULT_RISK_THRESHOLD, step=1,
        help="개선 후 위험도 점수가 이 값 이하이면 '설정 기준 이내'로 표시합니다.",
        key="risk_threshold",
    )
    st.caption(f"현재 기준: **{int(risk_threshold)}점 이하**")
    st.caption(
        "※ 본 기준은 SafePilot의 기본 설정값이며, 실제 적용 시 사업장의 "
        "위험성평가 기준 및 현장 여건에 따라 조정할 수 있습니다."
    )

st.markdown(
    """
<style>
/* =====================================================================
   SafePilot AI 디자인 시스템 (B2B 산업안전 SaaS)
   - 디자인 토큰(CSS 변수) 기반의 일관된 색·간격·그림자 체계
   - Streamlit 내부 구조 의존을 최소화: 자체 클래스(sp-*)와
     st.button(key=...)이 생성하는 안정 selector(.st-key-*)만 사용
   ===================================================================== */
:root {
  --sp-primary: #0d3b66;        /* 브랜드 네이비 */
  --sp-primary-2: #155a96;      /* 밝은 네이비 (그라디언트/호버) */
  --sp-accent: #2f6fb3;
  --sp-ink: #1e293b;            /* 본문 텍스트 */
  --sp-muted: #64748b;          /* 보조 텍스트 */
  --sp-surface: #ffffff;
  --sp-surface-2: #f8fafc;      /* 옅은 배경 */
  --sp-border: #e2e8f0;
  --sp-border-strong: #cbd5e1;
  --sp-shadow-sm: 0 1px 2px rgba(15, 23, 42, .05);
  --sp-shadow-md: 0 4px 14px rgba(13, 59, 102, .10);
  --sp-radius: 12px;
}

.block-container {padding-top: 1.2rem; max-width: 1200px;}

/* ---------- 헤더 (브랜드 영역) ---------- */
.sp-header {
  position: relative; overflow: hidden;
  background: linear-gradient(130deg, #092c4d 0%, var(--sp-primary) 45%, var(--sp-primary-2) 100%);
  border-radius: 16px; padding: 30px 34px 26px; color: #fff;
  box-shadow: var(--sp-shadow-md);
}
.sp-header::after {              /* 은은한 장식 원 — 과하지 않은 깊이감 */
  content: ""; position: absolute; right: -70px; top: -90px;
  width: 300px; height: 300px; border-radius: 50%;
  background: radial-gradient(circle, rgba(255,255,255,.08) 0%, rgba(255,255,255,0) 70%);
}
.sp-header .eyebrow {
  display: inline-block; font-size: .72rem; font-weight: 700;
  letter-spacing: .14em; color: #9fc3e8; text-transform: uppercase;
  margin-bottom: 8px;
}
.sp-header h1 {margin: 0; font-size: 1.95rem; font-weight: 800; color: #fff; letter-spacing: -.01em;}
.sp-header .sub {font-size: 1.04rem; font-weight: 500; opacity: .95; margin-top: 6px;}
.sp-header .desc {font-size: .865rem; opacity: .75; margin-top: 12px; line-height: 1.65; max-width: 720px;}
.sp-header .feat {margin-top: 16px; display: flex; flex-wrap: wrap; gap: 8px;}
.sp-header .feat span {
  font-size: .76rem; font-weight: 600; color: #dbe9f7;
  background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.16);
  border-radius: 999px; padding: 4px 12px;
}

/* ---------- 고지 배너 ---------- */
.sp-warn {
  display: flex; align-items: flex-start; gap: 8px;
  background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706;
  color: #92400e; border-radius: 10px; padding: 11px 16px;
  font-size: .865rem; line-height: 1.55; margin: 12px 0 4px 0;
}

/* ---------- 섹션 헤더 ---------- */
.sp-sec {
  display: flex; align-items: center; gap: 10px;
  color: var(--sp-ink); font-weight: 800; font-size: 1.13rem;
  margin: 10px 0 12px 0; letter-spacing: -.01em;
}
.sp-sec::before {
  content: ""; width: 4px; height: 1.15em; border-radius: 2px;
  background: linear-gradient(180deg, var(--sp-primary), var(--sp-accent));
  flex: 0 0 auto;
}

/* ---------- 모드 배지 ---------- */
.sp-badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 13px; border-radius: 999px;
  font-size: .78rem; font-weight: 700; letter-spacing: .01em;
}
.sp-badge::before {content: ""; width: 7px; height: 7px; border-radius: 50%; flex: 0 0 auto;}
.sp-badge.demo {background: #eef2ff; color: #4338ca; border: 1px solid #c7d2fe;}
.sp-badge.demo::before {background: #6366f1;}
.sp-badge.ai {background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0;}
.sp-badge.ai::before {background: #10b981;}
.sp-badge.edited {background: #fffbeb; color: #b45309; border: 1px solid #fde68a;}
.sp-badge.edited::before {background: #f59e0b;}

/* ---------- 메트릭 카드 ---------- */
.sp-metric {
  background: var(--sp-surface); border: 1px solid var(--sp-border);
  border-top: 3px solid var(--sp-primary);
  border-radius: var(--sp-radius); padding: 16px 10px 13px; text-align: center;
  box-shadow: var(--sp-shadow-sm);
  transition: box-shadow .18s ease, transform .18s ease;
}
.sp-metric:hover {box-shadow: var(--sp-shadow-md); transform: translateY(-2px);}
.sp-metric .v {
  font-size: 1.72rem; font-weight: 800; color: var(--sp-primary);
  line-height: 1.15; font-variant-numeric: tabular-nums; letter-spacing: -.02em;
}
.sp-metric .l {
  font-size: .72rem; font-weight: 600; color: var(--sp-muted);
  margin-top: 5px; letter-spacing: .05em;
}
.sp-metric.danger {border-top-color: #dc2626;}
.sp-metric.danger .v {color: #b91c1c;}
.sp-metric.warn {border-top-color: #ea580c;}
.sp-metric.warn .v {color: #c2410c;}

/* ---------- 위험 등급 배지 (색상은 인라인으로 주입) ---------- */
.risk-badge {
  display: inline-block; min-width: 68px; text-align: center;
  padding: 4px 11px; border-radius: 999px; color: #fff;
  font-weight: 700; font-size: .78rem; letter-spacing: .01em;
}

/* ---------- 교차검토 판정 Pill 배지 ---------- */
.status-pill {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  min-width: 86px; padding: 5px 14px; border-radius: 999px;
  font-size: .8rem; font-weight: 700; white-space: nowrap;
}
.status-pill::before {font-weight: 800; font-size: .82rem;}
.status-pill.s-ok  {background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0;}
.status-pill.s-ok::before  {content: "✓";}
.status-pill.s-fix {background: #fffbeb; color: #b45309; border: 1px solid #fde68a;}
.status-pill.s-fix::before {content: "!";}
.status-pill.s-na  {background: #f1f5f9; color: #64748b; border: 1px solid var(--sp-border-strong);}
.status-pill.s-na::before  {content: "–";}

/* ---------- 표 ---------- */
.sp-table-wrap {
  overflow-x: auto; border: 1px solid var(--sp-border);
  border-radius: var(--sp-radius); box-shadow: var(--sp-shadow-sm);
  background: var(--sp-surface);
}
table.sp-table {border-collapse: collapse; width: 100%; font-size: .855rem; min-width: 900px;}
table.sp-table th {
  background: var(--sp-surface-2); color: #475569;
  font-size: .74rem; font-weight: 700; letter-spacing: .06em;
  padding: 11px 10px; text-align: left; white-space: nowrap;
  border-bottom: 2px solid var(--sp-border);
  position: sticky; top: 0;
}
table.sp-table td {
  border-bottom: 1px solid #eef2f7; padding: 10px; vertical-align: top;
  color: var(--sp-ink); line-height: 1.55;
}
table.sp-table tr:last-child td {border-bottom: none;}
table.sp-table tbody tr:hover td, table.sp-table tr:hover td {background: #f6f9fd;}
table.sp-table td.c {text-align: center; white-space: nowrap;}
table.sp-table small {color: var(--sp-muted); font-size: .8em;}

/* ---------- PPE 칩 ---------- */
.ppe-chip {
  display: inline-flex; align-items: center; gap: 7px;
  background: var(--sp-surface); border: 1px solid var(--sp-border-strong);
  color: #334155; border-radius: 999px; padding: 5px 14px;
  margin: 3px 5px 3px 0; font-size: .83rem; font-weight: 600;
  box-shadow: var(--sp-shadow-sm);
}
.ppe-chip::before {
  content: ""; width: 7px; height: 7px; border-radius: 50%;
  background: var(--sp-accent); flex: 0 0 auto;
}

/* ---------- 변경사항 카드 ---------- */
.chg {
  display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
  background: var(--sp-surface); border: 1px solid var(--sp-border);
  border-left: 4px solid var(--sp-accent);
  border-radius: 0 10px 10px 0; padding: 10px 14px; margin: 7px 0;
  font-size: .875rem; line-height: 1.55; box-shadow: var(--sp-shadow-sm);
}
.chg .tag {
  font-size: .74rem; font-weight: 700; border-radius: 6px;
  padding: 2px 8px; white-space: nowrap;
}
.chg .tag.add {background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0;}
.chg .tag.mod {background: #fff7ed; color: #c2410c; border: 1px solid #fed7aa;}

/* ---------- 버튼 ---------- */
/* 메인 CTA: 위험성평가 생성 및 2차 교차검토 시작 */
.st-key-btn_generate button {
  background: linear-gradient(130deg, var(--sp-primary) 0%, var(--sp-primary-2) 100%);
  color: #fff; border: none; border-radius: 12px;
  min-height: 3.35rem; font-size: 1.05rem; font-weight: 800; letter-spacing: .01em;
  box-shadow: 0 4px 14px rgba(13, 59, 102, .28);
  transition: transform .16s ease, box-shadow .16s ease, filter .16s ease;
  margin-top: 6px;
}
.st-key-btn_generate button:hover {
  filter: brightness(1.07); transform: translateY(-1px);
  box-shadow: 0 7px 20px rgba(13, 59, 102, .34);
  color: #fff; border: none;
}
.st-key-btn_generate button:active {transform: translateY(0); box-shadow: 0 3px 10px rgba(13,59,102,.25);}
.st-key-btn_generate button:focus:not(:active) {color: #fff;}

/* 보조 버튼: 샘플 입력 불러오기 */
.st-key-btn_sample button {
  background: var(--sp-surface); color: var(--sp-primary);
  border: 1.5px solid var(--sp-border-strong); border-radius: 10px;
  font-weight: 700; min-height: 2.6rem;
  transition: border-color .15s ease, background .15s ease;
}
.st-key-btn_sample button:hover {border-color: var(--sp-primary); background: #f6f9fd; color: var(--sp-primary);}

/* 다운로드 버튼 */
.st-key-btn_download button, .st-key-btn_download_html button {
  background: linear-gradient(130deg, var(--sp-primary) 0%, var(--sp-primary-2) 100%);
  color: #fff; border: none; border-radius: 12px;
  min-height: 3rem; font-size: .98rem; font-weight: 800;
  box-shadow: 0 4px 14px rgba(13, 59, 102, .24);
  transition: transform .16s ease, box-shadow .16s ease, filter .16s ease;
}
.st-key-btn_download button:hover, .st-key-btn_download_html button:hover {
  filter: brightness(1.07); transform: translateY(-1px); color: #fff; border: none;
}
.st-key-btn_download_locked button {
  border-radius: 12px; min-height: 3rem; font-weight: 600;
}

/* ---------- 입력정보 확인 안내 (권장 안내 톤 — 오류 아님) ---------- */
.sp-check {
  border-radius: 10px; padding: 10px 16px; font-size: .875rem;
  line-height: 1.55; margin: 4px 0 10px 0; border: 1px solid var(--sp-border);
}
.sp-check.ok {background: #f4f9f6; border-color: #cde5d8; color: #2f6b4f;}
.sp-check.warn {background: #fdfaf3; border-color: #ecdfc0; color: #7a6234;}
.sp-check small {color: #94a3b8;}

/* ---------- 개선 전/후·검수·대책 표시 ---------- */
.ctl-tag {
  display: inline-block; font-size: .7rem; font-weight: 700;
  border-radius: 5px; padding: 1px 6px; margin-right: 5px; white-space: nowrap;
  background: #eef2ff; color: #4338ca; border: 1px solid #c7d2fe;
}
.ctl-tag.hi {background: #ecfdf5; color: #047857; border-color: #a7f3d0;}   /* 제거·대체·공학적 */
.mini-badge {
  display: inline-block; font-size: .72rem; font-weight: 700;
  border-radius: 999px; padding: 2px 9px; white-space: nowrap;
}
.mini-badge.over {background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca;}
.mini-badge.within {background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1;}
.mini-badge.review {background: #fffbeb; color: #b45309; border: 1px solid #fde68a;}
table.sp-table tr.nr-row td {background: #fffbeb !important;}
.blank-line {color: #94a3b8; letter-spacing: .05em;}
.risk-cell-num {font-size: 1.05rem; font-weight: 800;}

/* ---------- 기타 다듬기 ---------- */
[data-testid="stAlert"] {border-radius: 10px;}
div[data-testid="stExpander"] {border-radius: 10px;}
hr {margin: 1.4rem 0 1rem 0;}

/* ---------- 반응형 (모바일) ---------- */
@media (max-width: 640px) {
  .sp-header {padding: 22px 20px;}
  .sp-header h1 {font-size: 1.5rem;}
  .sp-header .desc {font-size: .82rem;}
  .sp-metric .v {font-size: 1.4rem;}
  .sp-sec {font-size: 1.02rem;}
  .st-key-btn_generate button {font-size: .95rem; min-height: 3rem;}
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 세션 상태 초기화
# ---------------------------------------------------------------------------

if "result" not in st.session_state:
    st.session_state.result = None  # FullResult
st.session_state.setdefault("result_ver", 0)  # 편집 위젯 상태 초기화용 버전 번호
for key in ["in_name", "in_location", "in_description", "in_equipment", "in_workers", "in_notes"]:
    st.session_state.setdefault(key, "")


def load_sample():
    key = st.session_state.get("demo_scenario", demo_data.DEFAULT_SCENARIO)
    s = demo_data.get_sample_input(key)
    st.session_state.in_name = s.name
    st.session_state.in_location = s.location
    st.session_state.in_description = s.description
    st.session_state.in_equipment = s.equipment
    st.session_state.in_workers = s.workers
    st.session_state.in_notes = s.notes


# ---------------------------------------------------------------------------
# 헤더
# ---------------------------------------------------------------------------

st.markdown(
    """
<div class="sp-header">
  <span class="eyebrow">Industrial Safety AI Solution</span>
  <h1>🦺 위험성평가 코파일럿 (SafePilot AI)</h1>
  <div class="desc">
    작업 정보를 입력하면 AI가 위험성평가, 예방대책, 개인보호구, TBM, 체크리스트를 생성하고,
    2차 AI가 누락·모순을 교차검토하여 보완한 최종 결과와 PDF 보고서를 제공합니다.
  </div>
  <div class="feat">
    <span>2단계 AI 교차검토</span>
    <span>20개 위험범주 전수 점검</span>
    <span>개선 전·후 위험성 관리</span>
    <span>TBM · 체크리스트 자동 생성</span>
    <span>PDF 보고서</span>
  </div>
</div>
<div class="sp-warn">⚠️ AI가 작성한 초안이며 현장 책임자의 최종 확인이 필요합니다.
법적 판단의 근거로 사용할 수 없습니다.</div>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 입력 영역
# ---------------------------------------------------------------------------

st.markdown('<div class="sp-sec">작업 정보 입력</div>', unsafe_allow_html=True)

top1, top2 = st.columns([2.2, 1])
with top1:
    key_exists = ai_service.has_api_key()
    mode = st.radio(
        "생성 모드",
        ["데모 모드 (API 키 불필요)", "실제 AI 모드 (API 키 필요)"],
        horizontal=True,
        index=1 if key_exists else 0,
        help="데모 모드는 미리 작성된 샘플 결과를 보여주고, 실제 AI 모드는 입력한 작업 정보로 AI가 새로 생성합니다.",
    )
    is_demo_mode = mode.startswith("데모")
    badge = (
        '<span class="sp-badge demo">현재: 데모 모드 — 샘플 결과 표시</span>'
        if is_demo_mode
        else '<span class="sp-badge ai">현재: 실제 AI 모드 — 입력 내용으로 생성</span>'
    )
    st.markdown(badge, unsafe_allow_html=True)
    if not is_demo_mode and not key_exists:
        st.warning(
            "API 키가 설정되어 있지 않습니다. `.env` 파일(로컬) 또는 Streamlit secrets(배포)에 "
            "`GEMINI_API_KEY`를 등록해 주세요. 키가 없다면 데모 모드를 이용해 주세요.",
            icon="🔑",
        )
with top2:
    st.selectbox(
        "샘플·데모 시나리오",
        options=list(demo_data.SCENARIO_LABELS.keys()),
        format_func=lambda k: demo_data.SCENARIO_LABELS[k],
        key="demo_scenario",
    )
    st.button(":material/content_paste: 샘플 입력 불러오기", on_click=load_sample,
              key="btn_sample", width="stretch")

c1, c2 = st.columns(2)
with c1:
    st.text_input("작업명 *", key="in_name", placeholder="예: 선박 블록 내부 배관 용접 작업")
    st.text_input("작업 장소 *", key="in_location", placeholder="예: OO조선소 제2도크 블록 내부")
    st.text_area("작업 내용 *", key="in_description", height=120,
                 placeholder="작업 순서와 방법을 구체적으로 입력할수록 정확한 평가가 생성됩니다.")
with c2:
    st.text_input("사용 장비", key="in_equipment", placeholder="예: CO2 용접기, 그라인더, 이동식 조명")
    st.text_input("작업 인원", key="in_workers", placeholder="예: 용접공 2명, 감시자 1명")
    st.text_area("특이사항", key="in_notes", height=120,
                 placeholder="예: 밀폐공간, 인접 도장 작업 병행, 야간 작업 등")

# ---------------------------------------------------------------------------
# 입력정보 확인 (로컬 규칙 기반 안내 — Gemini 호출 없음, 생성을 차단하지 않음)
# ---------------------------------------------------------------------------

_preview = WorkInput(
    name=st.session_state.in_name,
    location=st.session_state.in_location,
    description=st.session_state.in_description,
    equipment=st.session_state.in_equipment,
    workers=st.session_state.in_workers,
    notes=st.session_state.in_notes,
)
_review = input_check.review_input(_preview)
if _review["has_input"]:
    if _review["unconfirmed_count"] > 0 or _review["general"]:
        st.markdown(
            '<div class="sp-check warn"><b>입력정보 확인</b> — ⚠ 추가 확인 권장 정보 '
            f'{_review["unconfirmed_count"]}건이 있습니다. '
            "아직 입력에서 확인되지 않은 정보를 보완하면 목록에서 자동으로 빠집니다. "
            "<small>(안내일 뿐이며, 현재 정보 그대로도 생성할 수 있습니다)</small></div>",
            unsafe_allow_html=True,
        )
        with st.expander("추가 확인 권장 정보 보기", expanded=True):
            for note in _review["general"]:
                st.markdown(f"- {note}")
            for trait in _review["traits"]:
                if not trait["items"]:
                    continue
                st.markdown(f"**{trait['label']}**")
                st.markdown("\n".join(f"- {item}" for item in trait["items"]))
            if _review["confirmed_count"]:
                st.caption(
                    f"이미 입력에서 확인된 권장 항목 {_review['confirmed_count']}건은 "
                    "제외했습니다."
                )
    else:
        _done = (
            f' <small>(작업 특성 권장 확인 정보 {_review["confirmed_count"]}건이 '
            "모두 입력에서 확인되었습니다)</small>"
            if _review["confirmed_count"] else ""
        )
        st.markdown(
            '<div class="sp-check ok"><b>입력정보 확인</b> — ✅ 현재 입력정보로 '
            f"위험성평가를 시작할 수 있습니다.{_done}</div>",
            unsafe_allow_html=True,
        )

generate = st.button(
    ":material/fact_check: 위험성평가 생성 및 2차 교차검토 시작",
    type="primary", key="btn_generate", width="stretch",
)

# ---------------------------------------------------------------------------
# 생성 처리
# ---------------------------------------------------------------------------

if generate:
    work = WorkInput(
        name=st.session_state.in_name,
        location=st.session_state.in_location,
        description=st.session_state.in_description,
        equipment=st.session_state.in_equipment,
        workers=st.session_state.in_workers,
        notes=st.session_state.in_notes,
    )
    missing = work.missing_required()
    if not is_demo_mode and missing:
        st.error(f"다음 필수 항목을 입력해 주세요: {', '.join(missing)}", icon="✍️")
        st.session_state.result = None
    else:
        try:
            if is_demo_mode:
                # 데모 모드: 선택한 시나리오의 샘플 결과 사용 (입력이 비면 샘플 입력으로 대체)
                scenario = st.session_state.get("demo_scenario", demo_data.DEFAULT_SCENARIO)
                demo_work = work if not missing else demo_data.get_sample_input(scenario)
                with st.spinner("데모 결과를 불러오는 중..."):
                    first = demo_data.get_demo_first(scenario)
                    review = demo_data.get_demo_review(scenario)
                st.session_state.result = FullResult(
                    work_input=demo_work, first=first, review=review,
                    is_demo=True,
                    generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
                )
                st.session_state.result_ver += 1  # 새 결과 → 편집 위젯 상태 초기화
                if missing:
                    st.info("데모 모드: 입력값이 비어 있어 샘플 작업 정보로 결과를 표시합니다.", icon="ℹ️")
            else:
                with st.status("AI가 위험성평가를 작성하고 있습니다...", expanded=True) as status:
                    st.write("1단계: 작업 분석 및 위험성평가 초안 생성 중... (수 분이 걸릴 수 있습니다)")
                    first = ai_service.run_first_pass(work)
                    st.write(f"1단계 완료: 위험요인 {len(first.hazards)}건 도출")
                    st.write("2단계: AI 교차검토 및 누락 보완 중...")
                    review = ai_service.run_review_pass(work, first)
                    st.write(f"2단계 완료: 변경사항 {len(review.changes)}건 반영")
                    status.update(label="위험성평가 생성 완료", state="complete")
                st.session_state.result = FullResult(
                    work_input=work, first=first, review=review,
                    is_demo=False,
                    generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
                )
                st.session_state.result_ver += 1  # 새 결과 → 편집 위젯 상태 초기화
        except ai_service.AIServiceError as e:
            st.session_state.result = None
            st.error(str(e), icon="🚨")
        except Exception as e:  # 예상치 못한 오류도 사용자 친화적으로
            st.session_state.result = None
            st.error(f"예상치 못한 오류가 발생했습니다: {e}", icon="🚨")

# ---------------------------------------------------------------------------
# 결과 영역
# ---------------------------------------------------------------------------

result: FullResult | None = st.session_state.result

if result:
    final = result.review.final
    esc = html.escape

    # 최종 위험성 판단 기준 적용 (improvement_required 는 코드가 산정 — AI 출력 아님)
    try:
        apply_threshold(final, int(risk_threshold))
        result.threshold = int(risk_threshold)
    except Exception:
        pass  # 배포 전 세션에 남은 구버전 결과 객체 호환

    st.divider()
    mode_badge = (
        '<span class="sp-badge demo">데모 모드 결과 (샘플 데이터)</span>'
        if result.is_demo
        else '<span class="sp-badge ai">실제 AI 모드 결과</span>'
    )
    # getattr: 배포 전 세션에 남아 있는 구버전 결과 객체(edited 필드 없음)와의 호환 처리
    if getattr(result, "edited", False):
        mode_badge += ' <span class="sp-badge edited">책임자 수정 반영</span>'
    st.markdown(
        f'<div class="sp-sec">위험성평가 결과 {mode_badge}</div>', unsafe_allow_html=True
    )

    # 작업 개요
    w = result.work_input
    st.markdown(
        f"**작업명:** {esc(w.name)}  |  **장소:** {esc(w.location)}  |  **생성:** {result.generated_at}"
    )
    if final.work_overview:
        st.info(final.work_overview, icon="📌")
    if final.work_steps:
        with st.expander("작업 세부 단계 보기"):
            for s in final.work_steps:
                st.markdown(f"- {s}")

    # 핵심 위험도 요약 (danger/warn 클래스는 시각적 구분용 — 값 계산 로직은 동일)
    counts = final.count_by_level()
    m1, m2, m3, m4, m5 = st.columns(5)
    metrics = [
        (m1, len(final.hazards), "총 위험요인", ""),
        (m2, f"{final.max_risk_score}점", f"최고 위험도 ({final.max_risk_level})",
         "danger" if final.max_risk_level == "매우 높음" else ("warn" if final.max_risk_level == "높음" else "")),
        (m3, counts["매우 높음"], "매우 높음", "danger" if counts["매우 높음"] else ""),
        (m4, counts["높음"], "높음", "warn" if counts["높음"] else ""),
        (m5, counts["보통"] + counts["낮음"], "보통 이하", ""),
    ]
    for col, value, label, cls in metrics:
        col.markdown(
            f'<div class="sp-metric {cls}"><div class="v">{value}</div><div class="l">{label}</div></div>',
            unsafe_allow_html=True,
        )

    # 요약 상태 배지: 검수 필요 / 기준 초과 (코드 산정 상태)
    nr_count = getattr(final, "needs_review_count", 0)
    over_count = getattr(final, "improvement_required_count", 0)
    badges = []
    if nr_count:
        badges.append(f'<span class="mini-badge review">⚠ 검수 필요 항목: {nr_count}건</span>')
    if over_count:
        badges.append(
            f'<span class="mini-badge over">기준 초과({int(risk_threshold)}점) 항목: {over_count}건 — 작업 전 추가 개선 검토 필요</span>')
    if not badges:
        badges.append(
            f'<span class="mini-badge within">모든 위험요인이 개선 후 설정 기준({int(risk_threshold)}점) 이내입니다</span>')
    st.markdown('<div style="margin-top:8px">' + " ".join(badges) + "</div>", unsafe_allow_html=True)

    st.write("")

    # -----------------------------------------------------------------------
    # 결과 편집 모드 (책임자 검토·수정)
    # - 수정된 값은 Pydantic으로 재검증되며, 위험도 점수는 코드가 자동 재계산한다.
    # - AI 교차검토 내역(검증 기록)은 수정하지 않고 그대로 보존한다.
    # -----------------------------------------------------------------------
    ver = st.session_state.result_ver
    edit_on = st.toggle(
        ":material/edit_note: 결과 편집 모드 (책임자 검토·수정)",
        key=f"edit_toggle_{ver}",
        help="AI 결과를 현장 여건에 맞게 직접 수정할 수 있습니다. "
             "가능성·심각도를 수정하면 위험도 점수와 등급이 자동으로 다시 계산됩니다.",
    )
    if edit_on:
        with st.container(border=True):
            st.markdown("**① 위험성평가 표 수정** — 셀을 클릭해 내용을 고치고, "
                        "표 왼쪽 체크 후 Delete 키로 행 삭제, 맨 아래 빈 행에 입력하면 행이 추가됩니다.")
            hazard_df = pd.DataFrame([{
                "작업 단계": h.step,
                "분류": h.category,
                "위험요인": h.hazard,
                "원인": h.cause,
                "예상 피해": h.damage,
                "가능성(1-5)": h.likelihood,
                "심각도(1-5)": h.severity,
                "개선후 가능성(1-5)": getattr(h, "residual_likelihood", h.likelihood),
                "개선후 심각도(1-5)": getattr(h, "residual_severity", h.severity),
                "감소대책([유형] 내용, 줄바꿈 구분)": "\n".join(
                    getattr(m, "display", str(m)) for m in h.measures),
                "개인보호구(쉼표 구분)": ", ".join(h.ppe),
                "근거-가능성": getattr(h, "basis_likelihood", ""),
                "근거-심각도": getattr(h, "basis_severity", ""),
                "근거-개선후 가능성": getattr(h, "residual_basis_likelihood", ""),
                "근거-개선후 심각도": getattr(h, "residual_basis_severity", ""),
            } for h in final.hazards])
            _num_col = lambda help_txt: st.column_config.NumberColumn(  # noqa: E731
                min_value=1, max_value=5, step=1, help=help_txt)
            edited_df = st.data_editor(
                hazard_df,
                num_rows="dynamic",
                key=f"ed_hazards_{ver}",
                column_config={
                    "가능성(1-5)": _num_col("1=거의 없음 ~ 5=매우 높음"),
                    "심각도(1-5)": _num_col("1=경미 ~ 5=사망/다수 재해"),
                    "개선후 가능성(1-5)": _num_col("감소대책 이행 후 잔여 가능성"),
                    "개선후 심각도(1-5)": _num_col("감소대책 이행 후 잔여 심각도"),
                    "위험요인": st.column_config.TextColumn(width="large"),
                    "감소대책([유형] 내용, 줄바꿈 구분)": st.column_config.TextColumn(
                        width="large",
                        help="한 줄에 하나씩. 유형: [제거] [대체] [공학적] [관리적] [PPE] — 생략 시 관리적으로 처리"),
                },
            )
            st.caption("위험도 점수·등급(개선 전/후)은 저장 시 가능성 × 심각도로 자동 재계산됩니다. "
                       "개선 후 점수가 개선 전보다 높거나, 상위 대책 없이 심각도를 낮춘 행은 '검수 필요'로 표시됩니다. "
                       "위험요인이 비어 있는 행은 저장 시 제외됩니다.")

            st.markdown("**② 작업 개요 / 개인보호구 / TBM / 체크리스트 수정**")
            ed_overview = st.text_area(
                "작업 개요", value=final.work_overview, height=80, key=f"ed_ov_{ver}")
            ce1, ce2, ce3 = st.columns(3)
            ed_ppe = ce1.text_area(
                "개인보호구 (쉼표 또는 줄바꿈으로 구분)",
                value=", ".join(final.ppe_list), height=140, key=f"ed_ppe_{ver}")
            ed_tbm = ce2.text_area(
                "작업 전 TBM (한 줄에 한 항목)",
                value="\n".join(final.tbm), height=140, key=f"ed_tbm_{ver}")
            ed_chk = ce3.text_area(
                "작업 전 체크리스트 (한 줄에 한 항목)",
                value="\n".join(final.checklist), height=140, key=f"ed_chk_{ver}")

            if st.button(":material/save: 수정 내용 적용", type="primary",
                         key="btn_apply_edit", width="stretch"):
                hazards = []
                for _, row in edited_df.iterrows():
                    if not str(row.get("위험요인") or "").strip():
                        continue  # 위험요인이 빈 행은 제외
                    hazards.append({
                        "step": str(row.get("작업 단계") or "").strip(),
                        "category": str(row.get("분류") or "기타").strip() or "기타",
                        "hazard": str(row.get("위험요인") or "").strip(),
                        "cause": str(row.get("원인") or "").strip(),
                        "damage": str(row.get("예상 피해") or "").strip(),
                        "likelihood": row.get("가능성(1-5)"),
                        "severity": row.get("심각도(1-5)"),
                        "residual_likelihood": row.get("개선후 가능성(1-5)"),
                        "residual_severity": row.get("개선후 심각도(1-5)"),
                        "basis_likelihood": str(row.get("근거-가능성") or "").strip(),
                        "basis_severity": str(row.get("근거-심각도") or "").strip(),
                        "residual_basis_likelihood": str(row.get("근거-개선후 가능성") or "").strip(),
                        "residual_basis_severity": str(row.get("근거-개선후 심각도") or "").strip(),
                        # "[제거] 내용" 형태 문자열은 ControlMeasure 검증기가 유형·내용으로 해석
                        "measures": [m.strip() for m in
                                     str(row.get("감소대책([유형] 내용, 줄바꿈 구분)") or "").splitlines()
                                     if m.strip()],
                        "ppe": [p.strip() for p in
                                str(row.get("개인보호구(쉼표 구분)") or "").replace("\n", ",").split(",")
                                if p.strip()],
                    })
                # Pydantic 재검증: 1~5 범위 강제, 위험도 점수(개선 전/후)는 Python이 재계산
                new_final = AssessmentResult.model_validate({
                    "work_overview": ed_overview.strip(),
                    "work_steps": final.work_steps,
                    "hazards": hazards,
                    "no_hazard_steps": [ns.model_dump() for ns in getattr(final, "no_hazard_steps", [])],
                    "ppe_list": [p.strip() for p in ed_ppe.replace("\n", ",").split(",") if p.strip()],
                    "tbm": [l.strip() for l in ed_tbm.splitlines() if l.strip()],
                    "checklist": [l.strip() for l in ed_chk.splitlines() if l.strip()],
                })
                # 코드 전용 검증 파이프라인 (AI 재생성 없이): 규칙 위반 행은 '검수 필요' 표시,
                # 단계 번호 정렬·TBM 고정 항목 유지
                ai_service.postprocess_result(result.work_input, new_final,
                                              client=None, allow_regen=False)
                # 구버전 세션 객체와의 호환을 위해 현재 모델 클래스로 결과를 재구성한다
                data = result.model_dump()
                data["review"]["final"] = new_final.model_dump()
                data["edited"] = True
                st.session_state.result = FullResult.model_validate(data)
                st.session_state.result_ver += 1  # 편집 위젯을 새 값으로 초기화
                st.rerun()

    # 위험성평가 표 (개선 전·후 위험성 + 개선관리)
    st.markdown('<div class="sp-sec">위험성평가 표</div>', unsafe_allow_html=True)
    rows_html = ""
    for h in final.hazards:
        b_color = RISK_COLORS.get(h.risk_level, "#999")
        r_score = getattr(h, "residual_score", h.risk_score)
        r_level = getattr(h, "residual_level", h.risk_level)
        r_color = RISK_COLORS.get(r_level, "#999")
        needs_review = getattr(h, "needs_review", False)
        improvement_required = getattr(h, "improvement_required", False)

        # 위험요인 셀 (분류 태그 + 원인, 검수 필요 표시 포함)
        review_mark = (
            '<div><span class="mini-badge review">⚠ AI 검증 미통과 — 수동 검토 필요</span></div>'
            if needs_review else "")
        hazard_cell = (f"{review_mark}<b>{esc(h.hazard)}</b>"
                       f"<br><small>[{esc(h.category)}] 원인: {esc(h.cause)}</small>")

        # 감소대책 셀: [위계 라벨] 대책 + PPE + 상위 수준 검토 문구
        m_html = ""
        for m in getattr(h, "measures", []):
            ctype = getattr(m, "control_type", "administrative")
            label = getattr(m, "label", "관리적")
            desc = getattr(m, "description", str(m))
            hi = " hi" if ctype in ("elimination", "substitution", "engineering") else ""
            m_html += f'<div><span class="ctl-tag{hi}">{esc(label)}</span>{esc(desc)}</div>'
        ppe = ", ".join(esc(p) for p in h.ppe)
        if ppe:
            m_html += f"<small>PPE: {ppe}</small>"
        if getattr(h, "only_admin_ppe", lambda: False)():
            m_html += ('<div><small>※ 상위 수준의 감소대책(제거·대체·공학적 대책) 검토 필요</small></div>')

        # 개선 후 셀: 점수/등급 + 기준 판정
        judge = ('<span class="mini-badge over">기준 초과 — 작업 전 추가 개선 검토 필요</span>'
                 if improvement_required
                 else '<span class="mini-badge within">설정 기준 이내</span>')
        residual_cell = (f'<div class="risk-cell-num">{r_score}점</div>'
                         f'<span class="risk-badge" style="background:{r_color}">{esc(r_level)}</span>'
                         f"<div style='margin-top:4px'>{judge}</div>")

        row_cls = ' class="nr-row"' if needs_review else ""
        rows_html += f"""<tr{row_cls}>
          <td>{esc(h.step)}</td>
          <td>{hazard_cell}</td>
          <td>{esc(h.damage)}</td>
          <td class="c"><small>가능성 {h.likelihood} · 심각도 {h.severity}</small>
            <div class="risk-cell-num">{h.risk_score}점</div>
            <span class="risk-badge" style="background:{b_color}">{esc(h.risk_level)}</span></td>
          <td>{m_html}</td>
          <td class="c">{residual_cell}</td>
          <td><small>담당자 <span class="blank-line">______</span><br>
            예정일 <span class="blank-line">______</span><br>
            이행확인 <span class="blank-line">☐</span></small></td>
        </tr>"""

    # 유의미한 위험요인이 없는 작업단계
    for ns in getattr(final, "no_hazard_steps", []):
        rows_html += f"""<tr>
          <td>{esc(ns.step)}</td>
          <td colspan="6"><b>유의미한 위험요인 없음</b><br><small>사유: {esc(ns.reason or "-")}</small></td>
        </tr>"""

    st.markdown(
        f"""<div class="sp-table-wrap"><table class="sp-table" style="min-width:1050px">
        <tr><th>작업단계</th><th>위험요인</th><th>예상 피해</th><th>개선 전 위험성</th>
        <th>감소대책</th><th>개선 후 위험성</th><th>개선관리</th></tr>
        {rows_html}</table></div>""",
        unsafe_allow_html=True,
    )
    st.caption("위험도 점수 = 발생 가능성(1~5) × 피해 심각도(1~5), 개선 후 잔여 위험도 포함 — 모두 시스템이 직접 계산합니다. "
               "구간: 1~4 낮음 / 5~9 보통 / 10~16 높음 / 17~25 매우 높음 · "
               f"최종 위험성 판단 기준 {int(risk_threshold)}점 이하(사이드바에서 조정 가능). "
               "'설정 기준 이내'는 추가 개선이 불필요하다는 의미가 아니라, 설정된 판단 기준 범위 안에 들어왔다는 의미입니다. "
               "개선관리(담당자·예정일·이행확인)는 출력 후 수기 기입란입니다.")

    # 위험요인별 판단 근거 (표 밖 별도 영역)
    # - 이 탭의 역할은 "왜 개선 전/후 점수가 그렇게 판단되었는가"의 설명이다.
    # - 감소대책은 메인 위험성평가표에 이미 표시되므로 여기서 중복 표시하지 않는다.
    with st.expander("위험요인별 위험성 판단 근거 보기"):
        for i, h in enumerate(final.hazards, 1):
            bl = getattr(h, "basis_likelihood", "") or "-"
            bs = getattr(h, "basis_severity", "") or "-"
            rbl = getattr(h, "residual_basis_likelihood", "") or "-"
            rbs = getattr(h, "residual_basis_severity", "") or "-"
            r_l = getattr(h, "residual_likelihood", h.likelihood)
            r_s = getattr(h, "residual_severity", h.severity)
            if i > 1:
                st.markdown("---")
            st.markdown(f"**{i}. {esc(h.hazard)}**")
            st.markdown(
                f"**개선 전 판단**\n"
                f"- 가능성 {h.likelihood}점 — {esc(bl)}\n"
                f"- 심각도 {h.severity}점 — {esc(bs)}")
            st.markdown(
                f"**개선 후 판단**\n"
                f"- 가능성 {r_l}점 — {esc(rbl)}\n"
                f"- 심각도 {r_s}점 — {esc(rbs)}")
        st.caption("※ 위 점수는 SafePilot 자체 평가 기준(부록 수록)에 따른 것으로, 법정 단일 평가척도가 아닙니다.")

    # 개인보호구
    st.markdown('<div class="sp-sec">개인보호구 (PPE)</div>', unsafe_allow_html=True)
    st.markdown(
        "".join(f'<span class="ppe-chip">{esc(p)}</span>' for p in final.ppe_list),
        unsafe_allow_html=True,
    )

    col_tbm, col_chk = st.columns(2)
    with col_tbm:
        st.markdown('<div class="sp-sec">작업 전 TBM</div>', unsafe_allow_html=True)
        for i, item in enumerate(final.tbm, 1):
            st.markdown(f"**{i}.** {item}")
    with col_chk:
        st.markdown('<div class="sp-sec">작업 전 체크리스트</div>', unsafe_allow_html=True)
        for item in final.checklist:
            st.markdown(f"☐ {item}")

    # AI 교차검토 결과 (판정별 Pill 배지: 적정=Green / 보완=Amber / 해당없음=Gray)
    st.markdown('<div class="sp-sec">AI 교차검토 결과 (20개 위험범주 전수 점검)</div>', unsafe_allow_html=True)
    st.markdown(
        '<p style="font-size:.83rem; color:var(--sp-muted); margin:-4px 0 10px 14px; line-height:1.5;">'
        '※ 본 내용은 최종 결과에 반영된 AI 교차검토 및 보완 과정을 확인하기 위한 검증 기록입니다.</p>',
        unsafe_allow_html=True,
    )
    status_cls = {"적정": "s-ok", "보완": "s-fix", "해당없음": "s-na"}
    finding_rows = ""
    for f in result.review.findings:
        pill = status_cls.get(f.status, "s-na")
        finding_rows += f"""<tr>
          <td class="c">{esc(f.category)}</td>
          <td class="c"><span class="status-pill {pill}">{esc(f.status)}</span></td>
          <td>{esc(f.comment)}</td></tr>"""
    st.markdown(
        f"""<div class="sp-table-wrap"><table class="sp-table" style="min-width:600px">
        <tr><th>검토 범주</th><th>판정</th><th>검토 의견</th></tr>{finding_rows}</table></div>""",
        unsafe_allow_html=True,
    )

    # 변경사항
    st.markdown('<div class="sp-sec">검토 전후 변경사항</div>', unsafe_allow_html=True)
    if result.review.changes:
        for c in result.review.changes:
            tag_cls = "add" if c.action == "추가" else "mod"
            st.markdown(
                f'<div class="chg"><span class="tag {tag_cls}">[{c.action} · {esc(c.target)}]</span>'
                f"{esc(c.description)}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown("검토 결과 변경사항이 없습니다.")

    # 근로자 참여 (현장 기재용 — 저장 기능 없음)
    st.markdown('<div class="sp-sec">근로자 의견</div>', unsafe_allow_html=True)
    st.markdown(
        """<div class="sp-table-wrap" style="padding:14px 18px">
        <small style="color:#64748b">본 위험성평가 결과에 대한 근로자 의견을 청취하고 아래에 기재합니다. (출력 후 수기 기입란)</small>
        <div style="margin:10px 0 14px 0; border-bottom:1px dashed #cbd5e1; height:1.4em"></div>
        <div style="margin:0 0 14px 0; border-bottom:1px dashed #cbd5e1; height:1.4em"></div>
        <div style="color:#334155; font-size:.9rem">
          참여 근로자&nbsp;&nbsp; 성명 <span class="blank-line">______________</span>
          &nbsp;&nbsp;서명 <span class="blank-line">______________</span>
        </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # 책임자 확인 + PDF 다운로드
    st.divider()
    st.markdown('<div class="sp-sec">보고서 다운로드</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sp-warn">⚠️ 본 결과는 AI가 작성한 초안이며 현장 책임자의 최종 확인이 필요합니다.</div>',
        unsafe_allow_html=True,
    )
    confirmed = st.checkbox(
        "본 위험성평가 결과는 AI가 작성한 초안임을 이해하였으며, "
        "현장 책임자로서 위험요인 및 대책을 최종 검토·확인후 보고서를 출력합니다."
    )

    if confirmed:
        file_stem = f"SafePilot_위험성평가_{datetime.now().strftime('%Y%m%d_%H%M')}"
        if pdf_service.pdf_available():
            try:
                pdf_bytes = pdf_service.build_pdf(result)
                st.download_button(
                    ":material/download: PDF 보고서 다운로드",
                    data=pdf_bytes,
                    file_name=f"{file_stem}.pdf",
                    mime="application/pdf",
                    type="primary",
                    key="btn_download",
                    width="stretch",
                )
            except Exception:
                html_report = pdf_service.build_html_report(result)
                st.warning("PDF 생성에 실패하여 HTML 보고서로 대체합니다. "
                           "브라우저에서 열어 인쇄(PDF로 저장) 기능을 사용하세요.", icon="ℹ️")
                st.download_button(
                    ":material/download: HTML 보고서 다운로드",
                    data=html_report.encode("utf-8"),
                    file_name=f"{file_stem}.html",
                    mime="text/html",
                    type="primary",
                    key="btn_download_html",
                    width="stretch",
                )
        else:
            html_report = pdf_service.build_html_report(result)
            st.info("이 환경에서 한글 PDF 폰트를 찾지 못해 HTML 보고서를 제공합니다. "
                    "브라우저에서 열어 인쇄(PDF로 저장) 기능을 사용하세요.", icon="ℹ️")
            st.download_button(
                ":material/download: HTML 보고서 다운로드",
                data=html_report.encode("utf-8"),
                file_name=f"{file_stem}.html",
                mime="text/html",
                type="primary",
                key="btn_download_html",
                width="stretch",
            )
    else:
        st.button(":material/lock: PDF 보고서 다운로드 (책임자 확인 후 활성화)", disabled=True,
                  key="btn_download_locked", width="stretch")

# 푸터
st.divider()
st.caption(
    "SafePilot AI · AI 기반 위험성평가 초안 생성 도구 · "
    "본 서비스의 결과는 참고용 초안으로, 산업안전보건법상 위험성평가의 법적 요건을 대체하지 않습니다."
)
