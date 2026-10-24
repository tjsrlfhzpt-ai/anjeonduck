-- SafePlum 채용공고 — 직업안정법 시행령 제28조(직업정보제공사업자의 준수 사항) 서버 검증 (2026-10-24)
-- 새로 올리는 채용공고(board = 'job')는 사업자등록번호(검증번호 계산식 통과)·채용 담당 연락처·급여를 반드시 갖춰야 한다.
--  · 제1호: 업체명·사업자등록증 등으로 구인자를 확인할 수 없거나 연락처가 사서함 등인 구인광고 게재 금지
--  · 제6호: 최저임금에 미달하는 구인정보 게재 금지(급여 칸 필수 + 화면에서 최저임금 이상 확인)
-- 이미 올라와 있는 공고의 수정은 막지 않는다(insert 에만 적용). 다시 실행해도 된다.

create or replace function public.bizno_ok(v text) returns boolean
language plpgsql immutable as $$
declare d text := regexp_replace(coalesce(v, ''), '\D', '', 'g'); w int[] := array[1,3,7,1,3,7,1,3,5]; s int := 0; i int;
begin
  if d !~ '^\d{10}$' then return false; end if;
  for i in 1..9 loop s := s + substr(d, i, 1)::int * w[i]; end loop;
  s := s + (substr(d, 9, 1)::int * 5) / 10;
  return (10 - s % 10) % 10 = substr(d, 10, 1)::int;
end $$;

create or replace function public.posts_job_compliance() returns trigger
language plpgsql security definer set search_path = public as $$
declare c text;
begin
  if new.board <> 'job' or public.is_admin() then return new; end if;
  if not public.bizno_ok(new.meta ->> 'bizno') then raise exception 'JOB_BIZNO_INVALID'; end if;
  c := btrim(coalesce(new.meta ->> 'contact', ''));
  if char_length(c) < 7 or c ~* '(사서함|p\.?\s*o\.?\s*box)' or not (c ~ '@' or c ~ '\d{2,4}-?\d{3,4}-?\d{4}') then raise exception 'JOB_CONTACT_INVALID'; end if;
  if char_length(btrim(coalesce(new.meta ->> 'pay', ''))) < 2 then raise exception 'JOB_PAY_REQUIRED'; end if;
  return new;
end $$;

drop trigger if exists posts_job_compliance on public.posts;
create trigger posts_job_compliance before insert on public.posts
  for each row execute function public.posts_job_compliance();
