"""OpenAI API(Responses API, 구조화 출력) 호출. SOCIAL_MOCK=1 이면 API 없이 근거 묶음으로 모의 응답을 만든다(시험·드라이런용)."""
import json, os
from .common import cfg, env, http, HERE, ApiError, log


def prompt(name):
    return (HERE / "prompts" / f"{name}.md").read_text(encoding="utf-8")


def _strict(schema):
    """구조화 출력 strict 모드 요건: 모든 object 에 required 전체 + additionalProperties:false."""
    if schema.get("type") == "object":
        schema["required"] = list(schema["properties"])
        schema["additionalProperties"] = False
        for v in schema["properties"].values():
            _strict(v)
    elif schema.get("type") == "array":
        _strict(schema["items"])
    return schema


def S(**props):
    return {"type": "object", "properties": props}


STR = {"type": "string"}


def A(item):
    return {"type": "array", "items": item}


SCHEMAS = {
    "blog": S(title=STR, meta_description=STR, intro=STR, law_basis=A(S(ref=STR, explain=STR)), key_points=A(S(heading=STR, body=STR)),
              how_to=A(STR), checklist=A(STR), faq=A(S(q=STR, a=STR)), labels=A(STR)),
    "instagram": S(cover_title=STR, cover_sub=STR, cards=A(S(heading=STR, lines=A(STR))), caption=STR, hashtags=A(STR)),
    "facebook": S(text=STR, question=STR),
    "verify": S(claims=A(S(claim=STR, supported={"type": "boolean"}, reason=STR)), problems=A(STR), overall={"type": "string", "enum": ["pass", "fail"]}),
}


def call(kind, user_text, mock=None, model=None):
    """kind: blog | instagram | facebook | verify. 돌려주는 값은 스키마에 맞는 dict."""
    if os.environ.get("SOCIAL_MOCK") == "1":
        return mock() if mock else {}
    c = cfg()["openai"]
    body = {
        "model": model or c["model"],
        "instructions": prompt("system") + "\n\n" + prompt(kind) if kind != "verify" else prompt("verify"),
        "input": user_text,
        "text": {"format": {"type": "json_schema", "name": f"safeplum_{kind}", "strict": True, "schema": _strict(json.loads(json.dumps(SCHEMAS[kind])))}},
    }
    r = http("POST", "https://api.openai.com/v1/responses", json_body=body, timeout=c.get("timeout", 180),
             headers={"Authorization": "Bearer " + env("OPENAI_API_KEY", True), "Content-Type": "application/json"})
    if r.get("status") not in (None, "completed"):
        raise ApiError(f"OpenAI 응답이 끝나지 않음: status={r.get('status')} {r.get('incomplete_details')}", retryable=True)
    text = r.get("output_text") or ""
    if not text:
        for o in r.get("output", []):
            if o.get("type") == "message":
                for part in o.get("content", []):
                    if part.get("type") == "refusal":
                        raise ApiError("OpenAI 가 작성을 거절함: " + str(part.get("refusal"))[:200])
                    if part.get("type") == "output_text":
                        text += part.get("text", "")
    try:
        out = json.loads(text)
    except ValueError:
        raise ApiError("OpenAI 응답이 JSON 이 아님: " + text[:300], retryable=True)
    u = r.get("usage") or {}
    log(f"OpenAI {kind}: 입력 {u.get('input_tokens', '?')} · 출력 {u.get('output_tokens', '?')} 토큰")
    return out
