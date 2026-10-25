/* SafePlum AI 공통 모듈 — 사용자 본인의 Google Gemini API 키로 브라우저에서 바로 호출한다(서버 없음).
   - 키는 이 브라우저에만 둔다: 기본은 sessionStorage(창을 닫으면 지워짐), "이 기기에 기억"을 고른 경우에만 localStorage.
   - 키는 SafePlum 서버로 보내지 않는다(SafePlum 서버 자체가 없음). Google API로만 전송한다.
   - AI 결과는 초안이다. 호출하는 쪽에서 반드시 사람이 검토·수정한 뒤 확정하게 만든다.
   사용: SPAI.ensureKey().then(...) / SPAI.json({system, prompt, schema}) → Promise(object) / SPAI.text({...}) → Promise(string)
   근거 찾기(브라우저 안에서만): SPAI.law.search(질문, {keywords, laws, refs, k}) → 현행 조문 / SPAI.govqa.search(질문, k) → 고용노동부 질의회시
   개인정보 가리기: 보내기 전 전화번호·주민등록번호·이메일·계좌·차량번호 꼴은 자동으로 가린다(SPAI.scrub). */
(function () {
  "use strict";
  if (window.SPAI) return;
  var K_KEY = "safeplum.ai.key", K_MODEL = "safeplum.ai.model", K_AGREE = "safeplum.ai.agree", K_STATE = "safeplum.ai.state";
  var API = "https://generativelanguage.googleapis.com/v1beta/";
  var FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"];
  var KEY_GUIDE = "https://aistudio.google.com/app/apikey";
  // 사이트 뿌리 주소: 이 파일(assets/ai.js) 위치에서 거꾸로 구한다 — 어느 깊이의 페이지에서 불러도 같은 자료를 찾게
  var ROOT = (function () { try { var c = document.currentScript && document.currentScript.src; if (c) return c.replace(/assets\/ai\.js(\?.*)?$/, ""); } catch (e) {} return "/"; })();

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function sget(st, k) { try { return st.getItem(k) || ""; } catch (e) { return ""; } }
  function sset(st, k, v) { try { if (v) st.setItem(k, v); else st.removeItem(k); } catch (e) {} }
  function getKey() { return sget(sessionStorage, K_KEY) || sget(localStorage, K_KEY); }
  function remembered() { return !!sget(localStorage, K_KEY); }
  function setKey(k, remember) {
    k = String(k || "").trim();
    sset(sessionStorage, K_KEY, k); sset(localStorage, K_KEY, remember ? k : "");
    if (!k) sset(localStorage, K_MODEL, "");
    sset(localStorage, K_STATE, "");   // 키가 바뀌면 연결 상태도 처음부터
    fire();
  }
  function maskKey(k) { return k ? k.slice(0, 4) + "…" + k.slice(-4) : ""; }
  // ---------- 연결 상태: 키 설정(있음/없음)과 연결 결과(성공/오류)를 따로 기록한다 — 키 값은 기록하지 않는다
  //   none: 키 없음 · set: 키는 있지만 아직 연결 확인 전 · ok: 마지막 요청 성공 · key/network/quota/server/model/other: 마지막 요청 실패
  function readState() { try { return JSON.parse(sget(localStorage, K_STATE) || "null"); } catch (e) { return null; } }
  function writeState(code, msg) { try { localStorage.setItem(K_STATE, JSON.stringify({ s: code, m: String(msg || "").slice(0, 300), at: new Date().toISOString() })); } catch (e) {} fire(); }
  function status() {
    if (!getKey()) return { code: "none" };
    var st = readState();
    return st && st.s ? { code: st.s, msg: st.m, at: st.at } : { code: "set" };
  }
  function fire() { try { window.dispatchEvent(new CustomEvent("spai:status", { detail: status() })); } catch (e) {} }
  var STATUS_TEXT = {
    none: ["미설정", "AI 키가 아직 없습니다."],
    set: ["설정됨 · 연결 확인 전", "키는 저장되어 있지만 아직 연결을 확인하지 않았습니다."],
    ok: ["연결 확인됨", "마지막 AI 요청이 정상 처리되었습니다."],
    key: ["API 키 오류", "키가 올바르지 않거나 사용할 수 없는 키입니다. Google AI Studio에서 키를 다시 복사해 넣거나 새 키를 만드세요."],
    network: ["연결 실패", "Google AI 서버에 연결하지 못했습니다. 인터넷 연결을 확인하세요. 회사 네트워크(방화벽)에서 generativelanguage.googleapis.com 접속을 막는 경우도 있어 확인이 필요합니다."],
    quota: ["사용량 제한", "Google 사용 한도(분당·일일 요청 수)에 걸렸습니다. 잠시 뒤 다시 시도하거나 Google AI Studio에서 한도·결제 설정을 확인하세요."],
    server: ["외부 API 오류", "Google AI 서버가 잠시 응답하지 않았습니다. 잠시 뒤 다시 시도하세요."],
    model: ["모델 오류", "선택된 AI 모델을 쓸 수 없습니다. 연결을 다시 확인하면 쓸 수 있는 모델을 다시 고릅니다."],
    timeout: ["응답 지연", "AI 응답이 너무 오래 걸렸습니다. 다시 시도하세요."],
    other: ["기타 오류", "원인을 정확히 알 수 없는 오류입니다. 아래 상세 내용을 확인하고, 계속되면 오류 신고 창구로 알려 주세요."]
  };
  function statusLabel(st) { st = st || status(); var t = STATUS_TEXT[st.code] || STATUS_TEXT.other; return { code: st.code, label: t[0], help: t[1], detail: st.msg || "", at: st.at || "" }; }

  // ---------- 개인정보 가리기: AI로 보내기 전에 자동으로 바꾼다(화면·저장 내용은 그대로)
  var PII = [
    [/\b\d{6}\s*-\s*[1-8]\d{6}\b/g, "[주민번호 가림]"],
    [/\b01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}\b/g, "[휴대전화 가림]"],
    [/\b0(?:2|[3-6][1-5]|70)[-\s.]?\d{3,4}[-\s.]?\d{4}\b/g, "[전화번호 가림]"],
    [/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, "[이메일 가림]"],
    [/\b\d{2,6}-\d{2,6}-\d{2,8}(?:-\d{1,6})?\b(?=[^가-힣]{0,6}(?:계좌|은행|통장))/g, "[계좌 가림]"],
    [/\b\d{2,3}[가-힣]\s?\d{4}\b/g, "[차량번호 가림]"]
  ];
  var lastScrub = 0;
  function scrub(t) {
    var n = 0; t = String(t == null ? "" : t);
    PII.forEach(function (p) { t = t.replace(p[0], function () { n++; return p[1]; }); });
    return { text: t, n: n };
  }

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

  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  // ---------- 진행 표시: AI가 일하는 동안 화면 아래에 크게 보여 준다(단계·경과 시간·받은 글자 수·취소)
  var PCSS = ".spai-pg{position:fixed;left:50%;bottom:calc(18px + env(safe-area-inset-bottom,0px));transform:translateX(-50%);z-index:4900;width:min(460px,calc(100vw - 24px));background:#17365D;color:#fff;border-radius:14px;box-shadow:0 14px 40px rgba(10,20,40,.35);padding:14px 16px 12px;font:14px/1.5 'Pretendard','Noto Sans KR',system-ui,sans-serif}" +
    ".spai-pg[hidden]{display:none}.spai-pg-h{display:flex;align-items:center;gap:12px}" +
    ".spai-pg-sp{flex:none;width:26px;height:26px;border:3px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spai-r .8s linear infinite}" +
    ".spai-pg-t{flex:1;min-width:0}.spai-pg-t b{display:block;font-size:15px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.spai-pg-t span{display:block;font-size:12.5px;color:#C7D7EE}" +
    ".spai-pg-x{flex:none;min-height:36px;padding:0 12px;border-radius:8px;border:1px solid rgba(255,255,255,.45);background:transparent;color:#fff;font-weight:700;font-size:13px;cursor:pointer}" +
    ".spai-pg-bar{height:6px;border-radius:4px;background:rgba(255,255,255,.18);overflow:hidden;margin-top:10px;position:relative}" +
    ".spai-pg-bar i{position:absolute;left:0;top:0;bottom:0;width:0;background:#7DD3FC;border-radius:4px;transition:width .4s ease}" +
    ".spai-pg-bar.ind i{width:35%;animation:spai-ind 1.3s ease-in-out infinite}" +
    "@keyframes spai-ind{0%{left:-35%}100%{left:100%}}@keyframes spai-r{to{transform:rotate(360deg)}}" +
    ".spai-pg.done{background:#05603A}.spai-pg.done .spai-pg-sp{animation:none;border-color:#fff}.spai-pg.err{background:#B42318}.spai-pg.err .spai-pg-sp,.spai-pg.done .spai-pg-sp{display:none}" +
    "@media (max-width:1023px){.spai-pg{bottom:calc(76px + env(safe-area-inset-bottom,0px))}}" +
    "@media (prefers-reduced-motion:reduce){.spai-pg-sp,.spai-pg-bar.ind i{animation-duration:3s}}";
  var prog = null;
  // 예시 칩: 무엇을 적을지 모를 때 눌러서 입력칸에 넣는다(넣은 뒤 고쳐 쓰게 커서를 끝으로)
  var XCSS = ".spai-ex{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:8px 0 2px}.spai-ex-l{font-size:12.5px;font-weight:800;color:#475467;margin-right:2px}" +
    ".spai-ex button{min-height:34px;max-width:100%;padding:5px 11px;border-radius:17px;border:1px solid #C7D2FE;background:#F5F7FF;color:#3730A3;font-size:13px;line-height:1.35;text-align:left;cursor:pointer}" +
    ".spai-ex button:hover{background:#E0E7FF;border-color:#818CF8}.spai-cnt{font-size:12.5px;color:#667085;margin-top:4px}.spai-cnt.bad{color:#B42318;font-weight:700}.spai-cnt.ok{color:#05603A;font-weight:700}";
  function examples(box, list, input, opt) {
    opt = opt || {};
    if (!document.getElementById("spai-xcss")) { var s = document.createElement("style"); s.id = "spai-xcss"; s.textContent = XCSS; document.head.appendChild(s); }
    list = (list || []).filter(Boolean);
    box.innerHTML = list.length ? '<div class="spai-ex" role="group" aria-label="입력 예시"><span class="spai-ex-l">예시 눌러 넣기</span>' + list.map(function (x, i) { return '<button type="button" data-ex="' + i + '" title="눌러서 입력칸에 넣기">' + esc(x) + "</button>"; }).join("") + "</div>" : "";
    box.onclick = function (ev) { var b = ev.target.closest("[data-ex]"); if (!b) return; input.value = list[+b.dataset.ex]; input.dispatchEvent(new Event("input", { bubbles: true })); input.focus(); try { input.setSelectionRange(input.value.length, input.value.length); } catch (e) {} };
    // 글자 수 안내: 최소 글자 수를 입력칸 바로 아래에 늘 보여 준다
    var min = opt.min || 0, cnt = null;
    if (min) {
      cnt = input.parentNode.querySelector(".spai-cnt");
      if (!cnt) { cnt = document.createElement("p"); cnt.className = "spai-cnt"; input.insertAdjacentElement("afterend", cnt); }
      var upd = function () { var n = input.value.replace(/\s/g, "").length; cnt.className = "spai-cnt " + (n >= min ? "ok" : n ? "bad" : ""); cnt.textContent = n >= min ? "✓ " + n + "자 — AI가 쓸 수 있습니다" : "최소 " + min + "자 이상 적어 주세요 (지금 " + n + "자) · 무엇을·어디서·어떤 장비로 하는지 적으면 더 정확합니다"; };
      input.addEventListener("input", upd); upd();
    }
  }
  function progress(label, onCancel) {
    if (!document.getElementById("spai-pcss")) { var s = document.createElement("style"); s.id = "spai-pcss"; s.textContent = PCSS; document.head.appendChild(s); }
    var el = document.getElementById("spaiPg");
    if (!el) {
      el = document.createElement("div"); el.id = "spaiPg"; el.className = "spai-pg"; el.setAttribute("role", "status"); el.setAttribute("aria-live", "polite");
      el.innerHTML = '<div class="spai-pg-h"><span class="spai-pg-sp" aria-hidden="true"></span><div class="spai-pg-t"><b></b><span></span></div><button type="button" class="spai-pg-x">취소</button></div><div class="spai-pg-bar ind"><i></i></div>';
      document.body.appendChild(el);
    }
    if (prog && prog.timer) clearInterval(prog.timer);
    var st = { el: el, t0: Date.now(), chars: 0, stage: "보내는 중", label: label || "AI가 작성하는 중", cancel: onCancel };
    el.className = "spai-pg"; el.hidden = false;
    el.querySelector("b").textContent = st.label;
    el.querySelector(".spai-pg-x").hidden = !onCancel;
    el.querySelector(".spai-pg-x").onclick = function () { if (st.cancel) st.cancel(); };
    function draw() {
      var sec = Math.round((Date.now() - st.t0) / 1000), bar = el.querySelector(".spai-pg-bar"), fill = bar.querySelector("i");
      var stage = st.chars ? "답을 받는 중 · " + st.chars.toLocaleString() + "자" : (sec >= 3 ? "AI가 생각하는 중" : "요청 보내는 중");
      el.querySelector(".spai-pg-t span").textContent = stage + " · " + sec + "초" + (st.note ? " · " + st.note : "") + (sec >= 25 && !st.chars ? " — 내용이 많으면 30초 이상 걸릴 수 있습니다" : "");
      if (st.chars) { bar.classList.remove("ind"); fill.style.width = Math.round(25 + 70 * (1 - Math.exp(-st.chars / 1800))) + "%"; }
      else { bar.classList.add("ind"); fill.style.width = ""; }
    }
    st.timer = setInterval(draw, 500); draw();
    st.set = function (n) { st.chars = n; draw(); };
    st.notice = function (t) { st.note = t; draw(); };
    st.end = function (ok, msg) {
      clearInterval(st.timer);
      el.className = "spai-pg " + (ok ? "done" : "err");
      el.querySelector("b").textContent = msg || (ok ? "AI 초안이 준비되었습니다 — 검토 후 고쳐 쓰세요" : "AI 작업을 마치지 못했습니다");
      el.querySelector(".spai-pg-t span").textContent = ok ? Math.round((Date.now() - st.t0) / 1000) + "초 걸렸습니다" : "";
      el.querySelector(".spai-pg-x").hidden = true;
      el.querySelector(".spai-pg-bar").classList.remove("ind"); el.querySelector(".spai-pg-bar i").style.width = ok ? "100%" : "0";
      setTimeout(function () { if (prog === st) { el.hidden = true; prog = null; } }, ok ? 2200 : 4000);
    };
    prog = st;
    return st;
  }

  // ---------- 구조화 입력: 작업 유형·공정·설비·위치·인원·작업 내용·당일 조건 등을 칸으로 받는다
  //   field: {k, label, type: text|area|select|chips, options, required, ph}
  var FCSS = ".spai-f{display:flex;flex-direction:column;gap:4px;margin-top:10px}.spai-f>span{font-weight:700;font-size:13.5px}.spai-f>span em{color:#B42318;font-style:normal;margin-left:3px}" +
    ".spai-f input,.spai-f select,.spai-f textarea{width:100%;box-sizing:border-box;border:1px solid #c8d1dd;border-radius:9px;padding:9px 11px;font-family:inherit;font-size:15px;line-height:1.5;background:#fff;color:#1d2433}" +
    ".spai-f.bad input,.spai-f.bad select,.spai-f.bad textarea{border-color:#B42318;background:#FFF5F4}.spai-f .spai-err{color:#B42318;font-size:12.5px;font-weight:700}" +
    ".spai-chips{display:flex;flex-wrap:wrap;gap:6px}.spai-chips label{display:inline-flex;align-items:center;gap:4px;min-height:34px;padding:4px 11px;border:1px solid #C7D2FE;border-radius:17px;font-size:13.5px;cursor:pointer;background:#F5F7FF}" +
    ".spai-chips input{width:auto;margin:0}.spai-chips label:has(input:checked){background:#3730A3;border-color:#3730A3;color:#fff}" +
    ".spai-fg{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}.spai-fg .wide{grid-column:1/-1}@media (max-width:560px){.spai-fg{grid-template-columns:1fr}}" +
    ".spai-q{border:1px solid #F5D9A8;background:#FFFBF2;border-radius:12px;padding:12px 14px;margin-top:10px}.spai-q h4{margin:0 0 4px;font-size:15px;color:#7a4a00}";
  function fieldCSS() { if (!document.getElementById("spai-fcss")) { var s = document.createElement("style"); s.id = "spai-fcss"; s.textContent = FCSS + XCSS; document.head.appendChild(s); } }
  function fieldsHTML(fields, vals, idp) {
    vals = vals || {}; idp = idp || "spaiF";
    return '<div class="spai-fg">' + fields.map(function (f) {
      var v = vals[f.k] == null ? "" : vals[f.k], id = idp + "_" + f.k, inp;
      if (f.type === "select") inp = '<select id="' + id + '" data-f="' + esc(f.k) + '"><option value="">선택하세요</option>' + f.options.map(function (o) { return "<option" + (o === v ? " selected" : "") + ">" + esc(o) + "</option>"; }).join("") + "</select>";
      else if (f.type === "chips") { var on = String(v).split(/\s*,\s*/); inp = '<div class="spai-chips" data-f="' + esc(f.k) + '" role="group" aria-label="' + esc(f.label) + '">' + f.options.map(function (o) { return '<label><input type="checkbox" value="' + esc(o) + '"' + (on.indexOf(o) >= 0 ? " checked" : "") + ">" + esc(o) + "</label>"; }).join("") + "</div>"; }
      else if (f.type === "area") inp = '<textarea id="' + id + '" data-f="' + esc(f.k) + '" rows="' + (f.rows || 3) + '" maxlength="1500" placeholder="' + esc(f.ph || "") + '">' + esc(v) + "</textarea>";
      else inp = '<input id="' + id + '" type="text" data-f="' + esc(f.k) + '" maxlength="300" value="' + esc(v) + '" placeholder="' + esc(f.ph || "") + '">';
      var wide = f.type === "area" || f.type === "chips" || f.wide;
      return '<label class="spai-f' + (wide ? " wide" : "") + '" data-fw="' + esc(f.k) + '"' + (f.type === "chips" ? "" : ' for="' + id + '"') + "><span>" + esc(f.label) + (f.required ? "<em>*필수</em>" : "") + "</span>" + inp + '<b class="spai-err" hidden></b></label>';
    }).join("") + "</div>";
  }
  function readFields(root, fields) {
    var out = {};
    fields.forEach(function (f) {
      var el = root.querySelector('[data-f="' + f.k + '"]'); if (!el) return;
      if (f.type === "chips") out[f.k] = [].map.call(el.querySelectorAll("input:checked"), function (x) { return x.value; }).join(", ");
      else out[f.k] = String(el.value || "").trim();
    });
    return out;
  }
  // 필수 칸 검사: 빠진 칸을 빨갛게 표시하고 빠진 칸 이름 목록을 돌려준다
  function checkFields(root, fields, vals) {
    var miss = [];
    fields.forEach(function (f) {
      var w = root.querySelector('[data-fw="' + f.k + '"]'); if (!w) return;
      var bad = !!(f.required && String(vals[f.k] || "").replace(/\s/g, "").length < (f.min || 2));
      w.classList.toggle("bad", bad); var er = w.querySelector(".spai-err"); er.hidden = !bad; er.textContent = bad ? "이 칸을 채워야 상황에 맞는 초안을 만들 수 있습니다" : "";
      if (bad) miss.push(f.label);
    });
    return miss;
  }
  // 고쳐 쓰기 시작하면 그 칸의 '필수' 경고를 바로 지운다
  function clearOnInput(root) {
    function f(ev) { var w = ev.target.closest && ev.target.closest(".spai-f.bad"); if (!w) return; w.classList.remove("bad"); var er = w.querySelector(".spai-err"); if (er) er.hidden = true; }
    root.addEventListener("input", f); root.addEventListener("change", f);
  }
  function ctxText(fields, vals) {
    return fields.map(function (f) { var v = String(vals[f.k] || "").trim(); return v ? "- " + f.label + ": " + v : ""; }).filter(Boolean).join("\n");
  }
  // AI 답의 '정보 충분' 판단: 부족하면 일반적인 문서를 만들지 않고 질문을 돌려준다
  var CHECK_SCHEMA = { type: "OBJECT", properties: { enough: { type: "BOOLEAN" }, questions: { type: "ARRAY", items: { type: "STRING" } } }, required: ["enough"] };
  var CHECK_RULE = "먼저 작성자가 준 정보로 이 문서를 그 현장에 맞게 구체적으로 쓸 수 있는지 판단해 _check에 적는다. 작업 종류·장소·설비·작업 내용처럼 문서의 핵심이 빠지거나 모호해서 어느 현장에나 해당하는 일반적인 내용밖에 쓸 수 없으면 _check.enough=false로 하고, _check.questions에 꼭 필요한 질문만 1~4개(짧게, 답하기 쉬운 예시를 괄호로) 쓰고 나머지 칸은 모두 빈 값으로 둔다. 충분하면 _check.enough=true로 하고 questions는 빈 배열로 둔다.";
  var FORCE_RULE = "작성자가 추가 질문 없이 지금 정보로 작성해 달라고 했다. _check.enough=true로 하고, 모르는 부분은 '○○'로 비워 두며 지어내지 않는다.";
  // 문장 품질: 상황 → 위험요인 → 대책을 서로 연결하고, 어디에나 붙는 일반 문구만 쓰지 않는다
  var QUALITY_RULE = "작성 품질 규칙: ⓐ작성자가 준 작업 내용·설비·장소·인원·당일 조건을 문장에 직접 반영한다(예: '야간·우천'이면 조명·미끄럼 대책). ⓑ위험요인은 '무엇을 하다가 → 어떤 원인으로 → 어떤 재해'처럼 구체적으로 쓰고, 예방대책은 그 위험요인의 원인을 직접 없애거나 줄이는 조치로 짝을 맞춘다. ⓒ'안전교육 실시', '보호구 착용', '안전수칙 준수', '주의 철저'처럼 어느 작업에나 붙는 문구만 단독으로 쓰지 않는다 — 보호구는 종류(예: 안전대 체결, 절연장갑)를, 교육은 내용(예: 금형 교체 시 안전블록 사용법)을 적는다. ⓓ대책은 제거·대체 → 공학적(방호장치·차단) → 관리적(절차·허가·감시인) → 보호구 순으로 우선 검토한다. ⓔ업종·작업이 다르면 표현도 달라야 하며 같은 문장을 여러 칸에 반복하지 않는다.";
  var GENERIC = /^(?:안전\s*교육(?:\s*실시|\s*강화)?|보호구\s*(?:착용|지급)(?:\s*철저)?|안전\s*수칙\s*준수|주의\s*(?:철저|요망)?|안전\s*점검(?:\s*실시)?|정리\s*정돈|안전\s*관리\s*철저|관리\s*감독\s*철저)[\s.,·]*$/;
  // 일반 문구만으로 된 칸 찾기: 값 목록에서 해당하는 것만 돌려준다
  function lintGeneric(list) { return (list || []).filter(function (v) { return String(v || "").split(/\s*[,·\/]\s*|\n/).filter(Boolean).every(function (p) { return GENERIC.test(p.trim()); }) && String(v || "").trim(); }); }
  function needMore(r) { var c = r && r._check; return c && c.enough === false ? (c.questions || []).filter(Boolean).slice(0, 4) : null; }

  // 입력 창: 브라우저 기본 prompt() 대신 — 칸별 입력·예시 칩·필수 칸 안내
  //   opt.fields가 있으면 {k: 값} 객체를, 없으면 글 한 줄(문자열)을 돌려준다. 취소하면 null
  function ask(opt) {
    opt = opt || {}; injectCSS(); fieldCSS();
    var fields = opt.fields || [{ k: "_t", label: opt.label || "내용", type: "area", required: true, min: opt.min || 4, ph: opt.placeholder || "" }];
    var vals = opt.fields ? (opt.values || {}) : { _t: opt.value || "" };
    return new Promise(function (done) {
      var ov = document.createElement("div"); ov.className = "spai-ov";
      ov.innerHTML = '<div class="spai-m" role="dialog" aria-modal="true" aria-labelledby="spaiAskT"><h3 id="spaiAskT">' + esc(opt.title || "AI 초안") + "</h3>" +
        (opt.desc ? "<p>" + esc(opt.desc) + "</p>" : "") + (opt.questions && opt.questions.length ? '<div class="spai-q"><h4>AI가 더 알아야 할 것</h4><p style="margin:0;font-size:13.5px">아래 질문에 답하면 그 현장에 맞게 다시 작성합니다. 모르는 칸은 비워 두어도 됩니다.</p></div>' : "") +
        fieldsHTML(fields, vals) + '<div class="spai-askx"></div><p class="spai-note" style="margin-top:10px">회사명·실명·연락처 같은 개인정보는 적지 마세요.</p>' +
        '<div class="spai-row">' + (opt.force ? '<button type="button" class="spai-b" data-x="2" title="추가 질문 없이 지금 정보로 작성합니다(모르는 부분은 ○○로 비움)">' + esc(opt.force) + "</button>" : "") +
        '<button type="button" class="spai-b" data-x="0">취소</button><button type="button" class="spai-b pri" data-x="1">' + esc(opt.ok || "AI 초안 만들기") + "</button></div></div>";
      document.body.appendChild(ov); clearOnInput(ov);
      var main = ov.querySelector('[data-f="' + (opt.exampleFor || fields.filter(function (f) { return f.type === "area" || !f.type || f.type === "text"; })[0].k) + '"]');
      if (main && (opt.examples || []).length) examples(ov.querySelector(".spai-askx"), opt.examples, main, {});
      function close(v) { ov.remove(); document.removeEventListener("keydown", key); done(v); }
      function key(ev) { if (ev.key === "Escape") close(null); }
      document.addEventListener("keydown", key);
      ov.addEventListener("click", function (ev) {
        if (ev.target === ov) return close(null);
        var b = ev.target.closest("[data-x]"); if (!b) return;
        if (b.dataset.x === "0") return close(null);
        var v = readFields(ov, fields);
        if (b.dataset.x === "1" && checkFields(ov, fields, v).length) { var f1 = ov.querySelector(".spai-f.bad input,.spai-f.bad select,.spai-f.bad textarea"); if (f1) f1.focus(); return; }
        if (b.dataset.x === "2") v._force = true;
        close(opt.fields ? v : v._t);
      });
      setTimeout(function () { var f0 = ov.querySelector("input[type=text],select,textarea"); if (f0) f0.focus(); }, 30);
    });
  }
  // 질문 받기 → 답을 '추가 정보' 글로: 사용자가 취소하면 null, '이대로 작성'이면 {force:true}
  function askMore(questions, title) {
    var fields = questions.map(function (q, i) { return { k: "q" + i, label: q, type: "text" }; });
    return ask({ title: title || "추가 정보가 필요합니다", questions: questions, fields: fields, ok: "답하고 다시 만들기", force: "이대로 작성" }).then(function (v) {
      if (!v) return null;
      var t = questions.map(function (q, i) { return v["q" + i] ? "- " + q + " → " + v["q" + i] : ""; }).filter(Boolean).join("\n");
      return { text: t, force: !!v._force || !t };
    });
  }

  // 안내형 작성 흐름: 칸별 입력 → AI → (정보 부족이면) 질문·답 → 다시 AI. 마지막 결과를 돌려주고, 취소하면 null
  //   o: {key, title, desc, fields, values, examples, exampleFor, ok, run(vals, ctx, force) → Promise(AI 결과 객체)}
  function guided(o) {
    var saved = {}; try { saved = JSON.parse(localStorage.getItem("safeplum.aiin." + o.key) || "{}") || {}; } catch (e) { saved = {}; }
    var vals0 = Object.assign({}, saved, o.values || {});
    return ask({ title: o.title, desc: o.desc, fields: o.fields, values: vals0, examples: o.examples, exampleFor: o.exampleFor, ok: o.ok }).then(function (v) {
      if (!v) return null;
      try { localStorage.setItem("safeplum.aiin." + o.key, JSON.stringify(v)); } catch (e) {}
      var extra = "";
      function loop(force) {
        var ctx = "[작업 정보]\n" + ctxText(o.fields, v) + (extra ? "\n[AI 질문에 대한 답]\n" + extra : "");
        return o.run(v, ctx, force).then(function (r) {
          var q = force ? null : needMore(r);
          if (!q || !q.length) return { result: r, values: v };
          return askMore(q, (o.title || "AI 초안") + " — 추가 정보가 필요합니다").then(function (ans) {
            if (!ans) return null;
            if (ans.text) extra += (extra ? "\n" : "") + ans.text;
            return loop(ans.force);
          });
        });
      }
      return loop(false);
    });
  }

  // 한도(429)·서버 오류(5xx)·연결 끊김·응답 지연은 잠깐 쉬었다 한 번 더, 모델 없음(404)은 모델을 다시 골라 한 번 더 시도한다
  function gen(o, wantJSON) {
    var sc = scrub(o.prompt), ss = scrub(o.system || ""), pg = null;
    o = Object.assign({}, o, { prompt: sc.text, system: o.system ? ss.text : o.system }); lastScrub = sc.n + ss.n;
    if (!o.quiet) pg = progress(o.label, function () { if (pg.abort) pg.abort("cancel"); });
    function run(attempt) {
      return gen1(o, wantJSON, pg).catch(function (e) {
        var retry = attempt < 1 && ["quota", "server", "network", "timeout", "model", "parse", "empty"].indexOf(e.code) >= 0;
        if (!retry) throw e;
        if (pg) { pg.notice(e.code === "timeout" ? "응답이 늦어 한 번 더 시도합니다" : "한 번 더 시도합니다"); pg.set(0); }
        var next = e.code === "model" ? pickModel(true) : wait(e.code === "quota" ? 4000 : e.code === "parse" || e.code === "empty" ? 0 : 1500);
        return next.then(function () { return run(attempt + 1); });
      });
    }
    return run(0).then(function (r) { if (pg) pg.end(true); return r; }, function (e) {
      if (pg) pg.end(false, e.code === "cancel" ? "AI 작업을 취소했습니다" : e.message);
      throw e;
    });
  }

  // 생각(thinking) 수준: 최신 flash 모델은 기본으로 깊게 생각해 서식 초안에 1분 넘게 걸리기도 한다 → '낮게'로 요청.
  // 이 설정을 받지 않는 모델(오류 400)은 기억해 두고 설정 없이 보낸다.
  var K_NOTHINK = "safeplum.ai.nothink";
  function thinkOK(model) { return sget(localStorage, K_NOTHINK).split(",").indexOf(model) < 0; }
  function noThink(model) { var l = sget(localStorage, K_NOTHINK).split(",").filter(Boolean); if (l.indexOf(model) < 0) l.push(model); sset(localStorage, K_NOTHINK, l.slice(-8).join(",")); }

  // 답을 조각(SSE)으로 받는다: 글자가 들어오는 동안은 기다리고, 일정 시간 아무것도 오지 않을 때만 멈춘다.
  function stream(model, body, o, pg) {
    var key = getKey();
    if (!key) return Promise.reject(AIError("nokey", "AI 키가 설정되지 않았습니다."));
    var ctl = typeof AbortController === "function" ? new AbortController() : null, why = "", timer = null;
    var FIRST = o.timeout || 90000, IDLE = 45000, total = Date.now();
    function arm(ms) { if (!ctl) return; clearTimeout(timer); timer = setTimeout(function () { why = "timeout"; ctl.abort(); }, ms); }
    if (pg) pg.abort = function (w) { why = w || "cancel"; if (ctl) ctl.abort(); };
    arm(FIRST);
    var text = "", finish = "", blocked = "";
    function eat(line) {
      if (line.indexOf("data:") !== 0) return;
      var j; try { j = JSON.parse(line.slice(5).trim()); } catch (e) { return; }
      if (j.error) throw explain(j.error.code || 500, j);
      if (j.promptFeedback && j.promptFeedback.blockReason) blocked = j.promptFeedback.blockReason;
      var c = (j.candidates || [])[0];
      if (c) {
        (c.content && c.content.parts || []).forEach(function (p) { if (p.text && !p.thought) text += p.text; });
        if (c.finishReason) finish = c.finishReason;
      }
    }
    return fetch(API + "models/" + encodeURIComponent(model) + ":streamGenerateContent?alt=sse", {
      method: "POST", headers: { "x-goog-api-key": key, "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: ctl ? ctl.signal : undefined
    }).then(function (res) {
      if (!res.ok) return res.json().catch(function () { return {}; }).then(function (b) { throw explain(res.status, b); });
      arm(IDLE);
      if (!res.body || !res.body.getReader || typeof TextDecoder !== "function") return res.text().then(function (t) { t.split(/\r?\n/).forEach(eat); });
      var rd = res.body.getReader(), dec = new TextDecoder("utf-8"), buf = "";
      function pump() {
        return rd.read().then(function (r) {
          if (r.done) { buf += dec.decode(); buf.split(/\r?\n/).forEach(eat); return; }
          arm(IDLE);
          buf += dec.decode(r.value, { stream: true });
          var lines = buf.split(/\r?\n/); buf = lines.pop();
          lines.forEach(eat);
          if (pg) pg.set(text.length);
          return pump();
        });
      }
      return pump();
    }).then(function () {
      clearTimeout(timer);
      return { text: text, finish: finish, blocked: blocked, ms: Date.now() - total };
    }, function (err) {
      clearTimeout(timer);
      if (err && err.code) throw err;
      if (err && err.name === "AbortError") {
        if (why === "cancel") throw AIError("cancel", "AI 작업을 취소했습니다.");
        throw AIError("timeout", "AI 응답이 너무 오래 걸려 중단했습니다. 다시 시도해 주세요.", "모델 " + model + " · " + Math.round((Date.now() - total) / 1000) + "초 동안 " + (text ? "답이 중간에 멈춤" : "답이 시작되지 않음"));
      }
      throw AIError("network", "인터넷 연결을 확인해 주세요(Google AI 서버에 연결하지 못했습니다).");
    });
  }
  function gen1(o, wantJSON, pg) {
    return pickModel().then(function (model) {
      var body = {
        contents: [{ role: "user", parts: [{ text: o.prompt }] }],
        generationConfig: { temperature: o.temperature == null ? 0.4 : o.temperature, maxOutputTokens: o.maxTokens || 4096 }
      };
      if (thinkOK(model)) body.generationConfig.thinkingConfig = { thinkingLevel: "low" };
      if (o.system) body.systemInstruction = { parts: [{ text: o.system }] };
      if (wantJSON) { body.generationConfig.responseMimeType = "application/json"; if (o.schema) body.generationConfig.responseSchema = o.schema; }
      function send() {
        return stream(model, body, o, pg).catch(function (e) {
          // 생각 수준 설정을 모르는 모델: 설정을 빼고 바로 다시 보낸다(재시도 횟수에 넣지 않음)
          if (body.generationConfig.thinkingConfig && (e.code === "other" || e.code === "key") && /thinking/i.test(e.detail || "")) {
            noThink(model); delete body.generationConfig.thinkingConfig; return stream(model, body, o, pg);
          }
          throw e;
        });
      }
      return send().then(function (r) { writeState("ok"); return r; }, function (e) {
        if (e.code === "model") { sset(localStorage, K_MODEL, ""); }
        if (["key", "network", "quota", "server", "model", "timeout"].indexOf(e.code) >= 0) writeState(e.code, e.detail);
        else if (e.code !== "nokey" && e.code !== "cancel") writeState("other", e.message + (e.detail ? " — " + e.detail : ""));
        throw e;
      });
    }).then(function (r) {
      if (r.blocked) throw AIError("blocked", "AI가 이 요청에 답하지 않았습니다(안전 정책). 표현을 바꿔 다시 시도해 주세요.");
      var t = r.text;
      if (!t) throw AIError("empty", "AI가 빈 답을 보냈습니다. 다시 시도해 주세요.", r.finish);
      if (!wantJSON) return t;
      try { return JSON.parse(t.replace(/^```(?:json)?\s*|\s*```$/g, "")); }
      catch (e) {
        if (r.finish === "MAX_TOKENS") throw AIError("parse", "AI 답이 너무 길어 중간에 끊겼습니다. 상황을 조금 짧게 적거나 '빈 칸만 채우기'로 다시 시도해 주세요.", r.finish);
        throw AIError("parse", "AI 답을 해석하지 못했습니다. 다시 시도해 주세요.", r.finish);
      }
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

  // ---------- 화면: AI 키 설정 안내(처음 쓰는 사람은 단계별로, 이미 설정한 사람은 관리 화면으로)
  var CSS2 = ".spai-steps{display:flex;gap:4px;margin:2px 0 12px;padding:0;list-style:none;counter-reset:s}" +
    ".spai-steps li{flex:1;text-align:center;font-size:11.5px;color:#94A3B8;border-top:3px solid #E2E8F0;padding-top:6px}" +
    ".spai-steps li.on{color:#17365D;font-weight:800;border-color:#17365D}.spai-steps li.done{color:#05603a;border-color:#12B76A}" +
    ".spai-pw{display:flex;gap:6px;align-items:center}.spai-pw input{flex:1}" +
    ".spai-eye{flex:none;height:44px;margin-top:4px;padding:0 12px;border:1px solid #c8d1dd;border-radius:9px;background:#fff;font-weight:700;font-size:13px;cursor:pointer}" +
    ".spai-badge{display:inline-block;font-size:12px;font-weight:800;border-radius:6px;padding:1px 8px;background:#EEF2F6;color:#334155}" +
    ".spai-badge.ok{background:#DCFCE7;color:#05603A}.spai-badge.err{background:#FEE4E2;color:#B42318}.spai-badge.set{background:#FEF3C7;color:#92400E}" +
    ".spai-box{border:1px solid #E2E8F0;border-radius:10px;padding:10px 12px;margin:8px 0;background:#F8FAFC}" +
    ".spai-det{font-size:12px;color:#667085;word-break:break-all;margin-top:4px}" +
    ".spai-ul{margin:6px 0 6px 18px;padding:0}.spai-ul li{margin:3px 0}";
  function badgeCls(c) { return c === "ok" ? "ok" : c === "set" ? "set" : c === "none" ? "" : "err"; }
  function openSettings(opt) {
    injectCSS();
    if (!document.getElementById("spai-css2")) { var st2 = document.createElement("style"); st2.id = "spai-css2"; st2.textContent = CSS2; document.head.appendChild(st2); }
    opt = opt || {};
    return new Promise(function (resolve) {
      var ov = document.createElement("div"); ov.className = "spai-ov"; ov.setAttribute("role", "dialog"); ov.setAttribute("aria-modal", "true"); ov.setAttribute("aria-label", "AI 키 설정");
      var box = document.createElement("div"); box.className = "spai-m"; ov.appendChild(box); document.body.appendChild(ov);
      var STEPS = ["기능 소개", "키 준비", "키 입력", "연결 확인", "질문 시작"];
      var prevFocus = document.activeElement;
      function close(v) { ov.remove(); document.removeEventListener("keydown", onKey); fire(); try { if (prevFocus && prevFocus.focus) prevFocus.focus(); } catch (e) {} resolve(v); }
      function onKey(e) { if (e.key === "Escape") close(!!getKey()); }
      document.addEventListener("keydown", onKey);
      ov.addEventListener("click", function (e) { if (e.target === ov) close(!!getKey()); });
      function steps(i) { return '<ol class="spai-steps" aria-label="설정 단계">' + STEPS.map(function (t, j) { return '<li class="' + (j < i ? "done" : j === i ? "on" : "") + '"' + (j === i ? ' aria-current="step"' : "") + ">" + (j + 1) + ". " + t + "</li>"; }).join("") + "</ol>"; }
      function btns(h) { return '<div class="spai-row">' + h + "</div>"; }
      function focus(sel) { setTimeout(function () { var el = box.querySelector(sel); if (el) el.focus(); }, 30); }
      // 1. 기능 소개
      function s1() {
        box.innerHTML = '<h3>AI 기능 처음 설정하기</h3>' + steps(0) +
          "<p><b>" + esc(opt.feature || "SafePlum AI 기능") + "</b>은 현행 산업안전보건 법령 조문(필요하면 고용노동부 질의회시)을 먼저 찾아, 그 자료를 근거로 AI가 답하거나 서식 초안을 만드는 기능입니다.</p>" +
          '<div class="spai-box"><b>이 기능은 Google Gemini API 키가 필요합니다.</b><ul class="spai-ul"><li>키는 구글 계정으로 <b>무료로 발급</b>받을 수 있습니다(사용 한도는 Google 정책을 따릅니다).</li><li>키는 <b>이 브라우저에만</b> 저장되고 SafePlum 서버로 보내지 않습니다.</li><li>AI를 쓸 때만 질문과 찾은 조문이 Google로 바로 전송됩니다.</li></ul></div>' +
          '<p style="font-size:13px;color:#667085">서식 작성·계산 도구는 키 없이도 모두 쓸 수 있습니다. AI 버튼만 키가 필요합니다.</p>' +
          btns('<button type="button" class="spai-b" data-x>나중에</button><button type="button" class="spai-b pri" data-n>다음 — 키 준비</button>');
        box.querySelector("[data-x]").onclick = function () { close(false); }; box.querySelector("[data-n]").onclick = s2; focus("[data-n]");
      }
      // 2. 키 준비
      function s2() {
        box.innerHTML = '<h3>API 키 준비</h3>' + steps(1) +
          '<ol class="spai-ul"><li><a class="spai-a" href="' + KEY_GUIDE + '" target="_blank" rel="noopener">Google AI Studio API 키 페이지 ↗</a>를 새 창에서 엽니다(Google 공식 페이지).</li><li>구글 계정으로 로그인한 뒤 <b>「API 키 만들기(Create API key)」</b>를 누릅니다.</li><li>만들어진 키 옆의 <b>복사</b> 버튼을 누릅니다.</li><li>이 창으로 돌아와 「다음」을 누르고 붙여 넣습니다.</li></ol>' +
          '<div class="spai-note"><b>입력 주의</b> — 무료 키로 보낸 내용은 Google이 서비스 개선에 쓸 수 있고 사람이 검토할 수 있습니다(Google 약관). 실명·연락처·주민번호 등 개인정보와 회사 기밀은 넣지 마세요.</div>' +
          btns('<button type="button" class="spai-b" data-b>이전</button><button type="button" class="spai-b pri" data-n>다음 — 키 입력</button>');
        box.querySelector("[data-b]").onclick = s1; box.querySelector("[data-n]").onclick = function () { s3(""); }; focus("[data-n]");
      }
      // 3. 키 입력(+보기/숨기기) → 4. 연결 확인
      function s3(err, typed) {
        var k = typed != null ? typed : getKey();
        box.innerHTML = '<h3>API 키 입력</h3>' + steps(2) +
          '<label for="spaiKey">API 키</label><div class="spai-pw"><input type="password" id="spaiKey" autocomplete="off" spellcheck="false" placeholder="Google AI Studio에서 복사한 키 붙여 넣기" value="' + esc(k) + '"><button type="button" class="spai-eye" id="spaiEye" aria-pressed="false" aria-controls="spaiKey">보기</button></div>' +
          '<label class="spai-chk"><input type="checkbox" id="spaiRem"' + (remembered() ? " checked" : "") + '><span>이 기기에 기억하기 <small style="color:#667">(끄면 브라우저 창을 닫을 때 지워짐 · 공용 PC에서는 끄세요)</small></span></label>' +
          '<div class="spai-st' + (err ? " err" : "") + '" id="spaiSt" aria-live="polite">' + (err || "") + "</div>" +
          btns('<button type="button" class="spai-b" data-b>이전</button><button type="button" class="spai-b" data-x>취소(저장 안 함)</button><button type="button" class="spai-b pri" id="spaiOk">저장하고 연결 확인</button>');
        var inp = box.querySelector("#spaiKey"), eye = box.querySelector("#spaiEye"), stl = box.querySelector("#spaiSt"), ok = box.querySelector("#spaiOk");
        eye.onclick = function () { var show = inp.type === "password"; inp.type = show ? "text" : "password"; eye.textContent = show ? "숨기기" : "보기"; eye.setAttribute("aria-pressed", String(show)); inp.focus(); };
        box.querySelector("[data-b]").onclick = getKey() ? manage : s2;
        box.querySelector("[data-x]").onclick = function () { close(!!getKey()); };
        ok.onclick = function () {
          // 공백·줄바꿈·따옴표·보이지 않는 문자는 지우고, 실제 유효성은 연결 확인(Google 응답)으로 판단한다(키 형식은 Google이 바꿀 수 있어 좁게 막지 않는다)
          var v = inp.value.replace(/[\s​-‍﻿"'`]/g, ""); inp.value = v;
          if (!/^[\x21-\x7E]{20,300}$/.test(v)) { stl.className = "spai-st err"; stl.textContent = "키 형식이 맞지 않습니다. Google AI Studio에서 복사한 키를 그대로 붙여 넣어 주세요(앞뒤 공백·줄바꿈 없이)."; inp.focus(); return; }
          var prevS = sget(sessionStorage, K_KEY), prevL = sget(localStorage, K_KEY), prevState = sget(localStorage, K_STATE);
          setKey(v, box.querySelector("#spaiRem").checked);
          s4(prevS, prevL, prevState, v);
        };
        inp.addEventListener("keydown", function (e) { if (e.key === "Enter") ok.click(); });
        focus("#spaiKey");
      }
      function s4(prevS, prevL, prevState, typed) {
        box.innerHTML = '<h3>연결 확인</h3>' + steps(3) + '<p class="spai-st" aria-live="polite"><span class="spai-busy">Google AI 서버에 연결해 키를 확인하는 중…</span></p>';
        pickModel(true).then(function (m) {
          sset(localStorage, K_AGREE, "1"); writeState("ok");
          box.innerHTML = '<h3>연결되었습니다</h3>' + steps(4) +
            '<p><span class="spai-badge ok">연결 확인됨</span> 사용 모델: <b>' + esc(m) + "</b></p>" +
            '<p>이제 AI 기능을 쓸 수 있습니다. 키를 바꾸거나 지우려면 언제든 「AI 키 설정」을 누르세요.</p>' +
            btns('<button type="button" class="spai-b pri" data-go>' + esc(opt.startLabel || "시작하기") + "</button>");
          box.querySelector("[data-go]").onclick = function () { close(true); }; focus("[data-go]");
        }, function (e) {
          // 실패한 키는 저장하지 않고 이전 상태로 되돌린다
          sset(sessionStorage, K_KEY, prevS); sset(localStorage, K_KEY, prevL); sset(localStorage, K_STATE, prevState); fire();
          var t = STATUS_TEXT[e.code] || STATUS_TEXT.other;
          s3("<b>" + esc(t[0]) + "</b> — " + esc(t[1]) + (e.detail ? '<div class="spai-det">Google 응답: ' + esc(String(e.detail).slice(0, 200)) + "</div>" : "") + '<div class="spai-det">입력한 키는 저장하지 않았습니다.</div>', typed);
        });
      }
      // 이미 설정한 사람: 상태·관리
      function manage() {
        var st = statusLabel();
        box.innerHTML = '<h3>AI 키 설정</h3>' +
          '<div class="spai-box"><p style="margin:0">상태 <span class="spai-badge ' + badgeCls(st.code) + '">' + esc(st.label) + "</span></p>" +
          '<p style="margin:6px 0 0;font-size:13.5px">' + esc(st.help) + "</p>" + (st.detail && st.code !== "ok" ? '<div class="spai-det">상세: ' + esc(st.detail) + "</div>" : "") +
          (st.at ? '<div class="spai-det">마지막 확인 ' + esc(new Date(st.at).toLocaleString("ko-KR")) + "</div>" : "") + "</div>" +
          "<p>저장된 키: <code>" + esc(maskKey(getKey())) + "</code> · 저장 위치: " + (remembered() ? "이 기기(브라우저)에 기억" : "이 창을 닫을 때까지만") + (sget(localStorage, K_MODEL) ? " · 모델 " + esc(sget(localStorage, K_MODEL)) : "") + "</p>" +
          '<p style="font-size:13px;color:#667085">키는 이 브라우저에만 있고 SafePlum 서버로 보내지 않습니다. AI 요청은 Google(generativelanguage.googleapis.com)로 바로 갑니다.</p>' +
          '<div class="spai-st" id="spaiSt" aria-live="polite"></div>' +
          btns('<button type="button" class="spai-b red" data-del>키 지우기</button><button type="button" class="spai-b" data-chg>키 바꾸기</button><button type="button" class="spai-b" data-test>연결 다시 확인</button><button type="button" class="spai-b pri" data-x>닫기</button>');
        var stl = box.querySelector("#spaiSt");
        box.querySelector("[data-x]").onclick = function () { close(true); };
        box.querySelector("[data-chg]").onclick = function () { s3(""); };
        box.querySelector("[data-del]").onclick = function () { if (!window.confirm("이 브라우저에 저장된 AI 키를 지울까요? AI 기능을 쓰려면 다시 넣어야 합니다.")) return; setKey(""); close(false); };
        box.querySelector("[data-test]").onclick = function () {
          var b = this; b.disabled = true; stl.className = "spai-st"; stl.innerHTML = '<span class="spai-busy">연결 확인 중…</span>';
          pickModel(true).then(function () { writeState("ok"); manage(); }, function (e) { writeState(["key", "network", "quota", "server", "model", "timeout"].indexOf(e.code) >= 0 ? e.code : "other", e.detail || e.message); manage(); });
        };
        focus("[data-x]");
      }
      if (getKey()) manage(); else if (opt.skipIntro) s2(); else s1();
    });
  }
  function ensureKey(opt) { return getKey() ? Promise.resolve(true) : openSettings(opt); }

  // ---------- 근거 찾기 1: 현행 조문(assets/lawai.json, 사이트 빌드 때 국가법령정보센터 원문으로 만든 묶음)
  var JOSA = /(으로써|으로서|에서는|에게는|으로는|이라도|까지는|에서|에게|으로|부터|까지|이나|이란|이라|하고|해야|하나요|인가요|있나요|되나요|합니까|입니까|해요|은|는|이|가|을|를|의|에|와|과|도|만|로|요)$/;
  function terms(s) {
    var out = [];
    String(s || "").replace(/[^가-힣A-Za-z0-9·]+/g, " ").split(/\s+/).forEach(function (w) {
      w = w.replace(/·/g, ""); var b = w;
      for (var i = 0; i < 2; i++) b = b.replace(JOSA, "");
      if (b.length >= 2 && out.indexOf(b) < 0) out.push(b);
    });
    return out;
  }
  function count(hay, t) { var n = 0, i = hay.indexOf(t); while (i >= 0 && n < 4) { n++; i = hay.indexOf(t, i + t.length); } return n; }
  var LAWNAME = { "산업안전보건법": "act", "산안법": "act", "법": "act", "시행령": "yeong", "영": "yeong", "시행규칙": "rule", "규칙": "rule", "산업안전보건기준에관한규칙": "krule", "안전보건규칙": "krule", "기준규칙": "krule", "중대재해처벌법": "sapa", "중처법": "sapa", "중대재해처벌법시행령": "sapa_dec", "중처법시행령": "sapa_dec" };
  // "안전보건규칙 제657조~제659조 · 시행규칙 제25조" 같은 근거 문구 → [["krule","제657조"],…]
  function parseRefs(txt) {
    var out = [], cur = "act";
    String(txt || "").replace(/\s+/g, "").replace(/(산업안전보건기준에관한규칙|중대재해처벌법시행령|중처법시행령|산업안전보건법|중대재해처벌법|안전보건규칙|기준규칙|시행령|시행규칙|산안법|중처법)|제(\d+)조(?:의(\d+))?(?:[~∼-]제?(\d+)조)?/g, function (m, nm, a, b, to) {
      if (nm) { cur = LAWNAME[nm] || cur; if (/시행령/.test(nm) && /중대|중처/.test(nm)) cur = "sapa_dec"; return; }
      var from = +a, end = to ? Math.min(+to, from + 6) : from;
      for (var n = from; n <= end; n++) out.push([cur, "제" + n + "조" + (n === from && b ? "의" + b : "")]);
    });
    return out;
  }
  var LAW = { db: null, p: null };
  function lawDB() {
    if (LAW.db) return Promise.resolve(LAW.db);
    if (LAW.p) return LAW.p;
    LAW.p = fetch(ROOT + "assets/lawai.json", { cache: "force-cache" }).then(function (r) {
      if (!r.ok) throw AIError("data", "조문 자료를 불러오지 못했습니다(" + r.status + "). 새로고침해 주세요.");
      return r.json();
    }).then(function (d) {
      d.arts.forEach(function (a) { a.push((a[2] + " " + a[3]).replace(/\s+/g, "")); a.push(a[2].replace(/\s+/g, "")); });
      LAW.db = d; return d;
    }).catch(function (e) { LAW.p = null; throw e; });
    return LAW.p;
  }
  function joAnchor(jo) { var m = /제(\d+)조(?:의(\d+))?/.exec(jo || ""); return m ? "j" + m[1] + (m[2] ? "-" + m[2] : "") : ""; }
  function lawItem(d, i) {
    var a = d.arts[i], l = d.laws[a[0]], an = joAnchor(a[1]);
    return { i: i, key: l.key, law: l.short, jo: a[1], title: a[2], text: a[3],
      label: l.short + " " + a[1] + (a[2] && a[2] !== "과태료" ? "(" + a[2] + ")" : ""),
      url: l.key === "pen" ? ROOT + "tools/penalty/" : ROOT + "laws/" + l.key + "/" + (an ? "#" + an : "") };
  }
  function lawSearch(q, opt) {
    opt = opt || {};
    return lawDB().then(function (d) {
      var qt = terms(q), kt = [];
      (opt.keywords || []).forEach(function (k) { k = String(k).replace(/\s+/g, ""); if (k.length >= 2 && kt.indexOf(k) < 0) kt.push(k); });
      var direct = []; String(q).replace(/제\s*(\d+)\s*조(?:\s*의\s*(\d+))?/g, function (_, a, b) { direct.push("제" + a + "조" + (b ? "의" + b : "")); });
      var pref = {}; (opt.laws || []).forEach(function (k) { pref[k] = 1; });
      var refs = {}; (opt.refs || []).forEach(function (r) { refs[r[0] + "|" + r[1]] = 1; });
      var scored = [];
      d.arts.forEach(function (a, i) {
        var hay = a[4], ttl = a[5], s = 0, hit = 0, key = d.laws[a[0]].key;
        kt.forEach(function (t) { var n = count(hay, t); if (n) { hit++; s += 3 + n * 2 + (ttl.indexOf(t) >= 0 ? 8 : 0); } });
        qt.forEach(function (t) { var n = count(hay, t); if (n) { hit++; s += 1 + n + (ttl.indexOf(t) >= 0 ? 4 : 0); } });
        if (refs[key + "|" + a[1]]) s += 60;   // 서식·도구의 근거 조문은 맨 앞에
        if (!s) return;
        if (direct.indexOf(a[1]) >= 0) s += 30;
        if (pref[key]) s *= 1.3;
        s *= 1 + Math.min(hit, 6) * 0.15;
        s /= 1 + Math.max(0, a[3].length - 1500) / 6000;
        scored.push([s, i]);
      });
      scored.sort(function (x, y) { return y[0] - x[0]; });
      return scored.slice(0, opt.k || 14).map(function (x) { return lawItem(d, x[1]); });
    });
  }
  function lawCtx(items, max) { return items.map(function (it, n) { return "[" + (n + 1) + "] " + it.label + "\n" + it.text.slice(0, max || 1400); }).join("\n\n"); }

  // ---------- 근거 찾기 2: 고용노동부 질의회시(laws/qa/list.json 으로 고르고, 고른 몇 건만 본문을 받아 온다)
  var GQ = { list: null, p: null, cache: {} };
  function gqList() {
    if (GQ.list) return Promise.resolve(GQ.list);
    if (GQ.p) return GQ.p;
    GQ.p = fetch(ROOT + "laws/qa/list.json", { cache: "force-cache" }).then(function (r) { if (!r.ok) throw AIError("data", "질의회시 목록을 불러오지 못했습니다."); return r.json(); })
      .then(function (L) { L.forEach(function (x) { x.push((x[1] + " " + x[4]).replace(/\s+/g, "")); }); GQ.list = L; return L; })
      .catch(function (e) { GQ.p = null; throw e; });
    return GQ.p;
  }
  function gqBody(id) {
    if (GQ.cache[id]) return Promise.resolve(GQ.cache[id]);
    return fetch(ROOT + "laws/qa/" + id + "/", { cache: "force-cache" }).then(function (r) { return r.ok ? r.text() : ""; }).then(function (h) {
      var doc = new DOMParser().parseFromString(h || "", "text/html");
      var q = doc.querySelector(".gq-q .gq-tx"), a = doc.querySelector(".gq-a .gq-tx");
      function txt(el) { return el ? [].map.call(el.querySelectorAll("p"), function (p) { return p.textContent.trim(); }).filter(Boolean).join("\n") : ""; }
      var o = { q: txt(q), a: txt(a) };
      GQ.cache[id] = o; return o;
    }).catch(function () { return { q: "", a: "" }; });
  }
  function gqSearch(q, opt) {
    opt = opt || {};
    return gqList().then(function (L) {
      var qt = terms(q), kt = [];
      (opt.keywords || []).forEach(function (k) { k = String(k).replace(/\s+/g, ""); if (k.length >= 2 && kt.indexOf(k) < 0) kt.push(k); });
      var sc = [];
      L.forEach(function (x, i) {
        var hay = x[5], tt = x[1].replace(/\s+/g, ""), s = 0, hit = 0;
        kt.forEach(function (t) { if (hay.indexOf(t) >= 0) { hit++; s += 4 + (tt.indexOf(t) >= 0 ? 5 : 0); } });
        qt.forEach(function (t) { if (hay.indexOf(t) >= 0) { hit++; s += 2 + (tt.indexOf(t) >= 0 ? 3 : 0); } });
        if (!s || hit < Math.min(2, kt.length + qt.length)) return;
        s *= 1 + Math.min(hit, 6) * 0.2;
        if (x[2] && x[2] >= "2020-01-16") s *= 1.25;   // 전부개정 이후 회신을 앞에
        sc.push([s, i]);
      });
      sc.sort(function (a, b) { return b[0] - a[0]; });
      var top = sc.slice(0, opt.k || 4).map(function (z) { return L[z[1]]; });
      return Promise.all(top.map(function (x) { return gqBody(x[0]).then(function (b) {
        return { id: x[0], title: x[1], date: x[2], cat: x[3], old: !!(x[2] && x[2] < "2020-01-16"), q: b.q, a: b.a, url: ROOT + "laws/qa/" + x[0] + "/" };
      }); }));
    });
  }

  window.SPAI = {
    hasKey: function () { return !!getKey(); },
    ensureKey: ensureKey,
    openSettings: openSettings,
    json: function (o) { return ensureKey().then(function (ok) { if (!ok) throw AIError("nokey", "AI 키가 설정되지 않았습니다."); return gen(o, true); }); },
    text: function (o) { return ensureKey().then(function (ok) { if (!ok) throw AIError("nokey", "AI 키가 설정되지 않았습니다."); return gen(o, false); }); },
    model: function () { return sget(localStorage, K_MODEL); },
    status: function () { return statusLabel(); },
    esc: esc,
    css: injectCSS,
    root: ROOT,
    scrub: function (t) { return scrub(t).text; },
    lastScrub: function () { return lastScrub; },
    progress: progress,
    examples: examples,
    ask: ask,
    askMore: askMore,
    guided: guided,
    fields: { html: fieldsHTML, read: readFields, check: checkFields, text: ctxText, css: fieldCSS, live: clearOnInput },
    check: { schema: CHECK_SCHEMA, rule: CHECK_RULE, force: FORCE_RULE, need: needMore, quality: QUALITY_RULE, generic: lintGeneric },
    law: { db: lawDB, search: lawSearch, refs: parseRefs, ctx: lawCtx, terms: terms },
    govqa: { search: gqSearch },
    NOTICE: "AI가 만든 초안입니다. 현장 상황에 맞는지 반드시 검토·수정한 뒤 사용하세요."
  };
})();
