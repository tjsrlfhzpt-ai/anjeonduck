/* SafePlum 게시판(커뮤니티 · Q&A) — 화면 전용.
   권한 검증은 여기서 하지 않는다: 누가 무엇을 쓸 수 있는지는 supabase/schema.sql 의 RLS·함수가 결정하고,
   이 파일은 그 결과(성공·거절)를 보여 줄 뿐이다. 사용자가 쓴 글은 반드시 텍스트로만 넣는다(innerHTML 금지). */
(function () {
  "use strict";
  var CFG = window.ST_CM || {}, root = document.getElementById("cm");
  if (!root) return;
  var PAGE = root.dataset.page, REL = CFG.root || "../", PER = 20;
  var BOARDS = { free: "커뮤니티", qna: "Q&A" };
  var ERR = {
    LOGIN_REQUIRED: "로그인이 필요합니다.", RATE_LIMIT: "너무 빠르게 연속으로 등록했습니다. 잠시 뒤 다시 시도하세요.",
    DAILY_LIMIT: "하루 등록 한도를 넘었습니다. 내일 다시 시도하세요.", NOT_ALLOWED: "권한이 없거나 이미 삭제된 글입니다.",
    POST_NOT_FOUND: "삭제되었거나 없는 글입니다.", NICKNAME_INVALID: "닉네임은 한글·영문·숫자·밑줄 2~12자이며 운영자를 연상시키는 이름은 쓸 수 없습니다.",
    NICKNAME_TAKEN: "이미 쓰고 있는 닉네임입니다.", NICKNAME_COOLDOWN: "닉네임은 7일에 한 번만 바꿀 수 있습니다.",
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
    if (ME) add(bar, [h("span", null, h("b", null, ME.nickname), " 님"), h("a", { href: url("account") }, "마이페이지"),
      h("button", { type: "button", class: "linkbtn", onclick: function () { sb.auth.signOut().then(function () { location.href = url(""); }); } }, "로그아웃")]);
    else add(bar, [h("a", { href: url("account", { next: location.pathname + location.search }) }, "로그인"), h("a", { href: url("account", { mode: "join" }) }, "회원가입")]);
    return bar;
  }
  function tabs(cur) {
    return h("div", { class: "cm-top" }, h("div", { class: "seg cm-tabs", role: "group", "aria-label": "게시판" },
      Object.keys(BOARDS).map(function (b) { return h("a", { class: "cm-tab", href: url("", { b: b }), "aria-current": b === cur ? "page" : null }, BOARDS[b]); })), userBar());
  }
  function busy(btn, on, label) { btn.disabled = on; if (label) btn.textContent = label; }

  // ---------------------------------------------------------------- 목록
  function pageList() {
    var b = BOARDS[qs("b")] ? qs("b") : "free", cat = qs("c"), kw = qs("q").slice(0, 40), p = Math.max(1, parseInt(qs("p"), 10) || 1);
    document.title = BOARDS[b] + " | " + document.title.split(" | ").pop();
    loading();
    var q = sb.from("posts").select("id,board,category,title,created_at,comment_count,accepted_comment_id,notice,author:profiles(nickname)", { count: "exact" })
      .eq("board", b).order("notice", { ascending: false }).order("created_at", { ascending: false }).range((p - 1) * PER, p * PER - 1);
    if (cat) q = q.eq("category", cat);
    if (kw) q = q.ilike("title", "%" + kw.replace(/[\\%_]/g, "\\$&") + "%");
    q.then(function (r) {
      if (r.error) return show(tabs(b), note(msg(r.error), "err"), h("p", { class: "btns" }, h("button", { type: "button", class: "btn btn-ghost", onclick: pageList }, "다시 시도")));
      var rows = r.data || [], total = r.count || 0, pages = Math.max(1, Math.ceil(total / PER));
      var cats = (CFG.cats && CFG.cats[b]) || [];
      var filter = h("div", { class: "cm-filter" },
        h("div", { class: "chips" }, [h("a", { class: "chip", href: url("", { b: b, q: kw }), "aria-current": !cat ? "true" : null }, "전체")].concat(
          cats.map(function (c) { return h("a", { class: "chip", href: url("", { b: b, c: c, q: kw }), "aria-current": c === cat ? "true" : null }, c); }))),
        h("form", { class: "cm-search", role: "search", onsubmit: function (ev) { ev.preventDefault(); location.href = url("", { b: b, c: cat, q: this.q.value.trim() }); } },
          h("input", { type: "search", name: "q", value: kw, placeholder: "제목 검색", "aria-label": "제목 검색", maxlength: "40" }), h("button", { type: "submit", class: "btn btn-sm btn-ghost" }, "검색")),
        h("a", { class: "btn btn-sm", href: ME ? url("write", { b: b }) : url("account", { next: url("write", { b: b }) }) }, b === "qna" ? "질문하기" : "글쓰기"));
      var list = h("ul", { class: "cm-list" }, rows.map(function (x) {
        var state = b === "qna" ? h("span", { class: "cm-st " + (x.accepted_comment_id ? "cm-st-ok" : x.comment_count ? "cm-st-ans" : "cm-st-wait") }, x.accepted_comment_id ? "채택 완료" : x.comment_count ? "답변 " + x.comment_count : "답변 대기") : null;
        return h("li", { class: x.notice ? "cm-notice" : null }, h("a", { href: url("view", { id: x.id }) },
          h("span", { class: "cm-cat" }, x.notice ? "공지" : (x.category || BOARDS[b])),
          h("span", { class: "cm-t" }, x.title, b !== "qna" && x.comment_count ? h("em", { "aria-label": "댓글 " + x.comment_count + "개" }, " [" + x.comment_count + "]") : null),
          state, h("span", { class: "cm-meta" }, nick(x), " · ", h("time", { datetime: x.created_at }, when(x.created_at)))));
      }));
      var empty = !rows.length ? h("div", { class: "empty" }, kw || cat ? null : h("img", { class: "cm-empty-i", src: REL + "assets/img/plum/wave.webp", width: "96", height: "96", alt: "" }), h("p", null, kw || cat ? "조건에 맞는 글이 없습니다." : (b === "qna" ? "아직 질문이 없습니다. 첫 질문을 남겨 보세요." : "아직 글이 없습니다. 첫 글을 남겨 보세요."))) : null;
      var pager = pages > 1 ? h("nav", { class: "cm-pager", "aria-label": "페이지" },
        p > 1 ? h("a", { class: "btn btn-sm btn-ghost", href: url("", { b: b, c: cat, q: kw, p: p - 1 }) }, "← 이전") : null,
        h("span", null, p + " / " + pages), p < pages ? h("a", { class: "btn btn-sm btn-ghost", href: url("", { b: b, c: cat, q: kw, p: p + 1 }) }, "다음 →") : null) : null;
      show(tabs(b), filter, empty || list, pager);
    }, function (e) { show(tabs(b), note(msg(e), "err")); });
  }

  // ---------------------------------------------------------------- 글 보기
  function pageView() {
    var id = parseInt(qs("id"), 10);
    if (!id) return show(note("주소가 올바르지 않습니다.", "err"), h("p", { class: "btns" }, h("a", { class: "btn btn-ghost", href: url("") }, "목록으로")));
    loading();
    Promise.all([
      sb.from("posts").select("id,board,category,title,body,created_at,updated_at,author_id,comment_count,accepted_comment_id,notice,author:profiles(nickname)").eq("id", id).maybeSingle(),
      sb.from("comments").select("id,body,created_at,author_id,author:profiles(nickname)").eq("post_id", id).order("created_at", { ascending: true }).limit(500)
    ]).then(function (rs) {
      var post = rs[0].data, err = rs[0].error || rs[1].error;
      if (err) return show(note(msg(err), "err"));
      if (!post) return show(h("div", { class: "empty" }, h("p", null, "삭제되었거나 없는 글입니다."), h("p", { class: "btns" }, h("a", { class: "btn btn-ghost", href: url("") }, "목록으로"))));
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
        !mine ? h("button", { type: "button", class: "linkbtn", onclick: report("post", post.id) }, "신고") : null);
      var art = h("article", { class: "cm-post" },
        h("p", { class: "cm-post-cat" }, h("a", { href: url("", { b: post.board }) }, BOARDS[post.board]), post.category ? " · " + post.category : "", post.notice ? " · 공지" : ""),
        h("h2", { class: "cm-post-t" }, post.title),
        h("p", { class: "cm-post-meta" }, nick(post), " · ", h("time", { datetime: post.created_at }, when(post.created_at, true)), post.updated_at ? " · 수정됨" : ""),
        h("div", { class: "cm-body" }, rich(post.body)), acts);
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
      function tick() { cnt.textContent = body.value.length.toLocaleString() + " / 5,000자"; draft(key, { title: title.value, body: body.value, category: selC.value }); }
      [title, body, selC].forEach(function (el) { el.addEventListener("input", tick); }); tick();
      show(h("form", { class: "cm-form cm-write", onsubmit: function (ev) {
        ev.preventDefault();
        var t = title.value.trim(), bd = body.value.trim();
        if (t.length < 2) { out.textContent = ERR.posts_title_check; out.hidden = false; title.focus(); return; }
        if (bd.length < 5) { out.textContent = ERR.posts_body_check; out.hidden = false; body.focus(); return; }
        busy(btn, true, "저장 중…"); out.hidden = true;
        var req = post ? sb.from("posts").update({ title: t, body: bd, category: selC.value }).eq("id", post.id).select("id")
                       : sb.from("posts").insert({ board: selB.value, category: selC.value, title: t, body: bd, author_id: ME.id }).select("id");
        req.then(function (r) {
          var row = r.data && r.data[0];
          if (r.error || !row) { out.textContent = r.error ? msg(r.error) : ERR.NOT_ALLOWED; out.hidden = false; busy(btn, false, post ? "수정 저장" : "등록"); return; }
          draft(key, null); location.href = url("view", { id: row.id });
        }, function (e) { out.textContent = msg(e) + " 작성하던 내용은 이 브라우저에 임시 저장되어 있습니다."; out.hidden = false; busy(btn, false, post ? "수정 저장" : "등록"); });
      } },
        h("div", { class: "cm-row2" }, selB, selC), title, body, h("p", { class: "cm-cnt" }, cnt, h("span", { class: "hint" }, "작성 중인 내용은 이 브라우저에 임시 저장됩니다.")), out,
        h("p", { class: "hint" }, "등록하면 ", h("a", { href: REL + "board/rules/", target: "_blank" }, "게시판 이용수칙"), "에 동의한 것으로 봅니다. 닉네임 ", h("b", null, ME.nickname), "(으)로 공개됩니다."),
        h("p", { class: "btns" }, btn, h("a", { class: "btn btn-ghost", href: post ? url("view", { id: post.id }) : url("", { b: b }) }, "취소"))));
    }
    if (!id) return form(null);
    loading();
    sb.from("posts").select("id,board,category,title,body,author_id").eq("id", id).maybeSingle().then(function (r) {
      if (r.error) return show(note(msg(r.error), "err"));
      if (!r.data || r.data.author_id !== ME.id) return show(note("본인이 쓴 글만 수정할 수 있습니다.", "err"), h("p", { class: "btns" }, h("a", { class: "btn btn-ghost", href: url("") }, "목록으로")));
      form(r.data);
    });
  }

  // ---------------------------------------------------------------- 로그인·가입·내 계정
  function field(label, input, hint) { return h("label", { class: "cm-f" }, h("span", null, label), input, hint ? h("small", { class: "hint" }, hint) : null); }
  function pageAccount() {
    var here = location.origin + location.pathname;
    function result(out, text, ok) { out.textContent = text; out.className = "cm-note " + (ok ? "cm-ok" : "cm-err"); out.hidden = false; }
    function goNext() { var n = qs("next"); location.href = n && n.charAt(0) === "/" && n.charAt(1) !== "/" ? n : url(""); }

    if (RECOVERY) {
      var np = h("input", { type: "password", autocomplete: "new-password", minlength: "8", required: true }), o0 = h("p", { hidden: true }), b0 = h("button", { type: "submit", class: "btn" }, "비밀번호 변경");
      return show(h("form", { class: "cm-form cm-auth", onsubmit: function (ev) {
        ev.preventDefault(); busy(b0, true);
        sb.auth.updateUser({ password: np.value }).then(function (r) { busy(b0, false); if (r.error) return result(o0, msg(r.error)); RECOVERY = false; result(o0, "비밀번호를 바꿨습니다.", true); setTimeout(function () { location.href = url(""); }, 900); });
      } }, h("h2", { class: "h-sm" }, "새 비밀번호 설정"), field("새 비밀번호", np, "8자 이상"), o0, h("p", { class: "btns" }, b0)));
    }

    if (ARRIVE === "signup" && ME) {
      ARRIVE = "";
      return show(h("div", { class: "cm-auth cm-welcome" },
        h("img", { src: REL + "assets/img/plum/wave.webp", width: "96", height: "96", alt: "" }),
        h("h2", { class: "h-sm" }, "가입이 완료되었습니다"),
        h("p", { class: "cm-note cm-ok" }, "이메일 인증이 끝났습니다. ", h("b", null, ME.nickname), " 님으로 로그인되어 있어 다시 로그인할 필요가 없습니다."),
        h("p", { class: "btns" }, h("a", { class: "btn btn-block", href: url("") }, "게시판 둘러보기")),
        h("p", { class: "btns" }, h("a", { class: "btn btn-ghost btn-block", href: url("write") }, "첫 글 쓰기")),
        h("p", { class: "cm-alt" }, h("a", { href: url("account") }, "마이페이지(닉네임·비밀번호 변경)"))));
    }
    if (ME) {
      var nn = h("input", { type: "text", maxlength: "12", required: true, value: ME.nickname }), o1 = h("p", { hidden: true }), b1 = h("button", { type: "submit", class: "btn btn-ghost" }, "닉네임 변경");
      var pw = h("input", { type: "password", autocomplete: "new-password", minlength: "8", required: true }), o2 = h("p", { hidden: true }), b2 = h("button", { type: "submit", class: "btn btn-ghost" }, "비밀번호 변경");
      var o3 = h("p", { hidden: true });
      return show(h("div", { class: "cm-auth" },
        h("h2", { class: "h-sm" }, "마이페이지"), h("p", { class: "cm-note" }, "이메일 ", h("b", null, ME.email), " · 이메일은 다른 회원에게 보이지 않습니다."),
        h("form", { class: "cm-form", onsubmit: function (ev) {
          ev.preventDefault(); busy(b1, true);
          sb.rpc("set_nickname", { p: nn.value.trim() }).then(function (r) { busy(b1, false); result(o1, r.error ? msg(r.error) : "닉네임을 바꿨습니다.", !r.error); });
        } }, field("닉네임", nn, "한글·영문·숫자·밑줄 2~12자 · 7일에 한 번 변경"), o1, h("p", { class: "btns" }, b1)),
        h("form", { class: "cm-form", onsubmit: function (ev) {
          ev.preventDefault(); busy(b2, true);
          sb.auth.updateUser({ password: pw.value }).then(function (r) { busy(b2, false); if (!r.error) pw.value = ""; result(o2, r.error ? msg(r.error) : "비밀번호를 바꿨습니다.", !r.error); });
        } }, field("새 비밀번호", pw, "8자 이상"), o2, h("p", { class: "btns" }, b2)),
        h("div", { class: "cm-form cm-danger" }, h("h3", { class: "h-sm" }, "회원 탈퇴"),
          h("p", { class: "hint" }, "탈퇴하면 계정과 이메일이 바로 삭제되며 되돌릴 수 없습니다. 쓴 글과 댓글은 지워지지 않고 작성자가 '탈퇴한 회원'으로 바뀝니다. 지우고 싶은 글은 탈퇴 전에 직접 삭제하세요."), o3,
          h("p", { class: "btns" }, h("button", { type: "button", class: "btn btn-ghost", onclick: function () {
            if (window.prompt("탈퇴하려면 '탈퇴'라고 입력하세요.") !== "탈퇴") return;
            sb.rpc("delete_my_account").then(function (r) { if (r.error) return result(o3, msg(r.error)); sb.auth.signOut().then(function () { location.href = url(""); }, function () { location.href = url(""); }); });
          } }, "회원 탈퇴"))),
        h("p", { class: "btns" }, h("a", { class: "btn", href: url("") }, "게시판으로"))));
    }

    var mode = qs("mode") === "join" ? "join" : qs("mode") === "reset" ? "reset" : "login";
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
      } }, h("h2", { class: "h-sm" }, "로그인"), field("이메일", email), field("비밀번호", pw1), out, h("p", { class: "btns" }, bl),
        h("p", { class: "cm-alt" }, sw("join", "회원가입"), " · ", sw("reset", "비밀번호 찾기"))));
    }
    if (mode === "reset") {
      var br = h("button", { type: "submit", class: "btn btn-block" }, "재설정 메일 보내기");
      return show(h("form", { class: "cm-form cm-auth", onsubmit: function (ev) {
        ev.preventDefault(); busy(br, true);
        sb.auth.resetPasswordForEmail(email.value.trim(), { redirectTo: here }).then(function (r) { busy(br, false); result(out, r.error ? msg(r.error) : "가입된 이메일이면 비밀번호 재설정 메일을 보냈습니다. 메일함(스팸함 포함)을 확인하세요.", !r.error); });
      } }, h("h2", { class: "h-sm" }, "비밀번호 찾기"), field("가입한 이메일", email), out, h("p", { class: "btns" }, br), h("p", { class: "cm-alt" }, sw("login", "로그인으로"))));
    }
    var nk = h("input", { type: "text", maxlength: "12", required: true, autocomplete: "nickname" }), pw2 = h("input", { type: "password", autocomplete: "new-password", minlength: "8", required: true });
    var ag1 = h("input", { type: "checkbox", required: true }), ag2 = h("input", { type: "checkbox", required: true }), bj = h("button", { type: "submit", class: "btn btn-block" }, "인증 메일 받기");
    show(h("form", { class: "cm-form cm-auth", onsubmit: function (ev) {
      ev.preventDefault(); out.hidden = true;
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
    } }, h("h2", { class: "h-sm" }, "회원가입"),
      h("p", { class: "hint" }, "이름·전화번호는 받지 않습니다. 이메일 인증만 하면 됩니다."),
      field("이메일", email, "인증 메일을 받을 주소 · 다른 회원에게 보이지 않습니다"), field("비밀번호", pw2, "8자 이상"), field("닉네임", nk, "한글·영문·숫자·밑줄 2~12자 · 글에 공개됩니다"),
      h("label", { class: "cm-chk" }, ag1, h("span", null, h("a", { href: REL + "board/rules/", target: "_blank" }, "게시판 이용수칙"), "과 ", h("a", { href: REL + "privacy/", target: "_blank" }, "개인정보 처리방침"), "을 읽었고 동의합니다. (필수)")),
      h("label", { class: "cm-chk" }, ag2, h("span", null, "만 14세 이상입니다. (필수)")),
      out, h("p", { class: "btns" }, bj), h("p", { class: "cm-alt" }, "이미 회원이면 ", sw("login", "로그인"))));
  }

  var ROUTES = { list: pageList, view: pageView, write: pageWrite, account: pageAccount };
  sb.auth.onAuthStateChange(function (ev) { if (ev === "PASSWORD_RECOVERY") { RECOVERY = true; if (PAGE === "account") pageAccount(); } });
  loading();
  if (qs("logout") && PAGE === "account") {   // 헤더의 '로그아웃'
    var bye = function () { location.replace(url("")); };
    sb.auth.signOut().then(bye, bye);
    return;
  }
  loadMe().then(function () { (ROUTES[PAGE] || pageList)(); }, function (e) { show(note(msg(e), "err")); });
})();
