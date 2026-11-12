"""카드뉴스·블로그 표지 이미지 만들기 (Pillow).

AI 이미지 생성을 쓰지 않고 정해진 틀에 글자를 얹는다 — 한글이 깨지지 않고, 조문 번호·수치가 원고 그대로 찍힌다.
인스타그램 API 는 JPEG 만 받으므로 JPEG 로 저장한다. 카드 1080×1350(4:5), 블로그 표지 1200×630.
"""
import pathlib
from PIL import Image, ImageDraw, ImageFont
from .common import HERE, ROOT, cfg

W, H = 1080, 1350
NAVY, BLUE, AMBER, BG, TEXT, MUTED, LINE, WHITE = "#0F172A", "#1D4ED8", "#F59E0B", "#F8FAFC", "#0F172A", "#64748B", "#E2E8F0", "#FFFFFF"
FONTS = {"x": "Pretendard-ExtraBold.otf", "s": "Pretendard-SemiBold.otf", "r": "Pretendard-Regular.otf"}
_fc = {}


def font(w, size):
    k = (w, size)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(str(HERE / "fonts" / FONTS[w]), size)
    return _fc[k]


def wrap(text, f, maxw):
    """낱말 단위 줄바꿈(한글 단어가 중간에 끊기지 않게). 한 낱말이 폭을 넘으면 글자 단위로 끊는다."""
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for word in para.split():
            trial = (cur + " " + word).strip()
            if f.getlength(trial) <= maxw:
                cur = trial
                continue
            if cur:
                lines.append(cur)
            cur = word
            while f.getlength(cur) > maxw:
                i = len(cur)
                while i > 1 and f.getlength(cur[:i]) > maxw:
                    i -= 1
                lines.append(cur[:i])
                cur = cur[i:]
        if cur:
            lines.append(cur)
    return lines


def fit(text, weight, size, maxw, max_lines, min_size=34):
    """폭과 줄 수에 맞을 때까지 글자 크기를 줄인다. 그래도 넘치면 마지막 줄을 말줄임."""
    while True:
        f = font(weight, size)
        lines = wrap(text, f, maxw)
        if len(lines) <= max_lines or size <= min_size:
            break
        size -= 4
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and f.getlength(lines[-1] + "…") > maxw:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return f, lines, size


def draw_lines(d, x, y, lines, f, fill, gap=1.32):
    lh = int(f.size * gap)
    for ln in lines:
        d.text((x, y), ln, font=f, fill=fill)
        y += lh
    return y


def brand(im, d, y, dark, page=None, w=W):
    """아래쪽 브랜드 줄 — 로고 + 이름 + 쪽 번호."""
    c = cfg()
    lp = ROOT / "assets" / "img" / "plum" / "logo.webp"
    x = 80
    if lp.exists():
        logo = Image.open(lp).convert("RGBA").resize((64, 64), Image.LANCZOS)
        im.paste(logo, (x, y - 8), logo)
        x += 84
    d.text((x, y), c["brand"]["name"], font=font("x", 36), fill=WHITE if dark else NAVY)
    nw = font("x", 36).getlength(c["brand"]["name"])
    d.text((x + nw + 16, y + 6), c["base_url"].replace("https://", ""), font=font("r", 28), fill="#CBD5E1" if dark else MUTED)
    if page:
        t = f"{page[0]} / {page[1]}"
        f = font("s", 28)
        d.text((w - 80 - f.getlength(t), y + 6), t, font=f, fill="#CBD5E1" if dark else MUTED)


def chip(d, x, y, text, fg, bg):
    f = font("s", 30)
    tw = f.getlength(text)
    d.rounded_rectangle((x, y, x + tw + 44, y + 58), radius=29, fill=bg)
    d.text((x + 22, y + 11), text, font=f, fill=fg)


def render_card(spec, idx, total):
    dark = spec["type"] in ("cover", "final")
    im = Image.new("RGB", (W, H), NAVY if spec["type"] == "cover" else (BLUE if spec["type"] == "final" else BG))
    d = ImageDraw.Draw(im)
    if spec["type"] == "cover":
        d.rectangle((0, 0, W, 14), fill=AMBER)
        chip(d, 80, 120, spec["label"], NAVY, AMBER)
        f, lines, _ = fit(spec["title"], "x", 104, W - 160, 5, 60)
        y = draw_lines(d, 80, 250, lines, f, WHITE, 1.24)
        f2, l2, _ = fit(spec.get("sub", ""), "r", 44, W - 160, 3, 34)
        d.rectangle((80, y + 36, 200, y + 42), fill=AMBER)
        draw_lines(d, 80, y + 84, l2, f2, "#CBD5E1")
        d.text((80, H - 250), "옆으로 넘겨 보세요  →", font=font("s", 34), fill=AMBER)
    elif spec["type"] == "body":
        d.rectangle((0, 0, 14, H), fill=BLUE)
        d.text((80, 104), spec["label"], font=font("s", 30), fill=BLUE)
        d.text((80, 170), f"{idx - 1:02d}", font=font("x", 120), fill=AMBER)
        f, lines, _ = fit(spec["title"], "x", 84, W - 160, 3, 52)
        y = draw_lines(d, 80, 350, lines, f, TEXT, 1.26)
        y += 36
        d.line((80, y, W - 80, y), fill=LINE, width=3)
        y += 64
        size = 58
        while True:                                     # 본문 줄이 카드 아래로 넘치지 않을 때까지 줄인다
            fb = font("r", size)
            blocks = [wrap(ln, fb, W - 160 - 50) for ln in spec["lines"]]
            need = sum(len(b) * int(size * 1.4) + 40 for b in blocks)
            if y + need < H - 190 or size <= 34:
                break
            size -= 2
        for b in blocks:
            d.rounded_rectangle((80, y + int(size * 0.38), 98, y + int(size * 0.38) + 18), radius=4, fill=BLUE)
            y = draw_lines(d, 130, y, b, fb, "#334155", 1.4) + 40
    else:
        d.rectangle((0, 0, W, 14), fill=AMBER)
        f, lines, _ = fit(spec["title"], "x", 68, W - 160, 6, 48)
        y = draw_lines(d, 80, 300, lines, f, WHITE, 1.36)
        fu = font("x", 60)
        uw = fu.getlength(spec["url"])
        d.rounded_rectangle((80, y + 70, 80 + uw + 90, y + 190), radius=60, fill=AMBER)
        d.text((125, y + 96), spec["url"], font=fu, fill=NAVY)
        d.text((80, y + 240), "프로필 링크에서 바로 이동할 수 있습니다", font=font("r", 36), fill="#DBE6FE")
    brand(im, d, H - 130, dark, (idx, total))
    return im


def render_all(specs, out_dir):
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, s in enumerate(specs, 1):
        p = out / f"{i:02d}.jpg"
        render_card(s, i, len(specs)).save(p, "JPEG", quality=88, optimize=True, progressive=False)
        paths.append(p)
    return paths


def render_cover(title, label, out_path):
    """블로그 글 맨 위 표지(1200×630)."""
    w, h = 1200, 630
    im = Image.new("RGB", (w, h), NAVY)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, w, 12), fill=AMBER)
    chip(d, 80, 70, label, NAVY, AMBER)
    f, lines, _ = fit(title, "x", 76, w - 160, 3, 44)
    draw_lines(d, 80, 175, lines, f, WHITE, 1.28)
    brand(im, d, h - 110, True, None, w)
    p = pathlib.Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    im.save(p, "JPEG", quality=88, optimize=True)
    return p
