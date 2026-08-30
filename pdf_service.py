"""SafePilot AI - 보고서 생성 (PDF / HTML)

- ReportLab으로 PDF 보고서를 생성한다. (가로 방향 A4 — 개선 전·후 위험성 표 가독성 확보)
- 한글이 깨지지 않도록 시스템에 설치된 한글 폰트를 탐색하여 사용한다.
  (Windows: 맑은 고딕, Streamlit Cloud: packages.txt의 fonts-nanum으로 설치되는 나눔고딕)
- 사용 가능한 한글 폰트가 없으면 HTML 보고서 다운로드로 대체한다.
- 위험도 점수·등급(개선 전/후)과 기준 초과·검수 필요 상태는 모두 코드 계산값을 사용한다.
"""

from __future__ import annotations

import html
import io
import os

from models import (
    DEFAULT_RISK_THRESHOLD, FullResult, RISK_COLORS, apply_threshold,
)

# 한글 폰트 후보 경로 (일반 / 볼드)
_FONT_CANDIDATES = [
    # Windows
    (r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf"),
    # Streamlit Community Cloud (packages.txt: fonts-nanum)
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
     "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
    ("/usr/share/fonts/truetype/nanum/NanumGothicCoding.ttf", None),
    # 기타 Linux
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", None),
    # macOS
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", None),
]


def find_korean_font() -> tuple[str | None, str | None]:
    """사용 가능한 한글 폰트 경로 (일반, 볼드)를 반환한다. 없으면 (None, None)."""
    for regular, bold in _FONT_CANDIDATES:
        if os.path.exists(regular):
            if bold and not os.path.exists(bold):
                bold = None
            return regular, bold
    return None, None


def pdf_available() -> bool:
    """한글 PDF 생성이 가능한 환경인지 여부."""
    regular, _ = find_korean_font()
    return regular is not None


# 보고서 상단에 넣을 기관 로고 후보 경로 (없으면 로고 없이 생성)
_LOGO_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "kosha_logo.png"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png"),
]


def find_logo() -> str | None:
    """사용 가능한 로고 이미지 경로를 반환한다. 없으면 None."""
    for path in _LOGO_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _threshold_of(result: FullResult) -> int:
    return int(getattr(result, "threshold", DEFAULT_RISK_THRESHOLD) or DEFAULT_RISK_THRESHOLD)


# 위험등급별 연한 배경 틴트 (검정 글씨 가독성을 유지하면서 등급을 색으로 구분)
_LEVEL_TINTS = {
    "낮음": "#e8f5e9",
    "보통": "#fff8e1",
    "높음": "#ffe9d6",
    "매우 높음": "#ffe2e0",
}


def _measure_lines(h) -> list[str]:
    """감소대책을 '[유형] 내용' 문자열 목록으로 변환한다."""
    lines = []
    for m in getattr(h, "measures", []):
        label = getattr(m, "label", None) or "관리적"
        desc = getattr(m, "description", None)
        lines.append(f"[{label}] {desc}" if desc is not None else f"- {m}")
    return lines


# ---------------------------------------------------------------------------
# PDF 생성 (가로 A4)
# ---------------------------------------------------------------------------

def build_pdf(result: FullResult) -> bytes:
    """위험성평가 결과를 PDF 바이트로 생성한다."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    regular_path, bold_path = find_korean_font()
    if not regular_path:
        raise RuntimeError("사용 가능한 한글 폰트를 찾지 못했습니다.")

    # TTC 파일도 subfontIndex 0으로 등록 시도
    if regular_path.endswith(".ttc"):
        pdfmetrics.registerFont(TTFont("KR", regular_path, subfontIndex=0))
    else:
        pdfmetrics.registerFont(TTFont("KR", regular_path))
    if bold_path:
        pdfmetrics.registerFont(TTFont("KR-Bold", bold_path))
        bold_font = "KR-Bold"
    else:
        bold_font = "KR"

    styles = {
        "title": ParagraphStyle("title", fontName=bold_font, fontSize=18,
                                leading=24, alignment=TA_CENTER,
                                textColor=colors.HexColor("#0d3b66")),
        "subtitle": ParagraphStyle("subtitle", fontName="KR", fontSize=9,
                                   leading=13, alignment=TA_CENTER,
                                   textColor=colors.HexColor("#555555")),
        "h2": ParagraphStyle("h2", fontName=bold_font, fontSize=12, leading=17,
                             spaceBefore=10, spaceAfter=4,
                             textColor=colors.HexColor("#0d3b66")),
        "body": ParagraphStyle("body", fontName="KR", fontSize=9, leading=14),
        "cell": ParagraphStyle("cell", fontName="KR", fontSize=8, leading=12),
        "cell_b": ParagraphStyle("cell_b", fontName=bold_font, fontSize=8, leading=12),
        "warn": ParagraphStyle("warn", fontName="KR", fontSize=8.5, leading=13,
                               textColor=colors.HexColor("#8a5a00")),
        "note": ParagraphStyle("note", fontName="KR", fontSize=8, leading=12,
                               spaceAfter=4, textColor=colors.HexColor("#64748b")),
        "alert": ParagraphStyle("alert", fontName=bold_font, fontSize=8, leading=12,
                                textColor=colors.HexColor("#b45309")),
    }

    def P(text, style="body"):
        return Paragraph(html.escape(str(text)).replace("\n", "<br/>"), styles[style])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        topMargin=12 * mm, bottomMargin=12 * mm,
        leftMargin=13 * mm, rightMargin=13 * mm,
        title="SafePilot AI 위험성평가 보고서",
    )
    CONTENT_W = 271  # 가로 A4 사용 가능 폭(mm)

    story = []
    w = result.work_input
    final = result.review.final
    threshold = _threshold_of(result)
    # improvement_required 는 항상 코드가 재산정한다 (AI 출력 불신)
    try:
        apply_threshold(final, threshold)
    except Exception:
        pass
    nr_count = getattr(final, "needs_review_count", 0)
    over_count = getattr(final, "improvement_required_count", 0)

    # 상단 로고 (assets/kosha_logo.png가 있으면 좌측 상단에 표시)
    logo_path = find_logo()
    if logo_path:
        try:
            img_w, img_h = ImageReader(logo_path).getSize()
            logo_width = 42 * mm
            logo_height = logo_width * img_h / img_w  # 비율 유지
            logo = Image(logo_path, width=logo_width, height=logo_height)
            logo.hAlign = "LEFT"
            story.append(logo)
            story.append(Spacer(1, 2.5 * mm))
            story.append(HRFlowable(width="100%", thickness=0.6,
                                    color=colors.HexColor("#d7e3ef")))
            story.append(Spacer(1, 4 * mm))
        except Exception:
            pass  # 로고 파일 문제 시 로고 없이 진행 (보고서 생성은 계속)

    # 제목
    story.append(Paragraph("SafePilot AI 위험성평가 보고서", styles["title"]))
    story.append(Spacer(1, 3 * mm))
    mode_txt = "데모 모드(샘플 데이터)" if result.is_demo else "AI 모드"
    if getattr(result, "edited", False):
        mode_txt += " · 현장 책임자 수정 반영"
    story.append(Paragraph(
        f"작성 일시: {result.generated_at} | 생성 방식: {mode_txt} | "
        f"최종 위험성 판단 기준: {threshold}점 이하(사용자 설정)", styles["subtitle"]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "본 보고서는 AI가 작성한 초안이며, 현장 책임자의 최종 확인이 필요합니다.",
        styles["warn"]))
    summary_bits = []
    if nr_count:
        summary_bits.append(f"⚠ 검수 필요 항목: {nr_count}건 (AI 검증 미통과 — 수동 검토 필요)")
    if over_count:
        summary_bits.append(f"기준 초과 항목: {over_count}건 — 작업 전 추가 개선 검토 필요")
    if summary_bits:
        story.append(Spacer(1, 1.5 * mm))
        story.append(Paragraph(" / ".join(summary_bits), styles["alert"]))
    story.append(Spacer(1, 4 * mm))

    # 1. 작업 정보
    story.append(Paragraph("1. 작업 정보", styles["h2"]))
    info_rows = [
        [P("작업명", "cell_b"), P(w.name, "cell"),
         P("작업 장소", "cell_b"), P(w.location, "cell")],
        [P("사용 장비", "cell_b"), P(w.equipment or "-", "cell"),
         P("작업 인원", "cell_b"), P(w.workers or "-", "cell")],
        [P("작업 내용", "cell_b"), P(w.description, "cell"),
         P("특이사항", "cell_b"), P(w.notes or "-", "cell")],
    ]
    t = Table(info_rows, colWidths=[24 * mm, 111.5 * mm, 24 * mm, 111.5 * mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f8")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eef3f8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    # 2. 작업 개요
    if final.work_overview:
        story.append(Paragraph("2. 작업 개요", styles["h2"]))
        story.append(P(final.work_overview))

    # 3. 위험성평가 표 (개선 전·후)
    story.append(Paragraph("3. 위험성평가 표 (개선 전·후 위험성 및 개선관리)", styles["h2"]))
    head = [P(x, "cell_b") for x in
            ["작업단계", "위험요인", "예상 피해", "개선 전 위험성",
             "감소대책", "개선 후 위험성", "개선관리"]]
    rows = [head]
    level_cells = []  # (row, col, 색상) — 등급 배경
    review_rows = []  # 검수 필요 행
    for h in final.hazards:
        needs_review = getattr(h, "needs_review", False)
        improvement_required = getattr(h, "improvement_required", False)
        r_score = getattr(h, "residual_score", h.risk_score)
        r_level = getattr(h, "residual_level", h.risk_level)

        hz_txt = f"{h.hazard}\n[{h.category}] (원인) {h.cause}"
        if needs_review:
            hz_txt = "⚠ AI 검증 미통과 — 수동 검토 필요\n" + hz_txt
            reason = getattr(h, "needs_review_reason", "")
            if reason:
                hz_txt += f"\n(사유: {reason})"

        before_txt = (f"가능성 {h.likelihood} · 심각도 {h.severity}\n"
                      f"{h.risk_score}점 / {h.risk_level}")
        after_txt = f"{r_score}점 / {r_level}\n" + (
            "기준 초과 — 작업 전\n추가 개선 검토 필요" if improvement_required else "설정 기준 이내")

        m_lines = _measure_lines(h)
        if getattr(h, "only_admin_ppe", lambda: False)():
            m_lines.append("※ 상위 수준의 감소대책(제거·대체·공학적) 검토 필요")
        if h.ppe:
            m_lines.append("PPE: " + ", ".join(h.ppe))

        row_idx = len(rows)
        rows.append([
            P(h.step, "cell"),
            P(hz_txt, "cell"),
            P(h.damage, "cell"),
            P(before_txt, "cell"),
            P("\n".join(m_lines), "cell"),
            P(after_txt, "cell_b" if improvement_required else "cell"),
            P("담당자 ______\n예정일 ______\n이행확인 [   ]", "cell"),
        ])
        level_cells.append((row_idx, 3, _LEVEL_TINTS.get(h.risk_level, "#f1f5f9")))
        level_cells.append((row_idx, 5, _LEVEL_TINTS.get(r_level, "#f1f5f9")))
        if needs_review:
            review_rows.append(row_idx)

    # 유의미한 위험요인이 없는 단계
    for ns in getattr(final, "no_hazard_steps", []):
        rows.append([
            P(ns.step, "cell"),
            P(f"유의미한 위험요인 없음\n사유: {ns.reason or '-'}", "cell"),
            P("-", "cell"), P("-", "cell"), P("-", "cell"), P("-", "cell"), P("-", "cell"),
        ])

    t = Table(rows, colWidths=[24 * mm, 55 * mm, 30 * mm, 27 * mm, 66 * mm, 27 * mm, 42 * mm],
              repeatRows=1)
    style_cmds = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        # 헤더: 연한 파랑 배경 + 검정 굵은 글씨(cell_b 스타일)로 가독성 확보
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6f0fa")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (3, 1), (3, -1), "CENTER"),
        ("ALIGN", (5, 1), (5, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        # 개선 전 위험성 열: '가능성 n · 심각도 n'이 한 줄에 들어가도록 좌우 여백 축소
        # (해당 문자열 폭 69.8pt > 기본 여백 6pt 시 가용 64.5pt → 2pt 여백으로 72.5pt 확보)
        ("LEFTPADDING", (3, 0), (3, -1), 2),
        ("RIGHTPADDING", (3, 0), (3, -1), 2),
    ]
    # 개선 전/후 위험성 셀에 등급별 연한 틴트 적용
    for r, c, tint in level_cells:
        style_cmds.append(("BACKGROUND", (c, r), (c, r), colors.HexColor(tint)))
    # 검수 필요 행 강조는 등급 틴트보다 우선 적용
    for r in review_rows:
        style_cmds.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#fff7e0")))
    t.setStyle(TableStyle(style_cmds))
    story.append(t)
    story.append(Paragraph(
        f"위험도 점수 = 발생가능성(1~5) × 피해심각도(1~5), 개선 후 잔여 위험도 포함 — 모두 코드가 계산. "
        f"구간: 1~4 낮음 / 5~9 보통 / 10~16 높음 / 17~25 매우 높음. "
        f"'설정 기준 이내'는 추가 개선이 불필요하다는 의미가 아니라 설정된 판단 기준({threshold}점 이하) "
        f"범위 안에 들어왔다는 의미임. 개선관리(담당자·예정일·이행확인)는 출력 후 수기 기입란.", styles["note"]))

    # 4. 개인보호구
    story.append(Paragraph("4. 개인보호구(PPE)", styles["h2"]))
    story.append(P(", ".join(final.ppe_list) or "-"))

    # 5. TBM
    story.append(Paragraph("5. 작업 전 TBM(Tool Box Meeting)", styles["h2"]))
    for i, item in enumerate(final.tbm, 1):
        story.append(P(f"{i}. {item}"))

    # 6. 체크리스트
    story.append(Paragraph("6. 작업 전 체크리스트", styles["h2"]))
    check_rows = [[P("No.", "cell_b"), P("점검 항목", "cell_b"), P("확인", "cell_b")]]
    for i, item in enumerate(final.checklist, 1):
        check_rows.append([P(i, "cell"), P(item, "cell"), P("[   ]", "cell")])
    t = Table(check_rows, colWidths=[12 * mm, 239 * mm, 20 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3f8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    # 7. 근로자 의견 (현장 기재용)
    # (AI 교차검토 결과·검토 전후 변경사항·판단 근거는 화면에서만 확인하는
    #  검증 기록으로, 현장 제출용 보고서에는 싣지 않는다.)
    story.append(Paragraph("7. 근로자 의견", styles["h2"]))
    story.append(Paragraph("본 위험성평가 결과에 대한 근로자 의견을 청취하고 아래에 기재합니다.", styles["note"]))
    opinion_rows = [
        [P("근로자 의견", "cell_b"), P("\n\n\n", "cell")],
        [P("참여 근로자", "cell_b"), P("성명 ______________        서명 ______________", "cell")],
    ]
    t = Table(opinion_rows, colWidths=[34 * mm, 237 * mm],
              rowHeights=[22 * mm, 10 * mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    # 8. 현장 책임자 확인
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("8. 현장 책임자 확인", styles["h2"]))
    sign_rows = [
        [P("확인 내용", "cell_b"),
         P("본 위험성평가 결과를 검토하였으며, 현장 여건에 맞게 최종 확인함", "cell")],
        [P("소속 / 직책", "cell_b"), P("", "cell")],
        [P("성명 / 서명", "cell_b"), P("", "cell")],
        [P("확인 일자", "cell_b"), P("", "cell")],
    ]
    t = Table(sign_rows, colWidths=[34 * mm, 237 * mm],
              rowHeights=[10 * mm, 10 * mm, 10 * mm, 10 * mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t)

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "※ 본 문서는 SafePilot AI가 생성한 초안으로, 법적 효력을 갖는 확정 문서가 아닙니다. "
        "현장 책임자의 검토와 최종 확인 후 사용하시기 바랍니다.", styles["warn"]))

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# HTML 보고서 (PDF 폰트가 없을 때의 대체 수단)
# ---------------------------------------------------------------------------

def build_html_report(result: FullResult) -> str:
    """브라우저에서 열어 인쇄(PDF 저장)할 수 있는 HTML 보고서를 생성한다."""
    w = result.work_input
    final = result.review.final
    esc = html.escape
    threshold = _threshold_of(result)
    try:
        apply_threshold(final, threshold)
    except Exception:
        pass
    nr_count = getattr(final, "needs_review_count", 0)
    over_count = getattr(final, "improvement_required_count", 0)
    mode_txt = "데모 모드(샘플 데이터)" if result.is_demo else "AI 모드"
    if getattr(result, "edited", False):
        mode_txt += " · 현장 책임자 수정 반영"

    hazard_rows = ""
    for h in final.hazards:
        needs_review = getattr(h, "needs_review", False)
        improvement_required = getattr(h, "improvement_required", False)
        r_score = getattr(h, "residual_score", h.risk_score)
        r_level = getattr(h, "residual_level", h.risk_level)
        m_html = "".join(f"<div>{esc(line)}</div>" for line in _measure_lines(h))
        if getattr(h, "only_admin_ppe", lambda: False)():
            m_html += "<div><small>※ 상위 수준의 감소대책(제거·대체·공학적) 검토 필요</small></div>"
        if h.ppe:
            m_html += f"<small>PPE: {esc(', '.join(h.ppe))}</small>"
        review_mark = ("<div style='color:#b45309;font-weight:bold'>⚠ AI 검증 미통과 — 수동 검토 필요</div>"
                       if needs_review else "")
        judge = ("기준 초과 — 작업 전 추가 개선 검토 필요" if improvement_required else "설정 기준 이내")
        hazard_rows += f"""<tr{' style="background:#fff7e0"' if needs_review else ''}>
        <td>{esc(h.step)}</td>
        <td>{review_mark}<b>{esc(h.hazard)}</b><br><small>[{esc(h.category)}] 원인: {esc(h.cause)}</small></td>
        <td>{esc(h.damage)}</td>
        <td class="c"><small>가능성 {h.likelihood} · 심각도 {h.severity}</small><br><b>{h.risk_score}점</b><br>
          <span style="background:{RISK_COLORS.get(h.risk_level, '#999')};color:#fff;padding:1px 8px;border-radius:8px">{esc(h.risk_level)}</span></td>
        <td>{m_html}</td>
        <td class="c"><b>{r_score}점</b><br>
          <span style="background:{RISK_COLORS.get(r_level, '#999')};color:#fff;padding:1px 8px;border-radius:8px">{esc(r_level)}</span>
          <br><small>{esc(judge)}</small></td>
        <td><small>담당자 ______<br>예정일 ______<br>이행확인 ☐</small></td>
        </tr>"""
    for ns in getattr(final, "no_hazard_steps", []):
        hazard_rows += f"""<tr><td>{esc(ns.step)}</td>
        <td colspan="6"><b>유의미한 위험요인 없음</b><br><small>사유: {esc(ns.reason or '-')}</small></td></tr>"""

    # AI 교차검토 결과·검토 전후 변경사항·판단 근거는 화면에서만 확인하는
    # 검증 기록으로, 현장 제출용 보고서에는 싣지 않는다.
    tbm_items = "".join(f"<li>{esc(t)}</li>" for t in final.tbm)
    check_items = "".join(
        f"<tr><td class='c'>{i}</td><td>{esc(item)}</td><td class='c'>[&nbsp;&nbsp;&nbsp;]</td></tr>"
        for i, item in enumerate(final.checklist, 1)
    )
    summary_bits = []
    if nr_count:
        summary_bits.append(f"⚠ 검수 필요 항목: {nr_count}건")
    if over_count:
        summary_bits.append(f"기준 초과 항목: {over_count}건 — 작업 전 추가 개선 검토 필요")
    summary_html = (f"<p class='warn'>{' / '.join(summary_bits)}</p>" if summary_bits else "")

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>SafePilot AI 위험성평가 보고서</title>
<style>
body{{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#222;font-size:14px}}
h1{{color:#0d3b66;text-align:center;font-size:22px}}
h2{{color:#0d3b66;font-size:16px;border-bottom:2px solid #0d3b66;padding-bottom:4px;margin-top:28px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}}
th,td{{border:1px solid #bbb;padding:6px;vertical-align:top;text-align:left}}
th{{background:#e6f0fa}}
.c{{text-align:center}}
.warn{{background:#fff7e0;border:1px solid #e6c96b;padding:10px;border-radius:6px;color:#8a5a00;font-size:12.5px}}
.meta{{text-align:center;color:#666;font-size:12px}}
pre{{font-family:inherit;white-space:pre-wrap;background:#f6f8fb;border:1px solid #dde5ee;padding:10px;border-radius:6px;font-size:12.5px}}
@media print{{body{{margin:0}}}}
</style></head><body>
<h1>SafePilot AI 위험성평가 보고서</h1>
<p class="meta">작성 일시: {esc(result.generated_at)} | 생성 방식: {esc(mode_txt)} |
최종 위험성 판단 기준: {threshold}점 이하(사용자 설정)</p>
<p class="warn">본 보고서는 AI가 작성한 초안이며, 현장 책임자의 최종 확인이 필요합니다.</p>
{summary_html}

<h2>1. 작업 정보</h2>
<table>
<tr><th style="width:110px">작업명</th><td>{esc(w.name)}</td></tr>
<tr><th>작업 장소</th><td>{esc(w.location)}</td></tr>
<tr><th>작업 내용</th><td>{esc(w.description)}</td></tr>
<tr><th>사용 장비</th><td>{esc(w.equipment or "-")}</td></tr>
<tr><th>작업 인원</th><td>{esc(w.workers or "-")}</td></tr>
<tr><th>특이사항</th><td>{esc(w.notes or "-")}</td></tr>
</table>

<h2>2. 작업 개요</h2><p>{esc(final.work_overview)}</p>

<h2>3. 위험성평가 표 (개선 전·후 위험성 및 개선관리)</h2>
<table><tr><th>작업단계</th><th>위험요인</th><th>예상 피해</th><th>개선 전 위험성</th><th>감소대책</th><th>개선 후 위험성</th><th>개선관리</th></tr>
{hazard_rows}</table>
<p style="font-size:12px;color:#64748b">'설정 기준 이내'는 추가 개선이 불필요하다는 의미가 아니라,
설정된 판단 기준({threshold}점 이하) 범위 안에 들어왔다는 의미입니다. 개선관리 항목은 출력 후 수기 기입란입니다.</p>

<h2>4. 개인보호구(PPE)</h2><p>{esc(", ".join(final.ppe_list))}</p>

<h2>5. 작업 전 TBM</h2><ol>{tbm_items}</ol>

<h2>6. 작업 전 체크리스트</h2>
<table><tr><th style="width:40px">No.</th><th>점검 항목</th><th style="width:60px">확인</th></tr>{check_items}</table>

<h2>7. 근로자 의견</h2>
<p style="font-size:12px;color:#64748b">본 위험성평가 결과에 대한 근로자 의견을 청취하고 아래에 기재합니다.</p>
<table>
<tr><th style="width:120px">근로자 의견</th><td style="height:70px"></td></tr>
<tr><th>참여 근로자</th><td>성명 ______________ &nbsp;&nbsp; 서명 ______________</td></tr>
</table>

<h2>8. 현장 책임자 확인</h2>
<table>
<tr><th style="width:120px">확인 내용</th><td>본 위험성평가 결과를 검토하였으며, 현장 여건에 맞게 최종 확인함</td></tr>
<tr><th>소속 / 직책</th><td style="height:30px"></td></tr>
<tr><th>성명 / 서명</th><td style="height:30px"></td></tr>
<tr><th>확인 일자</th><td style="height:30px"></td></tr>
</table>

<p class="warn" style="margin-top:20px">※ 본 문서는 SafePilot AI가 생성한 초안으로, 법적 효력을 갖는 확정 문서가 아닙니다.
현장 책임자의 검토와 최종 확인 후 사용하시기 바랍니다.</p>
</body></html>"""
