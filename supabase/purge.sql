-- 삭제한 글·댓글의 보관 기간(3개월)이 지나면 실제로 지운다. 개인정보 처리방침의 "삭제일부터 3개월" 약속을 지키는 부분.
-- schema.sql 을 실행한 뒤 SQL Editor 에서 한 번 실행한다. 다시 실행해도 된다.
-- 보관 기간을 바꾸면 아래 interval 과 config/site.json 의 community.privacy.deleted_retention 을 함께 고친다.
create or replace function public.purge_deleted() returns void
language sql security definer set search_path = public as $$
  delete from public.comments where deleted_at < now() - interval '3 months';
  delete from public.posts where deleted_at < now() - interval '3 months';
$$;
revoke execute on function public.purge_deleted() from public, anon, authenticated;

create extension if not exists pg_cron;
-- 매일 03:17(KST) = 18:17(UTC)
select cron.schedule('safeplum-purge-deleted', '17 18 * * *', 'select public.purge_deleted()');
