-- SafePlum 게시판(커뮤니티 · Q&A) 데이터베이스
-- Supabase 대시보드 → SQL Editor 에 통째로 붙여 넣고 한 번 실행합니다. 다시 실행해도 기존 글은 지워지지 않습니다.
--
-- 원칙
--  · 권한은 화면이 아니라 여기(RLS·함수)에서 검증한다. 브라우저에 들어가는 anon 키로는 아래 정책이 허용한 일만 할 수 있다.
--  · 이메일은 auth.users 에만 있고 공개 테이블(profiles)에는 닉네임만 둔다.
--  · 글·댓글 삭제는 지우지 않고 deleted_at 을 찍는다(분쟁·신고 대응용 이력). 탈퇴하면 계정과 이메일은 지워지고 글의 작성자는 비워진다.

-- ------------------------------------------------------------ 회원 프로필
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  nickname text not null,
  role text not null default 'member' check (role in ('member', 'admin')),
  created_at timestamptz not null default now(),
  nickname_changed_at timestamptz,
  constraint profiles_nickname_len check (char_length(nickname) between 2 and 12),
  constraint profiles_nickname_chars check (nickname ~ '^[0-9A-Za-z가-힣_]+$')
);
create unique index if not exists profiles_nickname_key on public.profiles (lower(nickname));

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles where id = auth.uid() and role = 'admin');
$$;

create or replace function public.nickname_ok(p text) returns boolean
language sql immutable as $$
  select p is not null and char_length(p) between 2 and 12 and p ~ '^[0-9A-Za-z가-힣_]+$'
     and lower(p) not in ('운영자', '운영팀', '관리자', 'admin', 'safetake', '세이프테이크', 'safeplum', '세이프플럼');
$$;

-- 가입 전 닉네임 중복 확인(비로그인도 호출 가능)
create or replace function public.nickname_available(p text) returns boolean
language sql stable security definer set search_path = public as $$
  select public.nickname_ok(p) and not exists (select 1 from public.profiles where lower(nickname) = lower(p));
$$;

-- 가입하면 프로필을 자동으로 만든다. 닉네임이 규칙에 안 맞거나 그사이 선점되면 임시 닉네임을 준다(가입 자체는 막지 않는다).
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
declare n text := btrim(coalesce(new.raw_user_meta_data ->> 'nickname', ''));
begin
  if not public.nickname_ok(n) or exists (select 1 from public.profiles where lower(nickname) = lower(n)) then
    n := '안전인' || substr(md5(new.id::text), 1, 6);
  end if;
  insert into public.profiles (id, nickname) values (new.id, n) on conflict (id) do nothing;
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_user();

-- ------------------------------------------------------------ 글
create table if not exists public.posts (
  id bigint generated always as identity primary key,
  board text not null check (board in ('free', 'qna')),
  category text not null default '' check (char_length(category) <= 20),
  title text not null check (char_length(btrim(title)) between 2 and 80),
  body text not null check (char_length(btrim(body)) between 5 and 5000),
  author_id uuid references public.profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  deleted_at timestamptz,
  deleted_by uuid,
  comment_count integer not null default 0,
  accepted_comment_id bigint,
  notice boolean not null default false
);
create index if not exists posts_board_created on public.posts (board, created_at desc) where deleted_at is null;
create index if not exists posts_author on public.posts (author_id, created_at desc);

-- ------------------------------------------------------------ 댓글(Q&A에서는 답변)
create table if not exists public.comments (
  id bigint generated always as identity primary key,
  post_id bigint not null references public.posts (id) on delete cascade,
  body text not null check (char_length(btrim(body)) between 1 and 2000),
  author_id uuid references public.profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  deleted_at timestamptz,
  deleted_by uuid
);
create index if not exists comments_post on public.comments (post_id, created_at) where deleted_at is null;
create index if not exists comments_author on public.comments (author_id, created_at desc);

-- ------------------------------------------------------------ 신고
create table if not exists public.reports (
  id bigint generated always as identity primary key,
  target_type text not null check (target_type in ('post', 'comment')),
  target_id bigint not null,
  reporter_id uuid references public.profiles (id) on delete set null,
  reason text not null check (char_length(btrim(reason)) between 2 and 300),
  created_at timestamptz not null default now(),
  handled_at timestamptz,
  handled_note text,
  unique (target_type, target_id, reporter_id)
);

-- ------------------------------------------------------------ 쓰기 규칙(트리거)
-- app.sys = '1' 은 아래 함수들이 내부에서만 켜는 표시다. 브라우저(PostgREST)에서는 켤 수 없다.
create or replace function public.posts_before_insert() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then raise exception 'LOGIN_REQUIRED'; end if;
  new.author_id := auth.uid();
  new.created_at := now(); new.updated_at := null; new.deleted_at := null; new.deleted_by := null;
  new.comment_count := 0; new.accepted_comment_id := null;
  new.title := btrim(new.title); new.category := btrim(coalesce(new.category, ''));
  if not public.is_admin() then
    new.notice := false;
    if exists (select 1 from public.posts where author_id = auth.uid() and created_at > now() - interval '30 seconds') then
      raise exception 'RATE_LIMIT';
    end if;
    if (select count(*) from public.posts where author_id = auth.uid() and created_at > now() - interval '1 day') >= 30 then
      raise exception 'DAILY_LIMIT';
    end if;
  end if;
  return new;
end $$;
drop trigger if exists posts_bi on public.posts;
create trigger posts_bi before insert on public.posts for each row execute function public.posts_before_insert();

create or replace function public.posts_before_update() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(current_setting('app.sys', true), '') = '1' then return new; end if;
  -- 본인 수정으로 바꿀 수 있는 것은 분류·제목·본문뿐이다. 나머지는 원래 값으로 되돌린다.
  -- author_id 가 비워지는 것은 탈퇴(on delete set null)뿐이므로 그대로 둔다. 브라우저에는 author_id 수정 권한이 없다.
  new.id := old.id; new.board := old.board; new.created_at := old.created_at;
  if new.author_id is not null then new.author_id := old.author_id; end if;
  new.deleted_at := old.deleted_at; new.deleted_by := old.deleted_by;
  new.comment_count := old.comment_count; new.accepted_comment_id := old.accepted_comment_id;
  if not public.is_admin() then new.notice := old.notice; end if;
  new.title := btrim(new.title); new.category := btrim(coalesce(new.category, ''));
  new.updated_at := now();
  return new;
end $$;
drop trigger if exists posts_bu on public.posts;
create trigger posts_bu before update on public.posts for each row execute function public.posts_before_update();

create or replace function public.comments_before_insert() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then raise exception 'LOGIN_REQUIRED'; end if;
  new.author_id := auth.uid(); new.created_at := now(); new.deleted_at := null; new.deleted_by := null;
  if not exists (select 1 from public.posts where id = new.post_id and deleted_at is null) then raise exception 'POST_NOT_FOUND'; end if;
  if not public.is_admin() then
    if exists (select 1 from public.comments where author_id = auth.uid() and created_at > now() - interval '10 seconds') then
      raise exception 'RATE_LIMIT';
    end if;
    if (select count(*) from public.comments where author_id = auth.uid() and created_at > now() - interval '1 day') >= 100 then
      raise exception 'DAILY_LIMIT';
    end if;
  end if;
  return new;
end $$;
drop trigger if exists comments_bi on public.comments;
create trigger comments_bi before insert on public.comments for each row execute function public.comments_before_insert();

create or replace function public.comments_after_insert() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  perform set_config('app.sys', '1', true);
  update public.posts set comment_count = comment_count + 1 where id = new.post_id;
  perform set_config('app.sys', '', true);
  return null;
end $$;
drop trigger if exists comments_ai on public.comments;
create trigger comments_ai after insert on public.comments for each row execute function public.comments_after_insert();

-- ------------------------------------------------------------ 행 수준 보안(RLS)
alter table public.profiles enable row level security;
alter table public.posts enable row level security;
alter table public.comments enable row level security;
alter table public.reports enable row level security;

drop policy if exists profiles_read on public.profiles;
create policy profiles_read on public.profiles for select using (true);
-- profiles 는 직접 수정 정책이 없다 → 닉네임은 set_nickname(), 등급(role)은 운영자가 대시보드에서만 바꾼다.

drop policy if exists posts_read on public.posts;
create policy posts_read on public.posts for select using (deleted_at is null or public.is_admin());
drop policy if exists posts_insert on public.posts;
create policy posts_insert on public.posts for insert to authenticated with check (author_id = auth.uid());
drop policy if exists posts_update on public.posts;
create policy posts_update on public.posts for update to authenticated
  using ((author_id = auth.uid() or public.is_admin()) and deleted_at is null)
  with check ((author_id = auth.uid() or public.is_admin()) and deleted_at is null);

drop policy if exists comments_read on public.comments;
create policy comments_read on public.comments for select using (deleted_at is null or public.is_admin());
drop policy if exists comments_insert on public.comments;
create policy comments_insert on public.comments for insert to authenticated with check (author_id = auth.uid());

drop policy if exists reports_admin on public.reports;
create policy reports_admin on public.reports for select to authenticated using (public.is_admin());

revoke all on public.profiles, public.posts, public.comments, public.reports from anon, authenticated;
grant select on public.profiles, public.posts, public.comments to anon, authenticated;
grant insert (board, category, title, body, author_id, notice) on public.posts to authenticated;
grant update (category, title, body, notice) on public.posts to authenticated;
grant insert (post_id, body, author_id) on public.comments to authenticated;
grant select on public.reports to authenticated;

-- ------------------------------------------------------------ 기능 함수(RPC)
create or replace function public.delete_post(p_id bigint) returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then raise exception 'LOGIN_REQUIRED'; end if;
  perform set_config('app.sys', '1', true);
  update public.posts set deleted_at = now(), deleted_by = auth.uid()
   where id = p_id and deleted_at is null and (author_id = auth.uid() or public.is_admin());
  if not found then perform set_config('app.sys', '', true); raise exception 'NOT_ALLOWED'; end if;
  perform set_config('app.sys', '', true);
end $$;

create or replace function public.delete_comment(p_id bigint) returns void
language plpgsql security definer set search_path = public as $$
declare pid bigint;
begin
  if auth.uid() is null then raise exception 'LOGIN_REQUIRED'; end if;
  update public.comments set deleted_at = now(), deleted_by = auth.uid()
   where id = p_id and deleted_at is null and (author_id = auth.uid() or public.is_admin())
   returning post_id into pid;
  if pid is null then raise exception 'NOT_ALLOWED'; end if;
  perform set_config('app.sys', '1', true);
  update public.posts set comment_count = greatest(comment_count - 1, 0),
         accepted_comment_id = case when accepted_comment_id = p_id then null else accepted_comment_id end
   where id = pid;
  perform set_config('app.sys', '', true);
end $$;

-- Q&A: 질문 작성자가 답변 하나를 채택한다(같은 답변을 다시 누르면 채택 취소).
create or replace function public.accept_answer(p_comment bigint) returns void
language plpgsql security definer set search_path = public as $$
declare pid bigint;
begin
  select c.post_id into pid from public.comments c join public.posts p on p.id = c.post_id
   where c.id = p_comment and c.deleted_at is null and p.deleted_at is null and p.board = 'qna'
     and (p.author_id = auth.uid() or public.is_admin());
  if pid is null then raise exception 'NOT_ALLOWED'; end if;
  perform set_config('app.sys', '1', true);
  update public.posts set accepted_comment_id = case when accepted_comment_id = p_comment then null else p_comment end where id = pid;
  perform set_config('app.sys', '', true);
end $$;

create or replace function public.set_nickname(p text) returns void
language plpgsql security definer set search_path = public as $$
declare cur record;
begin
  if auth.uid() is null then raise exception 'LOGIN_REQUIRED'; end if;
  p := btrim(p);
  if not public.nickname_ok(p) then raise exception 'NICKNAME_INVALID'; end if;
  select * into cur from public.profiles where id = auth.uid();
  if cur.nickname_changed_at is not null and cur.nickname_changed_at > now() - interval '7 days' then raise exception 'NICKNAME_COOLDOWN'; end if;
  if exists (select 1 from public.profiles where lower(nickname) = lower(p) and id <> auth.uid()) then raise exception 'NICKNAME_TAKEN'; end if;
  update public.profiles set nickname = p, nickname_changed_at = now() where id = auth.uid();
end $$;

create or replace function public.report_content(p_type text, p_id bigint, p_reason text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then raise exception 'LOGIN_REQUIRED'; end if;
  if (select count(*) from public.reports where reporter_id = auth.uid() and created_at > now() - interval '1 day') >= 20 then raise exception 'DAILY_LIMIT'; end if;
  insert into public.reports (target_type, target_id, reporter_id, reason) values (p_type, p_id, auth.uid(), btrim(p_reason))
  on conflict (target_type, target_id, reporter_id) do nothing;
end $$;

-- 탈퇴: 계정(이메일 포함)을 지운다. 프로필은 함께 지워지고, 쓴 글·댓글은 작성자가 비워진 채 남는다.
create or replace function public.delete_my_account() returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then raise exception 'LOGIN_REQUIRED'; end if;
  delete from auth.users where id = auth.uid();
end $$;

revoke execute on function public.delete_post(bigint), public.delete_comment(bigint), public.accept_answer(bigint),
  public.set_nickname(text), public.report_content(text, bigint, text), public.delete_my_account() from public, anon;
grant execute on function public.delete_post(bigint), public.delete_comment(bigint), public.accept_answer(bigint),
  public.set_nickname(text), public.report_content(text, bigint, text), public.delete_my_account() to authenticated;
grant execute on function public.nickname_available(text), public.is_admin() to anon, authenticated;

-- ------------------------------------------------------------ 회원 채용공고(board = 'job') — supabase/jobs.sql 과 같은 내용
--
-- 채용공고는 posts 의 세 번째 게시판(board = 'job')이다. 회사명·근무지·마감일 같은 항목은 meta(jsonb)에 둔다.
-- 권한 규칙은 커뮤니티·Q&A와 같다: 읽기는 누구나, 쓰기는 이메일 인증 회원, 수정·삭제는 본인과 운영자.

alter table public.posts add column if not exists meta jsonb not null default '{}'::jsonb;

alter table public.posts drop constraint if exists posts_board_check;
alter table public.posts add constraint posts_board_check check (board in ('free', 'qna', 'job'));

alter table public.posts drop constraint if exists posts_meta_check;
alter table public.posts add constraint posts_meta_check check (jsonb_typeof(meta) = 'object' and char_length(meta::text) <= 2000);

-- 채용공고에 꼭 있어야 하는 것: 회사명, 지원 방법(https 주소 또는 설명). 마감일은 YYYY-MM-DD 이거나 비워 둔다(상시).
create or replace function public.job_meta_ok(m jsonb) returns boolean
language sql immutable as $$
  select char_length(btrim(coalesce(m ->> 'company', ''))) between 2 and 60
     and char_length(btrim(coalesce(m ->> 'apply', ''))) between 5 and 300
     and coalesce(m ->> 'deadline', '') ~ '^(\d{4}-\d{2}-\d{2})?$'
     and char_length(coalesce(m ->> 'region', '')) <= 40
     and char_length(coalesce(m ->> 'career', '')) <= 40
     and char_length(coalesce(m ->> 'employment', '')) <= 20;
$$;

-- 사진 첨부(모든 게시판): meta.images 는 최대 3장, 자기 폴더(<회원 id>/파일.jpg)에 올린 것만 붙일 수 있다.
create or replace function public.post_images_ok(m jsonb, owner uuid) returns boolean
language sql immutable as $$
  select case when not (m ? 'images') then true
              when jsonb_typeof(m -> 'images') <> 'array' then false
              else jsonb_array_length(m -> 'images') <= 3
               and not exists (select 1 from jsonb_array_elements(m -> 'images') x
                               where jsonb_typeof(x) <> 'string'
                                  or (x #>> '{}') !~ '^[0-9a-f-]{36}/[0-9a-z]{6,40}\.jpg$'
                                  or split_part(x #>> '{}', '/', 1) is distinct from owner::text) end;
$$;

create or replace function public.posts_before_insert() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then raise exception 'LOGIN_REQUIRED'; end if;
  new.author_id := auth.uid();
  new.created_at := now(); new.updated_at := null; new.deleted_at := null; new.deleted_by := null;
  new.comment_count := 0; new.accepted_comment_id := null;
  new.title := btrim(new.title); new.category := btrim(coalesce(new.category, ''));
  if new.board = 'job' then
    if not public.job_meta_ok(new.meta) then raise exception 'JOB_META_INVALID'; end if;
  else
    -- 커뮤니티·Q&A 는 사진 목록만 남긴다
    new.meta := case when jsonb_typeof(new.meta -> 'images') = 'array' and jsonb_array_length(new.meta -> 'images') > 0 then jsonb_build_object('images', new.meta -> 'images') else '{}'::jsonb end;
  end if;
  if not public.post_images_ok(new.meta, auth.uid()) then raise exception 'IMAGES_INVALID'; end if;
  if not public.is_admin() then
    new.notice := false;
    if exists (select 1 from public.posts where author_id = auth.uid() and created_at > now() - interval '30 seconds') then
      raise exception 'RATE_LIMIT';
    end if;
    if (select count(*) from public.posts where author_id = auth.uid() and created_at > now() - interval '1 day') >= 30 then
      raise exception 'DAILY_LIMIT';
    end if;
    -- 채용공고는 하루 5건까지(도배·광고 방지)
    if new.board = 'job' and (select count(*) from public.posts where author_id = auth.uid() and board = 'job' and created_at > now() - interval '1 day') >= 5 then
      raise exception 'JOB_DAILY_LIMIT';
    end if;
  end if;
  return new;
end $$;

create or replace function public.posts_before_update() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(current_setting('app.sys', true), '') = '1' then return new; end if;
  -- 본인 수정으로 바꿀 수 있는 것은 분류·제목·본문·채용 항목(meta)뿐이다. 나머지는 원래 값으로 되돌린다.
  -- author_id 가 비워지는 것은 탈퇴(on delete set null)뿐이므로 그대로 둔다. 브라우저에는 author_id 수정 권한이 없다.
  new.id := old.id; new.board := old.board; new.created_at := old.created_at;
  if new.author_id is not null then new.author_id := old.author_id; end if;
  new.deleted_at := old.deleted_at; new.deleted_by := old.deleted_by;
  new.comment_count := old.comment_count; new.accepted_comment_id := old.accepted_comment_id;
  if not public.is_admin() then new.notice := old.notice; end if;
  new.title := btrim(new.title); new.category := btrim(coalesce(new.category, ''));
  if old.board = 'job' then
    if not public.job_meta_ok(new.meta) then raise exception 'JOB_META_INVALID'; end if;
  else
    -- 커뮤니티·Q&A 는 사진 목록만 남긴다
    new.meta := case when jsonb_typeof(new.meta -> 'images') = 'array' and jsonb_array_length(new.meta -> 'images') > 0 then jsonb_build_object('images', new.meta -> 'images') else '{}'::jsonb end;
  end if;
  if new.meta is distinct from old.meta and not public.post_images_ok(new.meta, old.author_id) then raise exception 'IMAGES_INVALID'; end if;
  new.updated_at := now();
  return new;
end $$;

grant insert (meta) on public.posts to authenticated;
grant update (meta) on public.posts to authenticated;

create index if not exists posts_job_open on public.posts (created_at desc) where board = 'job' and deleted_at is null;


-- ---------------------------------------------------------------- 게시판 사진 첨부 (Storage)
-- 공개 버킷 post-images: 누구나 볼 수 있고, 올리기·지우기는 로그인 회원이 자기 폴더(<회원 id>/)에만 할 수 있다.
-- 파일은 브라우저에서 JPEG로 줄여 올린다. 한 장 1MB, JPEG만 받는다(서버에서 제한).
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('post-images', 'post-images', true, 1048576, array['image/jpeg'])
on conflict (id) do update set public = true, file_size_limit = 1048576, allowed_mime_types = array['image/jpeg'];

drop policy if exists "post_images_insert" on storage.objects;
create policy "post_images_insert" on storage.objects for insert to authenticated
  with check (bucket_id = 'post-images' and (storage.foldername(name))[1] = auth.uid()::text);
drop policy if exists "post_images_select_own" on storage.objects;
create policy "post_images_select_own" on storage.objects for select to authenticated
  using (bucket_id = 'post-images' and (storage.foldername(name))[1] = auth.uid()::text);
drop policy if exists "post_images_delete" on storage.objects;
create policy "post_images_delete" on storage.objects for delete to authenticated
  using (bucket_id = 'post-images' and ((storage.foldername(name))[1] = auth.uid()::text or public.is_admin()));


-- ============================================================ 운영자 관리 기능 (admin.sql 과 같은 내용)

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

drop function if exists public.admin_members(text, boolean);
create function public.admin_members(p_q text default '', p_only_suspended boolean default false)
returns table (id uuid, nickname text, role text, created_at timestamptz, posts bigint, comments bigint, reported bigint,
               suspended boolean, until timestamptz, reason text, email text, verified boolean, last_seen timestamptz)
language plpgsql stable security definer set search_path = public as $$
begin
  perform public.admin_only();
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
  delete from auth.users where id = p_user;
  perform public.admin_note('강제 탈퇴', nick, btrim(p_reason) || case when coalesce(p_purge, false) then ' · 글 가림' else '' end || case when coalesce(p_block, false) then ' · 재가입 차단' else '' end);
end $$;

revoke execute on function public.admin_stats(), public.admin_delete_user(uuid, text, boolean, boolean), public.block_banned_signup(), public.mask_email(text), public.email_hash(text) from public, anon;
grant execute on function public.admin_stats(), public.admin_delete_user(uuid, text, boolean, boolean) to authenticated;

-- ------------------------------------------------------------ 운영자 지정 (가입한 뒤 한 번만, 이메일을 바꿔서 따로 실행)
-- update public.profiles set role = 'admin' where id = (select id from auth.users where email = '운영자 이메일');
