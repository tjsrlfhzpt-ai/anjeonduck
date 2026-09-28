/* 안전duck — 검색·필터·정렬·즐겨찾기. 서버 호출 없음. */
(function () {
  "use strict";
  var FAV_KEY = "anjeonduck.fav.v1";

  function readFav() {
    try { var v = JSON.parse(localStorage.getItem(FAV_KEY) || "[]"); return Array.isArray(v) ? v : []; }
    catch (e) { return []; }
  }
  function writeFav(list) {
    try { localStorage.setItem(FAV_KEY, JSON.stringify(list)); return true; } catch (e) { return false; }
  }
  function todayStr() {
    var d = new Date(), m = d.getMonth() + 1, day = d.getDate();
    return d.getFullYear() + "-" + (m < 10 ? "0" : "") + m + "-" + (day < 10 ? "0" : "") + day;
  }
  function daysBetween(a, b) {
    return Math.round((Date.parse(b + "T00:00:00") - Date.parse(a + "T00:00:00")) / 86400000);
  }
  var isDate = function (s) { return /^\d{4}-\d{2}-\d{2}$/.test(s || ""); };

  // 1) 마감 상태를 방문 시점 기준으로 다시 계산 (사이트는 하루 1회만 빌드되므로)
  var today = todayStr();
  document.querySelectorAll("[data-deadline]").forEach(function (el) {
    var dl = el.getAttribute("data-deadline");
    if (!isDate(dl)) return;
    var left = daysBetween(today, dl);
    el.classList.toggle("closed", left < 0);
    var badge = el.querySelector("[data-dl-badge]");
    if (!badge) return;
    var md = dl.slice(5).replace("-", ".");
    var txt, cls;
    if (left < 0) { txt = "마감"; cls = "badge-muted"; }
    else if (left === 0) { txt = "오늘 마감"; cls = "badge-soon"; }
    else if (left <= 3) { txt = "D-" + left; cls = "badge-soon"; }
    else if (left <= 7) { txt = "D-" + left; cls = "badge-orange"; }
    else { txt = el.classList.contains("apply-card") ? "D-" + left : md + " 마감"; cls = "badge-line"; }
    badge.textContent = txt;
    badge.className = "badge " + cls;
  });

  // 2) 홈 검색 범위(서식 / 채용)
  var sf = document.querySelector("[data-scope-form]");
  if (sf) {
    sf.addEventListener("change", function (ev) {
      if (ev.target.name === "scope") sf.setAttribute("action", ev.target.value);
    });
    sf.addEventListener("submit", function () {
      var s = sf.querySelector('input[name="scope"]:checked');
      if (s) { sf.setAttribute("action", s.value); s.disabled = true; } // 주소에 scope= 가 붙지 않게
    });
  }

  // 3) 즐겨찾기
  var favs = readFav();
  function paintFav() {
    document.querySelectorAll("[data-fav]").forEach(function (b) {
      var on = favs.indexOf(b.getAttribute("data-fav")) >= 0;
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.textContent = on ? "★" : "☆";
      b.setAttribute("aria-label", on ? "즐겨찾기 해제" : "즐겨찾기");
    });
  }
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-fav]");
    if (!b) return;
    var id = b.getAttribute("data-fav"), i = favs.indexOf(id);
    if (i >= 0) favs.splice(i, 1); else favs.push(id);
    if (!writeFav(favs)) b.title = "이 브라우저에서는 즐겨찾기를 저장할 수 없습니다(사생활 보호 모드 등).";
    paintFav();
    apply();
  });
  paintFav();

  // 4) 목록 필터
  var list = document.querySelector("[data-list]");
  var q = document.querySelector(".filter-q");
  var hideClosed = document.querySelector(".hide-closed");
  var onlyFav = document.querySelector(".only-fav");
  var countEl = document.querySelector("[data-count]");
  var emptyEl = document.querySelector("[data-empty]");
  var sortEl = document.querySelector(".sort");
  var ATTR = { job: "data-job", ctype: "data-ctype", industry: "data-industry", cat: "data-cat" };

  function selected() {
    var s = {};
    document.querySelectorAll("[data-filter]").forEach(function (g) {
      var on = g.querySelector('.chip[aria-pressed="true"]');
      s[g.getAttribute("data-filter")] = on ? on.getAttribute("data-value") : "";
    });
    return s;
  }

  function apply() {
    if (!list) return;
    var terms = (q && q.value ? q.value : "").toLowerCase().split(/\s+/).filter(Boolean);
    var sel = selected(), shown = 0;
    list.querySelectorAll("[data-item]").forEach(function (it) {
      var text = (it.getAttribute("data-text") || "").toLowerCase();
      var ok = terms.every(function (t) { return text.indexOf(t) >= 0; });
      Object.keys(sel).forEach(function (k) {
        if (!ok || !sel[k]) return;
        var v = it.getAttribute(ATTR[k]) || "";
        ok = k === "job" ? v.split("|").indexOf(sel[k]) >= 0 : v === sel[k];
      });
      if (ok && hideClosed && hideClosed.checked && it.classList.contains("closed")) ok = false;
      if (ok && onlyFav && onlyFav.checked && favs.indexOf(it.getAttribute("data-id")) < 0) ok = false;
      it.hidden = !ok;
      if (ok) shown++;
    });
    if (countEl) countEl.textContent = shown;
    if (emptyEl) {
      emptyEl.hidden = shown !== 0;
      var p = emptyEl.querySelector("p");
      if (p && !p.getAttribute("data-default")) p.setAttribute("data-default", p.textContent);
      if (p) p.textContent = (onlyFav && onlyFav.checked && favs.length === 0)
        ? "아직 즐겨찾기한 자료가 없습니다. 목록 오른쪽 ☆를 눌러 추가하세요."
        : p.getAttribute("data-default");
    }
  }

  function sortList() {
    if (!list || !sortEl) return;
    var mode = sortEl.value;
    var items = Array.prototype.slice.call(list.querySelectorAll("[data-item]"));
    items.sort(function (a, b) {
      var ca = a.classList.contains("closed") ? 1 : 0, cb = b.classList.contains("closed") ? 1 : 0;
      if (ca !== cb) return ca - cb;
      if (mode === "deadline") {
        var da = a.getAttribute("data-deadline"), db = b.getAttribute("data-deadline");
        var ka = isDate(da) ? da : "9999", kb = isDate(db) ? db : "9999"; // 상시 등은 뒤로
        return ka < kb ? -1 : ka > kb ? 1 : 0;
      }
      var pa = a.getAttribute("data-posted") || "", pb = b.getAttribute("data-posted") || "";
      return pa > pb ? -1 : pa < pb ? 1 : 0;
    });
    items.forEach(function (it) { list.appendChild(it); });
  }

  document.addEventListener("click", function (ev) {
    var c = ev.target.closest(".chip");
    if (c && c.parentNode.hasAttribute("data-filter")) {
      c.parentNode.querySelectorAll(".chip").forEach(function (x) { x.setAttribute("aria-pressed", "false"); });
      c.setAttribute("aria-pressed", "true");
      apply();
      return;
    }
    if (ev.target.closest("[data-reset]")) {
      document.querySelectorAll("[data-filter]").forEach(function (g) {
        g.querySelectorAll(".chip").forEach(function (x) {
          x.setAttribute("aria-pressed", x.getAttribute("data-value") === "" ? "true" : "false");
        });
      });
      if (q) q.value = "";
      apply();
    }
  });
  if (q) q.addEventListener("input", apply);
  [hideClosed, onlyFav].forEach(function (x) { if (x) x.addEventListener("change", apply); });
  if (sortEl) sortEl.addEventListener("change", sortList);

  // 좁은 화면에서는 필터 패널을 접은 채로 시작
  var fp = document.querySelector("[data-fpanel]");
  if (fp && window.matchMedia && window.matchMedia("(max-width: 900px)").matches) fp.removeAttribute("open");

  // 홈 검색창에서 넘어온 ?q= 반영
  try {
    var pq = new URLSearchParams(location.search).get("q");
    if (pq && q) q.value = pq;
  } catch (e) { /* 구형 브라우저: 무시 */ }
  sortList();
  apply();
})();
