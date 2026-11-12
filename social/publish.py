"""플랫폼 게시 — Blogger API v3, Facebook Graph API(페이지), Instagram Graph API(카드뉴스 캐러셀).

모든 게시 함수는 (게시물 ID, 공개 주소)를 돌려주고, 돌려주기 전에 실제로 올라갔는지 다시 조회해 확인한다.
SOCIAL_DRY=1 이면 API 를 부르지 않고 보낼 요청만 기록한다.
"""
import os, subprocess, time
from .common import cfg, env, http, log, STATE, ApiError
from . import compose

DRY = lambda: os.environ.get("SOCIAL_DRY") == "1"
_tok = {}


def G(path):
    return f"https://graph.facebook.com/{cfg()['graph_version']}/{path}"


# ---------------------------------------------------------------- 구글
def google_token():
    """리프레시 토큰으로 1시간짜리 접근 토큰을 받는다(Blogger·Search Console·Sheets 공용)."""
    if "g" in _tok and _tok["g"][1] > time.time() + 60:
        return _tok["g"][0]
    r = http("POST", "https://oauth2.googleapis.com/token", data={
        "client_id": env("GOOGLE_CLIENT_ID", True), "client_secret": env("GOOGLE_CLIENT_SECRET", True),
        "refresh_token": env("GOOGLE_REFRESH_TOKEN", True), "grant_type": "refresh_token"})
    _tok["g"] = (r["access_token"], time.time() + int(r.get("expires_in", 3600)))
    return r["access_token"]


def media_url(item_id, name):
    """social-data 브랜치에 올라간 이미지의 공개 주소. 커밋 번호를 넣어 캐시 지연 없이 바로 열리고 바뀌지 않는다."""
    repo = env("GITHUB_REPOSITORY") or "tjsrlfhzpt-ai/anjeonduck"
    try:
        sha = subprocess.run(["git", "-C", str(STATE), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20).stdout.strip() or "social-data"
    except Exception:
        sha = "social-data"
    if cfg()["image_host"] == "raw":
        return f"https://raw.githubusercontent.com/{repo}/{sha}/media/{item_id}/{name}"
    return f"https://cdn.jsdelivr.net/gh/{repo}@{sha}/media/{item_id}/{name}"


def blogger(item):
    blog = env("BLOGGER_BLOG_ID", not DRY()) or "(미설정)"
    b = item["raw"]["blog"]
    cover = media_url(item["id"], "cover.jpg") if (STATE / "media" / item["id"] / "cover.jpg").exists() else ""
    body = {"kind": "blogger#post", "title": b["title"], "content": compose.blog_html(item, cover), "labels": [l.replace(",", " ")[:30] for l in b.get("labels", [])][:8]}
    if DRY():
        log(f"[드라이런] Blogger POST /blogs/{blog}/posts 제목='{b['title']}' 본문 {len(body['content'])}자 라벨 {body['labels']}")
        return "dry", ""
    h = {"Authorization": "Bearer " + google_token()}
    base = f"https://www.googleapis.com/blogger/v3/blogs/{blog}/posts"
    # 이전 실행이 응답을 못 받고 끊겼을 수 있다 — 같은 제목의 글이 최근에 올라가 있으면 다시 올리지 않는다
    recent = http("GET", base, headers=h, params={"maxResults": 20, "fetchBodies": "false", "status": "live"}).get("items", [])
    for p in recent:
        if p.get("title") == b["title"]:
            log("이미 올라간 글을 찾음 — 다시 올리지 않음:", p["url"])
            return p["id"], p["url"]
    r = http("POST", base + "/", headers=h, json_body=body, params={"isDraft": "false"}, tries=1)   # 중복 게시를 막으려고 자동 재전송은 하지 않는다
    chk = http("GET", f"{base}/{r['id']}", headers=h, params={"fields": "id,url,status"})
    if chk.get("status") not in (None, "LIVE"):
        raise ApiError(f"Blogger 글 상태가 LIVE 가 아님: {chk.get('status')}")
    return chk["id"], chk["url"]


# ---------------------------------------------------------------- 메타(페이스북·인스타그램)
def _meta_token():
    return env("META_PAGE_TOKEN", True)


def facebook(item):
    page = env("META_PAGE_ID", not DRY()) or "(미설정)"
    text = compose.fb_text(item)
    link = compose.utm_link("facebook", item, compose.primary_path(item))
    if DRY():
        log(f"[드라이런] Facebook POST /{page}/feed link={link}\n{text}")
        return "dry", ""
    tok = _meta_token()
    recent = http("GET", G(f"{page}/posts"), params={"fields": "id,message,permalink_url", "limit": 10, "access_token": tok}).get("data", [])
    for p in recent:
        if (p.get("message") or "")[:60] == text[:60]:
            log("이미 올라간 게시물을 찾음 — 다시 올리지 않음:", p.get("permalink_url"))
            return p["id"], p.get("permalink_url", "")
    r = http("POST", G(f"{page}/feed"), data={"message": text, "link": link, "access_token": tok}, tries=1)
    chk = http("GET", G(r["id"]), params={"fields": "id,permalink_url,created_time", "access_token": tok})
    return chk["id"], chk.get("permalink_url", "")


def _fb_hosted(page, tok, path):
    """이미지를 페이스북 페이지에 '비공개 사진'으로 올리고 그 주소를 받는다 — 인스타그램이 외부 주소를 못 읽을 때의 우회로."""
    with open(path, "rb") as f:
        r = http("POST", G(f"{page}/photos"), data={"published": "false", "temporary": "true", "access_token": tok}, files={"source": (os.path.basename(path), f, "image/jpeg")}, tries=2)
    imgs = http("GET", G(r["id"]), params={"fields": "images", "access_token": tok}).get("images", [])
    if not imgs:
        raise ApiError("페이스북 임시 사진 주소를 받지 못함")
    return max(imgs, key=lambda i: i.get("width", 0))["source"]


def _wait_container(cid, tok, label):
    for _ in range(30):
        s = http("GET", G(cid), params={"fields": "status_code,status", "access_token": tok})
        if s.get("status_code") == "FINISHED":
            return
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise ApiError(f"인스타그램 {label} 처리 실패: {s.get('status')}")
        time.sleep(4)
    raise ApiError(f"인스타그램 {label} 처리가 2분 안에 끝나지 않음", retryable=True)


def instagram(item):
    ig = env("META_IG_USER_ID", not DRY()) or "(미설정)"
    caption = compose.ig_caption(item)
    mdir = STATE / "media" / item["id"]
    files = sorted(p for p in mdir.glob("[0-9][0-9].jpg"))
    if not files:
        raise ApiError("카드 이미지가 없음: " + str(mdir))
    if DRY():
        log(f"[드라이런] Instagram 캐러셀 {len(files)}장 /{ig}/media → /{ig}/media_publish\n첫 이미지 {media_url(item['id'], files[0].name)}\n{caption}")
        return "dry", ""
    tok = _meta_token()
    recent = http("GET", G(f"{ig}/media"), params={"fields": "id,caption,permalink", "limit": 10, "access_token": tok}).get("data", [])
    for m in recent:
        if (m.get("caption") or "")[:60] == caption[:60]:
            log("이미 올라간 게시물을 찾음 — 다시 올리지 않음:", m.get("permalink"))
            return m["id"], m.get("permalink", "")
    lim = http("GET", G(f"{ig}/content_publishing_limit"), params={"fields": "quota_usage,config", "access_token": tok}).get("data", [{}])[0]
    if lim.get("quota_usage", 0) >= (lim.get("config") or {}).get("quota_total", 50):
        raise ApiError("인스타그램 24시간 게시 한도에 도달", retryable=True)
    page = env("META_PAGE_ID")

    def child(path, hosted):
        url = _fb_hosted(page, tok, path) if hosted else media_url(item["id"], path.name)
        r = http("POST", G(f"{ig}/media"), data={"image_url": url, "is_carousel_item": "true", "access_token": tok})
        return r["id"]

    try:
        kids = [child(p, False) for p in files]
    except ApiError as e:
        if not page or e.status not in (400, 500):
            raise
        log("인스타그램이 이미지 주소를 읽지 못함 → 페이스북 임시 사진 주소로 다시 시도:", str(e)[:200])
        kids = [child(p, True) for p in files]
    for k in kids:
        _wait_container(k, tok, "카드")
    if len(kids) == 1:
        raise ApiError("캐러셀은 2장 이상이어야 함")
    car = http("POST", G(f"{ig}/media"), data={"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption, "access_token": tok})
    _wait_container(car["id"], tok, "캐러셀")
    pub = http("POST", G(f"{ig}/media_publish"), data={"creation_id": car["id"], "access_token": tok}, tries=1)
    chk = http("GET", G(pub["id"]), params={"fields": "id,permalink", "access_token": tok})
    return chk["id"], chk.get("permalink", "")


PUBLISHERS = {"blogger": blogger, "instagram": instagram, "facebook": facebook}
NEEDS = {"blogger": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "BLOGGER_BLOG_ID"],
         "instagram": ["META_PAGE_TOKEN", "META_IG_USER_ID"], "facebook": ["META_PAGE_TOKEN", "META_PAGE_ID"]}


def connected(platform):
    return all(env(k) for k in NEEDS[platform])


# ---------------------------------------------------------------- 연결 점검
def preflight():
    """각 서비스에 가볍게 물어 연결 상태를 표로 만든다. 게시는 하지 않는다."""
    rows = []

    def check(name, need, fn):
        miss = [k for k in need if not env(k)]
        if miss:
            rows.append((name, "미연결", "없는 값: " + ", ".join(miss)))
            return
        try:
            rows.append((name, "정상", fn()))
        except Exception as e:
            rows.append((name, "오류", str(e)[:260]))

    def openai():
        ids = [m["id"] for m in http("GET", "https://api.openai.com/v1/models", headers={"Authorization": "Bearer " + env("OPENAI_API_KEY")}).get("data", [])]
        m = cfg()["openai"]["model"]
        if m not in ids:
            raise ApiError(f"설정한 모델 '{m}' 을 이 키로 쓸 수 없음. 쓸 수 있는 gpt 모델 예: " + ", ".join(sorted(i for i in ids if i.startswith("gpt-"))[-8:]))
        return f"모델 {m} 사용 가능"

    def blog():
        r = http("GET", f"https://www.googleapis.com/blogger/v3/blogs/{env('BLOGGER_BLOG_ID')}", headers={"Authorization": "Bearer " + google_token()})
        return f"{r.get('name')} — {r.get('url')}"

    def fb():
        tok = env("META_PAGE_TOKEN")
        r = http("GET", G(env("META_PAGE_ID")), params={"fields": "name,link", "access_token": tok})
        d = http("GET", G("debug_token"), params={"input_token": tok, "access_token": tok}).get("data", {})
        exp = d.get("expires_at")
        need = {"pages_manage_posts", "pages_read_engagement"} - set(d.get("scopes", []))
        note = "만료 없음" if not exp else "만료 " + time.strftime("%Y-%m-%d", time.localtime(exp))
        if exp and exp - time.time() < 10 * 86400:
            raise ApiError(f"페이지 토큰이 곧 만료됨({note}) — 매뉴얼 5장대로 다시 발급하세요")
        return f"{r.get('name')} · 토큰 {note}" + (f" · 빠진 권한: {', '.join(sorted(need))}" if need and d.get("scopes") else "")

    def ig():
        r = http("GET", G(env("META_IG_USER_ID")), params={"fields": "username,media_count", "access_token": env("META_PAGE_TOKEN")})
        return f"@{r.get('username')} · 게시물 {r.get('media_count')}개"

    def stats():
        from .metrics import supabase_stats
        from .common import today
        r = supabase_stats(today(), today())
        return f"오늘 방문 {sum(v['visitors'] for v in r.get('visitors', []))} · UTM 기록 {len(r.get('utm', []))}줄"

    check("OpenAI", ["OPENAI_API_KEY"], openai)
    check("Blogger", NEEDS["blogger"], blog)
    check("Facebook 페이지", NEEDS["facebook"], fb)
    check("Instagram", NEEDS["instagram"], ig)
    check("유입 집계(Supabase)", ["SOCIAL_STATS_KEY"], stats)
    return rows
