-- SafePlum 회원 채용공고 게시판
-- schema.sql 을 이미 실행한 프로젝트에서 SQL Editor 에 통째로 붙여 넣고 한 번 실행한다. 다시 실행해도 기존 글은 그대로다.
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
    new.meta := '{}'::jsonb;
  end if;
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
    new.meta := '{}'::jsonb;
  end if;
  new.updated_at := now();
  return new;
end $$;

grant insert (meta) on public.posts to authenticated;
grant update (meta) on public.posts to authenticated;

create index if not exists posts_job_open on public.posts (created_at desc) where board = 'job' and deleted_at is null;
