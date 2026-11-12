# 세이프플럼 SNS 자동 운영

세이프플럼 저장소의 검증된 데이터로 안전보건 콘텐츠를 만들어 **Google Blogger · Instagram · Facebook 페이지**에 올리고, 세이프플럼으로 들어온 방문을 게시물별로 셉니다. 서버 없이 GitHub Actions 로 돌아가며 추가 서버비는 없습니다(OpenAI 사용료만 듭니다).

작성 2026-11-12. 이 문서의 "확인 상태" 표를 먼저 읽어 주세요 — 실제 계정에 연결해 본 적이 아직 없습니다.

## 1. 확인 상태

| 구분 | 내용 | 상태 |
|---|---|---|
| 주제 풀·근거 묶음 | 저장소 데이터에서 주제 2,354개 생성, 링크 대상이 모두 실제 페이지인지 대조 | 실행 확인 |
| 검증 관문(규칙 대조) | 근거에 없는 조문·수치·날짜·금지 표현·주소·플랫폼 간 복제 차단 | 시험 통과(11개 시험) |
| 카드뉴스·블로그 표지 | 1080×1350 JPEG 5~8장, 1200×630 표지 | 실제 렌더 확인 |
| 일정 실행·상태 저장 | 워크플로 문법, social-data 브랜치 만들기·저장·다시 받기 | 로컬 원격으로 확인 |
| 유입 집계(사이트) | ping.js 수정, 사이트 빌드·감사 통과 | 빌드 확인. SQL 은 아직 미실행 |
| OpenAI 원고 작성·AI 검증 | 요청 형식은 공식 문서 기준으로 작성 | **미검증**(키 없음) |
| Blogger·Facebook·Instagram 게시 | 요청 형식은 공식 문서 기준으로 작성 | **미검증**(계정·토큰 없음) |
| 성과 수집·월간 보고서 | 보고서 생성은 확인, 플랫폼 수치 수집은 미검증 | 일부 확인 |

미검증 항목은 계정을 연결한 뒤 4장의 순서(연결 점검 → 드라이런 → 1회 실제 게시)로 하나씩 확인합니다. 그 전까지는 "동작한다"고 말할 수 없습니다.

## 2. 구조

```
GitHub Actions (social.yml, 한국 시간)
 07:55  plan       주제 선정 → 근거 묶음 → OpenAI 원고(블로그·인스타·페북 각각) → 검증 → 카드·표지 제작 → 대기열
 08:55  blogger    Blogger API v3 게시 → 다시 조회해 확인
 10:55  instagram  Instagram Graph API 캐러셀 게시 → 확인
 13:55  facebook   Facebook Graph API 페이지 게시 → 확인
 17:55  collect    반응·유입·가입·검색 수집
 매월 1일 report   월간 보고서(표) → 이슈로 알림

main 브랜치          social/ 코드 · data/ 검증된 법령·질의회시·사례 (콘텐츠의 유일한 근거)
social-data 브랜치   장부(state/ledger.json, ledger.csv) · 원고(queue/) · 이미지(media/) · 성과(metrics/) · 보고서(reports/) · 오류(logs/)
```

| 파일 | 역할 |
|---|---|
| `social/config.json` | 하루 건수, 요일별 분야, 자동 게시 여부, 모델, 안내 문구 변형, 금지 표현 |
| `social/evidence.py` | 주제 풀·근거 묶음(콘텐츠·키워드 데이터베이스) |
| `social/prompts/*.md` | 안전보건 전문 에이전트 지침(공통·블로그·인스타·페북·검증자) |
| `social/llm.py` | OpenAI Responses API(구조화 출력) |
| `social/compose.py` | 링크(UTM)·안내 문구·출처 표기·블로그 HTML 조립 |
| `social/verify.py` | 게시 전 검증 관문 |
| `social/cards.py` | 카드뉴스·표지 이미지 |
| `social/publish.py` | 세 플랫폼 게시, 연결 점검 |
| `social/store.py` | 장부·오류 기록·이슈 알림·구글 시트 사본 |
| `social/metrics.py`, `report.py` | 성과 수집, 월간 보고서 |
| `supabase/utm.sql`, `assets/ping.js` | 세이프플럼 유입 집계 |

### 요청서와 다르게 만든 부분

| 요청 | 실제 | 이유 |
|---|---|---|
| n8n | GitHub Actions | 실행 환경으로 GitHub Actions 를 선택하셨음. 서버 0원, 사이트 배포와 같은 방식 |
| 이미지 생성 API | 틀에 글자를 얹는 방식(Pillow) | AI 이미지는 한글과 조문 번호가 깨짐. 안전보건 카드에서 숫자가 틀리면 사고. 추가 비용도 없음 |
| Google Sheets 로 관리 | 장부는 social-data 브랜치(JSON·CSV), 시트는 선택 사본 | 시트가 고장 나도 게시가 멈추지 않게. `ledger.csv` 는 깃허브에서 표로 바로 열림 |
| Google Analytics 4 | 세이프플럼 자체 집계(UTM 횟수) | 사이트에 GA4 가 설치돼 있지 않음. 기존 방문자 집계와 같은 방식이라 쿠키·개인정보 추가 수집 없음 |
| 08시 최신 뉴스 조사 | 저장소의 브리핑·개정 소식·입법 포인트 데이터에서 새 항목 확인 | 깃허브 실행 서버에서 law.go.kr 접속이 실패했던 이력이 있음. 운영자 검토 전(`review: pending`) 브리핑은 보류함으로 감 |
| 매일 1~2건 | 기본 1건(`posts_per_day`), 2건으로 올릴 수 있음 | 새 블로그에 AI 글을 하루 여러 건 올리면 구글이 '대량 생성 콘텐츠'로 볼 위험. 한 달 지켜본 뒤 늘리기 권장 |

## 3. 정확성 관리 — 글이 올라가기까지

| 단계 | 하는 일 | 걸리면 |
|---|---|---|
| ① 근거 묶음 | 주제마다 저장소의 조문 원문·질의회시·사례·공식 발표만 묶어 AI 에게 줌. 원문 확인이 안 끝난 업무(`status: check`)는 주제에서 제외 | — |
| ② 원고 작성 | AI 는 정보만 씀. 주소·홍보 문구·출처 표기는 코드가 붙임(없는 기능·틀린 링크가 구조적으로 못 들어감) | — |
| ③ 규칙 대조 | 조문·별표 번호, 수치+단위, 날짜가 근거 묶음에 있는지 글자 단위로 대조. 금지 표현, 주소 삽입, 분량, 플랫폼 간 복제, 이전 글과 제목 중복, 링크 대상 실재 여부, 출처 도메인 | 고칠 점을 알려 주고 1회 다시 작성 |
| ④ AI 검증자 | 작성과 별도 호출로 사실 주장을 하나씩 근거와 대조(권장→의무, 예정→확정, 발표일·시행일 혼동 포함) | 1회 다시 작성 |
| ⑤ 보류 | 두 번째에도 걸리거나, 검토 전 소식이거나, 그 등급의 자동 게시를 꺼 둔 경우 | 게시하지 않고 `social-hold` 이슈 생성 |
| ⑥ 게시 확인 | 올린 뒤 다시 조회해 공개 상태·주소 확인, 장부 기록 | 실패 기록·재시도 |

보류된 글은 이슈에 원고와 걸린 점이 붙어 옵니다. 저장소 소유자가 그 이슈에 **`/승인`** 또는 **`/폐기`** 라고 댓글을 달면 처리됩니다.

처음 2주는 `config.json` 의 `auto_publish` 를 둘 다 `false` 로 두고 모든 글을 `/승인` 으로 내보내며 품질을 보는 것을 권합니다. 규칙 대조는 보수적이라 맞는 글도 가끔 보류시킵니다(예: "1천만원"처럼 근거와 표기가 다른 수치).

## 4. 설치 순서

준비물이 하나도 없는 상태 기준입니다. A~D 는 계정 발급, E 는 깃허브 설정, F 는 시험입니다. 블로그만 먼저 연결해도 됩니다 — 연결 안 된 플랫폼은 오류가 아니라 '미연결'로 건너뜁니다.

### A. OpenAI

| 순서 | 할 일 |
|---|---|
| 1 | platform.openai.com 가입 → Billing 에서 결제 수단 등록·충전 |
| 2 | API keys → Create new secret key → 값 복사 (다시 볼 수 없음) |
| 3 | 깃허브 Secret `OPENAI_API_KEY` 에 저장 |

모델은 `config.json` 의 `openai.model`(기본 `gpt-5.6-terra`) 또는 저장소 변수 `OPENAI_MODEL` 로 정합니다. 연결 점검이 그 모델을 쓸 수 있는지 확인하고, 안 되면 쓸 수 있는 모델 이름을 알려 줍니다. 주제 1건당 호출은 4회(작성 3 + 검증 1), 다시 쓰면 최대 8회입니다.

### B. Google Blogger

| 순서 | 할 일 |
|---|---|
| 1 | blogger.com 에서 블로그 개설(이름·주소). 대시보드 주소 `blogger.com/blog/posts/숫자` 의 숫자가 **블로그 ID** → 저장소 변수 `BLOGGER_BLOG_ID` |
| 2 | console.cloud.google.com → 새 프로젝트 → "API 및 서비스 > 라이브러리"에서 **Blogger API** 사용 설정 (서치콘솔 수치도 받으려면 **Google Search Console API**, 시트 사본을 쓰려면 **Google Sheets API** 도) |
| 3 | "OAuth 동의 화면": 사용자 유형 외부, 앱 이름·이메일 입력. 만든 뒤 **"앱 게시(프로덕션)"** 로 전환 — 테스트 상태로 두면 토큰이 7일 뒤 만료됩니다 |
| 4 | "사용자 인증 정보 > OAuth 클라이언트 ID": 유형 **웹 애플리케이션**, 승인된 리디렉션 URI 에 `https://developers.google.com/oauthplayground` → 클라이언트 ID·보안 비밀 복사 |
| 5 | developers.google.com/oauthplayground → 오른쪽 위 톱니 → "Use your own OAuth credentials" 체크 → 4의 두 값 입력 |
| 6 | 왼쪽 입력란에 범위를 넣고 Authorize: `https://www.googleapis.com/auth/blogger https://www.googleapis.com/auth/webmasters.readonly` (시트 사본을 쓰면 `https://www.googleapis.com/auth/spreadsheets` 추가). 블로그를 만든 구글 계정으로 동의 |
| 7 | "Exchange authorization code for tokens" → **Refresh token** 복사 |
| 8 | 깃허브 Secret 3개: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` |

### C. Facebook 페이지 · Instagram

| 순서 | 할 일 |
|---|---|
| 1 | Facebook 에서 세이프플럼 **페이지** 만들기 |
| 2 | Instagram 앱 → 설정 → 계정 유형 → **프로페셔널 계정(비즈니스)** 으로 전환하고 1의 페이지와 연결 |
| 3 | developers.facebook.com → 내 앱 → 앱 만들기(유형: 비즈니스). 앱 설정 > 기본에서 **앱 ID·앱 시크릿** 확인, 개인정보처리방침 URL 에 `https://safeplum.com/privacy/` |
| 4 | 도구 > 그래프 API 탐색기: 앱 선택 → "사용자 토큰" → 권한 추가: `pages_show_list` `pages_read_engagement` `pages_manage_posts` `read_insights` `instagram_basic` `instagram_content_publish` `instagram_manage_insights` `business_management` → Generate Access Token (페이지·인스타 계정 선택) |
| 5 | 4의 단기 토큰을 60일 토큰으로 교환(아래 요청 예시 ①) |
| 6 | 60일 사용자 토큰으로 페이지 토큰 받기(요청 예시 ②) → 응답의 `access_token` 이 **페이지 토큰**(만료 없음), `id` 가 **페이지 ID** |
| 7 | 인스타그램 계정 ID 받기(요청 예시 ③) |
| 8 | 앱을 **라이브 모드**로 전환 — 개발 모드에서 API 로 올린 글은 앱 관리자에게만 보입니다 |
| 9 | 깃허브 Secret `META_PAGE_TOKEN`, 변수 `META_PAGE_ID`, `META_IG_USER_ID` |
| 10 | 인스타그램 프로필 링크를 `https://safeplum.com/?utm_source=instagram&utm_medium=social&utm_campaign=profile` 로 설정(캡션의 주소는 눌리지 않음) |

```bash
# ① 단기 → 60일 사용자 토큰
curl -G "https://graph.facebook.com/v26.0/oauth/access_token" \
  -d grant_type=fb_exchange_token -d client_id=앱ID -d client_secret=앱시크릿 -d fb_exchange_token=단기토큰
# ② 페이지 토큰·페이지 ID
curl -G "https://graph.facebook.com/v26.0/me/accounts" -d access_token=60일토큰
# ③ 인스타그램 계정 ID
curl -G "https://graph.facebook.com/v26.0/페이지ID" -d fields=instagram_business_account -d access_token=페이지토큰
```

메타 개발자 화면은 자주 바뀌어 메뉴 이름이 다를 수 있습니다. 라이브 전환 뒤 첫 게시물은 로그아웃한 브라우저에서도 보이는지 꼭 확인하세요. 보이지 않으면 앱 검수(해당 권한의 고급 액세스)가 필요한 경우입니다.

### D. 세이프플럼 유입 집계 (Supabase)

| 순서 | 할 일 |
|---|---|
| 1 | Supabase SQL Editor 에서 `supabase/utm.sql` 전체 실행 |
| 2 | 32자 이상 임의 문자열을 만들어 파일 맨 아래 `insert into public.social_keys …` 줄에 넣어 실행 |
| 3 | 같은 값을 깃허브 Secret `SOCIAL_STATS_KEY` 에 저장 |

실행 전에는 유입 수치가 '수집하지 못함'으로 나올 뿐 사이트나 게시에는 영향이 없습니다.

### E. 깃허브 설정 (저장소 Settings → Secrets and variables → Actions)

| 종류 | 이름 | 값 |
|---|---|---|
| Secret | `OPENAI_API_KEY` | A-2 |
| Secret | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` | B-4, B-7 |
| Secret | `META_PAGE_TOKEN` | C-6 |
| Secret | `SOCIAL_STATS_KEY` | D-2 |
| Variable | `BLOGGER_BLOG_ID` | B-1 |
| Variable | `META_PAGE_ID`, `META_IG_USER_ID` | C-6, C-7 |
| Variable | `SOCIAL_ENABLED` | `true` 로 두면 예약 실행 시작. 지우거나 다른 값이면 정지 |
| Variable(선택) | `OPENAI_MODEL`, `SOCIAL_POSTS_PER_DAY`, `SOCIAL_SHEET_ID`, `GSC_SITE_URL` | 모델 이름 / 1 또는 2 / 구글 시트 ID / 서치콘솔 속성 주소 |

토큰·키는 Secret 에만 넣습니다. 이 저장소는 공개 저장소라 파일이나 이슈에 적으면 누구나 볼 수 있습니다.

### F. 시험 순서 (Actions → "SNS 자동 운영" → Run workflow)

| 순서 | task | dry_run | 확인할 것 |
|---|---|---|---|
| 1 | `preflight` | 체크 | 서비스별 정상/미연결/오류 표 |
| 2 | `plan` | 체크 | 오늘 주제와 검증 결과. social-data 브랜치 `queue/`·`media/` 에 원고와 카드가 생김 |
| 3 | `blogger` | 체크 | 보낼 제목·본문 길이가 기록에 찍힘(게시 안 함) |
| 4 | `blogger` | 해제 | 실제 1건 게시. 블로그에서 글·표지·링크 확인 |
| 5 | `instagram`, `facebook` | 해제 | 각각 1건. 로그아웃 상태에서도 보이는지 확인 |
| 6 | — | — | 문제없으면 변수 `SOCIAL_ENABLED=true` |

로컬에서도 같은 명령을 쓸 수 있습니다: `SOCIAL_MOCK=1 SOCIAL_DRY=1 python3 -m social.run plan` (API 없이 전 구간), `python3 -m unittest social.tests.test_social`.

## 5. API 요청 형식 (코드가 실제로 보내는 것)

```bash
# OpenAI — 구조화 출력(JSON 스키마)으로 원고 받기
curl https://api.openai.com/v1/responses -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" -d '{
  "model": "gpt-5.6-terra", "instructions": "<system.md + blog.md>", "input": "[주제] … [근거 묶음] …",
  "text": {"format": {"type": "json_schema", "name": "safeplum_blog", "strict": true, "schema": { … }}}}'

# 구글 접근 토큰(1시간) 받기
curl https://oauth2.googleapis.com/token -d client_id=… -d client_secret=… -d refresh_token=… -d grant_type=refresh_token
# Blogger 게시 → 확인
curl -X POST "https://www.googleapis.com/blogger/v3/blogs/$BLOG_ID/posts/?isDraft=false" -H "Authorization: Bearer $AT" \
  -H "Content-Type: application/json" -d '{"kind":"blogger#post","title":"…","content":"<p>…</p>","labels":["TBM"]}'
curl "https://www.googleapis.com/blogger/v3/blogs/$BLOG_ID/posts/$POST_ID?fields=id,url,status" -H "Authorization: Bearer $AT"

# Facebook 페이지 게시 → 확인
curl -X POST "https://graph.facebook.com/v26.0/$PAGE_ID/feed" -d message="…" -d link="https://safeplum.com/tools/tbm/?utm_source=facebook&…" -d access_token=$PAGE_TOKEN
curl -G "https://graph.facebook.com/v26.0/$POST_ID" -d fields=id,permalink_url -d access_token=$PAGE_TOKEN

# Instagram 캐러셀: 카드마다 컨테이너 → 캐러셀 컨테이너 → 게시 → 확인 (이미지는 공개 주소의 JPEG)
curl -X POST "https://graph.facebook.com/v26.0/$IG_ID/media" -d image_url="https://cdn.jsdelivr.net/gh/<저장소>@<커밋>/media/<글ID>/01.jpg" -d is_carousel_item=true -d access_token=$PAGE_TOKEN
curl -G "https://graph.facebook.com/v26.0/$CONTAINER_ID" -d fields=status_code -d access_token=$PAGE_TOKEN     # FINISHED 까지 대기
curl -X POST "https://graph.facebook.com/v26.0/$IG_ID/media" -d media_type=CAROUSEL -d children="id1,id2,…" -d caption="…" -d access_token=$PAGE_TOKEN
curl -X POST "https://graph.facebook.com/v26.0/$IG_ID/media_publish" -d creation_id=$CAROUSEL_ID -d access_token=$PAGE_TOKEN
```

추적 주소 형식: `https://safeplum.com/<도구 경로>?utm_source=<blogger|instagram|facebook>&utm_medium=<blog|social>&utm_campaign=<분야>&utm_content=<글 ID>` — 글마다, 플랫폼마다 다릅니다.

## 6. 오류와 복구

| 상황 | 자동 처리 | 운영자가 할 일 |
|---|---|---|
| 429·5xx·연결 끊김 | 2·6·18초 간격 재시도(게시 요청 자체는 중복을 막으려고 재전송하지 않음) | 없음 |
| 게시 실패 | 장부에 실패·사유 기록, 다음 예약 실행 때 재시도(최대 3회). 재시도 전에 최근 게시물을 조회해 이미 올라갔으면 다시 올리지 않음 | 3회 모두 실패하면 `social-error` 이슈 확인 |
| 토큰 만료·권한 오류(401·403) | 즉시 `social-error` 이슈 | 4장대로 토큰 재발급 → Secret 교체 → task `retry` 실행 |
| 인스타그램이 이미지 주소를 못 읽음 | 페이스북 임시 사진 주소로 자동 전환 | 없음 |
| 08시 실행이 빠짐(깃허브 예약 누락) | 게시 실행이 먼저 원고 작성을 채움 | 없음 |
| 48시간 넘게 못 올린 글 | '건너뜀' 처리(묵은 글이 뒤늦게 올라가지 않게) | 없음 |
| 잘못된 정보를 게시 후 발견 | — | 변수 `SOCIAL_ENABLED` 를 지워 정지 → 플랫폼에서 글 수정·삭제 → 원인 데이터(`data/`) 수정 |
| 수집 일부 실패 | 나머지 계속, 보고서에 '수집하지 못한 항목'으로 표시(0 으로 적지 않음) | 필요하면 연결 점검 |

모든 오류는 social-data 브랜치 `logs/errors.jsonl` 에 남고(토큰은 가림), 실행 요약은 Actions 실행 화면 Summary 에 표로 나옵니다.

## 7. 성과 측정

| 항목 | 출처 | 비고 |
|---|---|---|
| 플랫폼별 게시 수 | 장부 | |
| 도달·조회·좋아요·댓글·공유·저장 | Instagram·Facebook 인사이트 | 게시 직후에는 값이 비어 있을 수 있음 |
| 블로그 댓글, 블로그 30일 조회수 | Blogger API | 글별 조회수는 API 가 주지 않음 |
| 플랫폼·분야·게시물별 세이프플럼 유입 | 자체 집계(`utm_hits`) | 방문 횟수만 셈. 같은 탭에서 같은 게시물은 1회 |
| 방문자·신규 가입·커뮤니티 글·댓글 | Supabase `social_stats` | 읽기 전용 열쇠로 조회 |
| 검색 노출·클릭·검색어 | Search Console API | 구글 토큰에 webmasters.readonly 권한 필요 |
| 월간 보고서 | `reports/YYYY-MM.md` + 이슈 | 분야별 '글 1건당 유입' 순위 포함 |

## 8. 알려진 한계

| 항목 | 내용 |
|---|---|
| 실제 API 미검증 | 1장 표 참고. 첫 연결 때 오류가 나올 수 있고, 그때 고쳐야 합니다 |
| 예약 시각 | 깃허브 예약 실행은 몇 분~수십 분 늦을 수 있습니다 |
| 인스타그램 링크 | 캡션 주소는 눌리지 않아 게시물별 유입은 프로필 링크(utm_campaign=profile)로만 잡힙니다 |
| 최신 소식 | 저장소의 브리핑·개정 소식 데이터가 갱신돼야 새 소식 주제가 생깁니다. 실시간 뉴스 수집은 하지 않습니다 |
| 이미지 저장 | 카드 이미지가 social-data 브랜치 이력에 쌓입니다(하루 약 0.5~1MB). 작업 폴더에서는 45일 뒤 지우지만 이력에는 남습니다 |
| 메타 정책 | 앱 모드·검수 요건은 메타가 바꿀 수 있습니다 |
| 댓글·DM 응대 | 자동화하지 않습니다 |
