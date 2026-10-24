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
  var K_KEY = "safeplum.ai.key", K_MODEL = "safeplum.ai.model", K_AGREE = "safeplum.ai.agree";
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
  }
  function maskKey(k) { return k ? k.slice(0, 4) + "…" + k.slice(-4) : ""; }

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
  // 한도(429)·서버 오류(5xx)·연결 끊김은 잠깐 쉬었다 한 번 더, 모델 없음(404)은 모델을 다시 골라 한 번 더 시도한다
  function gen(o, wantJSON, attempt) {
    attempt = attempt || 0;
    if (!attempt) { var sc = scrub(o.prompt), ss = scrub(o.system || ""); o = Object.assign({}, o, { prompt: sc.text, system: o.system ? ss.text : o.system }); lastScrub = sc.n + ss.n; }
    return gen1(o, wantJSON).catch(function (e) {
      if (attempt >= 1) throw e;
      if (e.code === "quota" || e.code === "server" || e.code === "network") return wait(e.code === "quota" ? 4000 : 2000).then(function () { return gen(o, wantJSON, attempt + 1); });
      if (e.code === "model") return pickModel(true).then(function () { return gen(o, wantJSON, attempt + 1); });
      if (e.code === "parse" || e.code === "empty") return gen(o, wantJSON, attempt + 1);
      throw e;
    });
  }
  function gen1(o, wantJSON) {
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
        '<label>API 키<input type="password" id="spaiKey" autocomplete="off" spellcheck="false" placeholder="Google AI Studio에서 복사한 키" value="' + esc(k) + '"></label>' +
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
        // 공백·줄바꿈·따옴표·보이지 않는 문자는 지우고, 실제 유효성은 아래 연결 확인(Google 응답)으로 판단한다.
        // 키 형식은 Google이 바꿀 수 있으므로(예: AIza…, 점이 들어간 새 형식) 글자 종류를 좁게 막지 않는다.
        var v = inp.value.replace(/[\s\u200B-\u200D\uFEFF"'`]/g, ""); inp.value = v;
        if (!/^[\x21-\x7E]{20,300}$/.test(v)) { st.className = "spai-st err"; st.textContent = "키 형식이 맞지 않습니다. Google AI Studio에서 복사한 키를 그대로 붙여 넣어 주세요."; return; }
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
    esc: esc,
    css: injectCSS,
    root: ROOT,
    scrub: function (t) { return scrub(t).text; },
    lastScrub: function () { return lastScrub; },
    law: { db: lawDB, search: lawSearch, refs: parseRefs, ctx: lawCtx, terms: terms },
    govqa: { search: gqSearch },
    NOTICE: "AI가 만든 초안입니다. 현장 상황에 맞는지 반드시 검토·수정한 뒤 사용하세요."
  };
})();
