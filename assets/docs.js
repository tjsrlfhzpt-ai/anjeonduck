/* SafePlum 문서 공통 모듈 — 결재란 · 인쇄용 서명 이미지 · 사진 첨부 · 내 데이터 백업
   서버 없이 이 기기(브라우저)에만 저장한다.
   - 결재란/서명: localStorage "safetake.appr.*"
   - 사진: IndexedDB "safetake" / store "photos" (용량이 커서 localStorage 대신)
   - 백업: "safetake." 로 시작하는 localStorage 전부 + 사진을 JSON 하나로 내보내고 불러온다. */
(function () {
  "use strict";
  if (window.ADoc) return;
  var P = "safetake.";
  // 예전 이름으로 저장된 입력값을 새 이름으로 한 번 옮긴다(같은 키가 이미 있으면 건드리지 않음)
  try {
    var OLD = ["anjeon", "duck."].join("");
    if (!localStorage.getItem(P + "migrated")) {
      var mv = [];
      for (var mi = 0; mi < localStorage.length; mi++) { var mk = localStorage.key(mi); if (mk && mk.indexOf(OLD) === 0) mv.push(mk); }
      mv.forEach(function (k) { var nk = P + k.slice(OLD.length); if (localStorage.getItem(nk) === null) localStorage.setItem(nk, localStorage.getItem(k)); localStorage.removeItem(k); });
      localStorage.setItem(P + "migrated", "1");
    }
  } catch (e) { /* 저장소를 못 쓰는 환경 */ }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function lget(k, d) { try { var v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }
  function lset(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { toast("이 브라우저에 저장하지 못했습니다(저장 공간 부족 또는 사생활 보호 모드)."); return false; } }
  function pad(n) { return ("0" + n).slice(-2); }
  function ymd(d) { d = d || new Date(); return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }

  // ---------- 공통 스타일(어느 페이지에 붙어도 같은 모양)
  var CSS = "" +
    ".ad-appr{border-collapse:collapse;font-size:12px;color:#111;background:#fff;margin-left:auto}" +
    ".ad-appr th,.ad-appr td{border:1px solid #111;text-align:center;padding:2px 4px;min-width:62px;font-weight:600;vertical-align:middle}" +
    ".ad-appr .ad-h{min-width:0;width:22px;padding:2px;line-height:1.25;background:#fff}" +
    ".ad-appr .ad-t{outline:0;min-height:16px;border-radius:3px;white-space:nowrap}" +
    ".ad-appr .ad-t:focus,.ad-appr .ad-n:focus{background:#E6F0FD}" +
    ".ad-appr td.ad-s{height:46px;padding:0;position:relative;cursor:pointer}" +
    ".ad-appr td.ad-s:hover{background:#F3F7FD}" +
    ".ad-appr td.ad-s img{display:block;max-width:92px;max-height:40px;margin:auto}" +
    ".ad-appr td.ad-s .ad-d{position:absolute;right:2px;bottom:0;font-size:9px;font-weight:500;color:#555}" +
    ".ad-appr td.ad-s .ad-ph{font-size:10.5px;color:#9aa3ad;font-weight:500}" +
    ".ad-appr td.ad-nm{font-size:11px;font-weight:500;height:18px;padding:0 3px}" +
    ".ad-appr .ad-n{outline:0;min-height:15px;white-space:nowrap}" +
    ".ad-appr .ad-n:empty::before{content:attr(data-ph);color:#b8c0ca}" +
    ".ad-ctl{display:flex;flex-wrap:wrap;gap:4px 10px;justify-content:flex-end;margin-top:4px;font-size:11.5px}" +
    ".ad-ctl button{font:inherit;background:none;border:0;padding:2px 0;color:#1F6FD1;cursor:pointer}" +
    ".ad-ctl button:hover{text-decoration:underline}" +
    ".ad-wrap{display:inline-block;vertical-align:top}" +
    ".ad-modal{position:fixed;inset:0;z-index:1000;background:rgba(10,20,35,.55);display:flex;align-items:center;justify-content:center;padding:16px}" +
    ".ad-box{background:#fff;color:#18243A;border-radius:16px;box-shadow:0 20px 50px rgba(0,0,0,.3);width:100%;max-width:520px;padding:20px;max-height:92vh;overflow:auto}" +
    ".ad-box h2{font-size:18px;margin:0 0 4px;color:#17365D}.ad-box p{margin:0 0 10px;font-size:14px;color:#46546A;line-height:1.55}" +
    ".ad-cv{width:100%;height:200px;border:2px dashed #C9D3E0;border-radius:12px;touch-action:none;background:#fff;cursor:crosshair;display:block}" +
    ".ad-row{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;margin-top:12px}" +
    ".ad-btn{display:inline-flex;align-items:center;justify-content:center;height:40px;padding:0 16px;border-radius:10px;border:1px solid #1F6FD1;background:#1F6FD1;color:#fff;font:inherit;font-weight:700;font-size:14px;cursor:pointer}" +
    ".ad-btn.g{background:#fff;color:#1F6FD1;border-color:#E3E8EF}.ad-btn.r{background:#fff;color:#C8352B;border-color:#F3C9C5}" +
    ".ad-btn:disabled{opacity:.5;cursor:default}" +
    ".ad-toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:#17365D;color:#fff;padding:10px 16px;border-radius:10px;font-size:14px;z-index:1100;box-shadow:0 8px 24px rgba(0,0,0,.25);max-width:90vw}" +
    /* 사진 */
    ".ad-photos{margin-top:18px}" +
    ".ad-ph-h{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:8px}" +
    ".ad-ph-h h3{font-size:14px;margin:0;padding-left:8px;border-left:4px solid #17365D;color:#111}" +
    ".ad-ph-acts{display:flex;gap:6px;flex-wrap:wrap;align-items:center;font-size:12.5px}" +
    ".ad-ph-acts label.ad-btn{height:32px;padding:0 12px;font-size:13px}" +
    ".ad-ph-acts select{height:32px;border:1px solid #E3E8EF;border-radius:8px;font:inherit;padding:0 6px;background:#fff;color:#18243A}" +
    ".ad-grid{display:grid;grid-template-columns:repeat(var(--ad-cols,2),minmax(0,1fr));gap:10px}" +
    ".ad-fig{min-width:0;margin:0;border:1px solid #111;display:flex;flex-direction:column;break-inside:avoid;page-break-inside:avoid;background:#fff}" +
    ".ad-fig .ad-img{height:var(--ad-h,230px);display:flex;align-items:center;justify-content:center;background:#F4F6F9;overflow:hidden;border-bottom:1px solid #111}" +
    ".ad-fig img{max-width:100%;max-height:100%;object-fit:contain;display:block}" +
    ".ad-cap{display:grid;grid-template-columns:auto minmax(0,1fr);font-size:12px;color:#111}" +
    ".ad-cap>b{padding:3px 6px;border-right:1px solid #111;border-bottom:1px solid #ccc;background:#F4F6F9;font-weight:700;white-space:nowrap}" +
    ".ad-cap>div,.ad-cap>select{padding:3px 6px;border-bottom:1px solid #ccc;min-height:22px;outline:0}" +
    ".ad-cap>*:nth-last-child(-n+2){border-bottom:0}" +
    ".ad-cap>select{min-width:0;width:100%;text-overflow:ellipsis;border:0;border-bottom:1px solid #ccc;font:inherit;background:#fff;color:#111;appearance:auto}" +
    ".ad-cap [contenteditable]:empty::before{content:attr(data-ph);color:#9aa3ad}" +
    ".ad-cap [contenteditable]:focus{background:#E6F0FD}" +
    ".ad-fig-ctl{display:flex;justify-content:flex-end;gap:8px;padding:3px 6px;border-top:1px dashed #ccc;font-size:11.5px}" +
    ".ad-fig-ctl button{font:inherit;background:none;border:0;color:#1F6FD1;cursor:pointer;padding:0}" +
    ".ad-fig-ctl button.del{color:#C8352B}" +
    ".ad-empty{border:1px dashed #C9D3E0;border-radius:10px;padding:18px;text-align:center;color:#6B788C;font-size:13px}" +
    ".ad-cam{font:inherit;font-size:11px;line-height:1;border:1px solid #D8E7FA;background:#EDF4FD;color:#1F6FD1;border-radius:6px;padding:3px 5px;cursor:pointer;margin-left:4px;vertical-align:middle}" +
    ".ad-cam b{font-weight:700}" +
    "@media (pointer:fine){.ad-mob{display:none !important}}" +
    "@media (max-width:640px){.ad-grid{grid-template-columns:repeat(min(var(--ad-cols,2),2),minmax(0,1fr))}.ad-fig .ad-img{height:160px}}" +
    "@media print{.ad-toast,.ad-modal,.ad-noprint,.ad-ctl,.ad-ph-acts,.ad-fig-ctl,.ad-cam{display:none !important}.ad-photos.ad-none{display:none}.ad-appr td.ad-s .ad-ph{visibility:hidden}.ad-appr td.ad-s:hover{background:none}.ad-photos{break-before:auto}.ad-cap>select{appearance:none;-webkit-appearance:none}.ad-cap>select[data-empty]{color:transparent}.ad-cap [contenteditable]:empty::before,.ad-appr .ad-n:empty::before{content:none}.ad-empty{display:none}}";
  (function () { var s = document.createElement("style"); s.id = "ad-css"; s.textContent = CSS; (document.head || document.documentElement).appendChild(s); })();

  var tt;
  function toast(msg) {
    var el = document.querySelector(".ad-toast");
    if (!el) { el = document.createElement("div"); el.className = "ad-toast"; el.setAttribute("role", "status"); document.body.appendChild(el); }
    el.textContent = msg; el.hidden = false; clearTimeout(tt); tt = setTimeout(function () { el.hidden = true; }, 2600);
  }

  // =====================================================================
  // 결재란
  // =====================================================================
  var DEF = P + "appr.default";
  var BASE = { cols: ["담당", "검토", "승인"], names: ["", "", ""] };
  function defLine() {
    var d = lget(DEF, null);
    if (!d || !d.cols || !d.cols.length) d = BASE;
    return { cols: d.cols.slice(), names: (d.names || []).slice() };
  }
  function apprState(key) {
    var s = lget(P + "appr." + key, null), d = defLine();
    if (!s || !s.cols) return { own: false, cols: d.cols, names: d.names, signs: (s && s.signs) || [], dates: (s && s.dates) || [] };
    s.own = true; s.names = s.names || []; s.signs = s.signs || []; s.dates = s.dates || []; return s;
  }
  var INST = [];
  function apprSave(key, s, from) {
    lset(P + "appr." + key, { cols: s.cols, names: s.names, signs: s.signs, dates: s.dates });
    INST.forEach(function (it) { if (it.key === key && it.el !== from && document.contains(it.el)) it.draw(); });
  }

  function mountApproval(el, key, opts) {
    opts = opts || {};
    if (!el) return;
    function draw() {
      var s = apprState(key), n = s.cols.length;
      var h = '<table class="ad-appr' + (opts.cls ? " " + opts.cls : "") + '" aria-label="결재란"><tr><th rowspan="3" class="ad-h">' + esc(opts.label || "결<br>재").replace(/&lt;br&gt;/g, "<br>") + "</th>";
      for (var i = 0; i < n; i++) h += '<th><div class="ad-t" contenteditable="true" role="textbox" aria-label="결재 칸 ' + (i + 1) + ' 이름" data-i="' + i + '">' + esc(s.cols[i]) + "</div></th>";
      h += "</tr><tr>";
      for (var j = 0; j < n; j++) {
        var sg = s.signs[j];
        h += '<td class="ad-s" data-sign="' + j + '" tabindex="0" role="button" aria-label="' + esc(s.cols[j]) + ' 서명' + (sg ? " (서명됨, 누르면 다시 서명)" : " 넣기") + '">' +
          (sg ? '<img src="' + esc(sg) + '" alt="' + esc(s.cols[j]) + ' 서명">' + (s.dates[j] ? '<span class="ad-d">' + esc(String(s.dates[j]).slice(5).replace("-", ".")) + "</span>" : "") : '<span class="ad-ph ad-noprint">서명</span>') + "</td>";
      }
      h += "</tr><tr>";
      for (var k = 0; k < n; k++) h += '<td class="ad-nm"><div class="ad-n" contenteditable="true" role="textbox" aria-label="' + esc(s.cols[k]) + ' 성명" data-ph="성명" data-n="' + k + '">' + esc(s.names[k] || "") + "</div></td>";
      h += "</tr></table>";
      h += '<div class="ad-ctl ad-noprint"><button type="button" data-a="add">＋ 칸</button><button type="button" data-a="del"' + (n <= 1 ? " disabled" : "") + '>－ 칸</button>' +
        '<button type="button" data-a="def" title="지금 결재란(칸 이름·성명)을 모든 서식의 기본값으로">모든 서식 기본으로</button>' +
        (s.own ? '<button type="button" data-a="reset">기본값으로</button>' : "") + "</div>";
      el.innerHTML = h;
    }
    function own() { var s = apprState(key); if (!s.own) { s.own = true; } return s; }
    el.addEventListener("input", function (ev) {
      var t = ev.target, s = own();
      if (t.dataset.i != null) s.cols[+t.dataset.i] = t.textContent.trim();
      else if (t.dataset.n != null) s.names[+t.dataset.n] = t.textContent.trim();
      else return;
      apprSave(key, s, el);
    });
    el.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" && ev.target.isContentEditable) { ev.preventDefault(); ev.target.blur(); }
      if ((ev.key === "Enter" || ev.key === " ") && ev.target.dataset && ev.target.dataset.sign != null) { ev.preventDefault(); sign(+ev.target.dataset.sign); }
    });
    el.addEventListener("click", function (ev) {
      var c = ev.target.closest("[data-sign]");
      if (c) { sign(+c.dataset.sign); return; }
      var b = ev.target.closest("[data-a]"); if (!b) return;
      var s = own(), a = b.dataset.a;
      if (a === "add") { if (s.cols.length >= 6) { toast("결재 칸은 6개까지 둘 수 있습니다."); return; } s.cols.push("확인"); s.names.push(""); }
      else if (a === "del") { if (s.cols.length <= 1) return; s.cols.pop(); s.names.pop(); s.signs.length = Math.min(s.signs.length, s.cols.length); s.dates.length = Math.min(s.dates.length, s.cols.length); }
      else if (a === "def") { lset(DEF, { cols: s.cols, names: s.names }); toast("이 결재란을 모든 서식의 기본값으로 저장했습니다. 이미 고친 서식은 그대로입니다."); }
      else if (a === "reset") { var sg = s.signs, dt = s.dates, d = defLine(); try { localStorage.removeItem(P + "appr." + key); } catch (e) {} if (sg.some(Boolean)) apprSave(key, { cols: d.cols, names: d.names, signs: sg.slice(0, d.cols.length), dates: dt.slice(0, d.cols.length) }); }
      if (a !== "def" && a !== "reset") apprSave(key, s);
      draw();
    });
    function sign(i) {
      var s = apprState(key);
      openPad({ title: (s.cols[i] || "결재") + " 서명", has: !!s.signs[i], name: s.names[i] || "" }, function (res) {
        var st = own();
        if (res === null) { st.signs[i] = null; st.dates[i] = null; }
        else { st.signs[i] = res; st.dates[i] = ymd(); }
        apprSave(key, st); draw();
      });
    }
    INST = INST.filter(function (it) { return document.contains(it.el) && it.el !== el; });
    INST.push({ key: key, el: el, draw: draw });
    draw();
    return { redraw: draw };
  }

  // 인쇄 전용 서식(화면에 서식이 안 보이는 도구)용: 저장된 결재란을 그대로 그린 읽기 전용 표
  function apprHTML(key) {
    var s = apprState(key), n = s.cols.length, h = '<table class="ad-appr"><tr><th rowspan="3" class="ad-h">결<br>재</th>';
    for (var i = 0; i < n; i++) h += "<th>" + esc(s.cols[i]) + "</th>";
    h += "</tr><tr>";
    for (var j = 0; j < n; j++) h += '<td class="ad-s">' + (s.signs[j] ? '<img src="' + esc(s.signs[j]) + '" alt="">' + (s.dates[j] ? '<span class="ad-d">' + esc(String(s.dates[j]).slice(5).replace("-", ".")) + "</span>" : "") : "") + "</td>";
    h += "</tr><tr>";
    for (var k = 0; k < n; k++) h += '<td class="ad-nm">' + esc(s.names[k] || "") + "</td>";
    return h + "</tr></table>";
  }
  function mountAll(root) { [].forEach.call((root || document).querySelectorAll("[data-appr]"), function (el) { if (!el.dataset.mounted) { el.dataset.mounted = "1"; mountApproval(el, el.dataset.appr); } }); }
  document.addEventListener("DOMContentLoaded", function () { mountAll(document); });

  // ---------- 서명 패드
  function openPad(o, done) {
    var m = document.createElement("div");
    m.className = "ad-modal"; m.setAttribute("role", "dialog"); m.setAttribute("aria-modal", "true"); m.setAttribute("aria-label", o.title);
    m.innerHTML = '<div class="ad-box"><h2>' + esc(o.title) + '</h2><p>손가락이나 마우스로 아래 칸에 서명하세요. 서명 이미지는 이 기기의 브라우저에만 저장됩니다.</p><p style="font-size:12.5px;color:#6B788C">이 기능은 인쇄용 서명 표시 기능이며, 모든 법정 전자서명 또는 전자문서 제출 요건을 충족한다는 의미가 아닙니다. 기관의 전자 제출 시스템이 요구하는 인증·서명은 따로 확인하세요.</p>' +
      '<canvas class="ad-cv" aria-label="서명 칸"></canvas>' +
      '<div class="ad-row">' + (o.name ? '<button type="button" class="ad-btn g" data-b="stamp">성명 도장으로</button>' : "") +
      (o.has ? '<button type="button" class="ad-btn r" data-b="remove">서명 지우기</button>' : "") +
      '<button type="button" class="ad-btn g" data-b="clear">다시 쓰기</button><button type="button" class="ad-btn g" data-b="cancel">취소</button><button type="button" class="ad-btn" data-b="ok" disabled>저장</button></div></div>';
    document.body.appendChild(m);
    var cv = m.querySelector("canvas"), ctx, drawn = false, down = false, last = null, prev = document.activeElement;
    function size() { var r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1; cv.width = r.width * dpr; cv.height = r.height * dpr; ctx = cv.getContext("2d"); ctx.scale(dpr, dpr); ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#0B1F3A"; ctx.lineWidth = 2.6; }
    size();
    function pt(ev) { var r = cv.getBoundingClientRect(); return { x: ev.clientX - r.left, y: ev.clientY - r.top }; }
    cv.addEventListener("pointerdown", function (ev) { down = true; last = pt(ev); cv.setPointerCapture(ev.pointerId); ctx.beginPath(); ctx.arc(last.x, last.y, 1.2, 0, 7); ctx.fillStyle = "#0B1F3A"; ctx.fill(); mark(); });
    cv.addEventListener("pointermove", function (ev) { if (!down) return; var p = pt(ev); ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(p.x, p.y); ctx.stroke(); last = p; mark(); });
    ["pointerup", "pointercancel", "pointerleave"].forEach(function (t) { cv.addEventListener(t, function () { down = false; }); });
    function mark() { if (!drawn) { drawn = true; m.querySelector('[data-b="ok"]').disabled = false; } }
    function close(v) { m.remove(); document.removeEventListener("keydown", key); if (prev && prev.focus) prev.focus(); if (v !== undefined) done(v); }
    function key(ev) { if (ev.key === "Escape") close(); }
    document.addEventListener("keydown", key);
    function trimmed() {
      // 여백을 잘라 작게 저장
      var w = cv.width, h = cv.height, d = ctx.getImageData(0, 0, w, h).data, x0 = w, y0 = h, x1 = 0, y1 = 0;
      for (var y = 0; y < h; y += 2) for (var x = 0; x < w; x += 2) if (d[(y * w + x) * 4 + 3] > 10) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      if (x1 <= x0) return null;
      var pw = x1 - x0 + 12, ph = y1 - y0 + 12, sc = Math.min(1, 240 / pw, 100 / ph), o2 = document.createElement("canvas");
      o2.width = Math.max(1, Math.round(pw * sc)); o2.height = Math.max(1, Math.round(ph * sc));
      o2.getContext("2d").drawImage(cv, x0 - 6, y0 - 6, pw, ph, 0, 0, o2.width, o2.height);
      return o2.toDataURL("image/png");
    }
    function stamp() {
      var c = document.createElement("canvas"), n = o.name.slice(0, 4), s = 96; c.width = s; c.height = s; var g = c.getContext("2d");
      g.strokeStyle = g.fillStyle = "#C8352B"; g.lineWidth = 5; g.beginPath(); g.arc(s / 2, s / 2, s / 2 - 5, 0, 7); g.stroke();
      g.font = "700 " + (n.length > 3 ? 20 : 26) + "px 'Malgun Gothic','Apple SD Gothic Neo',sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
      if (n.length <= 3) g.fillText(n, s / 2, s / 2 + 1); else { g.fillText(n.slice(0, 2), s / 2, s / 2 - 12); g.fillText(n.slice(2), s / 2, s / 2 + 14); }
      return c.toDataURL("image/png");
    }
    m.addEventListener("click", function (ev) {
      if (ev.target === m) { close(); return; }
      var b = ev.target.closest("[data-b]"); if (!b) return;
      var a = b.dataset.b;
      if (a === "clear") { ctx.clearRect(0, 0, cv.width, cv.height); drawn = false; m.querySelector('[data-b="ok"]').disabled = true; }
      else if (a === "cancel") close();
      else if (a === "remove") close(null);
      else if (a === "stamp") close(stamp());
      else if (a === "ok") { var u = trimmed(); close(u || undefined); }
    });
    setTimeout(function () { var f = m.querySelector('[data-b="cancel"]'); if (f) f.focus(); }, 30);
  }

  // =====================================================================
  // 사진 (IndexedDB)
  // =====================================================================
  var dbp = null;
  function db() {
    if (dbp) return dbp;
    dbp = new Promise(function (res, rej) {
      if (!window.indexedDB) { rej(new Error("이 브라우저는 사진 저장(IndexedDB)을 지원하지 않습니다.")); return; }
      var r = indexedDB.open("safetake", 1);
      r.onupgradeneeded = function () { var d = r.result; if (!d.objectStoreNames.contains("photos")) { var st = d.createObjectStore("photos", { keyPath: "id" }); st.createIndex("doc", "doc"); } };
      r.onsuccess = function () { res(r.result); };
      r.onerror = function () { rej(r.error || new Error("사진 저장소를 열 수 없습니다.")); };
    });
    return dbp;
  }
  function tx(mode, fn) {
    return db().then(function (d) {
      return new Promise(function (res, rej) {
        var t = d.transaction("photos", mode), st = t.objectStore("photos"), out = fn(st);
        t.oncomplete = function () { res(out && out.result !== undefined ? out.result : out); };
        t.onerror = function () { rej(t.error); }; t.onabort = function () { rej(t.error || new Error("저장 실패")); };
      });
    });
  }
  function listPhotos(doc) {
    return db().then(function (d) {
      return new Promise(function (res, rej) {
        var r = d.transaction("photos").objectStore("photos").index("doc").getAll(doc);
        r.onsuccess = function () { res((r.result || []).sort(function (a, b) { return a.ord - b.ord; })); }; r.onerror = function () { rej(r.error); };
      });
    });
  }
  function allPhotos() {
    return db().then(function (d) { return new Promise(function (res, rej) { var r = d.transaction("photos").objectStore("photos").getAll(); r.onsuccess = function () { res(r.result || []); }; r.onerror = function () { rej(r.error); }; }); });
  }
  function putPhoto(p) { return tx("readwrite", function (st) { st.put(p); }); }
  function delPhoto(id) { return tx("readwrite", function (st) { st.delete(id); }); }

  function shrink(file) {
    // 긴 변 1600px, JPEG 0.82 로 줄여 저장(원본 수 MB → 200~400KB)
    return new Promise(function (res, rej) {
      if (!/^image\//.test(file.type)) { rej(new Error(file.name + ": 이미지 파일이 아닙니다.")); return; }
      var url = URL.createObjectURL(file), img = new Image();
      img.onload = function () {
        var M = 1600, w = img.naturalWidth, h = img.naturalHeight, s = Math.min(1, M / Math.max(w, h)), c = document.createElement("canvas");
        c.width = Math.round(w * s); c.height = Math.round(h * s);
        var g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); g.drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url); res(c.toDataURL("image/jpeg", 0.82));
      };
      img.onerror = function () { URL.revokeObjectURL(url); rej(new Error(file.name + ": 이미지를 읽을 수 없습니다(HEIC는 사진 앱에서 JPG로 공유해 주세요).")); };
      img.src = url;
    });
  }
  var listeners = {};
  function changed(doc) { (listeners[doc] || []).forEach(function (f) { try { f(); } catch (e) {} }); }
  function addFiles(doc, files, rel) {
    files = [].slice.call(files || []);
    if (!files.length) return Promise.resolve(0);
    toast("사진 " + files.length + "장을 줄여서 저장하는 중…");
    return listPhotos(doc).then(function (ex) {
      var ord = ex.reduce(function (m, p) { return Math.max(m, p.ord); }, 0), ok = 0, errs = [];
      return files.reduce(function (pr, f) {
        return pr.then(function () {
          return shrink(f).then(function (data) {
            ord++; ok++;
            var taken = f.lastModified ? ymd(new Date(f.lastModified)) : ymd();
            return putPhoto({ id: doc + ":" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), doc: doc, data: data, caption: "", rel: rel || "", taken: taken, ord: ord, added: ymd() });
          }).catch(function (e) { errs.push(e.message); });
        });
      }, Promise.resolve()).then(function () {
        changed(doc);
        toast(errs.length ? ok + "장 저장, " + errs.length + "장 실패 — " + errs[0] : "사진 " + ok + "장을 첨부했습니다.");
        return ok;
      });
    }).catch(function (e) { toast(e.message || "사진을 저장하지 못했습니다."); return 0; });
  }
  function pick(doc, rel, camera) {
    var i = document.createElement("input"); i.type = "file"; i.accept = "image/*"; i.multiple = !camera;
    if (camera) i.setAttribute("capture", "environment");
    i.style.display = "none"; document.body.appendChild(i);
    i.addEventListener("change", function () { addFiles(doc, i.files, rel); i.remove(); });
    i.click();
  }

  function mountPhotos(el, doc, opts) {
    opts = opts || {};
    if (!el) return;
    var CK = P + "photos.cols." + doc;
    function draw() {
      listPhotos(doc).then(function (ps) {
        var cols = lget(CK, opts.cols || 2), items = typeof opts.items === "function" ? opts.items() : (opts.items || []);
        el.className = "ad-photos" + (ps.length ? "" : " ad-none");
        var h = '<div class="ad-ph-h"><h3>' + esc(opts.title || "사진 첨부") + (ps.length ? " (" + ps.length + "장)" : "") + '</h3><div class="ad-ph-acts">' +
          '<label class="ad-btn g"><input type="file" accept="image/*" multiple hidden data-f="1">사진 추가</label>' +
          '<label class="ad-btn g ad-mob"><input type="file" accept="image/*" capture="environment" hidden data-f="1">카메라</label>' +
          '<label>한 줄에 <select data-cols aria-label="한 줄에 들어갈 사진 수">' + [1, 2, 3].map(function (n) { return "<option" + (n === cols ? " selected" : "") + ">" + n + "</option>"; }).join("") + "</select> 장</label></div></div>";
        if (!ps.length) h += '<div class="ad-empty">현장 사진을 붙이면 사진마다 칸이 하나씩 생기고 설명·관련 항목·촬영일을 적을 수 있습니다. 인쇄하면 서식 뒤에 사진대지로 붙습니다.' + (opts.hint ? "<br>" + esc(opts.hint) : "") + "</div>";
        else {
          h += '<div class="ad-grid" style="--ad-cols:' + cols + ";--ad-h:" + (cols === 1 ? "360px" : cols === 3 ? "150px" : "230px") + '">';
          ps.forEach(function (p, i) {
            h += '<figure class="ad-fig" data-id="' + esc(p.id) + '"><div class="ad-img"><img src="' + p.data + '" alt="' + esc(p.caption || "현장 사진 " + (i + 1)) + '" loading="lazy"></div>' +
              '<div class="ad-cap"><b>사진 ' + (i + 1) + "</b><div contenteditable=\"true\" role=\"textbox\" data-cap data-ph=\"사진 설명 (예: 개구부 덮개 미설치)\">" + esc(p.caption) + "</div>" +
              (items.length || p.rel ? '<b>관련</b><select data-rel aria-label="관련 항목"' + (p.rel ? "" : " data-empty") + '><option value="">— 관련 항목 없음 —</option>' +
                (items.indexOf(p.rel) < 0 && p.rel ? "<option selected>" + esc(p.rel) + "</option>" : "") +
                items.map(function (it) { return "<option" + (it === p.rel ? " selected" : "") + ">" + esc(it) + "</option>"; }).join("") + "</select>" : "") +
              '<b>촬영일</b><div contenteditable="true" role="textbox" data-taken>' + esc(p.taken) + "</div></div>" +
              '<div class="ad-fig-ctl"><button type="button" data-mv="-1"' + (i ? "" : " disabled") + '>↑ 앞으로</button><button type="button" data-mv="1"' + (i < ps.length - 1 ? "" : " disabled") + '>↓ 뒤로</button><button type="button" class="del" data-del>삭제</button></div></figure>';
          });
          h += "</div>";
        }
        el.innerHTML = h;
      }).catch(function (e) {
        el.className = "ad-photos ad-none";
        el.innerHTML = '<div class="ad-empty">' + esc(e.message || "사진 기능을 쓸 수 없는 환경입니다.") + "</div>";
      });
    }
    var tm;
    el.addEventListener("change", function (ev) {
      var t = ev.target;
      if (t.dataset.f) { addFiles(doc, t.files); t.value = ""; return; }
      if (t.dataset.cols != null) { lset(CK, +t.value); draw(); return; }
      if (t.dataset.rel != null) { t.toggleAttribute("data-empty", !t.value); upd(t, { rel: t.value }); }
    });
    el.addEventListener("input", function (ev) {
      var t = ev.target;
      if (t.dataset.cap != null) { clearTimeout(tm); tm = setTimeout(function () { upd(t, { caption: t.textContent.trim() }); }, 300); }
      if (t.dataset.taken != null) { clearTimeout(tm); tm = setTimeout(function () { upd(t, { taken: t.textContent.trim() }); }, 300); }
    });
    el.addEventListener("keydown", function (ev) { if (ev.key === "Enter" && ev.target.isContentEditable) { ev.preventDefault(); ev.target.blur(); } });
    function upd(t, patch) {
      var id = t.closest("[data-id]").dataset.id;
      listPhotos(doc).then(function (ps) { var p = ps.filter(function (x) { return x.id === id; })[0]; if (!p) return; Object.keys(patch).forEach(function (k) { p[k] = patch[k]; }); return putPhoto(p); }).then(function () { (listeners[doc] || []).forEach(function (f) { if (f !== draw) try { f(); } catch (e) {} }); });
    }
    el.addEventListener("click", function (ev) {
      var fig = ev.target.closest("[data-id]"); if (!fig) return;
      var id = fig.dataset.id;
      if (ev.target.closest("[data-del]")) {
        if (!window.confirm("이 사진을 삭제할까요?")) return;
        delPhoto(id).then(function () { changed(doc); });
        return;
      }
      var mv = ev.target.closest("[data-mv]");
      if (mv) {
        listPhotos(doc).then(function (ps) {
          var i = ps.findIndex(function (p) { return p.id === id; }), j = i + (+mv.dataset.mv);
          if (i < 0 || j < 0 || j >= ps.length) return;
          var a = ps[i].ord; ps[i].ord = ps[j].ord; ps[j].ord = a;
          return Promise.all([putPhoto(ps[i]), putPhoto(ps[j])]);
        }).then(function () { changed(doc); });
      }
    });
    (listeners[doc] = listeners[doc] || []).push(draw);
    draw();
    return { redraw: draw };
  }
  function countPhotos(doc) { return listPhotos(doc).then(function (ps) { var m = {}; ps.forEach(function (p) { if (p.rel) m[p.rel] = (m[p.rel] || 0) + 1; }); return { total: ps.length, byRel: m }; }).catch(function () { return { total: 0, byRel: {} }; }); }
  function onPhotos(doc, fn) { (listeners[doc] = listeners[doc] || []).push(fn); }
  function clearPhotos(doc) { return listPhotos(doc).then(function (ps) { return Promise.all(ps.map(function (p) { return delPhoto(p.id); })); }).then(function () { changed(doc); }).catch(function () {}); }

  // =====================================================================
  // 내 데이터 백업 — localStorage("safetake.*") + 사진을 JSON 하나로
  // =====================================================================
  function localKeys() { var ks = []; try { for (var i = 0; i < localStorage.length; i++) { var k = localStorage.key(i); if (k && k.indexOf(P) === 0) ks.push(k); } } catch (e) {} return ks.sort(); }
  function summary() {
    var ks = localKeys(), bytes = 0;
    ks.forEach(function (k) { try { bytes += (localStorage.getItem(k) || "").length * 2; } catch (e) {} });
    var forms = ks.filter(function (k) { return /^safetake\.form\./.test(k); }).length;
    return allPhotos().then(function (ps) { ps.forEach(function (p) { bytes += (p.data || "").length; }); return { keys: ks.length, forms: forms, photos: ps.length, bytes: bytes }; })
      .catch(function () { return { keys: ks.length, forms: forms, photos: 0, bytes: bytes }; });
  }
  function exportAll() {
    var data = {};
    localKeys().forEach(function (k) { try { data[k] = localStorage.getItem(k); } catch (e) {} });
    return allPhotos().catch(function () { return []; }).then(function (ps) {
      var out = { app: "SafePlum", format: "safetake-backup", version: 1, exported: new Date().toISOString(), origin: location.origin, localStorage: data, photos: ps };
      var blob = new Blob([JSON.stringify(out)], { type: "application/json" });
      var a = document.createElement("a"), d = new Date();
      a.href = URL.createObjectURL(blob);
      a.download = "SafePlum_백업_" + d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate()) + "_" + pad(d.getHours()) + pad(d.getMinutes()) + ".json";
      document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
      return { keys: Object.keys(data).length, photos: ps.length };
    });
  }
  function importAll(file) {
    return new Promise(function (res, rej) {
      if (!file) { rej(new Error("파일을 고르세요.")); return; }
      if (file.size > 300 * 1024 * 1024) { rej(new Error("파일이 너무 큽니다(300MB 초과).")); return; }
      var r = new FileReader();
      r.onload = function () {
        var d;
        try { d = JSON.parse(r.result); } catch (e) { rej(new Error("백업 파일(JSON)을 읽을 수 없습니다.")); return; }
        if (!d || (d.format !== "safetake-backup" && d.format !== ["anjeon", "duck-backup"].join("")) || typeof d.localStorage !== "object") { rej(new Error("SafePlum 백업 파일이 아닙니다.")); return; }
        var n = 0, bad = 0;
        Object.keys(d.localStorage).forEach(function (k) {
          var ok0 = ["anjeon", "duck."].join(""), nk = k.indexOf(ok0) === 0 ? P + k.slice(ok0.length) : k;
          if (nk.indexOf(P) !== 0 || typeof d.localStorage[k] !== "string") { bad++; return; }
          try { localStorage.setItem(nk, d.localStorage[k]); n++; } catch (e) { bad++; }
        });
        var ps = Array.isArray(d.photos) ? d.photos.filter(function (p) { return p && typeof p.id === "string" && typeof p.doc === "string" && /^data:image\/(jpeg|png|webp);base64,/.test(p.data || ""); }) : [];
        (ps.length ? tx("readwrite", function (st) { ps.forEach(function (p) { st.put({ id: p.id, doc: p.doc, data: p.data, caption: String(p.caption || ""), rel: String(p.rel || ""), taken: String(p.taken || ""), ord: +p.ord || 0, added: String(p.added || "") }); }); }) : Promise.resolve())
          .then(function () { res({ keys: n, photos: ps.length, skipped: bad }); }, function (e) { res({ keys: n, photos: 0, skipped: bad, photoError: e && e.message }); });
      };
      r.onerror = function () { rej(new Error("파일을 읽지 못했습니다.")); };
      r.readAsText(file);
    });
  }
  function kb(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + "MB" : Math.max(1, Math.round(n / 1024)) + "KB"; }
  function openDataModal() {
    var m = document.createElement("div");
    m.className = "ad-modal"; m.setAttribute("role", "dialog"); m.setAttribute("aria-modal", "true"); m.setAttribute("aria-labelledby", "adDataT");
    m.innerHTML = '<div class="ad-box"><h2 id="adDataT">작성 내용 백업 · 삭제</h2>' +
      '<p>SafePlum 작성 도구는 입력한 내용을 SafePlum 서버로 보내지 않고 <b>이 기기의 이 브라우저</b>에 저장합니다. 브라우저 기록을 지우거나 다른 기기로 옮기면 보이지 않습니다.</p>' +
      '<ul style="font-size:13px;line-height:1.6;margin:8px 0 10px 18px;list-style:disc"><li><b>저장 위치</b> — 서식·도구 입력값, 결재란 이름, 인쇄용 서명 이미지: localStorage / 첨부 사진: IndexedDB</li><li><b>백업 파일(JSON)에 들어가는 것</b> — 위 항목 전부(사진·서명 이미지 포함). 파일을 받은 사람은 내용을 모두 볼 수 있습니다.</li><li><b>건강정보</b> — 건강진단 결과·질병명 등은 꼭 필요한 만큼만 적고, 이름 대신 관리번호를 쓰세요.</li><li><b>공용 PC</b> — 다른 사람도 같은 브라우저에서 내용을 볼 수 있습니다. 쓰고 나면 아래에서 삭제하세요.</li></ul>' +
      '<p data-sum>저장된 내용을 세는 중…</p>' +
      '<div class="ad-row" style="justify-content:flex-start"><button type="button" class="ad-btn" data-b="exp">백업 파일 내보내기 (JSON)</button>' +
      '<label class="ad-btn g"><input type="file" accept="application/json,.json" hidden data-imp>백업 불러오기</label><button type="button" class="ad-btn r" data-b="wipe">이 브라우저의 SafePlum 데이터 모두 삭제</button></div>' +
      '<p style="margin-top:12px;font-size:12.5px">불러오기는 같은 이름의 항목을 파일 내용으로 덮어씁니다. 파일에는 입력한 내용이 그대로 들어 있으니 안전한 곳에 보관하세요. 서버로는 아무것도 보내지 않습니다.</p>' +
      '<div class="ad-row"><button type="button" class="ad-btn g" data-b="close">닫기</button></div></div>';
    document.body.appendChild(m);
    var prev = document.activeElement;
    function sum() { summary().then(function (s) { var el = m.querySelector("[data-sum]"); if (el) el.innerHTML = "지금 이 브라우저에 <b>저장 항목 " + s.keys + "개</b>(서식 " + s.forms + "종 포함), <b>사진 " + s.photos + "장</b>, 약 " + kb(s.bytes) + "가 있습니다."; }); }
    sum();
    function close() { m.remove(); document.removeEventListener("keydown", key); if (prev && prev.focus) prev.focus(); }
    function key(ev) { if (ev.key === "Escape") close(); }
    document.addEventListener("keydown", key);
    m.addEventListener("click", function (ev) {
      if (ev.target === m) { close(); return; }
      var b = ev.target.closest("[data-b]"); if (!b) return;
      if (b.dataset.b === "close") close();
      if (b.dataset.b === "wipe") {
        if (!window.confirm("이 브라우저에 저장된 SafePlum 서식·도구 입력값, 서명 이미지, 사진을 모두 지웁니다. 되돌릴 수 없습니다. 계속할까요?")) return;
        var ks = []; for (var i = 0; i < localStorage.length; i++) { var k = localStorage.key(i); if (k && k.indexOf("safetake.") === 0) ks.push(k); }
        ks.forEach(function (k) { localStorage.removeItem(k); });
        var done = function () { toast("삭제했습니다 — 항목 " + ks.length + "개와 사진. 새로고침합니다."); setTimeout(function () { location.reload(); }, 900); };
        try { var rq = indexedDB.deleteDatabase("safetake"); rq.onsuccess = done; rq.onerror = done; rq.onblocked = done; } catch (e) { done(); }
      }
      if (b.dataset.b === "exp") { b.disabled = true; exportAll().then(function (r) { toast("백업 파일을 내려받았습니다 — 항목 " + r.keys + "개, 사진 " + r.photos + "장"); }).catch(function (e) { toast("내보내지 못했습니다: " + (e.message || e)); }).then(function () { b.disabled = false; }); }
    });
    m.querySelector("[data-imp]").addEventListener("change", function (ev) {
      var f = ev.target.files[0]; ev.target.value = "";
      if (!f) return;
      if (!window.confirm("'" + f.name + "' 내용으로 이 브라우저의 같은 항목을 덮어씁니다. 계속할까요?")) return;
      importAll(f).then(function (r) { toast("불러왔습니다 — 항목 " + r.keys + "개, 사진 " + r.photos + "장" + (r.skipped ? " (건너뜀 " + r.skipped + ")" : "") + ". 새로고침합니다."); sum(); setTimeout(function () { location.reload(); }, 1400); })
        .catch(function (e) { toast(e.message || "불러오지 못했습니다."); });
    });
    setTimeout(function () { var f = m.querySelector('[data-b="exp"]'); if (f) f.focus(); }, 30);
  }
  document.addEventListener("click", function (ev) { if (ev.target.closest && ev.target.closest("[data-mydata]")) { ev.preventDefault(); openDataModal(); } });

  window.ADoc = { mountApproval: mountApproval, apprHTML: apprHTML, mountAll: mountAll, mountPhotos: mountPhotos, pickPhoto: pick, addFiles: addFiles, countPhotos: countPhotos, onPhotos: onPhotos, clearPhotos: clearPhotos,
    exportAll: exportAll, importAll: importAll, openDataModal: openDataModal, toast: toast, esc: esc, ymd: ymd };
})();
