-- SafePlum 운영자 관리 기능: 신고 처리 · 회원 목록 · 글쓰기 정지 · 삭제 글 복구 · 처리 기록
-- schema.sql(과 jobs.sql)을 실행한 프로젝트에서 SQL Editor 에 통째로 붙여 넣고 한 번 실행한다. 다시 실행해도 안전하다.
-- 모든 관리 함수는 서버에서 운영자(profiles.role = 'admin')인지 확인한다. 화면에서 버튼을 숨기는 것에 기대지 않는다.

-- ------------------------------------------------------------ 글쓰기 정지
-- profiles 는 누구나 읽을 수 있으므로 정지 사유는 별도 표에 둔다(본인과 운영자만 읽는다).
create table if not exists public.suspensions (
  user_id uuid primary key references public.profiles (id) on delete cascade,
  until timestamptz,                    -- null = 기한 없음
  reason text not null check (char_length(btrim(reason)) between 2 and 200),
  by_admin uuid,
  created_at timestamptz not null default now()
);
alter table public.suspensions enable row level security;
drop policy if exists suspensions_read on public.suspensions;
create policy suspensions_read on public.suspensions for select to authenticated using (user_id = auth.uid() or public.is_admin());
revoke all on public.suspensions from anon, authenticated;
grant select on public.suspensions to authenticated;

create or replace function public.is_suspended(p uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.suspensions where user_id = p and (until is null or until > now()));
$$;

-- 정지된 회원은 글·댓글을 새로 쓰거나 고칠 수 없다(읽기, 자기 글 삭제, 신고는 가능).
create or replace function public.guard_suspended() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(current_setting('app.sys', true), '') = '1' then return new; end if;
  if auth.uid() is not null and public.is_suspended(auth.uid()) then raise exception 'SUSPENDED'; end if;
  return new;
end $$;
drop trigger if exists posts_guard_suspended on public.posts;
create trigger posts_guard_suspended before insert or update on public.posts for each row execute function public.guard_suspended();
drop trigger if exists comments_guard_suspended on public.comments;
create trigger comments_guard_suspended before insert on public.comments for each row execute function public.guard_suspended();

-- ------------------------------------------------------------ 처리 기록
create table if not exists public.admin_log (
  id bigint generated always as identity primary key,
  admin_id uuid,
  action text not null,
  target text not null default '',
  note text not null default '',
  created_at timestamptz not null default now()
);
create index if not exists admin_log_created on public.admin_log (created_at desc);
alter table public.admin_log enable row level security;
revoke all on public.admin_log from anon, authenticated;   -- 읽기도 함수(admin_logs)로만

create or replace function public.admin_only() returns void
language plpgsql stable security definer set search_path = public as $$
begin
  if auth.uid() is null then raise exception 'LOGIN_REQUIRED'; end if;
  if not public.is_admin() then raise exception 'ADMIN_ONLY'; end if;
end $$;

create or replace function public.admin_note(p_action text, p_target text, p_note text) returns void
language sql security definer set search_path = public as $$
  insert into public.admin_log (admin_id, action, target, note) values (auth.uid(), p_action, coalesce(p_target, ''), left(coalesce(p_note, ''), 300));
$$;
revoke execute on function public.admin_note(text, text, text) from public, anon, authenticated;

-- ------------------------------------------------------------ 신고
-- 같은 글·댓글에 들어온 신고를 한 줄로 묶어 보여 준다.
create or replace function public.admin_reports(p_open boolean default true)
returns table (target_type text, target_id bigint, post_id bigint, n bigint, reasons text, first_at timestamptz, last_at timestamptz,
               handled_at timestamptz, handled_note text, title text, snippet text, author_id uuid, author text, gone boolean)
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.admin_only();
  return query
  select g.target_type, g.target_id,
         case when g.target_type = 'post' then g.target_id else c.post_id end,
         g.n, g.reasons, g.first_at, g.last_at, g.handled_at, g.handled_note,
         coalesce(p.title, pc.title), left(coalesce(c.body, p.body, ''), 300),
         coalesce(c.author_id, p.author_id), pr.nickname,
         case when g.target_type = 'post' then (p.id is null or p.deleted_at is not null) else (c.id is null or c.deleted_at is not null) end
    from (select r.target_type, r.target_id, count(*) n, string_agg(r.reason, ' / ' order by r.created_at) reasons,
                 min(r.created_at) first_at, max(r.created_at) last_at, max(r.handled_at) handled_at, max(r.handled_note) handled_note,
                 bool_and(r.handled_at is not null) done
            from public.reports r group by r.target_type, r.target_id) g
    left join public.posts p on g.target_type = 'post' and p.id = g.target_id
    left join public.comments c on g.target_type = 'comment' and c.id = g.target_id
    left join public.posts pc on pc.id = c.post_id
    left join public.profiles pr on pr.id = coalesce(c.author_id, p.author_id)
   where g.done = not p_open
   order by g.last_at desc limit 200;
end $$;

-- 신고 처리 완료 표시(글을 지웠든 문제없다고 봤든 결과를 메모로 남긴다)
create or replace function public.admin_handle_report(p_type text, p_id bigint, p_note text) returns void
language plpgsql security definer set search_path = public as $$
begin
  perform public.admin_only();
  update public.reports set handled_at = now(), handled_note = left(btrim(coalesce(p_note, '')), 200)
   where target_type = p_type and target_id = p_id and handled_at is null;
  perform public.admin_note('신고 처리', p_type || ' #' || p_id, p_note);
end $$;

-- ------------------------------------------------------------ 회원
-- 이메일은 일부만 보여 준다(예: tj***@gmail.com). 전체 주소는 Supabase 대시보드에서만 본다.
create or replace function public.mask_email(p text) returns text
language sql immutable as $$
  select case when p is null or position('@' in p) < 2 then '' else left(split_part(p, '@', 1), 2) || '***@' || split_part(p, '@', 2) end;
$$;

-- 접속기록: 운영자가 회원 정보(목록)를 조회한 기록. 「개인정보의 안전성 확보조치 기준」의 접속기록 보관(1년 이상)에 대비해
-- 누가·언제·어디서(IP)·무엇을 했는지 남기고 자동으로 지우지 않는다. 운영자 화면에서는 읽기만 한다.
create table if not exists public.admin_access (
  id bigint generated always as identity primary key,
  admin_id uuid,
  at timestamptz not null default now(),
  what text not null,
  detail text not null default '',
  ip text not null default ''
);
create index if not exists admin_access_at on public.admin_access (at desc);
alter table public.admin_access enable row level security;
revoke all on public.admin_access from anon, authenticated;

create or replace function public.client_ip() returns text
language plpgsql stable as $$
declare h text := current_setting('request.headers', true);
begin
  if h is null or h = '' then return ''; end if;
  return left(btrim(split_part(coalesce(h::json ->> 'x-forwarded-for', ''), ',', 1)), 60);
exception when others then return '';
end $$;

drop function if exists public.admin_members(text, boolean);
create function public.admin_members(p_q text default '', p_only_suspended boolean default false)
returns table (id uuid, nickname text, role text, created_at timestamptz, posts bigint, comments bigint, reported bigint,
               suspended boolean, until timestamptz, reason text, email text, verified boolean, last_seen timestamptz)
language plpgsql volatile security definer set search_path = public as $$
begin
  perform public.admin_only();
  insert into public.admin_access (admin_id, what, detail, ip)
  values (auth.uid(), '회원 목록 조회', left(coalesce(btrim(p_q), ''), 40) || case when p_only_suspended then ' (정지 회원만)' else '' end, public.client_ip());
  return query
  select pr.id, pr.nickname, pr.role, pr.created_at,
         (select count(*) from public.posts x where x.author_id = pr.id and x.deleted_at is null),
         (select count(*) from public.comments x where x.author_id = pr.id and x.deleted_at is null),
         (select count(*) from public.reports r
            where (r.target_type = 'post' and exists (select 1 from public.posts x where x.id = r.target_id and x.author_id = pr.id))
               or (r.target_type = 'comment' and exists (select 1 from public.comments x where x.id = r.target_id and x.author_id = pr.id))),
         (s.user_id is not null and (s.until is null or s.until > now())), s.until, s.reason,
         public.mask_email(u.email::text), (u.email_confirmed_at is not null), u.last_sign_in_at
    from public.profiles pr left join public.suspensions s on s.user_id = pr.id left join auth.users u on u.id = pr.id
   where (coalesce(btrim(p_q), '') = '' or pr.nickname ilike '%' || replace(replace(replace(btrim(p_q), '\', '\\'), '%', '\%'), '_', '\_') || '%')
     and (not p_only_suspended or (s.user_id is not null and (s.until is null or s.until > now())))
   order by pr.created_at desc limit 200;
end $$;
revoke execute on function public.admin_members(text, boolean) from public, anon;
grant execute on function public.admin_members(text, boolean) to authenticated;


-- p_days: 1~3650 또는 null(기한 없음). 운영자와 자기 자신은 정지할 수 없다.
create or replace function public.admin_suspend(p_user uuid, p_days int, p_reason text) returns void
language plpgsql security definer set search_path = public as $$
declare nick text; rl text;
begin
  perform public.admin_only();
  select nickname, role into nick, rl from public.profiles where id = p_user;
  if nick is null then raise exception 'USER_NOT_FOUND'; end if;
  if p_user = auth.uid() or rl = 'admin' then raise exception 'CANNOT_SUSPEND_ADMIN'; end if;
  if p_days is not null and (p_days < 1 or p_days > 3650) then raise exception 'BAD_DAYS'; end if;
  if char_length(btrim(coalesce(p_reason, ''))) < 2 then raise exception 'REASON_REQUIRED'; end if;
  insert into public.suspensions (user_id, until, reason, by_admin, created_at)
  values (p_user, case when p_days is null then null else now() + make_interval(days => p_days) end, left(btrim(p_reason), 200), auth.uid(), now())
  on conflict (user_id) do update set until = excluded.until, reason = excluded.reason, by_admin = excluded.by_admin, created_at = now();
  perform public.admin_note('글쓰기 정지', nick, coalesce(p_days::text || '일', '기한 없음') || ' · ' || btrim(p_reason));
end $$;

create or replace function public.admin_unsuspend(p_user uuid) returns void
language plpgsql security definer set search_path = public as $$
declare nick text;
begin
  perform public.admin_only();
  select nickname into nick from public.profiles where id = p_user;
  delete from public.suspensions where user_id = p_user;
  if found then perform public.admin_note('정지 해제', coalesce(nick, ''), ''); end if;
end $$;

-- ------------------------------------------------------------ 삭제한 글·댓글 (복구)
create or replace function public.admin_deleted()
returns table (kind text, id bigint, post_id bigint, title text, snippet text, author text, deleted_at timestamptz, by_self boolean)
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.admin_only();
  return query
  select * from (
    select 'post'::text, p.id, p.id, p.title, left(p.body, 200), pr.nickname, p.deleted_at, (p.deleted_by is not distinct from p.author_id)
      from public.posts p left join public.profiles pr on pr.id = p.author_id where p.deleted_at is not null
    union all
    select 'comment'::text, c.id, c.post_id, pp.title, left(c.body, 200), pr.nickname, c.deleted_at, (c.deleted_by is not distinct from c.author_id)
      from public.comments c left join public.posts pp on pp.id = c.post_id left join public.profiles pr on pr.id = c.author_id where c.deleted_at is not null
  ) t order by 7 desc limit 200;
end $$;

create or replace function public.admin_restore(p_kind text, p_id bigint) returns void
language plpgsql security definer set search_path = public as $$
declare pid bigint;
begin
  perform public.admin_only();
  perform set_config('app.sys', '1', true);
  if p_kind = 'post' then
    update public.posts set deleted_at = null, deleted_by = null where id = p_id and deleted_at is not null;
    if not found then perform set_config('app.sys', '', true); raise exception 'NOT_FOUND'; end if;
  elsif p_kind = 'comment' then
    update public.comments set deleted_at = null, deleted_by = null where id = p_id and deleted_at is not null returning post_id into pid;
    if pid is null then perform set_config('app.sys', '', true); raise exception 'NOT_FOUND'; end if;
    update public.posts set comment_count = comment_count + 1 where id = pid;
  else
    perform set_config('app.sys', '', true); raise exception 'NOT_FOUND';
  end if;
  perform set_config('app.sys', '', true);
  perform public.admin_note('복구', p_kind || ' #' || p_id, '');
end $$;

-- 공지 지정·해제
create or replace function public.admin_set_notice(p_id bigint, p_on boolean) returns void
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  perform public.admin_only();
  perform set_config('app.sys', '1', true);
  update public.posts set notice = coalesce(p_on, false) where id = p_id and deleted_at is null;
  get diagnostics n = row_count;
  perform set_config('app.sys', '', true);
  if n = 0 then raise exception 'NOT_FOUND'; end if;
  perform public.admin_note(case when p_on then '공지 지정' else '공지 해제' end, 'post #' || p_id, '');
end $$;

-- 운영자가 남의 글·댓글을 지우면 기록에 남긴다(기존 삭제 함수는 그대로 두고 기록만 덧붙인다).
create or replace function public.log_admin_delete() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if old.deleted_at is null and new.deleted_at is not null and new.deleted_by is not null and new.deleted_by is distinct from old.author_id then
    insert into public.admin_log (admin_id, action, target, note)
    values (new.deleted_by, '삭제', tg_argv[0] || ' #' || old.id, left(case when tg_argv[0] = 'post' then (to_jsonb(old) ->> 'title') else (to_jsonb(old) ->> 'body') end, 80));
  end if;
  return new;
end $$;
drop trigger if exists posts_log_admin_delete on public.posts;
create trigger posts_log_admin_delete after update on public.posts for each row execute function public.log_admin_delete('post');
drop trigger if exists comments_log_admin_delete on public.comments;
create trigger comments_log_admin_delete after update on public.comments for each row execute function public.log_admin_delete('comment');

create or replace function public.admin_access_logs()
returns table (id bigint, at timestamptz, admin text, what text, detail text, ip text)
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.admin_only();
  return query select a.id, a.at, pr.nickname, a.what, a.detail, a.ip
    from public.admin_access a left join public.profiles pr on pr.id = a.admin_id order by a.at desc, a.id desc limit 200;
end $$;
revoke execute on function public.admin_access_logs(), public.client_ip() from public, anon;
grant execute on function public.admin_access_logs() to authenticated;

create or replace function public.admin_logs()
returns table (id bigint, created_at timestamptz, admin text, action text, target text, note text)
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.admin_only();
  return query select l.id, l.created_at, pr.nickname, l.action, l.target, l.note
    from public.admin_log l left join public.profiles pr on pr.id = l.admin_id order by l.created_at desc, l.id desc limit 200;
end $$;

revoke execute on function public.admin_reports(boolean), public.admin_handle_report(text, bigint, text), public.admin_members(text, boolean),
  public.admin_suspend(uuid, int, text), public.admin_unsuspend(uuid), public.admin_deleted(), public.admin_restore(text, bigint),
  public.admin_set_notice(bigint, boolean), public.admin_logs(), public.admin_only(), public.guard_suspended(), public.log_admin_delete() from public, anon;
grant execute on function public.admin_reports(boolean), public.admin_handle_report(text, bigint, text), public.admin_members(text, boolean),
  public.admin_suspend(uuid, int, text), public.admin_unsuspend(uuid), public.admin_deleted(), public.admin_restore(text, bigint),
  public.admin_set_notice(bigint, boolean), public.admin_logs() to authenticated;
grant execute on function public.is_suspended(uuid) to authenticated;

-- ============================================================ 방문자 수 · 가입자 확인 · 강제 탈퇴
-- ------------------------------------------------------------ 하루 방문자 수
-- 브라우저가 '그날 하루만 쓰는 임의 번호'를 하루에 한 번 보낸다. 번호는 매일 새로 만들어 다음 날과 이어지지 않고,
-- IP·계정과 연결하지 않는다. 날짜별로 몇 개가 들어왔는지만 센다.
create table if not exists public.visits (
  day date not null,
  vid text not null check (vid ~ '^[0-9a-f]{16,32}$'),
  primary key (day, vid)
);
alter table public.visits enable row level security;
revoke all on public.visits from anon, authenticated;

create or replace function public.visit_ping(p_vid text) returns void
language plpgsql security definer set search_path = public as $$
declare d date := (now() at time zone 'Asia/Seoul')::date;
begin
  if p_vid is null or p_vid !~ '^[0-9a-f]{16,32}$' then return; end if;
  if (select count(*) from public.visits where day = d) >= 200000 then return; end if;   -- 비정상 폭주 방지
  insert into public.visits (day, vid) values (d, p_vid) on conflict do nothing;
  if random() < 0.01 then delete from public.visits where day < d - 400; end if;
end $$;
revoke execute on function public.visit_ping(text) from public;
grant execute on function public.visit_ping(text) to anon, authenticated;

create or replace function public.admin_stats() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare d date := (now() at time zone 'Asia/Seoul')::date; t0 timestamptz := (d::timestamp at time zone 'Asia/Seoul');
begin
  perform public.admin_only();
  return jsonb_build_object(
    'today', d,
    'visitors_today', (select count(*) from public.visits where day = d),
    'visitors_yesterday', (select count(*) from public.visits where day = d - 1),
    'days', (select coalesce(jsonb_agg(jsonb_build_object('day', g.day, 'visitors', (select count(*) from public.visits v where v.day = g.day),
                     'joins', (select count(*) from public.profiles p where (p.created_at at time zone 'Asia/Seoul')::date = g.day),
                     'posts', (select count(*) from public.posts p where (p.created_at at time zone 'Asia/Seoul')::date = g.day),
                     'comments', (select count(*) from public.comments c where (c.created_at at time zone 'Asia/Seoul')::date = g.day)) order by g.day desc), '[]'::jsonb)
               from (select generate_series(d - 13, d, interval '1 day')::date as day) g),
    'members', (select count(*) from public.profiles),
    'joins_today', (select count(*) from public.profiles where created_at >= t0),
    'posts_today', (select count(*) from public.posts where created_at >= t0 and deleted_at is null),
    'comments_today', (select count(*) from public.comments where created_at >= t0 and deleted_at is null),
    'open_reports', (select count(distinct (target_type, target_id)) from public.reports where handled_at is null),
    'suspended', (select count(*) from public.suspensions where until is null or until > now()));
end $$;

-- ------------------------------------------------------------ 강제 탈퇴
-- 다시 가입하지 못하게 막을 이메일. 주소 자체는 남기지 않고 SHA-256 값만 둔다.
create table if not exists public.blocked_emails (
  email_hash text primary key,
  reason text not null default '',
  created_at timestamptz not null default now()
);
alter table public.blocked_emails enable row level security;
revoke all on public.blocked_emails from anon, authenticated;

create or replace function public.email_hash(p text) returns text
language sql immutable as $$ select encode(sha256(convert_to(lower(btrim(coalesce(p, ''))), 'UTF8')), 'hex'); $$;

create or replace function public.block_banned_signup() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.email is not null and exists (select 1 from public.blocked_emails where email_hash = public.email_hash(new.email::text)) then
    raise exception 'SIGNUP_BLOCKED';
  end if;
  return new;
end $$;
drop trigger if exists on_auth_user_block on auth.users;
create trigger on_auth_user_block before insert on auth.users for each row execute function public.block_banned_signup();

-- p_purge: 쓴 글·댓글도 함께 가린다(3개월 뒤 완전 삭제). p_block: 같은 이메일로 다시 가입하지 못하게 한다.
create or replace function public.admin_delete_user(p_user uuid, p_reason text, p_purge boolean default false, p_block boolean default false) returns void
language plpgsql security definer set search_path = public as $$
declare nick text; rl text; em text;
begin
  perform public.admin_only();
  select nickname, role into nick, rl from public.profiles where id = p_user;
  if nick is null then raise exception 'USER_NOT_FOUND'; end if;
  if p_user = auth.uid() or rl = 'admin' then raise exception 'CANNOT_SUSPEND_ADMIN'; end if;
  if char_length(btrim(coalesce(p_reason, ''))) < 2 then raise exception 'REASON_REQUIRED'; end if;
  select email::text into em from auth.users where id = p_user;
  if coalesce(p_purge, false) then
    perform set_config('app.sys', '1', true);
    update public.comments set deleted_at = now(), deleted_by = auth.uid() where author_id = p_user and deleted_at is null;
    update public.posts set deleted_at = now(), deleted_by = auth.uid() where author_id = p_user and deleted_at is null;
    update public.posts p set comment_count = (select count(*) from public.comments c where c.post_id = p.id and c.deleted_at is null),
           accepted_comment_id = case when exists (select 1 from public.comments c where c.id = p.accepted_comment_id and c.deleted_at is null) then p.accepted_comment_id else null end
     where exists (select 1 from public.comments c where c.post_id = p.id and c.author_id = p_user);
    perform set_config('app.sys', '', true);
  end if;
  if coalesce(p_block, false) and em is not null then
    insert into public.blocked_emails (email_hash, reason) values (public.email_hash(em), left(btrim(p_reason), 200)) on conflict (email_hash) do nothing;
  end if;
  insert into public.admin_access (admin_id, what, detail, ip) values (auth.uid(), '강제 탈퇴(계정 삭제)', nick, public.client_ip());
  delete from auth.users where id = p_user;
  perform public.admin_note('강제 탈퇴', nick, btrim(p_reason) || case when coalesce(p_purge, false) then ' · 글 가림' else '' end || case when coalesce(p_block, false) then ' · 재가입 차단' else '' end);
end $$;

revoke execute on function public.admin_stats(), public.admin_delete_user(uuid, text, boolean, boolean), public.block_banned_signup(), public.mask_email(text), public.email_hash(text) from public, anon;
grant execute on function public.admin_stats(), public.admin_delete_user(uuid, text, boolean, boolean) to authenticated;

-- 가입을 처리하는 Supabase 내부 역할이 가입 차단 확인 함수를 확실히 쓸 수 있게 한다(없는 환경에서는 건너뛴다).
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
    grant execute on function public.block_banned_signup(), public.email_hash(text) to supabase_auth_admin;
  end if;
end $$;
