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
