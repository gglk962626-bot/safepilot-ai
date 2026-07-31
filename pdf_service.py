"""SafePilot AI - 보고서 생성 (PDF / HTML)

- ReportLab으로 PDF 보고서를 생성한다.
- 한글이 깨지지 않도록 시스템에 설치된 한글 폰트를 탐색하여 사용한다.
  (Windows: 맑은 고딕, Streamlit Cloud: packages.txt의 fonts-nanum으로 설치되는 나눔고딕)
- 사용 가능한 한글 폰트가 없으면 HTML 보고서 다운로드로 대체한다.
"""

from __future__ import annotations

import html
import io
import os

from models import FullResult, RISK_COLORS

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


# ---------------------------------------------------------------------------
# PDF 생성
# ---------------------------------------------------------------------------

def build_pdf(result: FullResult) -> bytes:
    """위험성평가 결과를 PDF 바이트로 생성한다."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
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
    }

    def P(text, style="body"):
        return Paragraph(html.escape(str(text)).replace("\n", "<br/>"), styles[style])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=14 * mm, bottomMargin=14 * mm,
        leftMargin=13 * mm, rightMargin=13 * mm,
        title="SafePilot AI 위험성평가 보고서",
    )

    story = []
    w = result.work_input
    final = result.review.final

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
        f"작성 일시: {result.generated_at} | 생성 방식: {mode_txt}", styles["subtitle"]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "본 보고서는 AI가 작성한 초안이며, 현장 책임자의 최종 확인이 필요합니다.",
        styles["warn"]))
    story.append(Spacer(1, 4 * mm))

    # 작업 정보
    story.append(Paragraph("1. 작업 정보", styles["h2"]))
    info_rows = [
        [P("작업명", "cell_b"), P(w.name, "cell")],
        [P("작업 장소", "cell_b"), P(w.location, "cell")],
        [P("작업 내용", "cell_b"), P(w.description, "cell")],
        [P("사용 장비", "cell_b"), P(w.equipment or "-", "cell")],
        [P("작업 인원", "cell_b"), P(w.workers or "-", "cell")],
        [P("특이사항", "cell_b"), P(w.notes or "-", "cell")],
    ]
    t = Table(info_rows, colWidths=[28 * mm, 156 * mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    # 작업 개요
    if final.work_overview:
        story.append(Paragraph("2. 작업 개요", styles["h2"]))
        story.append(P(final.work_overview))

    # 위험성평가 표
    story.append(Paragraph("3. 위험성평가 표", styles["h2"]))
    head = [P(x, "cell_b") for x in
            ["작업 단계", "분류", "위험요인 / 원인 / 예상 피해", "가능성", "심각도", "점수", "등급", "예방대책"]]
    rows = [head]
    for h in final.hazards:
        detail = f"{h.hazard}\n(원인) {h.cause}\n(피해) {h.damage}"
        rows.append([
            P(h.step, "cell"), P(h.category, "cell"), P(detail, "cell"),
            P(h.likelihood, "cell"), P(h.severity, "cell"),
            P(h.risk_score, "cell_b"), P(h.risk_level, "cell_b"),
            P("\n".join(f"- {m}" for m in h.measures), "cell"),
        ])
    t = Table(rows, colWidths=[22 * mm, 17 * mm, 52 * mm, 10 * mm, 10 * mm, 10 * mm, 14 * mm, 49 * mm],
              repeatRows=1)
    style_cmds = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        # 헤더: 연한 파랑 배경 + 검정 굵은 글씨(cell_b 스타일)로 가독성 확보
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6f0fa")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (3, 1), (6, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    # 등급 셀 배경색
    for i, h in enumerate(final.hazards, start=1):
        style_cmds.append(
            ("BACKGROUND", (6, i), (6, i),
             colors.HexColor(RISK_COLORS.get(h.risk_level, "#999999"))))
        style_cmds.append(("TEXTCOLOR", (6, i), (6, i), colors.white))
    t.setStyle(TableStyle(style_cmds))
    story.append(t)

    # 개인보호구
    story.append(Paragraph("4. 개인보호구(PPE)", styles["h2"]))
    story.append(P(", ".join(final.ppe_list) or "-"))

    # TBM
    story.append(Paragraph("5. 작업 전 TBM(Tool Box Meeting)", styles["h2"]))
    for i, item in enumerate(final.tbm, 1):
        story.append(P(f"{i}. {item}"))

    # 체크리스트
    story.append(Paragraph("6. 작업 전 체크리스트", styles["h2"]))
    check_rows = [[P("No.", "cell_b"), P("점검 항목", "cell_b"), P("확인", "cell_b")]]
    for i, item in enumerate(final.checklist, 1):
        check_rows.append([P(i, "cell"), P(item, "cell"), P("[   ]", "cell")])
    t = Table(check_rows, colWidths=[12 * mm, 152 * mm, 20 * mm], repeatRows=1)
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

    # AI 검토 내역
    story.append(Paragraph("7. AI 교차검토 결과 (17개 위험범주 전수 점검)", styles["h2"]))
    story.append(Paragraph(
        "※ 본 내용은 최종 결과에 반영된 AI 교차검토 및 보완 과정을 확인하기 위한 검증 기록입니다.",
        styles["note"]))
    rv_rows = [[P("검토 범주", "cell_b"), P("판정", "cell_b"), P("검토 의견", "cell_b")]]
    for f in result.review.findings:
        rv_rows.append([P(f.category, "cell"), P(f.status, "cell"), P(f.comment, "cell")])
    t = Table(rv_rows, colWidths=[34 * mm, 18 * mm, 132 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3f8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    if result.review.changes:
        story.append(Paragraph("8. 검토 전후 변경사항", styles["h2"]))
        for i, c in enumerate(result.review.changes, 1):
            story.append(P(f"{i}. [{c.action}/{c.target}] {c.description}"))

    # 책임자 확인란
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("9. 현장 책임자 확인", styles["h2"]))
    sign_rows = [
        [P("확인 내용", "cell_b"),
         P("본 위험성평가 결과를 검토하였으며, 현장 여건에 맞게 최종 확인함", "cell")],
        [P("소속 / 직책", "cell_b"), P("", "cell")],
        [P("성명 / 서명", "cell_b"), P("", "cell")],
        [P("확인 일자", "cell_b"), P("", "cell")],
    ]
    t = Table(sign_rows, colWidths=[34 * mm, 150 * mm],
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
    mode_txt = "데모 모드(샘플 데이터)" if result.is_demo else "AI 모드"
    if getattr(result, "edited", False):
        mode_txt += " · 현장 책임자 수정 반영"

    hazard_rows = "".join(
        f"""<tr>
        <td>{esc(h.step)}</td><td>{esc(h.category)}</td>
        <td>{esc(h.hazard)}<br><small>(원인) {esc(h.cause)}<br>(피해) {esc(h.damage)}</small></td>
        <td class="c">{h.likelihood}</td><td class="c">{h.severity}</td>
        <td class="c"><b>{h.risk_score}</b></td>
        <td class="c" style="background:{RISK_COLORS.get(h.risk_level, '#999')};color:#fff">{esc(h.risk_level)}</td>
        <td>{"".join(f"<div>- {esc(m)}</div>" for m in h.measures)}</td>
        </tr>"""
        for h in final.hazards
    )
    finding_rows = "".join(
        f"<tr><td>{esc(f.category)}</td><td class='c'>{esc(f.status)}</td><td>{esc(f.comment)}</td></tr>"
        for f in result.review.findings
    )
    change_items = "".join(
        f"<li>[{esc(c.action)}/{esc(c.target)}] {esc(c.description)}</li>"
        for c in result.review.changes
    )
    tbm_items = "".join(f"<li>{esc(t)}</li>" for t in final.tbm)
    check_items = "".join(
        f"<tr><td class='c'>{i}</td><td>{esc(item)}</td><td class='c'>[&nbsp;&nbsp;&nbsp;]</td></tr>"
        for i, item in enumerate(final.checklist, 1)
    )

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>SafePilot AI 위험성평가 보고서</title>
<style>
body{{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#222;font-size:14px}}
h1{{color:#0d3b66;text-align:center;font-size:22px}}
h2{{color:#0d3b66;font-size:16px;border-bottom:2px solid #0d3b66;padding-bottom:4px;margin-top:28px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}}
th,td{{border:1px solid #bbb;padding:6px;vertical-align:top;text-align:left}}
th{{background:#eef3f8}}
.c{{text-align:center}}
.warn{{background:#fff7e0;border:1px solid #e6c96b;padding:10px;border-radius:6px;color:#8a5a00;font-size:12.5px}}
.meta{{text-align:center;color:#666;font-size:12px}}
@media print{{body{{margin:0}}}}
</style></head><body>
<h1>SafePilot AI 위험성평가 보고서</h1>
<p class="meta">작성 일시: {esc(result.generated_at)} | 생성 방식: {esc(mode_txt)}</p>
<p class="warn">본 보고서는 AI가 작성한 초안이며, 현장 책임자의 최종 확인이 필요합니다.</p>

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

<h2>3. 위험성평가 표</h2>
<table><tr><th>작업 단계</th><th>분류</th><th>위험요인</th><th>가능성</th><th>심각도</th><th>점수</th><th>등급</th><th>예방대책</th></tr>
{hazard_rows}</table>

<h2>4. 개인보호구(PPE)</h2><p>{esc(", ".join(final.ppe_list))}</p>

<h2>5. 작업 전 TBM</h2><ol>{tbm_items}</ol>

<h2>6. 작업 전 체크리스트</h2>
<table><tr><th style="width:40px">No.</th><th>점검 항목</th><th style="width:60px">확인</th></tr>{check_items}</table>

<h2>7. AI 교차검토 결과 (17개 위험범주 전수 점검)</h2>
<p style="font-size:12px;color:#64748b;margin-top:-4px">※ 본 내용은 최종 결과에 반영된 AI 교차검토 및 보완 과정을 확인하기 위한 검증 기록입니다.</p>
<table><tr><th style="width:140px">검토 범주</th><th style="width:70px">판정</th><th>검토 의견</th></tr>{finding_rows}</table>

<h2>8. 검토 전후 변경사항</h2><ol>{change_items}</ol>

<h2>9. 현장 책임자 확인</h2>
<table>
<tr><th style="width:120px">확인 내용</th><td>본 위험성평가 결과를 검토하였으며, 현장 여건에 맞게 최종 확인함</td></tr>
<tr><th>소속 / 직책</th><td style="height:30px"></td></tr>
<tr><th>성명 / 서명</th><td style="height:30px"></td></tr>
<tr><th>확인 일자</th><td style="height:30px"></td></tr>
</table>

<p class="warn" style="margin-top:20px">※ 본 문서는 SafePilot AI가 생성한 초안으로, 법적 효력을 갖는 확정 문서가 아닙니다.
현장 책임자의 검토와 최종 확인 후 사용하시기 바랍니다.</p>
</body></html>"""
