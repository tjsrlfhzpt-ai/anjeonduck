/* SafePlum — 검색·필터·정렬·즐겨찾기. 서버 호출 없음. */
(function () {
  "use strict";
  var FAV_KEY = "safetake.fav.v1";

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

  // 0) 헤더 회원 영역: 로그인돼 있으면 '마이페이지 · 로그아웃'으로 바꾼다.
  //    세션은 게시판(Supabase)이 이 브라우저에 저장해 둔 값을 읽기만 한다. 로그아웃은 계정 화면에서 처리한다.
  (function () {
    var box = document.getElementById("hdAuth"); if (!box) return;
    var ses = null;
    try { ses = JSON.parse(localStorage.getItem(box.getAttribute("data-key")) || "null"); } catch (e) { ses = null; }
    if (!ses || !ses.access_token || !ses.user) return;
    var acct = box.getAttribute("data-acct");
    box.textContent = "";
    var my = document.createElement("a"); my.href = acct; my.textContent = "마이페이지"; my.className = "hd-auth-my";
    var out = document.createElement("a"); out.href = acct + "?logout=1"; out.textContent = "로그아웃"; out.className = "hd-auth-out";
    var isAdm = false; try { isAdm = localStorage.getItem("safetake.adm") === ses.user.id; } catch (e) {}
    if (isAdm) { var ad = document.createElement("a"); ad.href = acct.replace(/account\/$/, "admin/"); ad.textContent = "운영 관리"; ad.className = "hd-auth-adm"; box.appendChild(ad); }
    box.appendChild(my); box.appendChild(out);
  })();

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
      b.textContent = (on ? "★" : "☆") + (b.classList.contains("fav-big") ? (on ? " 즐겨찾기됨" : " 즐겨찾기") : "");
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
  var ATTR = { job: "data-job", ctype: "data-ctype", industry: "data-industry", cat: "data-cat", topic: "data-topic" };
  var pageSize = list ? +(list.getAttribute("data-page-size") || 0) : 0, limit = pageSize;
  var moreWrap = document.querySelector("[data-more-wrap]"), moreBtn = document.querySelector("[data-more]");

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
      if (ok) shown++;
      it.hidden = !ok || (pageSize > 0 && shown > limit);
    });
    facets(terms, sel);
    if (countEl) countEl.textContent = shown;
    if (moreWrap) {
      moreWrap.hidden = !(pageSize > 0 && shown > limit);
      if (moreBtn) moreBtn.textContent = "더 보기 (" + Math.min(limit, shown) + " / " + shown + ")";
    }
    if (emptyEl) {
      emptyEl.hidden = shown !== 0;
      var p = emptyEl.querySelector("p");
      if (p && !p.getAttribute("data-default")) p.setAttribute("data-default", p.textContent);
      if (p) p.textContent = (onlyFav && onlyFav.checked && favs.length === 0)
        ? "아직 즐겨찾기한 자료가 없습니다. 목록 오른쪽 ☆를 눌러 추가하세요."
        : p.getAttribute("data-default");
    }
  }

  // 눌러도 결과가 0건인 선택지는 숨긴다(다른 필터·검색어 조건은 그대로 둔 채, 그 선택지를 골랐을 때의 건수로 판단)
  function facets(terms, sel) {
    var items = Array.prototype.slice.call(list.querySelectorAll("[data-item]")).map(function (it) {
      var text = (it.getAttribute("data-text") || "").toLowerCase();
      var base = terms.every(function (t) { return text.indexOf(t) >= 0; });
      if (base && hideClosed && hideClosed.checked && it.classList.contains("closed")) base = false;
      if (base && onlyFav && onlyFav.checked && favs.indexOf(it.getAttribute("data-id")) < 0) base = false;
      return base ? it : null;
    }).filter(Boolean);
    function has(it, k, v) { var x = it.getAttribute(ATTR[k]) || ""; return k === "job" ? x.split("|").indexOf(v) >= 0 : x === v; }
    document.querySelectorAll("[data-filter]").forEach(function (g) {
      var k = g.getAttribute("data-filter"); if (!ATTR[k]) return;
      var rest = items.filter(function (it) { return Object.keys(sel).every(function (o) { return o === k || !sel[o] || has(it, o, sel[o]); }); });
      var zero = 0;
      g.querySelectorAll(".chip").forEach(function (c) {
        var v = c.getAttribute("data-value"), cn = c.querySelector(".n");
        if (!v) { if (cn) cn.textContent = rest.length; return; }
        var n = rest.filter(function (it) { return has(it, k, v); }).length;
        if (cn) cn.textContent = n;
        var z = n === 0 && c.getAttribute("aria-pressed") !== "true";
        c.classList.toggle("chip-zero", z); if (z) zero++;
      });
      // 0건인 선택지는 접어 두고 '더보기'로 펼친다
      var mb = g.querySelector(".chip-more");
      if (!mb) {
        mb = document.createElement("button"); mb.type = "button"; mb.className = "chip-more";
        mb.addEventListener("click", function () { g.classList.toggle("show-zero"); apply(); });
        g.appendChild(mb);
      }
      var open = g.classList.contains("show-zero");
      mb.hidden = zero === 0; mb.setAttribute("aria-expanded", String(open));
      mb.textContent = open ? "접기" : "더보기 +" + zero;
    });
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
      limit = pageSize; apply();
      return;
    }
    var go = ev.target.closest("[data-topic-go]");
    if (go) {
      var g = document.querySelector('[data-filter="topic"]');
      if (g) {
        ev.preventDefault();
        document.querySelectorAll('[data-filter] .chip').forEach(function (x) { x.setAttribute("aria-pressed", x.getAttribute("data-value") === "" ? "true" : "false"); });
        g.querySelectorAll(".chip").forEach(function (x) { x.setAttribute("aria-pressed", x.getAttribute("data-value") === go.getAttribute("data-topic-go") ? "true" : "false"); });
        if (q) q.value = "";
        limit = pageSize; apply();
        var tgt = document.getElementById("res-list"); if (tgt) tgt.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      return;
    }
    if (ev.target.closest("[data-reset]")) {
      document.querySelectorAll("[data-filter].show-zero").forEach(function (g) { g.classList.remove("show-zero"); });
      document.querySelectorAll("[data-filter]").forEach(function (g) {
        g.querySelectorAll(".chip").forEach(function (x) {
          x.setAttribute("aria-pressed", x.getAttribute("data-value") === "" ? "true" : "false");
        });
      });
      if (q) q.value = "";
      apply();
    }
  });
  function applyReset() { limit = pageSize; apply(); }
  if (moreBtn) moreBtn.addEventListener("click", function () { limit += pageSize; apply(); });
  if (q) q.addEventListener("input", applyReset);
  [hideClosed, onlyFav].forEach(function (x) { if (x) x.addEventListener("change", apply); });
  if (sortEl) sortEl.addEventListener("change", sortList);

  // 좁은 화면에서는 필터 패널을 접은 채로 시작
  var fp = document.querySelector("[data-fpanel]");
  if (fp && window.matchMedia && window.matchMedia("(max-width: 900px)").matches) fp.removeAttribute("open");

  // 홈 검색창에서 넘어온 ?q= 반영
  try {
    var pq = new URLSearchParams(location.search).get("q");
    if (pq && q) q.value = pq;
    var sp = new URLSearchParams(location.search);
    ["topic", "cat"].forEach(function (k) {
      var v = sp.get(k), g = document.querySelector('[data-filter="' + k + '"]');
      if (!v || !g) return;
      g.querySelectorAll(".chip").forEach(function (x) { x.setAttribute("aria-pressed", x.getAttribute("data-value") === v ? "true" : "false"); });
    });
  } catch (e) { /* 구형 브라우저: 무시 */ }
  sortList();
  apply();
})();
