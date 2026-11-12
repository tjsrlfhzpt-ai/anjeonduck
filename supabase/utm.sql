-- SNS 유입 추적 (2026-11-12) — Supabase SQL Editor 에서 한 번 실행합니다. 여러 번 실행해도 됩니다.
--
-- 1) utm_ping: 방문 주소에 utm_source 가 붙어 있으면 브라우저(assets/ping.js)가 한 번 부른다.
--    '어느 날, 어느 채널·분야·게시물에서 몇 번 들어왔는지'만 센다. 방문자를 구분하는 값(IP·계정·기기)은 저장하지 않는다.
-- 2) social_stats: SNS 자동 운영(GitHub Actions)이 성과를 읽어 갈 때 부른다. 읽기 전용이고, 아래 social_keys 에 넣은 열쇠가 맞아야 답한다.
--    서비스 키(service_role)를 GitHub 에 넣지 않기 위한 장치다.

create table if not exists public.utm_hits (
  day date not null,
  source text not null,
  medium text not null default '',
  campaign text not null default '',
  content text not null default '',
  hits integer not null default 0,
  primary key (day, source, medium, campaign, content)
);
alter table public.utm_hits enable row level security;
revoke all on public.utm_hits from anon, authenticated;

create or replace function public.utm_ping(p_source text, p_medium text default '', p_campaign text default '', p_content text default '') returns void
language plpgsql security definer set search_path = public as $$
declare d date := (now() at time zone 'Asia/Seoul')::date;
        ok constant text := '^[0-9A-Za-z_.-]{1,40}$';
begin
  if p_source is null or p_source !~ ok then return; end if;
  p_medium := coalesce(p_medium, ''); p_campaign := coalesce(p_campaign, ''); p_content := coalesce(p_content, '');
  if (p_medium <> '' and p_medium !~ ok) or (p_campaign <> '' and p_campaign !~ ok) or (p_content <> '' and p_content !~ ok) then return; end if;
  -- 하루에 새로 생길 수 있는 조합 수를 막아 둔다(주소를 바꿔 가며 표를 부풀리는 장난 방지). 이미 있는 조합의 횟수는 계속 센다.
  if (select count(*) from public.utm_hits where day = d) >= 2000
     and not exists (select 1 from public.utm_hits where day = d and source = p_source and medium = p_medium and campaign = p_campaign and content = p_content) then
    return;
  end if;
  insert into public.utm_hits (day, source, medium, campaign, content, hits) values (d, p_source, p_medium, p_campaign, p_content, 1)
  on conflict (day, source, medium, campaign, content) do update set hits = public.utm_hits.hits + 1;
  if random() < 0.01 then delete from public.utm_hits where day < d - 800; end if;
end $$;
revoke execute on function public.utm_ping(text, text, text, text) from public;
grant execute on function public.utm_ping(text, text, text, text) to anon, authenticated;

create table if not exists public.social_keys (
  key text primary key check (char_length(key) >= 32),
  note text not null default '',
  created_at timestamptz not null default now()
);
alter table public.social_keys enable row level security;
revoke all on public.social_keys from anon, authenticated;

create or replace function public.social_stats(p_key text, p_from date, p_to date) returns jsonb
language plpgsql stable security definer set search_path = public as $$
begin
  if p_key is null or not exists (select 1 from public.social_keys where key = p_key) then
    return jsonb_build_object('error', 'unauthorized');
  end if;
  if p_to - p_from > 400 then p_from := p_to - 400; end if;
  return jsonb_build_object(
    'from', p_from, 'to', p_to,
    'utm', coalesce((select jsonb_agg(jsonb_build_object('day', day, 'source', source, 'medium', medium, 'campaign', campaign, 'content', content, 'hits', hits) order by day)
                     from public.utm_hits where day between p_from and p_to), '[]'::jsonb),
    'visitors', coalesce((select jsonb_agg(jsonb_build_object('day', x.day, 'visitors', x.n) order by x.day)
                          from (select day, count(*) as n from public.visits where day between p_from and p_to group by day) x), '[]'::jsonb),
    'signups', (select count(*) from public.profiles where (created_at at time zone 'Asia/Seoul')::date between p_from and p_to),
    'posts', (select count(*) from public.posts where (created_at at time zone 'Asia/Seoul')::date between p_from and p_to),
    'comments', (select count(*) from public.comments where (created_at at time zone 'Asia/Seoul')::date between p_from and p_to)
  );
end $$;
revoke execute on function public.social_stats(text, date, date) from public;
grant execute on function public.social_stats(text, date, date) to anon, authenticated;

-- 열쇠 넣기(한 번만): 아래 줄의 '여기에…' 를 32자 이상 임의 문자열로 바꿔 실행하고, 같은 값을 GitHub Secret SOCIAL_STATS_KEY 에 넣습니다.
-- insert into public.social_keys (key, note) values ('여기에_32자_이상_임의_문자열', 'GitHub Actions SNS 성과 수집');
