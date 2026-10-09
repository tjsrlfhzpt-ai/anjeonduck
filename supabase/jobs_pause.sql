-- SafePlum 회원 채용공고 등록 일시 중지 (서버 쪽 잠금)
-- Supabase SQL Editor 에 통째로 붙여 넣고 한 번 실행한다. 다시 실행해도 안전하다.
--
-- 화면에서 등록 버튼을 닫는 것(config/site.json features.job_posting = false)만으로는
-- 주소나 API 로 직접 보내는 등록까지 막지 못한다. 이 트리거가 있어야 서버에서 거절된다.
-- 막는 것: 채용공고(board = 'job') 새 글 등록 — 운영자 포함 모두.
-- 그대로 두는 것: 이미 올라온 공고의 열람·수정·삭제, 커뮤니티·Q&A 글쓰기.

create or replace function public.posts_job_paused() returns trigger
language plpgsql as $$
begin
  if new.board = 'job' then raise exception 'JOB_PAUSED'; end if;
  return new;
end $$;

drop trigger if exists posts_job_paused on public.posts;
create trigger posts_job_paused before insert on public.posts
  for each row execute function public.posts_job_paused();

-- ------------------------------------------------------------ 다시 열기
-- 등록을 다시 받을 때는 아래 한 줄만 실행하고, config/site.json 의 features.job_posting 을 true 로 바꿔 배포한다.
-- drop trigger if exists posts_job_paused on public.posts;
