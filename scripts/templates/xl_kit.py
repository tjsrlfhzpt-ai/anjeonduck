# -*- coding: utf-8 -*-
"""SafePlum 내려받기 양식(엑셀) 공통 디자인 도구.

- 글꼴: 맑은 고딕(한국어 Windows·Office 기본 탑재)
- 인쇄: A4, 너비 1쪽 맞춤, 제목 행 반복, 가운데 정렬, 머리글·바닥글 없음(쪽 번호만)
- 입력 칸은 흰 바탕, 머리글은 옅은 남색, 예시 줄은 회색 기울임
"""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule, CellIsRule
from openpyxl.worksheet.page import PageMargins

FONT = "맑은 고딕"
NAVY = "13233A"
INK = "1F2937"
MUTED = "6B7280"
HEAD = "E7ECF4"
SUB = "F3F5F9"
LINE = "8C97A8"
LIGHT = "C9D1DC"
RED, ORANGE, GREEN, YELLOW = "D92D20", "F79009", "079455", "FFF4CC"

thin = Side(style="thin", color=LINE)
hair = Side(style="thin", color=LIGHT)
med = Side(style="medium", color=NAVY)
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)


def f(size=10, bold=False, color=INK, italic=False):
    return Font(name=FONT, size=size, bold=bold, color=color, italic=italic)


def fill(c):
    return PatternFill("solid", start_color=c, end_color=c)


CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True, indent=0)
LEFT_TOP = Alignment(horizontal="left", vertical="top", wrap_text=True)


def new_book():
    wb = Workbook()
    wb.remove(wb.active)
    return wb


def sheet(wb, title, widths, landscape=False, tab=None, one_page=False):
    ws = wb.create_sheet(title)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 100
    ps = ws.page_setup
    ps.paperSize = ws.PAPERSIZE_A4
    ps.orientation = "landscape" if landscape else "portrait"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ps.fitToWidth = 1
    ps.fitToHeight = 1 if one_page else 0
    ws.print_options.horizontalCentered = True
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.55, header=0.2, footer=0.25)
    ws.oddFooter.center.text = "&P / &N"
    ws.oddFooter.center.size = 8
    ws.oddFooter.center.font = FONT
    if tab:
        ws.sheet_properties.tabColor = tab
    return ws


def cell(ws, ref, value=None, font=None, align=None, fill_c=None, border=None, fmt=None):
    c = ws[ref]
    if value is not None:
        c.value = value
    c.font = font or f()
    if align:
        c.alignment = align
    if fill_c:
        c.fill = fill(fill_c)
    if border:
        c.border = border
    if fmt:
        c.number_format = fmt
    return c


def box(ws, rng, value=None, font=None, align=CENTER, fill_c=None, fmt=None):
    """병합 + 테두리 + 값. rng 예: 'A3:C3'"""
    if ":" in rng:
        ws.merge_cells(rng)
    first = rng.split(":")[0]
    cells = ws[rng] if ":" in rng else ((ws[rng],),)
    for row in cells:
        for c in row:
            c.border = BOX
            if fill_c:
                c.fill = fill(fill_c)
            c.font = font or f()
            c.alignment = align
            if fmt:
                c.number_format = fmt
    if value is not None:
        ws[first].value = value
    return ws[first]


def title(ws, text, last_col, row=1, sub=None, height=34):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    c = ws.cell(row=row, column=1, value=text)
    c.font = f(18, True, NAVY)
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[row].height = height
    if sub:
        ws.merge_cells(start_row=row + 1, start_column=1, end_row=row + 1, end_column=last_col)
        s = ws.cell(row=row + 1, column=1, value=sub)
        s.font = f(9, False, MUTED)
        s.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        ws.row_dimensions[row + 1].height = 18


def approval(ws, row, first_col, labels=("담당", "검토", "승인"), width_cols=1, sign_h=34):
    """결재란: 첫 칸 '결재' 세로, 그 오른쪽에 칸 이름·서명 칸"""
    c0 = first_col
    ws.merge_cells(start_row=row, start_column=c0, end_row=row + 1, end_column=c0)
    k = ws.cell(row=row, column=c0, value="결\n재")
    for r in (row, row + 1):
        x = ws.cell(row=r, column=c0)
        x.border = BOX; x.fill = fill(HEAD); x.font = f(9, True); x.alignment = CENTER
    col = c0 + 1
    for lab in labels:
        a, b = col, col + width_cols - 1
        if b > a:
            ws.merge_cells(start_row=row, start_column=a, end_row=row, end_column=b)
            ws.merge_cells(start_row=row + 1, start_column=a, end_row=row + 1, end_column=b)
        for cc in range(a, b + 1):
            for r in (row, row + 1):
                x = ws.cell(row=r, column=cc)
                x.border = BOX; x.font = f(9, r == row); x.alignment = CENTER
                if r == row:
                    x.fill = fill(HEAD)
        ws.cell(row=row, column=a, value=lab)
        col = b + 1
    ws.row_dimensions[row].height = 18
    ws.row_dimensions[row + 1].height = sign_h


def header_row(ws, row, labels, height=30, start_col=1, fill_c=HEAD):
    for i, lab in enumerate(labels):
        c = ws.cell(row=row, column=start_col + i, value=lab)
        c.font = f(9.5, True, NAVY); c.fill = fill(fill_c); c.alignment = CENTER; c.border = BOX
    ws.row_dimensions[row].height = height


def grid(ws, r1, r2, c1, c2, height=22, align=None, wrap=True):
    for r in range(r1, r2 + 1):
        ws.row_dimensions[r].height = height
        for cc in range(c1, c2 + 1):
            x = ws.cell(row=r, column=cc)
            x.border = BOX
            x.font = f(9.5)
            x.alignment = align or Alignment(horizontal="center", vertical="center", wrap_text=wrap)


def _as_value(v, c):
    """예시 날짜·시각 글자를 진짜 날짜 값으로 — 그래야 기한 계산 수식이 예시 줄에서도 맞게 돈다"""
    import datetime as _dt, re as _re
    if not isinstance(v, str):
        return v
    if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        if c.number_format == "General":
            c.number_format = "yyyy-mm-dd"
        return _dt.date.fromisoformat(v)
    if _re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", v):
        if c.number_format == "General":
            c.number_format = "yyyy-mm-dd hh:mm"
        return _dt.datetime.strptime(v, "%Y-%m-%d %H:%M")
    if _re.fullmatch(r"\d{2}:\d{2}", v):
        if c.number_format == "General":
            c.number_format = "hh:mm"
        return _dt.datetime.strptime(v, "%H:%M").time()
    return v


def example(ws, row, values, start_col=1, height=None):
    """예시 줄: 회색 기울임(지우고 쓰기)"""
    for i, v in enumerate(values):
        if v is None:
            continue
        c = ws.cell(row=row, column=start_col + i)
        if not (isinstance(v, str) and v.startswith("=")):
            c.font = f(9.5, False, "8A94A3", True)
        c.value = _as_value(v, c)
    if height:
        ws.row_dimensions[row].height = height


def dv_list(ws, rng, items, prompt=None, allow_blank=True):
    src = '"' + ",".join(items) + '"'
    dv = DataValidation(type="list", formula1=src, allow_blank=allow_blank, showDropDown=False)
    dv.error = "목록에서 고르세요(목록을 바꾸려면 [데이터] → [데이터 유효성 검사])"
    dv.errorTitle = "입력 확인"
    dv.showErrorMessage = False  # 현장마다 표현이 달라 직접 입력도 허용
    if prompt:
        dv.prompt = prompt; dv.showInputMessage = True
    ws.add_data_validation(dv)
    dv.add(rng)
    return dv


def dv_ref(ws, rng, ref, prompt=None):
    dv = DataValidation(type="list", formula1=ref, allow_blank=True)
    dv.showErrorMessage = False
    if prompt:
        dv.prompt = prompt; dv.showInputMessage = True
    ws.add_data_validation(dv)
    dv.add(rng)


def dv_whole(ws, rng, lo, hi, prompt=None):
    dv = DataValidation(type="whole", operator="between", formula1=str(lo), formula2=str(hi), allow_blank=True)
    dv.error = f"{lo}~{hi} 사이 숫자를 넣으세요"; dv.errorTitle = "입력 확인"; dv.showErrorMessage = True
    if prompt:
        dv.prompt = prompt; dv.showInputMessage = True
    ws.add_data_validation(dv)
    dv.add(rng)


def dv_date(ws, rng):
    dv = DataValidation(type="date", operator="greaterThan", formula1="36526", allow_blank=True)
    dv.error = "날짜로 넣으세요(예: 2026-10-27)"; dv.errorTitle = "날짜 확인"; dv.showErrorMessage = True
    ws.add_data_validation(dv)
    dv.add(rng)


def color_text_rule(ws, rng, text, color, font_color="FFFFFF", bold=True):
    first = rng.split(":")[0]
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("{text}",{first}))'], fill=fill(color), font=Font(name=FONT, color=font_color, bold=bold)))


def guide_sheet(wb, name, lines, source=None):
    """'작성 안내' 시트: 무엇을 어디에 쓰는지, 근거"""
    ws = sheet(wb, "작성 안내", [4, 100], tab="98A2B3")
    title(ws, name + " — 작성 안내", 2, sub="SafePlum 무료 양식 · safeplum.com — 사업장 사정에 맞게 고쳐 쓰세요")
    r = 4
    for ln in lines:
        if isinstance(ln, tuple):
            h, body = ln
            ws.cell(row=r, column=1, value="■").font = f(10, True, NAVY)
            c = ws.cell(row=r, column=2, value=h); c.font = f(11, True, NAVY)
            r += 1
            for b in body:
                c = ws.cell(row=r, column=2, value=b); c.font = f(10); c.alignment = LEFT
                ws.row_dimensions[r].height = 16 * max(1, -(-len(b) // 62)) + 4  # 한글은 칸 너비 100에 한 줄 약 62자
                r += 1
            r += 1
    if source:
        c = ws.cell(row=r, column=2, value=source); c.font = f(9, False, MUTED, True); c.alignment = LEFT
        ws.row_dimensions[r].height = 30
    ws.oddFooter.center.text = ""
    return ws


def legend(ws, row, last_col, text="흰 칸에 입력 · 회색 기울임 글씨는 예시(지우고 쓰기) · 색이 있는 칸은 자동 계산"):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    c = ws.cell(row=row, column=1, value=text)
    c.font = f(8.5, False, MUTED)
    c.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[row].height = 16
