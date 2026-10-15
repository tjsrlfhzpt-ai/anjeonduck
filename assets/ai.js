/* SafePlum AI 공통 모듈 — 사용자 본인의 Google Gemini API 키로 브라우저에서 바로 호출한다(서버 없음).
   - 키는 이 브라우저에만 둔다: 기본은 sessionStorage(창을 닫으면 지워짐), "이 기기에 기억"을 고른 경우에만 localStorage.
   - 키는 SafePlum 서버로 보내지 않는다(SafePlum 서버 자체가 없음). Google API로만 전송한다.
   - AI 결과는 초안이다. 호출하는 쪽에서 반드시 사람이 검토·수정한 뒤 확정하게 만든다.
   사용: SPAI.ensureKey().then(...) / SPAI.json({system, prompt, schema}) → Promise(object) / SPAI.text({...}) → Promise(string) */
(function () {
  "use strict";
  if (window.SPAI) return;
  var K_KEY = "safeplum.ai.key", K_MODEL = "safeplum.ai.model", K_AGREE = "safeplum.ai.agree";
  var API = "https://generativelanguage.googleapis.com/v1beta/";
  var FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"];
  var KEY_GUIDE = "https://aistudio.google.com/app/apikey";

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function sget(st, k) { try { return st.getItem(k) || ""; } catch (e) { return ""; } }
  function sset(st, k, v) { try { if (v) st.setItem(k, v); else st.removeItem(k); } catch (e) {} }
  function getKey() { return sget(sessionStorage, K_KEY) || sget(localStorage, K_KEY); }
  function remembered() { return !!sget(localStorage, K_KEY); }
  function setKey(k, remember) {
    k = String(k || "").trim();
    sset(sessionStorage, K_KEY, k); sset(localStorage, K_KEY, remember ? k : "");
    if (!k) sset(localStorage, K_MODEL, "");
  }
  function maskKey(k) { return k ? k.slice(0, 4) + "…" + k.slice(-4) : ""; }

  // ---------- 오류를 사용자가 이해할 수 있는 말로
  function AIError(code, msg, detail) { var e = new Error(msg); e.code = code; e.detail = detail || ""; return e; }
  function explain(status, body) {
    var m = (body && body.error && (body.error.message || body.error.status)) || "";
    var r = JSON.stringify(body || {});
    if (status === 400 && /API_KEY_INVALID|API key not valid/i.test(r)) return AIError("key", "API 키가 올바르지 않습니다. 키를 다시 확인해 주세요.", m);
    if (status === 401 || status === 403) return AIError("key", "이 API 키로는 사용할 수 없습니다(권한 없음 또는 사용 중지된 키).", m);
    if (status === 429) return AIError("quota", "사용 한도에 걸렸습니다. 잠시 뒤 다시 시도하거나, Google AI Studio에서 한도·결제 설정을 확인해 주세요.", m);
    if (status === 404) return AIError("model", "선택된 AI 모델을 찾지 못했습니다. 키 설정에서 '연결 확인'을 다시 눌러 주세요.", m);
    if (status >= 500) return AIError("server", "Google AI 서버가 잠시 응답하지 않습니다. 잠시 뒤 다시 시도해 주세요.", m);
    return AIError("other", "AI 요청이 실패했습니다(" + status + ").", m);
  }
  function call(path, opt) {
    var key = getKey();
    if (!key) return Promise.reject(AIError("nokey", "AI 키가 설정되지 않았습니다."));
    opt = opt || {};
    var ctl = typeof AbortController === "function" ? new AbortController() : null;
    var timer = ctl ? setTimeout(function () { ctl.abort(); }, opt.timeout || 60000) : null;
    return fetch(API + path, {
      method: opt.body ? "POST" : "GET",
      headers: Object.assign({ "x-goog-api-key": key }, opt.body ? { "Content-Type": "application/json" } : {}),
      body: opt.body ? JSON.stringify(opt.body) : undefined,
      signal: ctl ? ctl.signal : undefined
    }).then(function (res) {
      if (timer) clearTimeout(timer);
      return res.json().catch(function () { return {}; }).then(function (b) { if (!res.ok) throw explain(res.status, b); return b; });
    }, function (err) {
      if (timer) clearTimeout(timer);
      if (err && err.name === "AbortError") throw AIError("timeout", "AI 응답이 너무 오래 걸려 중단했습니다. 다시 시도해 주세요.");
      throw AIError("network", "인터넷 연결을 확인해 주세요(Google AI 서버에 연결하지 못했습니다).");
    });
  }

  // ---------- 모델: 키로 쓸 수 있는 목록에서 가볍고 빠른 flash 계열을 고른다
  function rankModel(n) {
    var v = (n.match(/gemini-(\d+(?:\.\d+)?)/) || [0, "0"])[1];
    var s = parseFloat(v) * 10;
    if (/lite/.test(n)) s -= 3;
    if (/preview|exp/.test(n)) s -= 5;
    return s;
  }
  function pickModel(force) {
    var cached = sget(localStorage, K_MODEL);
    if (cached && !force) return Promise.resolve(cached);
    return call("models?pageSize=200").then(function (b) {
      var names = (b.models || []).filter(function (m) {
        return (m.supportedGenerationMethods || []).indexOf("generateContent") >= 0 &&
          /^models\/gemini-[\d.]+-flash/.test(m.name) && !/(image|tts|audio|live|thinking|embedding|vision)/.test(m.name);
      }).map(function (m) { return m.name.replace(/^models\//, ""); });
      names.sort(function (a, b) { return rankModel(b) - rankModel(a); });
      var pick = names[0] || FALLBACK_MODELS[0];
      sset(localStorage, K_MODEL, pick);
      return pick;
    });
  }

  function gen(o, wantJSON) {
    return pickModel().then(function (model) {
      var body = {
        contents: [{ role: "user", parts: [{ text: o.prompt }] }],
        generationConfig: { temperature: o.temperature == null ? 0.4 : o.temperature, maxOutputTokens: o.maxTokens || 4096 }
      };
      if (o.system) body.systemInstruction = { parts: [{ text: o.system }] };
      if (wantJSON) { body.generationConfig.responseMimeType = "application/json"; if (o.schema) body.generationConfig.responseSchema = o.schema; }
      return call("models/" + encodeURIComponent(model) + ":generateContent", { body: body, timeout: o.timeout }).catch(function (e) {
        if (e.code === "model") { sset(localStorage, K_MODEL, ""); }
        throw e;
      });
    }).then(function (b) {
      if (b.promptFeedback && b.promptFeedback.blockReason) throw AIError("blocked", "AI가 이 요청에 답하지 않았습니다(안전 정책). 표현을 바꿔 다시 시도해 주세요.");
      var c = (b.candidates || [])[0];
      var t = c && c.content && (c.content.parts || []).map(function (p) { return p.text || ""; }).join("");
      if (!t) throw AIError("empty", "AI가 빈 답을 보냈습니다. 다시 시도해 주세요.");
      if (!wantJSON) return t;
      try { return JSON.parse(t.replace(/^```(?:json)?\s*|\s*```$/g, "")); }
      catch (e) { throw AIError("parse", "AI 답을 해석하지 못했습니다. 다시 시도해 주세요."); }
    });
  }

  // ---------- 화면: 키 설정 창
  var CSS = "" +
    ".spai-ov{position:fixed;inset:0;background:rgba(10,20,35,.55);z-index:5000;display:flex;align-items:center;justify-content:center;padding:14px}" +
    ".spai-m{background:#fff;color:#1d2433;border-radius:14px;max-width:520px;width:100%;max-height:92vh;overflow:auto;padding:20px 20px 16px;box-shadow:0 20px 50px rgba(0,0,0,.25);font:14px/1.6 'Pretendard','Noto Sans KR',system-ui,sans-serif}" +
    ".spai-m h3{margin:0 0 6px;font-size:18px;color:#17365D}" +
    ".spai-m p{margin:6px 0}.spai-m ol{margin:6px 0 6px 18px;padding:0}.spai-m li{margin:2px 0}" +
    ".spai-m input[type=password],.spai-m input[type=text]{width:100%;box-sizing:border-box;height:44px;border:1px solid #c8d1dd;border-radius:9px;padding:0 12px;font-size:15px;margin-top:4px}" +
    ".spai-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;justify-content:flex-end}" +
    ".spai-b{min-height:42px;padding:0 16px;border-radius:9px;border:1px solid #c8d1dd;background:#fff;color:#1d2433;font-weight:700;font-size:14px;cursor:pointer}" +
    ".spai-b.pri{background:#17365D;border-color:#17365D;color:#fff}.spai-b.red{color:#b42318;border-color:#f1c4bf}" +
    ".spai-note{background:#FFF7E6;border:1px solid #F5D9A8;border-radius:9px;padding:9px 11px;font-size:13px;color:#7a4a00;margin:10px 0}" +
    ".spai-st{font-size:13px;margin-top:8px;min-height:20px}.spai-st.ok{color:#05603a}.spai-st.err{color:#b42318}" +
    ".spai-chk{display:flex;gap:8px;align-items:flex-start;font-size:13.5px;margin-top:10px}" +
    ".spai-chk input{margin-top:4px;width:18px;height:18px}" +
    ".spai-a{color:#1F6FD1;font-weight:700}" +
    ".spai-busy{display:inline-flex;align-items:center;gap:8px}" +
    ".spai-busy:before{content:'';width:14px;height:14px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:spai-r .8s linear infinite}" +
    "@keyframes spai-r{to{transform:rotate(360deg)}}";
  function injectCSS() { if (document.getElementById("spai-css")) return; var s = document.createElement("style"); s.id = "spai-css"; s.textContent = CSS; document.head.appendChild(s); }

  function openSettings() {
    injectCSS();
    return new Promise(function (resolve) {
      var ov = document.createElement("div"); ov.className = "spai-ov"; ov.setAttribute("role", "dialog"); ov.setAttribute("aria-modal", "true");
      var k = getKey();
      ov.innerHTML = '<div class="spai-m"><h3>AI 키 설정 (내 Gemini API 키)</h3>' +
        '<p>SafePlum의 AI 기능은 <b>본인의 Google Gemini API 키</b>로 동작합니다. 키는 <b>이 브라우저에만</b> 저장되고, SafePlum은 키나 입력 내용을 받지 않습니다(AI 요청은 Google로 바로 갑니다).</p>' +
        '<ol><li><a class="spai-a" href="' + KEY_GUIDE + '" target="_blank" rel="noopener">Google AI Studio API 키 페이지 ↗</a>에 구글 계정으로 로그인</li><li>「API 키 만들기」를 눌러 키 복사</li><li>아래 칸에 붙여 넣고 「연결 확인」</li></ol>' +
        '<label>API 키<input type="password" id="spaiKey" autocomplete="off" spellcheck="false" placeholder="AIza…" value="' + esc(k) + '"></label>' +
        '<label class="spai-chk"><input type="checkbox" id="spaiRem"' + (remembered() ? " checked" : "") + '><span>이 기기에 기억하기 <small style="color:#667">(끄면 창을 닫을 때 지워짐 · 공용 PC에서는 끄세요)</small></span></label>' +
        '<div class="spai-note"><b>입력 주의</b> — 무료 키로 보낸 내용은 Google이 서비스 개선에 쓸 수 있고 사람이 검토할 수 있습니다(Google 약관). <b>실명·연락처·주민번호 등 개인정보와 회사 기밀은 넣지 마세요.</b> AI 결과는 초안이므로 반드시 검토 후 사용하세요.</div>' +
        '<div class="spai-st" id="spaiSt" aria-live="polite">' + (k ? "저장된 키: " + esc(maskKey(k)) : "") + '</div>' +
        '<div class="spai-row">' + (k ? '<button type="button" class="spai-b red" id="spaiDel">키 지우기</button>' : "") +
        '<button type="button" class="spai-b" id="spaiCancel">닫기</button><button type="button" class="spai-b pri" id="spaiOk">연결 확인 후 저장</button></div></div>';
      document.body.appendChild(ov);
      var inp = ov.querySelector("#spaiKey"), st = ov.querySelector("#spaiSt"), ok = ov.querySelector("#spaiOk");
      setTimeout(function () { inp.focus(); }, 30);
      function close(v) { ov.remove(); document.removeEventListener("keydown", onKey); resolve(v); }
      function onKey(e) { if (e.key === "Escape") close(!!getKey()); }
      document.addEventListener("keydown", onKey);
      ov.addEventListener("click", function (e) { if (e.target === ov) close(!!getKey()); });
      ov.querySelector("#spaiCancel").onclick = function () { close(!!getKey()); };
      var del = ov.querySelector("#spaiDel"); if (del) del.onclick = function () { setKey(""); st.className = "spai-st"; st.textContent = "키를 지웠습니다."; inp.value = ""; del.remove(); };
      ok.onclick = function () {
        var v = inp.value.trim();
        if (!/^[A-Za-z0-9_\-]{20,}$/.test(v)) { st.className = "spai-st err"; st.textContent = "키 형식이 맞지 않습니다. Google AI Studio에서 복사한 키를 그대로 붙여 넣어 주세요."; return; }
        var prevS = sget(sessionStorage, K_KEY), prevL = sget(localStorage, K_KEY);
        setKey(v, ov.querySelector("#spaiRem").checked);
        ok.disabled = true; st.className = "spai-st"; st.innerHTML = '<span class="spai-busy">연결 확인 중…</span>';
        pickModel(true).then(function (m) {
          sset(localStorage, K_AGREE, "1");
          st.className = "spai-st ok"; st.textContent = "연결되었습니다. 사용 모델: " + m;
          setTimeout(function () { close(true); }, 700);
        }, function (e) {
          sset(sessionStorage, K_KEY, prevS); sset(localStorage, K_KEY, prevL);
          ok.disabled = false; st.className = "spai-st err"; st.textContent = e.message;
        });
      };
      inp.addEventListener("keydown", function (e) { if (e.key === "Enter") ok.click(); });
    });
  }
  function ensureKey() { return getKey() ? Promise.resolve(true) : openSettings(); }

  window.SPAI = {
    hasKey: function () { return !!getKey(); },
    ensureKey: ensureKey,
    openSettings: openSettings,
    json: function (o) { return ensureKey().then(function (ok) { if (!ok) throw AIError("nokey", "AI 키가 설정되지 않았습니다."); return gen(o, true); }); },
    text: function (o) { return ensureKey().then(function (ok) { if (!ok) throw AIError("nokey", "AI 키가 설정되지 않았습니다."); return gen(o, false); }); },
    model: function () { return sget(localStorage, K_MODEL); },
    esc: esc,
    css: injectCSS,
    NOTICE: "AI가 만든 초안입니다. 현장 상황에 맞는지 반드시 검토·수정한 뒤 사용하세요."
  };
})();
