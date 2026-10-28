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
    // 휴대폰에선 헤더 폭이 좁아 '운영 관리·로그아웃'을 헤더에서 숨기고(CSS), 전체 메뉴 서랍 맨 위에 같은 링크를 둔다.
    var mp = document.querySelector("#mnav .mnav-hd");
    if (mp) {
      var acc = document.createElement("div"); acc.className = "mnav-acc";
      [my, ad, out].forEach(function (a) { if (!a) return; var c = a.cloneNode(true); c.className = "mnav-acc-a"; acc.appendChild(c); });
      mp.parentNode.insertBefore(acc, mp.nextSibling);
    }
  })();

  // 0-1) PC 펼침 메뉴: 마우스를 아래 메뉴로 비스듬히 옮길 때 옆 항목(채용·게시판 등)을 스치면
  //      펼친 메뉴가 바로 바뀌어 사라지던 문제를 막는다. 다른 항목으로 바꿀 때만 잠깐(0.2초) 기다린다.
  (function () {
    var gnb = document.querySelector(".hd .gnb"); if (!gnb) return;
    var items = [].slice.call(gnb.querySelectorAll(".gnb-item")).filter(function (it) { return it.querySelector(".mega"); });
    if (!items.length) return;
    gnb.classList.add("js-mega");
    var cur = null, swT = 0, clT = 0;
    function open(it) { clearTimeout(swT); clearTimeout(clT); if (cur && cur !== it) cur.classList.remove("is-open"); cur = it; if (it) it.classList.add("is-open"); }
    function closeAll() { clearTimeout(swT); if (cur) cur.classList.remove("is-open"); cur = null; }
    items.forEach(function (it) {
      it.addEventListener("pointerenter", function (ev) {
        if (ev.pointerType && ev.pointerType !== "mouse") return;
        clearTimeout(clT);
        if (!cur || cur === it) { clearTimeout(swT); open(it); return; }
        clearTimeout(swT); swT = setTimeout(function () { open(it); }, 200);
      });
      it.addEventListener("pointerleave", function (ev) {
        if (ev.pointerType && ev.pointerType !== "mouse") return;
        if (cur === it) { clearTimeout(clT); clT = setTimeout(closeAll, 250); }
      });
    });
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") closeAll(); });
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
  var ATTR = { job: "data-job", ctype: "data-ctype", industry: "data-industry", emp: "data-emp", career: "data-career", edu: "data-edu", cat: "data-cat", topic: "data-topic" };
  var MULTI = { job: 1, career: 1 }; // 한 항목에 값이 여러 개(| 구분)
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
        ok = MULTI[k] ? v.split("|").indexOf(sel[k]) >= 0 : v === sel[k];
      });
      if (ok && hideClosed && hideClosed.checked && it.classList.contains("closed")) ok = false;
      if (ok && onlyFav && onlyFav.checked && favs.indexOf(it.getAttribute("data-id")) < 0) ok = false;
      if (ok) shown++;
      it.hidden = !ok || (pageSize > 0 && shown > limit);
    });
    facets(terms, sel);
    if (countEl) countEl.textContent = shown;
    qhead(terms, sel, shown);
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
      var rawq = q && q.value ? q.value.trim() : "";
      emptyEl.querySelectorAll("[data-q-href]").forEach(function (a) { a.setAttribute("href", a.getAttribute("data-q-href") + (rawq ? "?q=" + encodeURIComponent(rawq) : "")); });
    }
  }

  // 검색어·필터가 걸려 있으면 목록 바로 위에 "‘…’ 검색 결과 n건 · 전체 보기"를 보여 준다.
  // 주소(?q= ?topic= ?cat=)로 들어온 경우에는 안내용 덩어리([data-landing])를 접어 결과가 첫 화면에 오게 한다.
  var qh = null, arrived = false, baseTitle = document.title;
  function qhead(terms, sel, shown) {
    var parts = [];
    var raw = q && q.value ? q.value.trim() : "";
    if (raw) parts.push("\u2018" + raw + "\u2019");
    Object.keys(sel).forEach(function (k) { if (sel[k]) parts.push(sel[k]); });
    if (onlyFav && onlyFav.checked) parts.push("즐겨찾기");
    var on = parts.length > 0;
    if (!on) arrived = false;
    document.body.classList.toggle("is-arrived", arrived);
    if (!qh) {
      if (!on || !countEl) return;
      var cp = countEl.closest(".count") || countEl.parentNode;
      qh = document.createElement("div"); qh.className = "qhead"; qh.setAttribute("data-qhead", "");
      qh.setAttribute("role", "status");
      qh.innerHTML = '<h2 class="qhead-t"></h2><button type="button" class="btn btn-sm btn-ghost" data-reset>전체 보기</button>';
      cp.parentNode.insertBefore(qh, cp);
    }
    qh.hidden = !on;
    var cp2 = countEl && (countEl.closest(".count") || countEl.parentNode);
    if (cp2) cp2.hidden = on;
    if (on) {
      var t = qh.querySelector(".qhead-t"); t.textContent = "";
      var b = document.createElement("span"); b.className = "qhead-k"; b.textContent = parts.join(" · ");
      var n = document.createElement("strong"); n.textContent = shown;
      t.appendChild(b); t.appendChild(document.createTextNode(raw ? " 검색 결과 " : (list && list.classList.contains("jlist") ? " 공고 " : " 자료 ")));
      t.appendChild(n); t.appendChild(document.createTextNode("건"));
    }
    document.title = on && arrived ? parts.join(" · ") + " 검색 결과 — " + baseTitle : baseTitle;
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
    function has(it, k, v) { var x = it.getAttribute(ATTR[k]) || ""; return MULTI[k] ? x.split("|").indexOf(v) >= 0 : x === v; }
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
      mb.title = open ? "" : "지금 조건에서는 0건인 항목입니다. 고르면 검색어와 다른 필터를 풀고 그 항목을 보여 줍니다.";
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
      // 지금 조건에서 0건인 선택지를 누르면 막다른 길이 되지 않게 검색어·다른 필터를 풀고 그 항목만 보여 준다
      if (c.classList.contains("chip-zero")) {
        if (q) q.value = "";
        document.querySelectorAll("[data-filter]").forEach(function (g) {
          g.classList.remove("show-zero");
          g.querySelectorAll(".chip").forEach(function (x) { x.setAttribute("aria-pressed", x.getAttribute("data-value") === "" ? "true" : "false"); });
        });
      }
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
      if (onlyFav) onlyFav.checked = false;
      try { if (location.search) history.replaceState(null, "", location.pathname + location.hash); } catch (e) {}
      limit = pageSize; apply();
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
    if (pq && q) { q.value = pq; arrived = true; }
    var sp = new URLSearchParams(location.search);
    ["topic", "cat", "emp", "career", "edu"].forEach(function (k) {
      var v = sp.get(k), g = document.querySelector('[data-filter="' + k + '"]');
      if (!v || !g) return;
      if (!g.querySelector('.chip[data-value="' + v.replace(/["\\]/g, "") + '"]')) return; // 없는 값이면 전체로 둔다
      arrived = true;
      g.querySelectorAll(".chip").forEach(function (x) { x.setAttribute("aria-pressed", x.getAttribute("data-value") === v ? "true" : "false"); });
    });
  } catch (e) { /* 구형 브라우저: 무시 */ }
  sortList();
  apply();
})();
