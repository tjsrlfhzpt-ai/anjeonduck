-- SafePlum 2026-11-19 · '가입은 바로, 글쓰기 전 1회 인증' 수정
--
-- 문제: 'Confirm email' 을 끄면 Supabase가 가입 직후 email_confirmed_at 을 따로 한 번 더 채운다(가입 후 0.1초 안).
--   verify_on_write.sql 의 트리거 on_auth_user_confirm 이 이것을 '가입 메일 링크로 인증함'으로 보고
--   member_verify 에 기록 → 2026-11-11 이후 가입한 회원이 메일 인증 없이 바로 '인증 완료'가 되어 글쓰기가 막히지 않았다.
--   (2026-11-19 확인: 05:35:26.022 가입 회원이 05:35:26.099 에 method 'signup_email' 로 기록됨)
--
-- 고침:
--   1) 트리거는 '가입 후 10초 넘게 지나서' 이메일 확인된 경우만 기록(처음 회원 옮길 때 쓴 조건과 같음).
--      Confirm email 을 다시 켜는 경우(메일 링크를 눌러 인증)에도 그대로 동작한다.
--   2) 잘못 기록된 '자동 인증' 회원의 기록을 지운다 → 다음 글·댓글 쓸 때 1회 인증 상자가 나온다.
--      이미 쓴 글·댓글은 그대로 남는다. 운영자 계정은 원래 검사하지 않으므로 영향 없음.
--
-- 실행: Supabase > SQL Editor 에 이 파일 전체를 붙여 넣고 Run. 여러 번 실행해도 안전하다.

create or replace function public.verify_on_confirm() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if old.email_confirmed_at is null and new.email_confirmed_at is not null
     and new.email_confirmed_at > new.created_at + interval '10 seconds' then
    insert into public.member_verify (user_id, verified_at, method) values (new.id, new.email_confirmed_at, 'signup_email')
    on conflict (user_id) do nothing;
  end if;
  return new;
end $$;
revoke all on function public.verify_on_confirm() from public, anon, authenticated;

-- 지우기 전에 몇 명인지 보기(결과 창에 나옴)
select count(*) as 잘못_인증된_회원
from public.member_verify v join auth.users u on u.id = v.user_id
where v.method = 'signup_email' and v.verified_at <= u.created_at + interval '10 seconds';

delete from public.member_verify v
using auth.users u
where u.id = v.user_id
  and v.method = 'signup_email'
  and v.verified_at <= u.created_at + interval '10 seconds';

-- 확인용
-- select count(*) as 인증완료 from public.member_verify;
-- select tgname from pg_trigger where tgname in ('on_auth_user_confirm','posts_guard_verified','comments_guard_verified');
