"""공통 도구 — 경로, 한국 시간, JSON 읽기·쓰기, HTTP 요청(재시도), 기록."""
import json, os, sys, time, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent      # 사이트 저장소 루트
HERE = pathlib.Path(__file__).resolve().parent              # social/
STATE = pathlib.Path(os.environ.get("SOCIAL_STATE_DIR") or (ROOT / "_social"))   # social-data 브랜치를 받아 둔 폴더
KST = datetime.timezone(datetime.timedelta(hours=9))


def now():
    fake = os.environ.get("SOCIAL_NOW")          # 시험용: 2026-11-12T08:00
    return datetime.datetime.fromisoformat(fake).replace(tzinfo=KST) if fake else datetime.datetime.now(KST)


def today():
    return now().strftime("%Y-%m-%d")


def load(path, default=None):
    p = pathlib.Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save(path, data):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)                                 # 쓰다 끊겨도 원본이 깨지지 않게


_CFG = None


def cfg():
    global _CFG
    if _CFG is None:
        _CFG = load(HERE / "config.json")
        if os.environ.get("OPENAI_MODEL"):
            _CFG["openai"]["model"] = os.environ["OPENAI_MODEL"]
        if os.environ.get("SOCIAL_POSTS_PER_DAY", "").isdigit():
            _CFG["posts_per_day"] = max(1, min(2, int(os.environ["SOCIAL_POSTS_PER_DAY"])))
    return _CFG


def env(name, required=False):
    v = (os.environ.get(name) or "").strip()
    if required and not v:
        raise Missing(name)
    return v


class Missing(Exception):
    """필요한 비밀값·변수가 없다 — 오류가 아니라 '아직 연결 안 됨'으로 다룬다."""


class ApiError(Exception):
    def __init__(self, msg, status=None, body=None, retryable=False):
        super().__init__(msg)
        self.status, self.body, self.retryable = status, body, retryable


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def mask(text):
    """기록에 토큰이 남지 않게 가린다."""
    s = str(text)
    for k in ("OPENAI_API_KEY", "META_PAGE_TOKEN", "GOOGLE_REFRESH_TOKEN", "GOOGLE_CLIENT_SECRET", "SUPABASE_SERVICE_KEY"):
        v = os.environ.get(k)
        if v and len(v) > 6:
            s = s.replace(v, f"<{k}>")
    return s


def http(method, url, *, params=None, json_body=None, data=None, files=None, headers=None, timeout=60, tries=3):
    """요청을 보내고 JSON 을 돌려준다. 429·5xx·연결 오류는 2·6·18초 간격으로 다시 시도한다."""
    import requests
    last = None
    for i in range(tries):
        try:
            r = requests.request(method, url, params=params, json=json_body, data=data, files=files, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            last = ApiError(mask(f"연결 실패: {e}"), retryable=True)
        else:
            if r.status_code < 400:
                try:
                    return r.json() if r.content else {}
                except ValueError:
                    return {"_text": r.text}
            retry = r.status_code == 429 or r.status_code >= 500
            last = ApiError(mask(f"HTTP {r.status_code} {method} {url.split('?')[0]}: {r.text[:600]}"), r.status_code, r.text[:2000], retry)
            if not retry:
                raise last
        if i < tries - 1:
            time.sleep(2 * 3 ** i)
    raise last
