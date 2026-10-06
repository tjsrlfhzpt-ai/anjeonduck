/* SafePlum 게시판(커뮤니티 · Q&A) — 화면 전용.
   권한 검증은 여기서 하지 않는다: 누가 무엇을 쓸 수 있는지는 supabase/schema.sql 의 RLS·함수가 결정하고,
   이 파일은 그 결과(성공·거절)를 보여 줄 뿐이다. 사용자가 쓴 글은 반드시 텍스트로만 넣는다(innerHTML 금지). */
(function () {
  "use strict";
  var CFG = window.ST_CM || {}, root = document.getElementById("cm");
  if (!root) return;
  var PAGE = root.dataset.page, REL = CFG.root || "../", PER = 20;
  var BOARDS = { free: "커뮤니티", qna: "Q&A", job: "채용공고" };
  var ERR = {
    LOGIN_REQUIRED: "로그인이 필요합니다.", RATE_LIMIT: "너무 빠르게 연속으로 등록했습니다. 잠시 뒤 다시 시도하세요.",
    DAILY_LIMIT: "하루 등록 한도를 넘었습니다. 내일 다시 시도하세요.", SUSPENDED: "글쓰기가 정지된 계정입니다. 마이페이지에서 기간과 사유를 확인할 수 있습니다.", ADMIN_ONLY: "운영자만 쓸 수 있는 기능입니다.",
    CANNOT_SUSPEND_ADMIN: "운영자 계정과 자기 자신은 정지할 수 없습니다.", REASON_REQUIRED: "사유를 2자 이상 적어 주세요.", BAD_DAYS: "기간은 1~3650일 사이로 정하세요.", USER_NOT_FOUND: "회원을 찾을 수 없습니다.", NOT_FOUND: "대상을 찾을 수 없습니다. 이미 처리되었을 수 있습니다.",
    NOT_ALLOWED: "권한이 없거나 이미 삭제된 글입니다.",
    POST_NOT_FOUND: "삭제되었거나 없는 글입니다.", NICKNAME_INVALID: "닉네임은 한글·영문·숫자·밑줄 2~12자이며 운영자를 연상시키는 이름은 쓸 수 없습니다.",
    NICKNAME_TAKEN: "이미 쓰고 있는 닉네임입니다.", NICKNAME_COOLDOWN: "닉네임은 7일에 한 번만 바꿀 수 있습니다.",
    JOB_META_INVALID: "회사명(2~60자)과 지원 방법(5~300자)을 적고, 마감일은 날짜로 고르거나 비워 두세요.", IMAGES_INVALID: "사진은 3장까지, 이 화면에서 올린 사진만 붙일 수 있습니다.", JOB_DAILY_LIMIT: "채용공고는 하루 5건까지 등록할 수 있습니다.",
    "Invalid login credentials": "이메일 또는 비밀번호가 맞지 않습니다.", "Email not confirmed": "이메일 인증이 끝나지 않았습니다. 받은 메일의 인증 링크를 눌러 주세요.",
    "rate limit": "요청이 많아 잠시 막혔습니다. 몇 분 뒤 다시 시도하세요.", "posts_title_check": "제목은 2~80자로 적어 주세요.",
    "posts_body_check": "본문은 5~5,000자로 적어 주세요.", "comments_body_check": "댓글은 1~2,000자로 적어 주세요.",
    "Failed to fetch": "서버에 연결하지 못했습니다. 인터넷 연결을 확인하고 다시 시도하세요.", "JWT expired": "로그인이 만료되었습니다. 다시 로그인해 주세요.",
    "should be at least": "비밀번호는 8자 이상으로 정해 주세요.", "same as the old": "이전과 다른 비밀번호를 적어 주세요."
  };
  function msg(e) {
    var m = String((e && (e.message || e.error_description)) || e || "");
    for (var k in ERR) if (m.toLowerCase().indexOf(k.toLowerCase()) >= 0) return ERR[k];
    if (window.console) console.error("[게시판]", e);
    return "처리하지 못했습니다. 잠시 뒤 다시 시도하세요." + (m ? " (" + m.slice(0, 80) + ")" : "");
  }

  // ---- DOM 도우미: 문자열은 항상 텍스트 노드로 들어간다
  function h(tag, attrs) {
    var el = document.createElement(tag), i, k;
    for (k in attrs || {}) {
      if (attrs[k] == null || attrs[k] === false) continue;
      if (k === "class") el.className = attrs[k];
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), attrs[k]);
      else if (k === "hidden" || k === "disabled" || k === "required" || k === "checked") el[k] = !!attrs[k];
      else el.setAttribute(k, attrs[k]);
    }
    for (i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }
  function add(el, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) c.forEach(function (x) { add(el, x); });
    else el.appendChild(c.nodeType ? c : document.createTextNode(String(c)));
  }
  function show() { root.textContent = ""; for (var i = 0; i < arguments.length; i++) add(root, arguments[i]); }
  function note(text, kind) { return h("p", { class: "cm-note" + (kind ? " cm-" + kind : ""), role: kind === "err" ? "alert" : "status" }, text); }
  function loading() { show(h("p", { class: "cm-load", role: "status" }, "불러오는 중…")); }
  function qs(k) { return new URLSearchParams(location.search).get(k) || ""; }
  function url(page, params) {
    var p = new URLSearchParams(); for (var k in params || {}) if (params[k]) p.set(k, params[k]);
    var s = p.toString(); return REL + "board/" + (page ? page + "/" : "") + (s ? "?" + s : "");
  }
  function when(iso, full) {
    var d = new Date(iso), now = new Date(), p = function (n) { return (n < 10 ? "0" : "") + n; };
    if (isNaN(d)) return "";
    var hm = p(d.getHours()) + ":" + p(d.getMinutes()), ymd = d.getFullYear() + "." + p(d.getMonth() + 1) + "." + p(d.getDate());
    if (full) return ymd + " " + hm;
    return d.toDateString() === now.toDateString() ? hm : (d.getFullYear() === now.getFullYear() ? ymd.slice(5) : ymd);
  }
  function nick(row) { return (row && row.author && row.author.nickname) || "탈퇴한 회원"; }
  // 본문: 줄바꿈은 CSS(pre-wrap), https 주소만 링크로 만든다
  function rich(text) {
    var out = [], re = /https?:\/\/[^\s<>"']+/g, last = 0, m;
    while ((m = re.exec(text))) {
      var u = m[0].replace(/[.,)\]]+$/, "");
      out.push(text.slice(last, m.index), h("a", { href: u, target: "_blank", rel: "nofollow ugc noopener" }, u));
      last = m.index + u.length; re.lastIndex = last;
    }
    out.push(text.slice(last));
    return out;
  }
  function draft(key, val) {
    try {
      if (val === undefined) return JSON.parse(localStorage.getItem(key) || "null");
      if (val === null) localStorage.removeItem(key); else localStorage.setItem(key, JSON.stringify(val));
    } catch (e) { /* 저장소를 못 써도 글쓰기는 된다 */ }
    return null;
  }

  // ---- 설정 전(운영자가 아직 Supabase를 연결하지 않음)
  if (!CFG.url || !CFG.key || !window.supabase) {
    show(h("div", { class: "empty" }, h("p", { class: "cm-empty-t" }, "게시판을 준비하고 있습니다"),
      h("p", null, "회원가입과 글쓰기 기능은 개설 준비가 끝나는 대로 열립니다."),
      h("p", { class: "btns" }, h("a", { class: "btn btn-ghost", href: REL + "board/rules/" }, "이용수칙 미리 보기"))));
    return;
  }
  // 인증 메일의 링크로 들어왔는지는 주소의 # 뒤에 적혀 있다. 클라이언트가 읽고 지우기 전에 먼저 봐 둔다.
  var HASH = location.hash || "";
  var ARRIVE = /type=signup/.test(HASH) ? "signup" : /error_code=|error=/.test(HASH) ? "error" : "";
  var sb = window.supabase.createClient(CFG.url, CFG.key), ME = null, RECOVERY = false;

  function loadMe() {
    return sb.auth.getSession().then(function (r) {
      var s = r.data && r.data.session;
      if (!s) { ME = null; return null; }
      return sb.from("profiles").select("id,nickname,role,nickname_changed_at").eq("id", s.user.id).maybeSingle().then(function (p) {
        ME = { id: s.user.id, email: s.user.email, nickname: (p.data && p.data.nickname) || "회원", role: (p.data && p.data.role) || "member" };
        return ME;
      });
    });
  }
  function userBar() {
    var bar = h("div", { class: "cm-user" });
    if (ME) add(bar, [h("span", null, h("b", null, ME.nickname), " 님"), h("a", { href: url("account") }, "마이페이지"), ME.role === "admin" ? h("a", { class: "cm-adm", href: url("admin") }, "운영 관리") : null,
      h("button", { type: "button", class: "linkbtn", onclick: function () { sb.auth.signOut().then(function () { location.href = url(""); }); } }, "로그아웃")]);
    else add(bar, [h("a", { href: url("account", { next: location.pathname + location.search }) }, "로그인"), h("a", { href: url("account", { mode: "join" }) }, "회원가입")]);
    return bar;
  }
  function tabs(cur) {
    return h("div", { class: "cm-top" }, h("div", { class: "seg cm-tabs", role: "group", "aria-label": "게시판" },
      Object.keys(BOARDS).map(function (b) { return h("a", { class: "cm-tab", href: url("", { b: b }), "aria-current": b === cur ? "page" : null }, BOARDS[b]); })), userBar());
  }
  // 채용공고 마감 상태: 마감일이 없으면 상시, 지났으면 마감
  function jobState(m) {
    var d = m && /^\d{4}-\d{2}-\d{2}$/.test(m.deadline || "") ? m.deadline : "";
    if (!d) return { cls: "cm-st-ans", text: "상시", closed: false };
    var n = Math.round((Date.parse(d + "T00:00:00") - new Date(new Date().toDateString()).getTime()) / 864e5);
    if (n < 0) return { cls: "cm-st-wait", text: "마감", closed: true };
    return { cls: n <= 3 ? "cm-st-hot" : "cm-st-ok", text: n === 0 ? "오늘 마감" : "D-" + n, closed: false };
  }
  // 채용공고 화면에서는 상단 메뉴의 '채용'을 현재 위치로 표시한다(페이지는 게시판과 같은 파일을 쓴다)
  var NAV_JOB = false;
  document.addEventListener("DOMContentLoaded", function () { navJob(NAV_JOB); });  // 하단 메뉴는 이 스크립트보다 뒤에 있다
  function navJob(on) {
    NAV_JOB = on;
    [".gnb-item > a", ".dock a"].forEach(function (sel) {
      Array.prototype.forEach.call(document.querySelectorAll(sel), function (a) {
        var href = a.getAttribute("href") || "", isJob = /board\/(index\.html)?\?b=job$/.test(href), isBoard = /board\/(index\.html)?$/.test(href);
        if (isJob) { if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); }
        if (isBoard) { if (on) a.removeAttribute("aria-current"); else a.setAttribute("aria-current", "page"); }
      });
    });
  }
  function chatBox() {
    var c = CFG.chat; if (!c || !/^https:\/\/open\.kakao\.com\//.test(c.url || "")) return null;
    return h("a", { class: "cm-chat", href: c.url, target: "_blank", rel: "noopener" }, h("span", { class: "cm-chat-t" }, c.title || "오픈채팅방"), h("span", { class: "cm-chat-d" }, c.desc || ""), h("span", { class: "cm-chat-go" }, "카카오톡으로 참여 ↗"));
  }
  // ---- 사진 첨부: 브라우저에서 JPEG로 줄여(긴 변 1600px, 1MB 이하) 자기 폴더에 올린다. 다시 인코딩하므로 촬영 위치 등 EXIF 정보는 빠진다.
  var IMG_BUCKET = "post-images", IMG_MAX = 3, IMG_RE = /^[0-9a-f-]{36}\/[0-9a-z]{6,40}\.jpg$/;
  function imgUrl(path) { return CFG.url.replace(/\/+$/, "") + "/storage/v1/object/public/" + IMG_BUCKET + "/" + path; }
  function imgList(m) { return (m && Array.isArray(m.images) ? m.images : []).filter(function (x) { return typeof x === "string" && IMG_RE.test(x); }).slice(0, IMG_MAX); }
  function shrink(file) {
    return new Promise(function (ok, no) {
      if (!/^image\//.test(file.type || "")) return no(new Error("IMG_TYPE"));
      var u = URL.createObjectURL(file), im = new Image();
      im.onload = function () {
        URL.revokeObjectURL(u);
        var side = 1600, q = 0.85, tries = 0;
        (function go() {
          var k = Math.min(1, side / Math.max(im.naturalWidth, im.naturalHeight)), c = document.createElement("canvas");
          c.width = Math.max(1, Math.round(im.naturalWidth * k)); c.height = Math.max(1, Math.round(im.naturalHeight * k));
          var x = c.getContext("2d"); x.fillStyle = "#fff"; x.fillRect(0, 0, c.width, c.height); x.drawImage(im, 0, 0, c.width, c.height);
          c.toBlob(function (b) {
            if (!b) return no(new Error("IMG_TYPE"));
            if (b.size <= 1000000 || tries >= 5) return b.size <= 1000000 ? ok(b) : no(new Error("IMG_BIG"));
            tries++; q = Math.max(0.6, q - 0.1); side = Math.round(side * 0.8); go();
          }, "image/jpeg", q);
        })();
      };
      im.onerror = function () { URL.revokeObjectURL(u); no(new Error("IMG_TYPE")); };
      im.src = u;
    });
  }
  function upload(file) {
    return shrink(file).then(function (blob) {
      var path = ME.id + "/" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10) + ".jpg";
      return sb.storage.from(IMG_BUCKET).upload(path, blob, { contentType: "image/jpeg", cacheControl: "31536000", upsert: false }).then(function (r) {
        if (r.error) throw r.error;
        return path;
      });
    });
  }
  function imgErr(e) {
    var m = String((e && e.message) || e || "");
    if (/IMG_TYPE/.test(m)) return "사진 파일(JPG·PNG 등)만 올릴 수 있습니다.";
    if (/IMG_BIG/.test(m)) return "사진이 너무 큽니다. 더 작은 사진으로 올려 주세요.";
    if (/not found/i.test(m)) return "사진 첨부 기능을 준비하고 있습니다. 사진 없이 등록해 주세요.";
    if (/row-level security|unauthorized|jwt/i.test(m)) return "사진을 올릴 권한이 없습니다. 다시 로그인해 주세요.";
    return "사진을 올리지 못했습니다. 잠시 뒤 다시 시도해 주세요.";
  }
  function gallery(m) {
    var a = imgList(m); if (!a.length) return null;
    return h("div", { class: "cm-imgs" }, a.map(function (p, i) {
      return h("a", { href: imgUrl(p), target: "_blank", rel: "noopener" }, h("img", { src: imgUrl(p), alt: "첨부 사진 " + (i + 1), loading: "lazy" }));
    }));
  }
  // ---- 채용공고 공유 카드: 회사명·마감일이 들어간 정사각형 이미지를 브라우저에서 그려 저장한다(서버를 쓰지 않는다)
  function jobCard(post, m) {
    return new Promise(function (ok, no) {
      var W = 800, c = document.createElement("canvas"); c.width = W; c.height = W;
      var x = c.getContext("2d"), F = '"Pretendard Variable", Pretendard, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif';
      function rr(X, Y, w, h, r) { x.beginPath(); x.moveTo(X + r, Y); x.arcTo(X + w, Y, X + w, Y + h, r); x.arcTo(X + w, Y + h, X, Y + h, r); x.arcTo(X, Y + h, X, Y, r); x.arcTo(X, Y, X + w, Y, r); x.closePath(); }
      function fit(text, max, size, min, weight) { do { x.font = weight + " " + size + "px " + F; if (x.measureText(text).width <= max) break; size -= 4; } while (size > min); return size; }
      function wrap(text, max) {   // 두 줄까지. 띄어쓰기에서 먼저 나누고, 안 되면 글자 단위로 나눈다
        if (x.measureText(text).width <= max) return [text];
        var cut = -1, i;
        for (i = 1; i < text.length; i++) if (text.charAt(i) === " " && x.measureText(text.slice(0, i)).width <= max) cut = i;
        if (cut < 0) for (i = 1; i < text.length; i++) if (x.measureText(text.slice(0, i)).width <= max) cut = i;
        var a = text.slice(0, cut).trim(), b = text.slice(cut).trim();
        while (b.length > 1 && x.measureText(b).width > max) b = b.slice(0, -2) + "…";
        return [a, b];
      }
      x.fillStyle = "#EDE4F6"; x.fillRect(0, 0, W, W);
      x.fillStyle = "#5B2A86"; x.textAlign = "center"; x.textBaseline = "middle";
      x.font = "800 40px " + F; x.fillText("SafePlum 안전·보건 채용공고", W / 2, 110);
      x.fillStyle = "#fff"; x.shadowColor = "rgba(60,20,90,.18)"; x.shadowBlur = 24; x.shadowOffsetY = 8; rr(60, 190, W - 120, 330, 28); x.fill();
      x.shadowColor = "transparent"; x.shadowBlur = 0; x.shadowOffsetY = 0;
      var co = String(m.company || post.title || "").trim().slice(0, 60), dl = /^\d{4}-\d{2}-\d{2}$/.test(m.deadline || "") ? "(~" + (+m.deadline.slice(5, 7)) + "/" + (+m.deadline.slice(8, 10)) + ")" : "(상시 채용)";
      x.fillStyle = "#111827"; var size = fit(co, W - 200, 84, 52, "800"), lines = wrap(co, W - 200);
      if (lines.length > 1) size = Math.min(size, 60); x.font = "800 " + size + "px " + F; lines = wrap(co, W - 200);
      var y0 = 330 - (lines.length - 1) * (size * 0.62);
      lines.forEach(function (t, i) { x.fillText(t, W / 2, y0 + i * size * 1.24); });
      x.font = "800 64px " + F; x.fillStyle = "#5B2A86"; x.fillText(dl, W / 2, 460);
      x.textAlign = "left"; x.fillStyle = "#3B1B5A"; x.font = "800 44px " + F;
      var tag = String(post.category || "").trim(); x.fillText(tag ? tag + " 채용" : "안전·보건 채용", 330, 610);
      x.font = "600 30px " + F; x.fillStyle = "#5B2A86"; x.fillText(String(m.region || "").slice(0, 16) || "공고 원문에서 조건 확인", 330, 668);
      x.font = "800 34px " + F; x.fillStyle = "#111827"; x.fillText("safeplum.com", 330, 730);
      var im = new Image();
      function done() { c.toBlob(function (b) { b ? ok(b) : no(new Error("CARD")); }, "image/png"); }
      im.onload = function () { x.drawImage(im, 70, 540, 230, 230); done(); };
      im.onerror = done;
      im.src = REL + "assets/img/plum/hero.webp";
    });
  }
  function busy(btn, on, label) { btn.disabled = on; if (label) btn.textContent = label; }

  // ---------------------------------------------------------------- 목록
  function pageList() {
    var b = BOARDS[qs("b")] ? qs("b") : "free", cat = qs("c"), kw = qs("q").slice(0, 40), p = Math.max(1, parseInt(qs("p"), 10) || 1);
    document.title = BOARDS[b] + " | " + document.title.split(" | ").pop();
    navJob(b === "job");
    loading();
    var job = b === "job";
    var q = sb.from("posts").select("id,board,category,title,created_at,comment_count,accepted_comment_id,notice," + (job ? "meta," : "") + "author:profiles(nickname)", { count: "exact" })
      .eq("board", b).order("notice", { ascending: false }).order("created_at", { ascending: false }).range((p - 1) * PER, p * PER - 1);
    if (cat) q = q.eq("category", cat);
    if (kw) q = q.ilike("title", "%" + kw.replace(/[\\%_]/g, "\\$&") + "%");
    q.then(function (r) {
      if (r.error && job && /meta/.test(String(r.error.message || ""))) return show(tabs(b), chatBox(), h("div", { class: "empty" }, h("p", { class: "cm-empty-t" }, "채용공고 게시판을 준비하고 있습니다"), h("p", null, "곧 회원이 직접 채용공고를 올릴 수 있게 됩니다.")));
      if (r.error) return show(tabs(b), note(msg(r.error), "err"), h("p", { class: "btns" }, h("button", { type: "button", class: "btn btn-ghost", onclick: pageList }, "다시 시도")));
      var rows = r.data || [], total = r.count || 0, pages = Math.max(1, Math.ceil(total / PER));
      var cats = (CFG.cats && CFG.cats[b]) || [];
      var filter = h("div", { class: "cm-filter" },
        h("div", { class: "chips" }, [h("a", { class: "chip", href: url("", { b: b, q: kw }), "aria-current": !cat ? "true" : null }, "전체")].concat(
          cats.map(function (c) { return h("a", { class: "chip", href: url("", { b: b, c: c, q: kw }), "aria-current": c === cat ? "true" : null }, c); }))),
        h("form", { class: "cm-search", role: "search", onsubmit: function (ev) { ev.preventDefault(); location.href = url("", { b: b, c: cat, q: this.q.value.trim() }); } },
          h("input", { type: "search", name: "q", value: kw, placeholder: "제목 검색", "aria-label": "제목 검색", maxlength: "40" }), h("button", { type: "submit", class: "btn btn-sm btn-ghost" }, "검색")),
        h("a", { class: "btn btn-sm", href: ME ? url("write", { b: b }) : url("account", { next: url("write", { b: b }) }) }, b === "qna" ? "질문하기" : job ? "공고 등록" : "글쓰기"));
      var list = h("ul", { class: "cm-list" }, rows.map(function (x) {
        var state = b === "qna" ? h("span", { class: "cm-st " + (x.accepted_comment_id ? "cm-st-ok" : x.comment_count ? "cm-st-ans" : "cm-st-wait") }, x.accepted_comment_id ? "채택 완료" : x.comment_count ? "답변 " + x.comment_count : "답변 대기") : null;
        if (job && !x.notice) {
          var m = x.meta || {}, js = jobState(m);
          return h("li", { class: js.closed ? "cm-closed" : null }, h("a", { href: url("view", { id: x.id }) },
            h("span", { class: "cm-cat" }, x.category || "채용"),
            h("span", { class: "cm-t" }, h("b", { class: "cm-co" }, m.company || ""), " ", x.title, m.region ? h("span", { class: "cm-rg" }, " · " + m.region) : null),
            h("span", { class: "cm-st " + js.cls }, js.text), h("span", { class: "cm-meta" }, h("time", { datetime: x.created_at }, when(x.created_at)))));
        }
        return h("li", { class: x.notice ? "cm-notice" : null }, h("a", { href: url("view", { id: x.id }) },
          h("span", { class: "cm-cat" }, x.notice ? "공지" : (x.category || BOARDS[b])),
          h("span", { class: "cm-t" }, x.title, b !== "qna" && x.comment_count ? h("em", { "aria-label": "댓글 " + x.comment_count + "개" }, " [" + x.comment_count + "]") : null),
          state, h("span", { class: "cm-meta" }, nick(x), " · ", h("time", { datetime: x.created_at }, when(x.created_at)))));
      }));
      var empty = !rows.length ? h("div", { class: "empty" }, kw || cat ? null : h("img", { class: "cm-empty-i", src: REL + "assets/img/ico/" + (b === "qna" ? "ask" : job ? "helmet" : "chat") + ".webp", width: "96", height: "96", alt: "" }), h("p", null, kw || cat ? "조건에 맞는 글이 없습니다." : (b === "qna" ? "아직 질문이 없습니다. 첫 질문을 남겨 보세요." : job ? "아직 등록된 채용공고가 없습니다. 회원이면 누구나 공고를 올릴 수 있습니다." : "아직 글이 없습니다. 첫 글을 남겨 보세요."))) : null;
      var pager = pages > 1 ? h("nav", { class: "cm-pager", "aria-label": "페이지" },
        p > 1 ? h("a", { class: "btn btn-sm btn-ghost", href: url("", { b: b, c: cat, q: kw, p: p - 1 }) }, "← 이전") : null,
        h("span", null, p + " / " + pages), p < pages ? h("a", { class: "btn btn-sm btn-ghost", href: url("", { b: b, c: cat, q: kw, p: p + 1 }) }, "다음 →") : null) : null;
      show(tabs(b), job ? chatBox() : null, filter, empty || list, pager,
        job ? h("p", { class: "cm-more" }, h("a", { href: REL + "jobs/" }, "고용24·사람인 등 다른 채용 사이트에서 더 찾기 →")) : null,
        job ? h("p", { class: "src-note" }, "채용공고는 회원이 직접 올린 것입니다. SafePlum은 채용을 알선하거나 내용을 보증하지 않으며, 조건·마감일은 공고를 올린 회사에 확인하세요. 금전·개인 금융정보를 요구하는 공고는 신고해 주세요.") : null);
    }, function (e) { show(tabs(b), note(msg(e), "err")); });
  }

  // ---------------------------------------------------------------- 글 보기
  function pageView() {
    var id = parseInt(qs("id"), 10);
    if (!id) return show(note("주소가 올바르지 않습니다.", "err"), h("p", { class: "btns" }, h("a", { class: "btn btn-ghost", href: url("") }, "목록으로")));
    loading();
    Promise.all([
      sb.from("posts").select("*,author:profiles(nickname)").eq("id", id).maybeSingle(),
      sb.from("comments").select("id,body,created_at,author_id,author:profiles(nickname)").eq("post_id", id).order("created_at", { ascending: true }).limit(500)
    ]).then(function (rs) {
      var post = rs[0].data, err = rs[0].error || rs[1].error;
      if (err) return show(note(msg(err), "err"));
      if (!post) return show(h("div", { class: "empty" }, h("p", null, "삭제되었거나 없는 글입니다."), h("p", { class: "btns" }, h("a", { class: "btn btn-ghost", href: url("") }, "목록으로"))));
      var job = post.board === "job", jm = (job && post.meta) || {}, jst = job ? jobState(jm) : null; navJob(job);
      var qna = post.board === "qna", cms = rs[1].data || [], mine = ME && ME.id === post.author_id, admin = ME && ME.role === "admin", word = qna ? "답변" : "댓글";
      document.title = post.title + " | " + document.title.split(" | ").pop();
      function rpc(name, args, confirmText, after) {
        return function () {
          if (confirmText && !window.confirm(confirmText)) return;
          sb.rpc(name, args).then(function (r) { if (r.error) window.alert(msg(r.error)); else after(); });
        };
      }
      function report(type, tid) {
        return function () {
          if (!ME) { location.href = url("account", { next: location.pathname + location.search }); return; }
          var why = window.prompt("신고 사유를 적어 주세요(2~300자). 운영자가 확인한 뒤 조치합니다.");
          if (why == null) return;
          if (why.trim().length < 2) return window.alert("신고 사유를 2자 이상 적어 주세요.");
          sb.rpc("report_content", { p_type: type, p_id: tid, p_reason: why.trim().slice(0, 300) }).then(function (r) { window.alert(r.error ? msg(r.error) : "신고가 접수되었습니다."); });
        };
      }
      var acts = h("p", { class: "cm-acts" },
        mine ? h("a", { href: url("write", { id: post.id }) }, "수정") : null,
        mine || admin ? h("button", { type: "button", class: "linkbtn", onclick: rpc("delete_post", { p_id: post.id }, "이 글을 삭제할까요?", function () { location.href = url("", { b: post.board }); }) }, admin && !mine ? "삭제(운영자)" : "삭제") : null,
        !mine ? h("button", { type: "button", class: "linkbtn", onclick: report("post", post.id) }, "신고") : null,
        admin ? h("button", { type: "button", class: "linkbtn", onclick: rpc("admin_set_notice", { p_id: post.id, p_on: !post.notice }, post.notice ? "공지를 해제할까요?" : "이 글을 공지로 올릴까요?", pageView) }, post.notice ? "공지 해제" : "공지 지정") : null,
        admin && !mine && post.author ? h("a", { class: "linkbtn", href: url("admin", { tab: "members", q: post.author.nickname }) }, "작성자 관리") : null);
      var art = h("article", { class: "cm-post" },
        h("p", { class: "cm-post-cat" }, h("a", { href: url("", { b: post.board }) }, BOARDS[post.board]), post.category ? " · " + post.category : "", post.notice ? " · 공지" : ""),
        h("h2", { class: "cm-post-t" }, post.title),
        h("p", { class: "cm-post-meta" }, nick(post), " · ", h("time", { datetime: post.created_at }, when(post.created_at, true)), post.updated_at ? " · 수정됨" : ""),
        job ? h("dl", { class: "cm-job" }, [["회사", jm.company], ["근무지", jm.region], ["직무", post.category], ["경력", jm.career], ["고용형태", jm.employment], ["마감", (jm.deadline || "상시 채용") + (jst.closed ? " (마감됨)" : "")]].filter(function (x) { return x[1]; }).map(function (x) { return [h("dt", null, x[0]), h("dd", null, x[1])]; })) : null,
        h("div", { class: "cm-body" }, rich(post.body)),
        gallery(post.meta),
        job ? h("p", { class: "cm-share" },
          h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: function () {
            var b = this; busy(b, true, "만드는 중…");
            (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(function () { return jobCard(post, jm); }).then(function (blob) {
              var a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "SafePlum_채용_" + String(jm.company || "공고").replace(/[\\/:*?"<>|\s]+/g, "_").slice(0, 30) + ".png";
              document.body.appendChild(a); a.click(); a.remove(); setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000); busy(b, false, "공유 카드 저장");
            }, function () { busy(b, false, "공유 카드 저장"); window.alert("카드를 만들지 못했습니다."); });
          } }, "공유 카드 저장"),
          h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: function () {
            var b = this, t = (jm.company ? jm.company + " " : "") + post.title + (jm.deadline ? " (~" + (+jm.deadline.slice(5, 7)) + "/" + (+jm.deadline.slice(8, 10)) + ")" : "") + "\n" + location.href;
            var fin = function () { b.textContent = "복사했습니다"; setTimeout(function () { b.textContent = "제목·링크 복사"; }, 1600); };
            if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t).then(fin, function () { window.prompt("아래 내용을 복사하세요", t); });
            else window.prompt("아래 내용을 복사하세요", t);
          } }, "제목·링크 복사"),
          h("span", { class: "hint" }, "오픈채팅·메신저에 올릴 때 쓰세요.")) : null,
        job ? h("div", { class: "cm-apply" }, h("b", null, "지원 방법"), /^https:\/\/\S+$/.test(jm.apply || "") ? h("a", { class: "btn" + (jst.closed ? " btn-ghost" : ""), href: jm.apply, target: "_blank", rel: "nofollow ugc noopener" }, "지원 페이지 열기 ↗") : h("span", null, rich(jm.apply || ""))) : null,
        acts);
      var clist = h("ul", { class: "cm-cms" }, cms.map(function (c) {
        var cmine = ME && ME.id === c.author_id, picked = post.accepted_comment_id === c.id;
        return h("li", { class: picked ? "cm-picked" : null },
          h("p", { class: "cm-cm-meta" }, picked ? h("span", { class: "cm-st cm-st-ok" }, "질문자 채택") : null, h("b", null, nick(c)), " · ", h("time", { datetime: c.created_at }, when(c.created_at, true))),
          h("div", { class: "cm-body" }, rich(c.body)),
          h("p", { class: "cm-acts" },
            qna && (mine || admin) ? h("button", { type: "button", class: "linkbtn", onclick: rpc("accept_answer", { p_comment: c.id }, null, pageView) }, picked ? "채택 취소" : "이 답변 채택") : null,
            cmine || admin ? h("button", { type: "button", class: "linkbtn", onclick: rpc("delete_comment", { p_id: c.id }, "이 " + word + "을 삭제할까요?", pageView) }, "삭제") : null,
            !cmine ? h("button", { type: "button", class: "linkbtn", onclick: report("comment", c.id) }, "신고") : null));
      }));
      var form;
      if (ME) {
        var ta = h("textarea", { name: "body", rows: "4", maxlength: "2000", required: true, placeholder: qna ? "아는 내용을 근거(법 조문·고시·공식 자료)와 함께 적어 주세요." : "댓글을 적어 주세요.", "aria-label": word + " 내용" });
        var out = h("p", { class: "cm-note", role: "status", hidden: true }), btn = h("button", { type: "submit", class: "btn" }, word + " 등록");
        form = h("form", { class: "cm-form", onsubmit: function (ev) {
          ev.preventDefault();
          var body = ta.value.trim(); if (!body) return;
          busy(btn, true, "등록 중…"); out.hidden = true;
          sb.from("comments").insert({ post_id: post.id, body: body, author_id: ME.id }).then(function (r) {
            if (r.error) { out.textContent = msg(r.error); out.className = "cm-note cm-err"; out.hidden = false; busy(btn, false, word + " 등록"); }
            else pageView();
          });
        } }, ta, out, h("p", { class: "btns" }, btn));
      } else form = h("p", { class: "cm-note" }, word + "을 쓰려면 ", h("a", { href: url("account", { next: location.pathname + location.search }) }, "로그인"), "이 필요합니다.");
      show(tabs(post.board), art, h("h3", { class: "h-sm cm-cms-h" }, word + " " + cms.length), cms.length ? clist : h("p", { class: "hint" }, "아직 " + word + "이 없습니다."), form,
        job ? h("p", { class: "src-note" }, "이 공고는 회원이 직접 올린 것입니다. SafePlum은 채용을 알선하거나 내용을 보증하지 않습니다. 지원 전 회사와 조건을 직접 확인하고, 금전이나 통장·비밀번호를 요구하면 응하지 말고 신고해 주세요.") : null,
        qna ? h("p", { class: "src-note" }, "답변은 회원 개인의 의견이며 법령 해석이나 공식 답변이 아닙니다. 법 적용 여부는 법령 원문과 고용노동부 등 소관 기관에서 확인하세요.") : null,
        h("p", { class: "btns" }, h("a", { class: "btn btn-ghost", href: url("", { b: post.board }) }, "목록으로")));
    }, function (e) { show(note(msg(e), "err")); });
  }

  // ---------------------------------------------------------------- 글쓰기·수정
  function pageWrite() {
    if (!ME) { location.replace(url("account", { next: location.pathname + location.search })); return; }
    var id = parseInt(qs("id"), 10) || 0, b0 = BOARDS[qs("b")] ? qs("b") : "free";
    function form(post) {
      var b = post ? post.board : b0, key = "st.cm.draft." + (id || "new");
      var saved = draft(key) || {};
      var selB = h("select", { name: "board", "aria-label": "게시판", disabled: !!post }, Object.keys(BOARDS).map(function (k) { return h("option", { value: k }, BOARDS[k]); }));
      selB.value = b;
      var selC = h("select", { name: "category", "aria-label": "분류" });
      function fillCats() {
        selC.textContent = ""; add(selC, h("option", { value: "" }, "분류 선택(선택 사항)"));
        ((CFG.cats && CFG.cats[selB.value]) || []).forEach(function (c) { add(selC, h("option", { value: c }, c)); });
      }
      fillCats(); selB.addEventListener("change", fillCats);
      selC.value = (post && post.category) || saved.category || "";
      var title = h("input", { type: "text", name: "title", maxlength: "80", required: true, placeholder: "제목 (2~80자)", "aria-label": "제목", value: (saved.title != null ? saved.title : (post && post.title)) || "" });
      var body = h("textarea", { name: "body", rows: "14", maxlength: "5000", required: true, "aria-label": "본문", placeholder: "내용 (5~5,000자)\n\n· 사람 이름·연락처·사업장명 등 개인이나 회사를 알아볼 수 있는 정보는 적지 마세요.\n· 사고 사례는 누구인지 알 수 없게 적어 주세요." });
      body.value = (saved.body != null ? saved.body : (post && post.body)) || "";
      var cnt = h("span", { class: "hint" }), out = h("p", { class: "cm-note cm-err", role: "alert", hidden: true }), btn = h("button", { type: "submit", class: "btn" }, post ? "수정 저장" : "등록");
      // 채용공고 전용 칸
      var pm = (post && post.meta) || {}, sm = saved.meta || {};
      function jv(k) { return sm[k] != null ? sm[k] : (pm[k] || ""); }
      var J = {
        company: h("input", { type: "text", maxlength: "60", placeholder: "회사명 (필수)", "aria-label": "회사명", value: jv("company") }),
        region: h("input", { type: "text", maxlength: "40", placeholder: "근무지 (예: 경기 화성)", "aria-label": "근무지", value: jv("region") }),
        career: h("input", { type: "text", maxlength: "40", placeholder: "경력 (예: 신입·경력 3년 이상)", "aria-label": "경력", value: jv("career") }),
        employment: h("select", { "aria-label": "고용형태" }, ["", "정규직", "계약직", "파견·도급", "인턴", "기타"].map(function (v) { return h("option", { value: v }, v || "고용형태 선택"); })),
        deadline: h("input", { type: "date", "aria-label": "마감일" }),
        apply: h("input", { type: "text", maxlength: "300", placeholder: "지원 방법 (필수) — 채용 페이지 주소(https://…) 또는 접수 방법", "aria-label": "지원 방법", value: jv("apply") })
      };
      J.employment.value = jv("employment"); J.deadline.value = jv("deadline");
      function jmeta() { var o = {}; Object.keys(J).forEach(function (k) { o[k] = J[k].value.trim(); }); return o; }
      var jbox = h("div", { class: "cm-jobf" }, h("div", { class: "cm-row2 cm-row2e" }, J.company, J.region), h("div", { class: "cm-row3" }, J.career, J.employment, h("label", { class: "cm-dl" }, h("span", null, "마감일"), J.deadline)),
        J.apply, h("p", { class: "hint" }, "마감일을 비워 두면 '상시 채용'으로 표시됩니다. 회사명과 지원 방법은 공고를 보는 사람이 확인할 수 있게 정확히 적어 주세요."));
      // 사진 첨부(모든 게시판)
      var imgs = imgList(saved.meta && saved.meta.images ? saved.meta : pm), imgs0 = imgList(pm);
      var pick = h("input", { type: "file", accept: "image/*", multiple: true, class: "cm-file", "aria-label": "사진 선택" });
      var pickBtn = h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: function () { pick.click(); } }, "사진 첨부");
      var thumbs = h("ul", { class: "cm-thumbs" }), pst = h("span", { class: "hint", role: "status" });
      function drawImgs() {
        thumbs.textContent = "";
        imgs.forEach(function (p, i) {
          thumbs.appendChild(h("li", null, h("img", { src: imgUrl(p), alt: "첨부 사진 " + (i + 1) }),
            h("button", { type: "button", class: "cm-thumb-x", "aria-label": "첨부 사진 " + (i + 1) + " 빼기", onclick: function () { imgs.splice(i, 1); drawImgs(); tick(); } }, "×")));
        });
        thumbs.hidden = !imgs.length; pickBtn.disabled = imgs.length >= IMG_MAX;
        pst.textContent = imgs.length + " / " + IMG_MAX + "장";
      }
      pick.addEventListener("change", function () {
        var files = Array.prototype.slice.call(pick.files || []); pick.value = "";
        if (!files.length) return;
        var room = IMG_MAX - imgs.length, over = files.length > room; files = files.slice(0, room);
        out.hidden = true; pickBtn.disabled = true; btn.disabled = true; pst.textContent = "사진을 올리는 중…";
        files.reduce(function (pr, f) { return pr.then(function () { return upload(f).then(function (path) { imgs.push(path); drawImgs(); pst.textContent = "사진을 올리는 중…"; }); }); }, Promise.resolve())
          .then(function () { if (over) { out.textContent = "사진은 " + IMG_MAX + "장까지 붙일 수 있어 나머지는 올리지 않았습니다."; out.hidden = false; } },
                function (e) { console.error("[게시판] 사진", e); out.textContent = imgErr(e); out.hidden = false; })
          .then(function () { btn.disabled = false; drawImgs(); tick(); });
      });
      var imgBox = h("div", { class: "cm-imgf" }, h("p", { class: "cm-imgf-h" }, pickBtn, pst, pick), thumbs,
        h("p", { class: "hint" }, "최대 3장. 올릴 때 자동으로 줄여 저장합니다. 얼굴·명찰·차량번호·사업장명이 보이는 사진은 가리고 올려 주세요."));
      function syncJob() {
        var on = selB.value === "job"; jbox.hidden = !on;
        title.placeholder = on ? "공고 제목 (예: 안전관리자 경력직 채용)" : "제목 (2~80자)";
        body.placeholder = on ? "상세 내용 (5~5,000자)\n\n· 담당 업무, 자격 요건, 근무 조건, 전형 절차를 적어 주세요.\n· 주민등록번호·통장 사본 등 채용과 무관한 개인정보를 요구하는 내용은 올릴 수 없습니다." : "내용 (5~5,000자)\n\n· 사람 이름·연락처·사업장명 등 개인이나 회사를 알아볼 수 있는 정보는 적지 마세요.\n· 사고 사례는 누구인지 알 수 없게 적어 주세요.";
      }
      selB.addEventListener("change", syncJob); syncJob(); navJob(selB.value === "job"); selB.addEventListener("change", function () { navJob(selB.value === "job"); });
      function tick() { cnt.textContent = body.value.length.toLocaleString() + " / 5,000자"; var dm = jmeta(); dm.images = imgs.slice(); draft(key, { title: title.value, body: body.value, category: selC.value, meta: dm }); }
      [title, body, selC].concat(Object.keys(J).map(function (k) { return J[k]; })).forEach(function (el) { el.addEventListener("input", tick); el.addEventListener("change", tick); }); drawImgs(); tick();
      show(h("form", { class: "cm-form cm-write", onsubmit: function (ev) {
        ev.preventDefault();
        var t = title.value.trim(), bd = body.value.trim();
        if (t.length < 2) { out.textContent = ERR.posts_title_check; out.hidden = false; title.focus(); return; }
        if (bd.length < 5) { out.textContent = ERR.posts_body_check; out.hidden = false; body.focus(); return; }
        var isJob = selB.value === "job", mt = isJob ? jmeta() : null;
        if (isJob && (mt.company.length < 2 || mt.apply.length < 5)) { out.textContent = ERR.JOB_META_INVALID; out.hidden = false; (mt.company.length < 2 ? J.company : J.apply).focus(); return; }
        if (isJob && /^http:\/\//i.test(mt.apply)) { out.textContent = "지원 페이지 주소는 https:// 로 시작해야 합니다."; out.hidden = false; J.apply.focus(); return; }
        busy(btn, true, "저장 중…"); out.hidden = true;
        var rowU = { title: t, body: bd, category: selC.value }, rowI = { board: selB.value, category: selC.value, title: t, body: bd, author_id: ME.id };
        var metaOut = isJob ? mt : {};
        if (imgs.length) metaOut.images = imgs.slice();
        // 사진이 없고 원래도 없던 일반 글은 meta 를 보내지 않는다(예전 DB에서도 그대로 동작)
        if (isJob || imgs.length || imgs0.length) { rowU.meta = metaOut; rowI.meta = metaOut; }
        var req = post ? sb.from("posts").update(rowU).eq("id", post.id).select("id") : sb.from("posts").insert(rowI).select("id");
        req.then(function (r) {
          var row = r.data && r.data[0];
          if (r.error || !row) { out.textContent = r.error ? msg(r.error) : ERR.NOT_ALLOWED; out.hidden = false; busy(btn, false, post ? "수정 저장" : "등록"); return; }
          draft(key, null);
          // 수정하면서 뺀 사진은 저장이 끝난 뒤에 지운다(실패해도 글은 이미 저장됨)
          var gone = imgs0.filter(function (x) { return imgs.indexOf(x) < 0; });
          var done = function () { location.href = url("view", { id: row.id }); };
          if (gone.length) sb.storage.from(IMG_BUCKET).remove(gone).then(done, done); else done();
        }, function (e) { out.textContent = msg(e) + " 작성하던 내용은 이 브라우저에 임시 저장되어 있습니다."; out.hidden = false; busy(btn, false, post ? "수정 저장" : "등록"); });
      } },
        h("div", { class: "cm-row2" }, selB, selC), jbox, title, body, imgBox, h("p", { class: "cm-cnt" }, cnt, h("span", { class: "hint" }, "작성 중인 내용은 이 브라우저에 임시 저장됩니다.")), out,
        h("p", { class: "hint" }, "등록하면 ", h("a", { href: REL + "board/rules/", target: "_blank" }, "게시판 이용수칙"), "에 동의한 것으로 봅니다. 닉네임 ", h("b", null, ME.nickname), "(으)로 공개됩니다."),
        h("p", { class: "btns" }, btn, h("a", { class: "btn btn-ghost", href: post ? url("view", { id: post.id }) : url("", { b: b }) }, "취소"))));
    }
    if (!id) return form(null);
    loading();
    sb.from("posts").select("*").eq("id", id).maybeSingle().then(function (r) {
      if (r.error) return show(note(msg(r.error), "err"));
      if (!r.data || r.data.author_id !== ME.id) return show(note("본인이 쓴 글만 수정할 수 있습니다.", "err"), h("p", { class: "btns" }, h("a", { class: "btn btn-ghost", href: url("") }, "목록으로")));
      form(r.data);
    });
  }

  // ---------------------------------------------------------------- 로그인·가입·내 계정
  function field(label, input, hint) { return h("label", { class: "cm-f" }, h("span", null, label), input, hint ? h("small", { class: "hint" }, hint) : null); }
  // 비밀번호 확인 칸: 두 번 입력해 오타를 막는다. 다르면 칸 아래에 바로 알려 주고 제출을 막는다.
  function pwConfirm(pw) {
    var c = h("input", { type: "password", autocomplete: "new-password", minlength: "8", required: true }), m = h("small", { class: "cm-pwm", "aria-live": "polite" });
    function chk() {
      var same = c.value === pw.value;
      c.setCustomValidity(c.value && !same ? "비밀번호가 서로 다릅니다." : "");
      m.textContent = !c.value ? "" : same ? "비밀번호가 일치합니다." : "비밀번호가 서로 다릅니다.";
      m.className = "cm-pwm" + (c.value ? (same ? " ok" : " no") : "");
      return same;
    }
    pw.addEventListener("input", chk); c.addEventListener("input", chk);
    return { el: h("label", { class: "cm-f" }, h("span", null, "비밀번호 확인"), c, m), same: chk, input: c };
  }
  function pageAccount() {
    var here = location.origin + location.pathname;
    function result(out, text, ok) { out.textContent = text; out.className = "cm-note " + (ok ? "cm-ok" : "cm-err"); out.hidden = false; }
    function goNext() { var n = qs("next"); location.href = n && n.charAt(0) === "/" && n.charAt(1) !== "/" ? n : url(""); }

    if (RECOVERY) {
      var np = h("input", { type: "password", autocomplete: "new-password", minlength: "8", required: true }), o0 = h("p", { hidden: true }), b0 = h("button", { type: "submit", class: "btn" }, "비밀번호 변경"), c0 = pwConfirm(np);
      return show(h("form", { class: "cm-form cm-auth", onsubmit: function (ev) {
        ev.preventDefault(); if (!c0.same()) { c0.input.focus(); return result(o0, "비밀번호가 서로 다릅니다. 다시 확인해 주세요."); } busy(b0, true);
        sb.auth.updateUser({ password: np.value }).then(function (r) { busy(b0, false); if (r.error) return result(o0, msg(r.error)); RECOVERY = false; result(o0, "비밀번호를 바꿨습니다.", true); setTimeout(function () { location.href = url(""); }, 900); });
      } }, h("h2", { class: "h-sm" }, "새 비밀번호 설정"), field("새 비밀번호", np, "8자 이상"), c0.el, o0, h("p", { class: "btns" }, b0)));
    }

    if (ARRIVE === "signup" && ME) {
      ARRIVE = "";
      return show(h("div", { class: "cm-auth cm-welcome" },
        h("img", { src: REL + "assets/img/ico/cheer.webp", width: "96", height: "96", alt: "" }),
        h("h2", { class: "h-sm" }, "가입이 완료되었습니다"),
        h("p", { class: "cm-note cm-ok" }, "이메일 인증이 끝났습니다. ", h("b", null, ME.nickname), " 님으로 로그인되어 있어 다시 로그인할 필요가 없습니다."),
        h("p", { class: "btns" }, h("a", { class: "btn btn-block", href: url("") }, "게시판 둘러보기")),
        h("p", { class: "btns" }, h("a", { class: "btn btn-ghost btn-block", href: url("write") }, "첫 글 쓰기")),
        h("p", { class: "cm-alt" }, h("a", { href: url("account") }, "마이페이지(닉네임·비밀번호 변경)"))));
    }
    if (ME) {
      var nn = h("input", { type: "text", maxlength: "12", required: true, value: ME.nickname }), o1 = h("p", { hidden: true }), b1 = h("button", { type: "submit", class: "btn btn-ghost" }, "닉네임 변경");
      var pw = h("input", { type: "password", autocomplete: "new-password", minlength: "8", required: true }), o2 = h("p", { hidden: true }), b2 = h("button", { type: "submit", class: "btn btn-ghost" }, "비밀번호 변경"), c2 = pwConfirm(pw);
      var o3 = h("p", { hidden: true }), susBox = h("p", { class: "cm-note cm-err", role: "status", hidden: true });
      sb.from("suspensions").select("until,reason").eq("user_id", ME.id).maybeSingle().then(function (r) {
        var x = r && r.data; if (!x || (x.until && new Date(x.until) <= new Date())) return;
        susBox.textContent = "글쓰기가 정지된 상태입니다. 기간: " + (x.until ? when(x.until, true) + "까지" : "기한 없음") + " · 사유: " + x.reason + " — 이의가 있으면 문의 창구로 알려 주세요.";
        susBox.hidden = false;
      }, function () {});
      return show(h("div", { class: "cm-auth" },
        h("h2", { class: "h-sm" }, "마이페이지"), susBox, h("p", { class: "cm-note" }, "이메일 ", h("b", null, ME.email), " · 이메일은 다른 회원에게 보이지 않습니다."),
        h("form", { class: "cm-form", onsubmit: function (ev) {
          ev.preventDefault(); busy(b1, true);
          sb.rpc("set_nickname", { p: nn.value.trim() }).then(function (r) { busy(b1, false); result(o1, r.error ? msg(r.error) : "닉네임을 바꿨습니다.", !r.error); });
        } }, field("닉네임", nn, "한글·영문·숫자·밑줄 2~12자 · 7일에 한 번 변경"), o1, h("p", { class: "btns" }, b1)),
        h("form", { class: "cm-form", onsubmit: function (ev) {
          ev.preventDefault(); if (!c2.same()) { c2.input.focus(); return result(o2, "비밀번호가 서로 다릅니다. 다시 확인해 주세요."); } busy(b2, true);
          sb.auth.updateUser({ password: pw.value }).then(function (r) { busy(b2, false); if (!r.error) { pw.value = ""; c2.input.value = ""; c2.same(); } result(o2, r.error ? msg(r.error) : "비밀번호를 바꿨습니다.", !r.error); });
        } }, field("새 비밀번호", pw, "8자 이상"), c2.el, o2, h("p", { class: "btns" }, b2)),
        h("div", { class: "cm-form cm-danger" }, h("h3", { class: "h-sm" }, "회원 탈퇴"),
          h("p", { class: "hint" }, "탈퇴하면 계정과 이메일이 바로 삭제되며 되돌릴 수 없습니다. 쓴 글과 댓글은 지워지지 않고 작성자가 '탈퇴한 회원'으로 바뀝니다. 지우고 싶은 글은 탈퇴 전에 직접 삭제하세요."), o3,
          h("p", { class: "btns" }, h("button", { type: "button", class: "btn btn-ghost", onclick: function () {
            if (window.prompt("탈퇴하려면 '탈퇴'라고 입력하세요.") !== "탈퇴") return;
            sb.rpc("delete_my_account").then(function (r) { if (r.error) return result(o3, msg(r.error)); sb.auth.signOut().then(function () { location.href = url(""); }, function () { location.href = url(""); }); });
          } }, "회원 탈퇴"))),
        h("p", { class: "btns" }, h("a", { class: "btn", href: url("") }, "게시판으로"))));
    }

    var mode = qs("mode") === "join" ? "join" : qs("mode") === "reset" ? "reset" : "login";
    // 어디서 넘어왔는지에 맞춰 왜 로그인이 필요한지 한 줄로 알려 준다
    function why() {
      var n = qs("next"), t = "";
      if (/board\/write\/.*b=job/.test(n)) t = "채용공고는 회원이면 누구나 무료로 등록할 수 있습니다. 로그인하거나 무료로 가입해 주세요.";
      else if (/board\/write\/.*b=qna/.test(n)) t = "질문은 회원이면 누구나 올릴 수 있습니다. 로그인하거나 무료로 가입해 주세요.";
      else if (/board\/write\//.test(n)) t = "글쓰기는 회원이면 누구나 할 수 있습니다. 로그인하거나 무료로 가입해 주세요.";
      else if (/board\/view\//.test(n)) t = "댓글·신고는 로그인한 뒤에 할 수 있습니다.";
      return t ? h("p", { class: "cm-why" }, t) : null;
    }
    function sw(m, text) { return h("a", { href: url("account", { mode: m === "login" ? "" : m, next: qs("next") }) }, text); }
    var email = h("input", { type: "email", autocomplete: "email", required: true, maxlength: "120" }), out = h("p", { hidden: true });
    if (ARRIVE === "error") {   // 만료됐거나 이미 쓴 인증 링크
      ARRIVE = ""; mode = "login";
      out.textContent = "인증 링크가 만료되었거나 이미 사용된 링크입니다. 인증을 이미 마쳤다면 아래에서 로그인하세요. 로그인이 안 되면 회원가입을 다시 하면 인증 메일을 새로 받을 수 있습니다.";
      out.className = "cm-note cm-err"; out.hidden = false;
    }
    if (mode === "login") {
      var pw1 = h("input", { type: "password", autocomplete: "current-password", required: true }), bl = h("button", { type: "submit", class: "btn btn-block" }, "로그인");
      return show(h("form", { class: "cm-form cm-auth", onsubmit: function (ev) {
        ev.preventDefault(); busy(bl, true); out.hidden = true;
        sb.auth.signInWithPassword({ email: email.value.trim(), password: pw1.value }).then(function (r) { if (r.error) { busy(bl, false); return result(out, msg(r.error)); } goNext(); });
      } }, why(), h("h2", { class: "h-sm" }, "로그인"), field("이메일", email), field("비밀번호", pw1), out, h("p", { class: "btns" }, bl),
        h("p", { class: "cm-alt" }, sw("reset", "비밀번호 찾기")),
        h("div", { class: "cm-joinbox" }, h("p", null, h("b", null, "아직 회원이 아니신가요?"), " 가입은 무료이고 1분이면 됩니다. 이메일 인증만 하면 되고 이름·전화번호는 받지 않습니다."),
          h("a", { class: "btn btn-ghost btn-block", href: url("account", { mode: "join", next: qs("next") }) }, "무료 회원가입"))));
    }
    if (mode === "reset") {
      var br = h("button", { type: "submit", class: "btn btn-block" }, "재설정 메일 보내기");
      return show(h("form", { class: "cm-form cm-auth", onsubmit: function (ev) {
        ev.preventDefault(); busy(br, true);
        sb.auth.resetPasswordForEmail(email.value.trim(), { redirectTo: here }).then(function (r) { busy(br, false); result(out, r.error ? msg(r.error) : "가입된 이메일이면 비밀번호 재설정 메일을 보냈습니다. 메일함(스팸함 포함)을 확인하세요.", !r.error); });
      } }, h("h2", { class: "h-sm" }, "비밀번호 찾기"), field("가입한 이메일", email), out, h("p", { class: "btns" }, br), h("p", { class: "cm-alt" }, sw("login", "로그인으로"))));
    }
    var nk = h("input", { type: "text", maxlength: "12", required: true, autocomplete: "nickname" }), pw2 = h("input", { type: "password", autocomplete: "new-password", minlength: "8", required: true });
    var ag1 = h("input", { type: "checkbox", required: true }), ag2 = h("input", { type: "checkbox", required: true }), bj = h("button", { type: "submit", class: "btn btn-block" }, "인증 메일 받기"), cj = pwConfirm(pw2);
    show(h("form", { class: "cm-form cm-auth", onsubmit: function (ev) {
      ev.preventDefault(); out.hidden = true;
      if (!cj.same()) { cj.input.focus(); return result(out, "비밀번호가 서로 다릅니다. 다시 확인해 주세요."); }
      var n = nk.value.trim();
      if (!/^[0-9A-Za-z가-힣_]{2,12}$/.test(n)) return result(out, ERR.NICKNAME_INVALID);
      busy(bj, true);
      sb.rpc("nickname_available", { p: n }).then(function (r) {
        if (r.error) throw r.error;
        if (!r.data) { busy(bj, false); result(out, n.length < 2 ? ERR.NICKNAME_INVALID : "이미 쓰고 있거나 쓸 수 없는 닉네임입니다."); return null; }
        return sb.auth.signUp({ email: email.value.trim(), password: pw2.value, options: { data: { nickname: n }, emailRedirectTo: here } });
      }).then(function (r) {
        if (!r) return;
        busy(bj, false);
        if (r.error) return result(out, msg(r.error));
        if (r.data && r.data.session) return goNext();
        result(out, "인증 메일을 보냈습니다. 메일의 링크를 누르면 가입이 끝납니다. 메일이 안 보이면 스팸함을 확인하세요. 이미 가입한 이메일이라면 메일이 가지 않으니 로그인하거나 비밀번호 찾기를 이용하세요.", true);
      }).catch(function (e) { busy(bj, false); result(out, msg(e)); });
    } }, why(), h("h2", { class: "h-sm" }, "무료 회원가입"),
      h("p", { class: "hint" }, "누구나 무료로 가입합니다. 이름·전화번호는 받지 않고 이메일 인증만 하면 됩니다."),
      field("이메일", email, "인증 메일을 받을 주소 · 다른 회원에게 보이지 않습니다"), field("비밀번호", pw2, "8자 이상"), cj.el, field("닉네임", nk, "한글·영문·숫자·밑줄 2~12자 · 글에 공개됩니다"),
      h("label", { class: "cm-chk" }, ag1, h("span", null, h("a", { href: REL + "board/rules/", target: "_blank" }, "게시판 이용수칙"), "과 ", h("a", { href: REL + "privacy/", target: "_blank" }, "개인정보 처리방침"), "을 읽었고 동의합니다. (필수)")),
      h("label", { class: "cm-chk" }, ag2, h("span", null, "만 14세 이상입니다. (필수)")),
      out, h("p", { class: "btns" }, bj), h("p", { class: "cm-alt" }, "이미 회원이면 ", sw("login", "로그인"))));
  }

  // ---------------------------------------------------------------- 운영 관리 (운영자 전용 · 권한은 서버 함수가 다시 확인한다)
  function pageAdmin() {
    document.title = "운영 관리 | " + document.title.split(" | ").pop();
    if (!ME) { location.href = url("account", { next: location.pathname + location.search }); return; }
    if (ME.role !== "admin") return show(note("운영자만 볼 수 있는 화면입니다.", "err"), h("p", { class: "btns" }, h("a", { class: "btn btn-ghost", href: url("") }, "게시판으로")));
    var TABS = [["reports", "신고"], ["members", "회원"], ["deleted", "삭제한 글"], ["log", "처리 기록"]];
    var tab = TABS.some(function (t) { return t[0] === qs("tab"); }) ? qs("tab") : "reports", box = h("div", { class: "cm-adm-body" });
    function go(t, extra) { var p = { tab: t }; for (var k in extra || {}) p[k] = extra[k]; history.replaceState(null, "", url("admin", p)); tab = t; draw(); }
    function head() {
      return h("div", { class: "cm-top" }, h("div", { class: "seg cm-tabs", role: "group", "aria-label": "운영 관리" },
        TABS.map(function (t) { return h("button", { type: "button", class: "cm-tab", "aria-pressed": String(t[0] === tab), onclick: function () { go(t[0]); } }, t[1]); })), userBar());
    }
    function fail(e) {
      var m = String((e && e.message) || "");
      box.textContent = "";
      add(box, /could not find the function|does not exist|schema cache/i.test(m)
        ? note("운영 관리 기능을 준비하고 있습니다. Supabase SQL Editor 에서 supabase/admin.sql 을 한 번 실행해야 합니다.", "err") : note(msg(e), "err"));
    }
    function call(name, args, confirmText, after) {
      if (confirmText && !window.confirm(confirmText)) return;
      sb.rpc(name, args || {}).then(function (r) { if (r.error) window.alert(msg(r.error)); else (after || draw)(); }, function (e) { window.alert(msg(e)); });
    }
    function table(heads, rows, empty) {
      if (!rows.length) return h("div", { class: "empty" }, h("p", null, empty));
      return h("div", { class: "cm-tblw" }, h("table", { class: "cm-tbl cm-adm-t" }, h("thead", null, h("tr", null, heads.map(function (x) { return h("th", { scope: "col" }, x); }))), h("tbody", null, rows)));
    }
    function link(r) { return r.post_id ? h("a", { href: url("view", { id: r.post_id }), target: "_blank", rel: "noopener" }, r.title || "(제목 없음)") : (r.title || "(삭제되어 볼 수 없음)"); }
    function load(name, args, render) {
      box.textContent = ""; add(box, h("p", { class: "cm-load", role: "status" }, "불러오는 중…"));
      sb.rpc(name, args || {}).then(function (r) { if (r.error) return fail(r.error); box.textContent = ""; add(box, render(r.data || [])); }, fail);
    }
    function drawReports() {
      var open = qs("done") !== "1";
      load("admin_reports", { p_open: open }, function (rows) {
        return [h("p", { class: "cm-adm-bar" }, h("button", { type: "button", class: "chip", "aria-pressed": String(open), onclick: function () { go("reports"); } }, "처리 전"),
          h("button", { type: "button", class: "chip", "aria-pressed": String(!open), onclick: function () { go("reports", { done: "1" }); } }, "처리 완료"),
          h("span", { class: "hint" }, "같은 글·댓글에 들어온 신고는 한 줄로 묶어 보여 줍니다.")),
          table(["대상", "신고 사유", "작성자", "신고", open ? "조치" : "처리"], rows.map(function (r) {
            var kind = r.target_type === "post" ? "글" : "댓글";
            return h("tr", null,
              h("td", null, h("span", { class: "cm-cat" }, kind), " ", link(r), r.gone ? h("span", { class: "cm-st cm-st-wait" }, "삭제됨") : null, h("p", { class: "cm-adm-snip" }, r.snippet || "")),
              h("td", null, r.reasons), h("td", null, r.author || "탈퇴한 회원"),
              h("td", { class: "cm-meta" }, r.n + "건 · ", h("time", { datetime: r.last_at }, when(r.last_at))),
              open ? h("td", { class: "cm-adm-acts" },
                !r.gone ? h("button", { type: "button", class: "btn btn-sm", onclick: function () {
                  call(r.target_type === "post" ? "delete_post" : "delete_comment", { p_id: r.target_id }, "이 " + kind + "을 삭제할까요? (3개월 안에는 복구할 수 있습니다)", function () { call("admin_handle_report", { p_type: r.target_type, p_id: r.target_id, p_note: "삭제" }); });
                } }, "삭제") : null,
                h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: function () {
                  var n = window.prompt("처리 메모 (예: 문제없음, 경고함)", r.gone ? "삭제됨" : "문제없음"); if (n == null) return;
                  call("admin_handle_report", { p_type: r.target_type, p_id: r.target_id, p_note: n });
                } }, r.gone ? "처리 완료" : "문제없음"),
                r.author_id ? h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: function () { go("members", { q: r.author }); } }, "작성자 관리") : null)
              : h("td", { class: "cm-meta" }, (r.handled_note || "") + " · ", h("time", { datetime: r.handled_at }, when(r.handled_at))));
          }), open ? "처리할 신고가 없습니다." : "처리한 신고가 없습니다.")];
      });
    }
    function suspend(m) {
      var d = window.prompt(m.nickname + " 님의 글쓰기를 며칠 동안 정지할까요?\n숫자(예: 7, 30)를 적거나, 기한 없이 정지하려면 0을 적으세요.", "7");
      if (d == null) return;
      d = parseInt(d, 10); if (isNaN(d) || d < 0 || d > 3650) return window.alert(ERR.BAD_DAYS);
      var why = window.prompt("정지 사유 (회원 본인에게 보입니다 · 2~200자)", ""); if (why == null) return;
      if (why.trim().length < 2) return window.alert(ERR.REASON_REQUIRED);
      call("admin_suspend", { p_user: m.id, p_days: d === 0 ? null : d, p_reason: why.trim() });
    }
    function drawMembers() {
      var q = qs("q").slice(0, 20), only = qs("sus") === "1";
      load("admin_members", { p_q: q, p_only_suspended: only }, function (rows) {
        var inp = h("input", { type: "search", name: "q", value: q, placeholder: "닉네임 검색", "aria-label": "닉네임 검색", maxlength: "20" });
        return [h("div", { class: "cm-adm-bar" },
          h("form", { class: "cm-search", role: "search", onsubmit: function (ev) { ev.preventDefault(); go("members", { q: inp.value.trim(), sus: only ? "1" : "" }); } }, inp, h("button", { type: "submit", class: "btn btn-sm btn-ghost" }, "검색")),
          h("button", { type: "button", class: "chip", "aria-pressed": String(only), onclick: function () { go("members", { q: q, sus: only ? "" : "1" }); } }, "정지 중인 회원만"),
          h("span", { class: "hint" }, "가입일 최신순 200명까지. 이메일은 여기에 표시하지 않습니다.")),
          table(["닉네임", "가입일", "글·댓글", "신고 받음", "상태", "조치"], rows.map(function (m) {
            return h("tr", null,
              h("td", null, h("b", null, m.nickname), m.role === "admin" ? h("span", { class: "cm-st cm-st-ans" }, "운영자") : null),
              h("td", { class: "cm-meta" }, h("time", { datetime: m.created_at }, when(m.created_at, true).slice(0, 10))),
              h("td", { class: "cm-meta" }, m.posts + " · " + m.comments), h("td", { class: "cm-meta" }, String(m.reported)),
              h("td", null, m.suspended ? [h("span", { class: "cm-st cm-st-hot" }, "정지"), " ", h("span", { class: "cm-meta" }, (m.until ? when(m.until, true) + "까지" : "기한 없음")), h("p", { class: "cm-adm-snip" }, m.reason || "")] : "정상"),
              h("td", { class: "cm-adm-acts" }, m.role === "admin" ? null : m.suspended
                ? h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: function () { call("admin_unsuspend", { p_user: m.id }, m.nickname + " 님의 정지를 해제할까요?"); } }, "정지 해제")
                : h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: function () { suspend(m); } }, "글쓰기 정지")));
          }), q || only ? "조건에 맞는 회원이 없습니다." : "회원이 없습니다."),
          h("p", { class: "src-note" }, "정지된 회원은 글·댓글을 새로 쓰거나 고칠 수 없고, 읽기·자기 글 삭제·신고는 할 수 있습니다. 계정 자체를 없애거나 로그인을 막으려면 Supabase 대시보드(Authentication → Users)에서 처리하세요.")];
      });
    }
    function drawDeleted() {
      load("admin_deleted", {}, function (rows) {
        return [table(["종류", "내용", "작성자", "삭제", "조치"], rows.map(function (r) {
          return h("tr", null, h("td", null, h("span", { class: "cm-cat" }, r.kind === "post" ? "글" : "댓글")),
            h("td", null, h("b", null, r.title || ""), h("p", { class: "cm-adm-snip" }, r.snippet || "")), h("td", null, r.author || "탈퇴한 회원"),
            h("td", { class: "cm-meta" }, h("time", { datetime: r.deleted_at }, when(r.deleted_at, true)), " · " + (r.by_self ? "본인" : "운영자")),
            h("td", { class: "cm-adm-acts" }, h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: function () { call("admin_restore", { p_kind: r.kind, p_id: r.id }, "이 " + (r.kind === "post" ? "글" : "댓글") + "을 다시 보이게 할까요?"); } }, "복구")));
        }), "삭제한 글·댓글이 없습니다."),
        h("p", { class: "src-note" }, "삭제한 글은 3개월 동안 운영자만 볼 수 있게 보관한 뒤 완전히 지워집니다. 본인이 지운 글을 복구할 때는 신중하게 판단하세요.")];
      });
    }
    function drawLog() {
      load("admin_logs", {}, function (rows) {
        return table(["일시", "운영자", "조치", "대상", "메모"], rows.map(function (r) {
          return h("tr", null, h("td", { class: "cm-meta" }, h("time", { datetime: r.created_at }, when(r.created_at, true))), h("td", null, r.admin || ""), h("td", null, h("b", null, r.action)), h("td", null, r.target), h("td", null, r.note));
        }), "아직 처리 기록이 없습니다.");
      });
    }
    function draw() { show(head(), box); ({ reports: drawReports, members: drawMembers, deleted: drawDeleted, log: drawLog })[tab](); }
    draw();
  }

  var ROUTES = { list: pageList, view: pageView, write: pageWrite, account: pageAccount, admin: pageAdmin };
  sb.auth.onAuthStateChange(function (ev) { if (ev === "PASSWORD_RECOVERY") { RECOVERY = true; if (PAGE === "account") pageAccount(); } });
  loading();
  if (qs("logout") && PAGE === "account") {   // 헤더의 '로그아웃'
    var bye = function () { location.replace(url("")); };
    sb.auth.signOut().then(bye, bye);
    return;
  }
  loadMe().then(function () { (ROUTES[PAGE] || pageList)(); }, function (e) { show(note(msg(e), "err")); });
})();
