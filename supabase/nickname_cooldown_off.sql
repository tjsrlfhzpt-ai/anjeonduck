-- 닉네임 7일 변경 제한 해제 (2026-10-19). 다시 걸려면 schema.sql 의 set_nickname 을 그대로 다시 실행.
create or replace function public.set_nickname(p text) returns void
language plpgsql security definer set search_path = public as $$
declare cur record;
begin
  if auth.uid() is null then raise exception 'LOGIN_REQUIRED'; end if;
  p := btrim(p);
  if not public.nickname_ok(p) then raise exception 'NICKNAME_INVALID'; end if;
  select * into cur from public.profiles where id = auth.uid();
  if exists (select 1 from public.profiles where lower(nickname) = lower(p) and id <> auth.uid()) then raise exception 'NICKNAME_TAKEN'; end if;
  update public.profiles set nickname = p, nickname_changed_at = now() where id = auth.uid();
end $$;
