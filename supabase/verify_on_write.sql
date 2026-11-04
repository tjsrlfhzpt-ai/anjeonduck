-- SafePlum '가입은 바로, 글쓰기 전 1회 이메일 인증' (서버 쪽 잠금)
-- Supabase SQL Editor 에 통째로 붙여 넣고 한 번 실행한다. 다시 실행해도 안전하다.
--
-- 순서가 중요하다
--   1) 이 파일을 먼저 실행한다.  (지금까지 이메일 인증을 마친 회원은 '인증 완료'로 옮겨 둔다)
--   2) 그 다음 Authentication > Sign In / Providers > Email 에서 'Confirm email' 을 끈다.
--   거꾸로 하면 1)과 2) 사이에 가입한 사람도 메일 인증 없이 가입 처리되지만, 인증 기록이 없으므로 글은 못 쓴다(안전한 쪽으로 실패).
--
-- 막는 것(서버에서 거절): 인증 기록이 없는 회원의 새 글·새 댓글(채용공고 포함), 사진 올리기.
-- 그대로 두는 것: 읽기, 로그인, 닉네임·비밀번호 변경, 자기 글 수정·삭제, 신고, 탈퇴. 운영자는 검사하지 않는다.
--
-- 인증 방법: 로그인한 회원이 자기 이메일로 인증 코드(또는 링크)를 받아 확인하면, 그 세션 토큰의 amr(인증 방식)에
--   otp·magiclink 가 찍힌다. mark_verified() 는 그 기록이 15분 안의 것일 때만 '인증 완료'를 남긴다.
--   화면(브라우저)이 '인증했다'고 주장하는 것만으로는 기록되지 않는다.

create table if not exists public.member_verify (
  user_id uuid primary key references auth.users (id) on delete cascade,
  verified_at timestamptz not null default now(),
  method text not null default ''
);
alter table public.member_verify enable row level security;
revoke all on public.member_verify from anon, authenticated;
grant select on public.member_verify to authenticated;
drop policy if exists member_verify_read on public.member_verify;
create policy member_verify_read on public.member_verify for select to authenticated using (user_id = auth.uid() or public.is_admin());
-- insert/update/delete 정책은 두지 않는다 → 아래 security definer 함수·트리거로만 기록된다.

-- 1) 지금까지 가입 때 이메일 인증을 마친 회원 → 인증 완료로 옮김.
--    'Confirm email' 을 끈 뒤에는 가입과 동시에 email_confirmed_at 이 찍히므로(가입 시각과 거의 같음),
--    가입 후 10초 넘게 지나서 인증한 회원만 옮긴다 → 나중에 다시 실행해도 메일 인증 없이 가입한 회원은 옮겨지지 않는다.
insert into public.member_verify (user_id, verified_at, method)
select u.id, u.email_confirmed_at, 'signup_email'
from auth.users u
where u.email_confirmed_at is not null and u.email_confirmed_at > u.created_at + interval '10 seconds'
on conflict (user_id) do nothing;

-- 2) 'Confirm email' 을 켜 둔 동안 가입 메일 링크로 인증하는 회원도 자동으로 기록(가입 후 인증 = update)
create or replace function public.verify_on_confirm() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if old.email_confirmed_at is null and new.email_confirmed_at is not null then
    insert into public.member_verify (user_id, verified_at, method) values (new.id, new.email_confirmed_at, 'signup_email')
    on conflict (user_id) do nothing;
  end if;
  return new;
end $$;
drop trigger if exists on_auth_user_confirm on auth.users;
create trigger on_auth_user_confirm after update of email_confirmed_at on auth.users
  for each row execute function public.verify_on_confirm();

create or replace function public.is_verified(p uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.member_verify where user_id = p);
$$;

-- 3) 글쓰기 전 1회 인증: 방금(15분 안) 이메일로 받은 코드·링크·비밀번호 재설정으로 로그인한 세션에서만 기록
create or replace function public.mark_verified() returns boolean
language plpgsql security definer set search_path = public as $$
declare
  a jsonb := coalesce(auth.jwt() -> 'amr', '[]'::jsonb);
  m text;
begin
  if auth.uid() is null then raise exception 'LOGIN_REQUIRED'; end if;
  if public.is_verified(auth.uid()) then return true; end if;
  select e ->> 'method' into m
  from jsonb_array_elements(case when jsonb_typeof(a) = 'array' then a else '[]'::jsonb end) e
  where e ->> 'method' in ('otp', 'magiclink', 'email/signup', 'recovery', 'email_change')
    and coalesce((e ->> 'timestamp')::bigint, 0) > extract(epoch from now())::bigint - 900
  limit 1;
  if m is null then raise exception 'VERIFY_REQUIRED'; end if;
  insert into public.member_verify (user_id, verified_at, method) values (auth.uid(), now(), m)
  on conflict (user_id) do nothing;
  return true;
end $$;
revoke all on function public.mark_verified() from public, anon;
grant execute on function public.mark_verified() to authenticated;

-- 4) 새 글·새 댓글: 인증 기록이 없으면 거절
create or replace function public.guard_verified() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(current_setting('app.sys', true), '') = '1' then return new; end if;
  if auth.uid() is null or public.is_admin() then return new; end if;
  if not public.is_verified(auth.uid()) then raise exception 'VERIFY_REQUIRED'; end if;
  return new;
end $$;
revoke all on function public.guard_verified(), public.verify_on_confirm() from public, anon, authenticated;
drop trigger if exists posts_guard_verified on public.posts;
create trigger posts_guard_verified before insert on public.posts for each row execute function public.guard_verified();
drop trigger if exists comments_guard_verified on public.comments;
create trigger comments_guard_verified before insert on public.comments for each row execute function public.guard_verified();

-- 5) 사진 올리기도 인증한 회원만 (supabase/schema.sql·jobs.sql 의 같은 정책에 조건 하나를 더한 것)
drop policy if exists "post_images_insert" on storage.objects;
create policy "post_images_insert" on storage.objects for insert to authenticated
  with check (bucket_id = 'post-images' and (storage.foldername(name))[1] = auth.uid()::text
              and (public.is_verified(auth.uid()) or public.is_admin()));

-- ------------------------------------------------------------ 확인용
-- select count(*) as 인증완료 from public.member_verify;
-- select count(*) as 전체회원 from auth.users;
-- ------------------------------------------------------------ 되돌리기 (가입 때 인증하는 예전 방식으로)
-- Authentication 에서 'Confirm email' 을 다시 켜고 아래를 실행한다. member_verify 표는 남겨 둬도 된다.
-- drop trigger if exists posts_guard_verified on public.posts;
-- drop trigger if exists comments_guard_verified on public.comments;
