-- 글·댓글에 "쓸 당시 닉네임"을 저장한다 (2026-10-19).
-- 닉네임을 바꿔도 이미 쓴 글·댓글에는 그때 닉네임이 그대로 보인다. 탈퇴한 회원은 화면에서 '탈퇴한 회원'으로 보인다.
-- 사용법: Supabase SQL Editor 에 통째로 붙여 넣고 Run. 여러 번 실행해도 안전하다.
alter table public.posts add column if not exists author_nick text;
alter table public.comments add column if not exists author_nick text;

-- 지금까지 쓴 글·댓글은 현재 닉네임으로 채워 둔다.
update public.posts p set author_nick = pr.nickname from public.profiles pr where pr.id = p.author_id and p.author_nick is null;
update public.comments c set author_nick = pr.nickname from public.profiles pr where pr.id = c.author_id and c.author_nick is null;

-- 새 글·댓글: 기존 등록 트리거(posts_bi, comments_bi)가 작성자를 정한 다음, 이름순으로 뒤에 도는 이 트리거가 그 순간 닉네임을 적는다.
-- 브라우저에는 author_nick 쓰기 권한이 없어(컬럼 단위 grant) 다른 이름으로 위장할 수 없다.
create or replace function public.stamp_author_nick() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.author_nick := (select nickname from public.profiles where id = new.author_id);
  return new;
end $$;
drop trigger if exists posts_nick_bi on public.posts;
create trigger posts_nick_bi before insert on public.posts for each row execute function public.stamp_author_nick();
drop trigger if exists comments_nick_bi on public.comments;
create trigger comments_nick_bi before insert on public.comments for each row execute function public.stamp_author_nick();
