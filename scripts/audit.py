#!/usr/bin/env python3
"""법령 데이터·표현 감사. 오류(ERROR)가 있으면 1로 끝나 배포를 막고, 경고(WARN)는 알리기만 한다.

  python3 scripts/audit.py            # 저장소 데이터·원본 검사
  python3 scripts/audit.py _site      # 빌드 결과(HTML)까지 검사
  python3 scripts/audit.py --online   # 국가법령정보센터 연혁과 현행 공포번호 비교(실패해도 경고)
"""
import datetime as dt
import json
import pathlib
import re
import sys
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
ERR, WARN = [], []
OFFICIAL = ("law.go.kr", "moel.go.kr", "kosha.or.kr", "korea.kr", "assembly.go.kr", "moleg.go.kr", "nfa.go.kr", "me.go.kr", "data.go.kr", "opinion.lawmaking.go.kr", "lawmaking.go.kr", "gwanbo.go.kr")


def load(p):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def official(url):
    h = (urlparse(url or "").hostname or "").lower()
    return any(h == d or h.endswith("." + d) for d in OFFICIAL)


def isdate(s):
    try:
        dt.date.fromisoformat(s)
        return True
    except Exception:
        return False


def check_manifest(today):
    m = load("data/law_manifest.json")
    if not isdate(m.get("checked_at", "")):
        ERR.append("law_manifest: checked_at 없음")
    limit = int(m.get("stale_after_days", 45))
    lawtext = {}
    for l in m["laws"]:
        k, c = l["key"], l.get("current", {})
        for f in ("no", "promulgated", "effective", "source_url"):
            if not c.get(f):
                ERR.append(f"law_manifest {k}: current.{f} 누락")
        if c.get("source_url") and not official(c["source_url"]):
            ERR.append(f"law_manifest {k}: 공식기관 주소가 아님 {c['source_url']}")
        if not isdate(l.get("checked_at", "")):
            ERR.append(f"law_manifest {k}: checked_at 누락")
        elif (today - dt.date.fromisoformat(l["checked_at"])).days > limit:
            WARN.append(f"law_manifest {k}: 확인일 {l['checked_at']} — {limit}일 경과, 공식 원문 재확인 필요(화면에도 표시됨)")
        if isdate(c.get("effective", "")) and dt.date.fromisoformat(c["effective"]) > today:
            ERR.append(f"law_manifest {k}: current 의 시행일이 미래({c['effective']}) — 시행 예정본을 현재 시행으로 표시")
        for u in l.get("upcoming", []):
            for f in ("no", "promulgated", "effective", "source_url"):
                if not u.get(f):
                    ERR.append(f"law_manifest {k}: upcoming {u.get('no')} {f} 누락")
            if isdate(u.get("effective", "")) and dt.date.fromisoformat(u["effective"]) <= today:
                WARN.append(f"law_manifest {k}: 시행 예정 {u.get('no')}({u['effective']})의 시행일이 지났음 — 현행본·조문 본문 갱신 필요")
        if not l.get("used_by"):
            WARN.append(f"law_manifest {k}: used_by 비어 있음")
        # 본문 데이터가 매니페스트의 현재 시행본과 같은 버전인지
        p = ROOT / f"data/lawtext/{k}.json"
        if p.exists():
            t = json.loads(p.read_text(encoding="utf-8"))
            lawtext[k] = t
            eff = t.get("effective_iso") or ""
            if eff and eff != c.get("effective"):
                ERR.append(f"lawtext {k}: 본문 시행일 {eff} ≠ 매니페스트 현재 시행 {c.get('effective')} (과거 또는 미시행 버전 사용)")
            for a in t.get("articles", []):
                pe = (a.get("pending") or {}).get("effective")
                if pe and pe <= today.isoformat():
                    WARN.append(f"lawtext {k} {a.get('no', '')}: 시행 예정 문언의 시행일({pe})이 지남 — 본문 갱신 필요")
        else:
            ERR.append(f"lawtext {k}: 본문 데이터 없음")
    for n in m.get("notices", []):
        for f in ("no", "source_url", "checked_at"):
            if not n.get(f):
                ERR.append(f"law_manifest 고시 {n.get('key')}: {f} 누락")
        if n.get("status") != "verified":
            WARN.append(f"고시 {n['name']} {n['no']}: 확인 필요 상태")
    for b in m.get("bills", []):
        if not official(b.get("source_url", "")):
            ERR.append(f"law_manifest 입법 동향 {b.get('id')}: 공식 출처 아님")
    return m


def check_updates():
    for u in load("data/laws.json").get("updates", []):
        for f in ("date", "law", "title", "source_url"):
            if not u.get(f):
                ERR.append(f"laws.json 개정 소식 {u.get('id') or u.get('title')}: {f} 누락")
        if u.get("source_url") and not official(u["source_url"]):
            ERR.append(f"laws.json 개정 소식 {u.get('id')}: 공식 출처 아님 {u['source_url']}")


def check_briefs():
    d = ROOT / "data/briefs"
    for p in sorted(d.glob("*.json")) if d.exists() else []:
        b = json.loads(p.read_text(encoding="utf-8"))
        for i, it in enumerate(b.get("items", [])):
            srcs = it.get("sources") or ([{"url": it.get("url")}] if it.get("url") else [])
            if not any(official(s.get("url", "")) for s in srcs):
                ERR.append(f"{p.name} 항목 {i + 1}: 공식 1차 출처 없음(언론 보도만으로는 게시 불가)")


def check_data_dates():
    for p in sorted((ROOT / "data").glob("*.json")):
        if p.name in ("jobs.json", "job_posts.json", "hazards.json", "kosha_media.json", "edu_contents.json", "catalog.json", "law_manifest.json", "form_auto.json", "duck_signs.json", "library.json", "sites.json", "resources.json", "lawfiles.json", "lawref.json"):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as ex:
            ERR.append(f"{p.name}: JSON 오류 {ex}")
            continue
        if isinstance(d, dict) and not (d.get("checked") or d.get("checked_at") or d.get("verified_at")):
            WARN.append(f"{p.name}: 확인일(checked) 없음")


# (표현, 허용 문맥 정규식) — 허용 문맥에 해당하지 않는 사용은 오류
BANNED = [
    ("법적으로 문제없", None), ("이것만 하면 됩니다", None), ("법적 의무를 충족합니다", None), ("법정 5×4", None), ("법정 5x4", None),
    ("무조건", None),
    ("이 결과만으로", r"이 결과만으로[^.]{0,40}(안 됩니다|없습니다|마세요|아닙니다)"),
    ("법적 효력", r"법적 효력[^.]{0,30}(없|아닙|보증하지|의미가 아)"),
    ("전자서명", r"(전자서명[^.]{0,40}(아닙니다|의미가 아|충족한다는 의미)|법정 전자서명 또는)"),
    ("미적용", None),
    ("모든 사업장", r"모든 사업장[^.]{0,60}(아닙|않|확인|다를|별표 1|제외)"),
]

def strip_html(t):
    t = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", t)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


def check_phrases(site_dir):
    files = [p for p in list((ROOT / "apps").glob("*.html")) + [ROOT / "assets/docs.js", ROOT / "assets/app.js", ROOT / "build.py", ROOT / "lawpages.py", ROOT / "config/site.json"] if p.exists()]
    files += [p for p in (ROOT / "data").glob("*.json") if p.name not in ("jobs.json", "job_posts.json")]
    for p in files:
        txt = p.read_text(encoding="utf-8")
        # 작성 도구·양식 화면은 스스로를 '법정 서식'이라 부르지 않는다(부정문만 허용)
        extra = [("법정 서식", r"법정 서식(이 아|이 따로|\(별지\)|·별표)")] if p.parent.name == "apps" else []
        for word, ok in BANNED + extra:
            for m in re.finditer(re.escape(word), txt):
                ctx = txt[max(0, m.start() - 60):m.end() + 90].replace("\n", " ")
                if ok and re.search(ok, ctx):
                    continue
                if p.parent.name == "lawtext":
                    continue
                ERR.append(f"금지 표현 '{word}': {p.relative_to(ROOT)} …{ctx[40:130]}…")
    if site_dir:
        n = 0
        for p in pathlib.Path(site_dir).rglob("*.html"):
            rel = str(p.relative_to(site_dir))
            if rel.startswith("laws/") and rel.count("/") >= 2:
                continue  # 법령 원문 페이지는 원문 그대로
            txt = strip_html(p.read_text(encoding="utf-8"))
            n += 1
            for word in ("법적으로 문제없", "이것만 하면 됩니다", "법적 의무를 충족합니다", "미적용", "법정 5×4"):
                if word in txt:
                    ERR.append(f"금지 표현 '{word}': 빌드 결과 {rel}")
        print(f"  빌드 결과 {n}쪽 표현 검사")


def check_site(site_dir):
    """빌드 결과: 도구마다 법령 버전 표기, 건강·개인정보 입력 도구의 안내, 판정 면책문구."""
    sd = pathlib.Path(site_dir)
    site = load("config/site.json")
    for t in site.get("free_tools", []):
        p = sd / "tools" / t["id"] / "index.html"
        if not p.exists():
            ERR.append(f"빌드 결과에 도구 없음: {t['id']}")
            continue
        h = p.read_text(encoding="utf-8")
        if t.get("kind") == "page" and 'class="lawver"' not in h:
            ERR.append(f"도구 {t['id']}: 하단 법령 버전 표기 없음")
        if t.get("kind") != "page" and "법정 지정서식이 아님" not in h:
            ERR.append(f"도구 {t['id']}: 양식 지위 표기 없음")
    need = {
        "tools/selection/index.html": ["관할 행정기관의 공식 해석·처분을 대체하지 않습니다"],
        "tools/cvd/index.html": ["참고용 계산 기능", "고용상 불이익"],
        "tools/penalty/index.html": ["관할 행정기관이 판단합니다"],
        "tools/headcount/index.html": ["적용 법령별로 별도 확인이 필요합니다"],
        "tools/safety-cost/index.html": ["법정 최소 계상액의 참고 계산"],
        "tools/msds/index.html": ["자동 추출값 — 원문 확인 필요"],
        "tools/loto/index.html": ["보조양식"],
        "tools/risk/index.html": ["안전duck 기본 위험성평가 예시 기준"],
        "legal/index.html": ["국가법령정보센터", "오류 신고"],
        "index.html": ["법령 데이터 기준일"],
    }
    for rel, words in need.items():
        p = sd / rel
        h = p.read_text(encoding="utf-8") if p.exists() else ""
        for w in words:
            if w not in h:
                ERR.append(f"{rel}: 필수 안내 문구 없음 — '{w}'")
    forms = list((sd / "tools/forms").glob("*/index.html"))
    bad = [p.parent.name for p in forms if "법정 지정서식이 아님" not in p.read_text(encoding="utf-8")]
    if bad:
        ERR.append("서식 작성기 양식 지위 표기 없음: " + ", ".join(bad[:8]))
    print(f"  도구 {len(site.get('free_tools', []))}개 · 서식 {len(forms)}종 표기 검사")


def check_internal_links(site_dir):
    """빌드 결과의 내부 링크가 실제 파일을 가리키는지(스크립트 안의 조립식 주소는 제외)."""
    sd = pathlib.Path(site_dir).resolve()
    bad = {}
    n = 0
    for p in sd.rglob("*.html"):
        if p.name == "404.html":
            continue
        t = re.sub(r"<script[\s\S]*?</script>", "", p.read_text(encoding="utf-8"))
        for h in set(re.findall(r'href="([^"#?]+)', t)):
            if re.match(r"^(https?:|mailto:|tel:|javascript:|data:)", h):
                continue
            n += 1
            q = (p.parent / h).resolve()
            if q.is_dir():
                q = q / "index.html"
            if not q.exists():
                bad.setdefault(h, str(p.relative_to(sd)))
    for h, src in list(bad.items())[:20]:
        ERR.append(f"깨진 내부 링크: {h} (예: {src})")
    print(f"  내부 링크 {n}개 검사, 깨진 주소 {len(bad)}종")


def check_online(m):
    """국가법령정보센터 연혁 첫 줄의 공포번호가 매니페스트 current/upcoming 에 있는지. 접속 실패는 경고."""
    import urllib.request
    for l in m["laws"]:
        if not l.get("lsId"):
            WARN.append(f"online {l['key']}: lsId 없음 — 연혁 비교 생략")
            continue
        url = f"https://www.law.go.kr/LSW/lsHstListR.do?lsId={l['lsId']}&chrClsCd=010202"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (anjeonduck audit)"})
            html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
        except Exception as ex:
            WARN.append(f"online {l['key']}: 연혁 접속 실패({type(ex).__name__}) — 수동 확인 필요")
            continue
        nos = re.findall(r"제\s*(\d{3,6})\s*호", strip_html(html))
        known = {re.sub(r"\D", "", x.get("no", "").split("제")[-1]) for x in [l["current"]] + l.get("upcoming", []) + l.get("recent", [])}
        if not nos:
            WARN.append(f"online {l['key']}: 연혁에서 공포번호를 읽지 못함 — 수동 확인 필요")
        else:
            new = [n for n in nos[:3] if n not in known]
            if new:
                WARN.append(f"online {l['key']}: 매니페스트에 없는 공포번호 발견 제{', 제'.join(new)}호 — 새 개정 여부 확인 필요")


def main():
    args = sys.argv[1:]
    site_dir = next((a for a in args if not a.startswith("--")), None)
    today = dt.date.today()
    m = check_manifest(today)
    check_updates()
    check_briefs()
    check_data_dates()
    check_phrases(site_dir)
    if site_dir:
        check_site(site_dir)
        check_internal_links(site_dir)
    if "--online" in args:
        check_online(m)
    for w in WARN:
        print("  경고:", w)
    for x in ERR:
        print("  오류:", x)
    print(f"감사 결과: 오류 {len(ERR)}건, 경고 {len(WARN)}건")
    sys.exit(1 if ERR else 0)


if __name__ == "__main__":
    main()
