/* 홈 '이번 달 안전보건 달력' — 날짜를 고르면 그날 업무가 아래에 바뀐다.
   회차 계산은 tools/schedule(법정 주기업무 달력)과 같은 규칙을 쓴다. 그 화면에서 바꾼 설정(safetake.schedule)도 반영한다. */
(function () {
  var box = document.getElementById("moBox"), D = window.ST_MO;
  if (!box || !D) return;
  var cal = document.getElementById("moCal"), list = document.getElementById("moList"), head = document.getElementById("moDay");
  var WD = ["일", "월", "화", "수", "목", "금", "토"];
  var FREQ = { daily: "매일", every2: "2일마다", weekly: "매주", monthly: "매월", bimonthly: "2개월", quarterly: "분기", semiannual: "반기", yearly: "연 1회" };
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function ymd(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function lastDay(y, m) { return new Date(y, m + 1, 0).getDate(); }
  function dayIn(y, m, day) { var f = new Date(y, m, 1); return new Date(f.getFullYear(), f.getMonth(), Math.min(+day || 1, lastDay(f.getFullYear(), f.getMonth()))); }
  function wdOf(t) { var w = t.weekday; if (w === 0 || w === "0") return 0; w = +w; return w >= 1 && w <= 6 ? w : 1; }
  function allDays(t) { return t.work === false || t.work === "0" || t.work === 0; }
  function anchorOf(t) { var a = /^\d{4}-\d{2}-\d{2}$/.test(t.anchor || "") ? new Date(t.anchor + "T00:00:00") : null; return a && !isNaN(a) ? a : new Date(2026, 0, 1); }
  function dayDiff(a, b) { return Math.round((Date.UTC(a.getFullYear(), a.getMonth(), a.getDate()) - Date.UTC(b.getFullYear(), b.getMonth(), b.getDate())) / 864e5); }
  function due(t, ref) {
    var y = ref.getFullYear(), m = ref.getMonth();
    switch (t.freq) {
      case "every2": { var diff = dayDiff(ref, anchorOf(t)); var s = new Date(ref); s.setDate(s.getDate() - (((diff % 2) + 2) % 2)); s.setDate(s.getDate() + 1); return s; }
      case "monthly": return dayIn(y, m, t.day);
      case "bimonthly": { var m0 = ((+t.m0 || 1) - 1) % 2; var b = m - (((m - m0) % 2) + 2) % 2; var by = y; if (b < 0) { b += 12; by -= 1; } return dayIn(by, b, t.day); }
      case "quarterly": return dayIn(y, Math.floor(m / 3) * 3 + ((+t.qmonth || 1) - 1), t.day);
      case "semiannual": return dayIn(y, (m < 6 ? 0 : 6) + ((+t.hmonth || 6) - 1), t.day);
      default: return dayIn(y, (+t.month || 1) - 1, t.day);
    }
  }
  function occursOn(t, d) {
    if (t.freq === "daily") return allDays(t) ? true : (d.getDay() > 0 && d.getDay() < 6);
    if (t.freq === "weekly") return d.getDay() === wdOf(t);
    return ymd(due(t, d)) === ymd(d);
  }
  function routine(t) { return t.freq === "daily" || t.freq === "every2"; }

  // 업종(법정 주기업무 달력과 같은 저장값): 업종이 정해진 업무는 고른 업종에 맞을 때만 보인다
  var IK = "safetake.industry", IND = "", INDS = window.ST_IND || [];
  try { IND = localStorage.getItem(IK) || ""; } catch (e) { IND = ""; }
  if (!INDS.some(function (x) { return x[0] === IND; })) IND = "";
  (function () {
    if (!INDS.length) return;
    var sel = document.createElement("select"); sel.className = "sort mc-ind"; sel.setAttribute("aria-label", "업종");
    INDS.forEach(function (x) { var o = document.createElement("option"); o.value = x[0]; o.textContent = x[0] ? x[1] : "업종 전체"; if (x[0] === IND) o.selected = true; sel.appendChild(o); });
    sel.addEventListener("change", function () { IND = sel.value; try { if (IND) localStorage.setItem(IK, IND); else localStorage.removeItem(IK); } catch (e) {} T = tasks(); draw(); });
    box.insertBefore(sel, cal);
  })();
  // 기본 업무 + 사용자가 법정 주기업무 달력에서 바꾼 값
  var mine = false;
  function tasks() {
    var S = {};
    try { S = JSON.parse(localStorage.getItem("safetake.schedule") || "{}") || {}; } catch (e) { S = {}; }
    var ov = S.ov && typeof S.ov === "object" ? S.ov : {}, custom = Array.isArray(S.custom) ? S.custom : [];
    mine = Object.keys(ov).length > 0 || custom.length > 0;
    var out = [];
    D.forEach(function (t) {
      var o = ov[t.key] || {}, x = {}, k;
      for (k in t) x[k] = t[k];
      for (k in o) if (Object.prototype.hasOwnProperty.call(o, k)) x[k] = o[k];
      x.on = Object.prototype.hasOwnProperty.call(o, "on") ? o.on : (IND && Array.isArray(t.ind) ? t.ind.indexOf(IND) >= 0 : !t.off);
      if (x.on) out.push(x);
    });
    custom.forEach(function (c) {
      if (!c || typeof c !== "object" || !c.title || !FREQ[c.freq]) return;
      if (Object.prototype.hasOwnProperty.call(c, "on") && !c.on) return;
      var x = {}, k; for (k in c) x[k] = c[k]; x.custom = true; out.push(x);
    });
    return out;
  }

  var now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  var view = new Date(today.getFullYear(), today.getMonth(), 1), sel = new Date(today), T = tasks();

  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }
  function hrefOf(t) { return t.custom ? "tools/schedule/" : t.form ? "tools/forms/" + t.form + "/" : t.tool ? "tools/" + t.tool + "/" : "tools/schedule/"; }

  function drawCal() {
    var y = view.getFullYear(), m = view.getMonth(), first = view.getDay(), days = lastDay(y, m);
    cal.textContent = "";
    var bar = el("div", "mc-bar");
    var prev = el("button", "mc-nav", "‹"); prev.type = "button"; prev.setAttribute("aria-label", "이전 달");
    var next = el("button", "mc-nav", "›"); next.type = "button"; next.setAttribute("aria-label", "다음 달");
    var ttl = el("div", "mc-h", y + "년 " + (m + 1) + "월"); ttl.setAttribute("aria-live", "polite");
    var tb = el("button", "mc-today", "오늘"); tb.type = "button";
    prev.onclick = function () { move(-1); }; next.onclick = function () { move(1); };
    tb.onclick = function () { view = new Date(today.getFullYear(), today.getMonth(), 1); sel = new Date(today); draw(); focusSel(); };
    bar.appendChild(prev); bar.appendChild(ttl); bar.appendChild(next); bar.appendChild(tb);
    cal.appendChild(bar);
    var g = el("div", "mc-g"); g.setAttribute("role", "group"); g.setAttribute("aria-label", y + "년 " + (m + 1) + "월 날짜");
    WD.forEach(function (w, i) { var s = el("span", "mc-w" + (i === 0 ? " sun" : ""), w); s.setAttribute("aria-hidden", "true"); g.appendChild(s); });
    for (var i = 0; i < first; i++) g.appendChild(el("span"));
    for (var d = 1; d <= days; d++) {
      var dt = new Date(y, m, d), n = T.filter(function (t) { return !routine(t) && occursOn(t, dt); }).length;
      var b = el("button", "mc-d" + (ymd(dt) === ymd(today) ? " today" : "") + (n ? " on" : "") + (dt.getDay() === 0 ? " sun" : "") + (ymd(dt) === ymd(sel) ? " sel" : ""), String(d));
      b.type = "button"; b.dataset.d = d;
      b.setAttribute("aria-pressed", ymd(dt) === ymd(sel) ? "true" : "false");
      b.setAttribute("aria-label", (m + 1) + "월 " + d + "일 " + WD[dt.getDay()] + "요일" + (n ? ", 기한 업무 " + n + "건" : "") + (ymd(dt) === ymd(today) ? ", 오늘" : ""));
      g.appendChild(b);
    }
    cal.appendChild(g);
  }
  function move(k) {
    view = new Date(view.getFullYear(), view.getMonth() + k, 1);
    var same = view.getFullYear() === today.getFullYear() && view.getMonth() === today.getMonth();
    sel = same ? new Date(today) : new Date(view);
    draw();
  }
  function focusSel() { var b = cal.querySelector(".mc-d.sel"); if (b) b.focus(); }
  function item(t, dt) {
    var li = el("li"), tag = el("span", "mo-d" + (t.freq === "yearly" ? " y" : routine(t) || t.freq === "weekly" ? " r" : ""), FREQ[t.freq] || "");
    var a = el("a", null, t.title); a.href = hrefOf(t);
    li.appendChild(tag); li.appendChild(a);
    if (t.time && /^\d{1,2}:\d{2}$/.test(t.time)) li.appendChild(el("span", "mo-t", t.time));
    return li;
  }
  function nextAfter(dt) {
    for (var i = 1; i <= 120; i++) {
      var d = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate() + i);
      var hit = T.filter(function (t) { return !routine(t) && occursOn(t, d); });
      if (hit.length) return { d: d, t: hit };
    }
    return null;
  }
  function drawList() {
    var diff = dayDiff(sel, today);
    head.textContent = (sel.getMonth() + 1) + "월 " + sel.getDate() + "일 (" + WD[sel.getDay()] + ")" + (diff === 0 ? " · 오늘" : diff === 1 ? " · 내일" : diff === -1 ? " · 어제" : "");
    var hit = T.filter(function (t) { return occursOn(t, sel); });
    var main = hit.filter(function (t) { return !routine(t); }), rt = hit.filter(routine);
    main.sort(function (a, b) { return String(a.time || "").localeCompare(String(b.time || "")); });
    list.textContent = "";
    main.forEach(function (t) { list.appendChild(item(t, sel)); });
    if (!main.length) {
      var li = el("li", "mo-none"), nx = nextAfter(sel);
      li.appendChild(document.createTextNode("이 날 기한인 업무가 없습니다."));
      if (nx) {
        var bt = el("button", "mo-next", "다음 일정 " + (nx.d.getMonth() + 1) + "/" + nx.d.getDate() + " · " + nx.t[0].title + (nx.t.length > 1 ? " 외 " + (nx.t.length - 1) + "건" : ""));
        bt.type = "button";
        bt.onclick = function () { view = new Date(nx.d.getFullYear(), nx.d.getMonth(), 1); sel = nx.d; draw(); focusSel(); };
        li.appendChild(bt);
      }
      list.appendChild(li);
    }
    rt.forEach(function (t) { list.appendChild(item(t, sel)); });
    var note = document.getElementById("moMine"); if (note) note.hidden = !mine;
  }
  function draw() { drawCal(); drawList(); }
  cal.addEventListener("click", function (ev) {
    var b = ev.target.closest ? ev.target.closest(".mc-d") : null; if (!b) return;
    sel = new Date(view.getFullYear(), view.getMonth(), +b.dataset.d); draw(); focusSel();
  });
  cal.addEventListener("keydown", function (ev) {
    var k = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[ev.key];
    if (!k || !ev.target.classList || !ev.target.classList.contains("mc-d")) return;
    ev.preventDefault();
    sel = new Date(view.getFullYear(), view.getMonth(), +ev.target.dataset.d + k);
    view = new Date(sel.getFullYear(), sel.getMonth(), 1); draw(); focusSel();
  });
  draw();
  window.__mocal = { occursOn: occursOn, tasks: function () { return T; } };
})();
