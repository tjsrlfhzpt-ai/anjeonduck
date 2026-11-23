#!/usr/bin/env python3
"""유튜브 채널 새 영상 → data/videos.json 자동 추가 + 자체 썸네일(assets/img/videos/<id>.webp) 받기.

왜: 채널에 영상을 올려도 사이트 목록(data/videos.json)은 손으로 고쳐야 해서 한 달 넘게 갱신이 멈춘 적이 있다
(2026-10-12 이후 26편 누락, 2026-11-23 발견). 매일 한 번 채널 피드를 보고 빠진 영상만 덧붙인다.

- 채널 피드(https://www.youtube.com/feeds/videos.xml?channel_id=…)는 최근 공개 영상 15편만 준다. 예약·비공개 영상은 안 나온다.
- 이미 목록에 있는 영상, skip 에 넣은 영상은 건드리지 않는다(손으로 다듬은 제목·요약·근거를 덮어쓰지 않음).
- 새 항목은 설명란에서 요약·근거 조문·연결 작성기를 뽑고 "auto": true 를 붙인다. 나중에 손으로 다듬으면 auto 를 지워도 된다.
- 썸네일이 없는 유튜브 항목은 유튜브 썸네일을 받아 세로 540×960(가로 영상 960×540) webp 로 저장한다.
  방문자 화면은 이 자체 이미지를 쓰므로 재생 전에는 유튜브에 접속하지 않는다(기존 원칙 유지).
- 접속 실패는 경고만 하고 바뀐 것 없이 끝낸다(배포를 막지 않음).

사용: python3 scripts/sync_videos.py [--feed 파일.xml] [--no-posters]
"""
import argparse
import datetime as dt
import io
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data/videos.json"
POSTERS = ROOT / "assets/img/videos"
KST = dt.timezone(dt.timedelta(hours=9))
UA = "Mozilla/5.0 (compatible; SafePlumBot/1.0; +https://safeplum.com)"
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "media": "http://search.yahoo.com/mrss/"}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# 제목 낱말로 분류(위에서부터 먼저 맞는 것). build.py VIDEO_CAT_ORDER 와 같은 이름을 쓴다.
CATS = [
    ("화재·밀폐공간", "밀폐|맨홀|황화수소|질식|화재|소화기|불티|용접|소방|대피"),
    ("지게차·운반", "지게차|굴삭기|굴착기|크레인|운반|차량"),
    ("근골격계", "중량물|허리|근골격|들기"),
    ("추락·보호구", "추락|사다리|개구부|지붕|고소|안전대|안전모|넘어짐|전도|비계"),
    ("끼임·화학물질", "끼임|컨베이어|LOTO|화학|MSDS|세제|프레스|회전"),
    ("위험성평가", "위험성평가|아차사고"),
    ("점검·비상대응", "점검|비상|매뉴얼|훈련|서류|업무|중대재해|감독"),
]
# 분류별 기본 연결 작성기(설명란에 작성기 링크가 없을 때)
CAT_RELATED = {
    "화재·밀폐공간": [["tools/permit/", "안전작업허가서"]],
    "지게차·운반": [["tools/forms/wp-forklift/", "지게차 작업계획서"], ["tools/tbm/", "TBM 일지"]],
    "근골격계": [["tools/forms/wp-heavy/", "중량물 취급 작업계획서"], ["tools/forms/msd-survey/", "근골격계 유해요인조사표"]],
    "추락·보호구": [["tools/risk/", "위험성평가서"], ["tools/tbm/", "TBM 일지"]],
    "끼임·화학물질": [["tools/loto/", "LOTO 작업금지 태그"], ["tools/msds/", "MSDS 관리·경고표지"]],
    "위험성평가": [["tools/risk/", "위험성평가서"], ["tools/tbm/", "TBM 일지"]],
    "점검·비상대응": [["tools/schedule/", "법정 주기업무 달력"]],
}
LAW_RE = re.compile(
    r"(?:산업안전보건법|중대재해처벌법|화재예방법|산업안전보건기준에 관한 규칙|안전보건규칙)"
    r"(?:\s*시행령|\s*시행규칙)?\s*제\d+조(?:의\d+)?(?:\s*제\d+[항호])*")
BOILER = ("safeplum.com", "세이프플럼", "※", "관련 서식", "태그:", "[고정 댓글]", "📋", "👉", "📝", "▶")


def label_for(path):
    """tools/<slug>/ 이름은 빌드 결과(_site)의 페이지 제목에서 가져온다. 빌드 결과가 없으면 '관련 작성기'."""
    for base in (ROOT / "_site", ROOT):
        f = base / path / "index.html"
        if f.exists():
            m = re.search(r"<title>([^<|·]+)", f.read_text(encoding="utf-8", errors="ignore"))
            if m:
                return m.group(1).strip()
    return "관련 작성기"


def clean_title(t):
    t = re.sub(r"#\S+", "", t)
    t = re.sub(r"\s*\|\s*", " — ", t.strip())
    return re.sub(r"\s{2,}", " ", t).strip(" —|")


def summarize(desc, limit=170):
    lines = []
    for ln in desc.splitlines():
        s = ln.strip()
        if not s:
            continue
        if any(b in s for b in BOILER) or re.match(r"^\d{1,2}:\d{2}", s):
            if lines:
                break   # 본문 뒤의 홍보·안내 줄부터는 버림
            continue
        lines.append(s)
    text = " ".join(lines)
    text = re.sub(r"https?://\S+|#\S+", "", text)
    text = re.sub(r"[✔✅👉📋📝▶①②③④⑤⑥⑦⑧⑨]", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    ends = [m.end() for m in re.finditer(r"(?:다|요|함|음)\.|\)\.|\.(?=\s)", cut)]
    return cut[:ends[-1]].strip() if ends and ends[-1] > limit * 0.45 else cut.rstrip() + "…"


def laws(desc):
    out = []
    for m in LAW_RE.finditer(desc):
        s = re.sub(r"\s+", " ", m.group(0)).replace("안전보건규칙", "산업안전보건기준에 관한 규칙")
        if s not in out:
            out.append(s)
    return ", ".join(out[:4])


def categorize(title, desc):
    for text in (title, desc):
        for cat, pat in CATS:
            if re.search(pat, text):
                return cat
    return "점검·비상대응"


def related(desc, cat):
    out = []
    for m in re.finditer(r"safeplum\.com/(tools/[a-z0-9/_-]+?)/?(?=[\s)\"'<]|$)", desc):
        p = m.group(1).rstrip("/") + "/"
        if p != "tools/" and p not in [x[0] for x in out]:
            out.append([p, label_for(p)])
    return out[:3] or [list(x) for x in CAT_RELATED.get(cat, [])]


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = []
    for en in root.findall("a:entry", NS):
        vid = (en.findtext("yt:videoId", "", NS) or "").strip()
        if not ID_RE.match(vid):
            continue
        link = en.find("a:link", NS)
        href = link.get("href", "") if link is not None else ""
        grp = en.find("media:group", NS)
        desc = (grp.findtext("media:description", "", NS) if grp is not None else "") or ""
        pub = en.findtext("a:published", "", NS)
        try:
            day = dt.datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone(KST).date().isoformat()
        except ValueError:
            continue
        out.append({"id": vid, "title": en.findtext("a:title", "", NS) or "", "desc": desc, "date": day, "wide": "/shorts/" not in href})
    return out


def make_item(e):
    cat = categorize(e["title"], e["desc"])
    it = {"platform": "youtube", "youtube": e["id"]}
    if e["wide"]:
        it["format"] = "wide"
    it.update(date=e["date"], title=clean_title(e["title"]) or e["id"], summary=summarize(e["desc"]), topic=cat)
    lw = laws(e["desc"])
    if lw:
        it["law"] = lw
    it["related"] = related(e["desc"], cat)
    it["cat"] = cat
    it["auto"] = True
    return it


def save_poster(vid, wide):
    from PIL import Image
    W, H = (960, 540) if wide else (540, 960)
    names = ["maxresdefault", "hqdefault"] if wide else ["oar2", "maxresdefault", "hqdefault"]
    for n in names:
        try:
            raw = fetch(f"https://i.ytimg.com/vi/{vid}/{n}.jpg")
        except Exception:
            continue
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        if im.width < 200:   # 없는 썸네일 자리표시(120×90)는 건너뜀
            continue
        s = max(W / im.width, H / im.height)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        l, t = (im.width - W) // 2, (im.height - H) // 2
        im = im.crop((l, t, l + W, t + H))
        POSTERS.mkdir(parents=True, exist_ok=True)
        im.save(POSTERS / f"{vid}.webp", "WEBP", quality=72, method=6)
        return n
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", help="피드 XML 파일(시험용). 없으면 채널 피드를 받는다")
    ap.add_argument("--no-posters", action="store_true")
    a = ap.parse_args()

    data = json.loads(DATA.read_text(encoding="utf-8"))
    ch = data.get("youtube_channel_id", "")
    items = data.setdefault("items", [])
    have = {i.get("youtube") for i in items if i.get("youtube")} | set(data.get("skip") or [])
    changed = False

    try:
        xml = Path(a.feed).read_bytes() if a.feed else fetch(f"https://www.youtube.com/feeds/videos.xml?channel_id={ch}")
        entries = parse_feed(xml)
    except Exception as ex:  # 접속 실패·형식 오류 → 목록은 그대로
        print(f"경고: 유튜브 채널 피드를 읽지 못함({ex}) — 영상 목록은 그대로 둠")
        entries = []

    new = [make_item(e) for e in entries if e["id"] not in have]
    if new:
        items[:0] = new
        items.sort(key=lambda x: x.get("date", ""), reverse=True)   # 같은 날짜는 원래 순서 유지
        changed = True
        for it in new:
            print(f"추가: {it['date']} {it['youtube']} {it['title']} [{it['cat']}]")
    if new:
        data["checked"] = dt.datetime.now(KST).date().isoformat()   # 바뀐 게 없으면 파일을 건드리지 않는다(매일 빈 커밋 방지)

    if not a.no_posters:
        for it in items:
            vid = it.get("youtube", "")
            if ID_RE.match(vid) and not (POSTERS / f"{vid}.webp").exists():
                try:
                    got = save_poster(vid, it.get("format") == "wide")
                except Exception as ex:
                    got = ""
                    print(f"경고: 썸네일 처리 실패 {vid}: {ex}")
                print(f"썸네일 {'저장' if got else '못 받음'}: {vid} {got}")
                changed = changed or bool(got)

    if changed:
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"영상 {len(items)}편, 새로 추가 {len(new)}편")


if __name__ == "__main__":
    sys.exit(main())
