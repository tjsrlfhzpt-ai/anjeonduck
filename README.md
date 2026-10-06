# SafePlum

안전관리자를 위한 채용·서식·법령 포털. **서버 없음, 운영비 0원**인 정적 사이트입니다.

## 구조

```
config/site.json      사이트 이름·주소·도구(Mallo) 링크
config/sources.json   구글 시트 CSV 주소(선택)
data/jobs.json        채용공고
data/resources.json   서식·자료
data/laws.json        법령 바로가기 + 개정 소식
data/sites.json       공식 사이트, 외부 채용 검색 링크
assets/               CSS·JS·아이콘
build.py              → _site/ 에 완성 HTML 생성
scripts/sync_sheets.py  구글 시트 → data/*.json
scripts/check_links.py  끊긴 외부 링크 점검
templates/*.csv       구글 시트 머리글 서식
.github/workflows/deploy.yml  매일 자동 빌드·배포, 주 1회 링크 점검
```

## 무료 작성 도구

| 주소 | 원본 파일 | 빌드 때 넣는 것 |
|---|---|---|
| `/tools/tbm/` TBM 일지 | `apps/tbm.html` | `data/hazards.json` (위험요인 목록) |
| `/tools/risk/` 위험성평가서 | `apps/risk.html` | `data/hazards.json` |
| `/tools/committee/` 산보위 회의록·공고·결과보고 | `apps/committee.html` | `apps/committee.tailwind.css` |
| `/tools/council/` 협의체 회의록·개최 통보·결과보고 | `apps/council.html` | `apps/committee.tailwind.css` (산보위와 같이 씀 — 없는 모양은 파일 안 `<style>`에 일반 CSS로) |
| `/tools/safety-cost/` 산업안전보건관리비 계산기 | `apps/safety-cost.body.html` | 사이트 공통 틀(헤더·푸터) |
| `/tools/penalty/` 과태료 부과기준 조회 | `apps/penalty.body.html` | `data/penalties.json` + 공통 틀 |
| `/tools/headcount/` 상시근로자 수 계산기 | `apps/headcount.body.html` | 공통 틀 |
| `/tools/schedule/` 법정 주기업무 달력 | `apps/schedule.body.html` | `data/schedule.json` |
| `/tools/duties/` 직무·책임 조회 · 직무분장표 | `apps/duties.body.html` | `data/lawref.json` |
| `/tools/edu-hours/` 법정교육 시간 조회 | `apps/edu.body.html` | `data/edu_hours.json` |
| `/tools/retention/` 서류 보존기간·벌칙 조회 | `apps/retention.body.html` | `data/retention.json` + `data/lawref.json` |
| `/tools/selection/` 산안법·중처법 적용범위 판정(선임·구성 포함) | `apps/selection.body.html` | `data/selection.json` |
| `/tools/machines/` 기계·기구 법정 의무(안전인증·자율안전확인·안전검사·방호조치·작업 전 점검) | `apps/machines.body.html` | `data/machines.json` |
| `/tools/hpp/` 유해위험방지계획서 대상 진단 | `apps/hpp.body.html` | `data/hpp.json` |
| `/tools/loto/` LOTO 작업금지 태그(A4 가로 3개·양면) | `apps/loto.body.html` | 공통 틀 |
| `/tools/docmap/` 안전보건 서류 체계·감독 대비 자가점검 | `apps/docmap.body.html` | `data/docmap.json` |
| `/tools/forms/<id>/` 서식 작성기 45종(업무일지 3종 포함) | `apps/form.body.html` (서식 엔진 1개) | `data/forms.json` 23종 + 별표 3에서 자동 생성한 작업시작 전 점검표 19종 |
| `/tools/` 법령 순서 카탈로그 | `build.py` | `data/catalog.json` (벤치마킹 목록 78개와 상태) |

### 서식 추가하는 법
`data/forms.json` 의 `forms` 에 하나 더 넣으면 빌드 때 페이지가 생깁니다. 칸 종류: `fields`(라벨·입력, `type`: text/date/select/radio), `text`(긴 글), `table`(행 추가 가능, `defaults`로 기본 문구), `check`(점검표, `opts`로 판정 칸), `signs`(서명줄), `note`(법령 안내문). 사용자는 결재란 이름·점검 항목 문구·표 기본 문구를 화면에서 고칠 수 있고 행·점검 항목을 늘릴 수 있습니다.

### 법령이 바뀌면 고칠 곳

| 도구 | 근거 (원문 확인 2026-09-28) | 고칠 곳 |
|---|---|---|
| 산업안전보건관리비 | 고용노동부고시 제2025-11호(2025.2.12 시행) 제4조·별표 1 | `apps/safety-cost.body.html` 의 `RATES` |
| 과태료 | 산안법 시행령 별표 35(대통령령 제36540호, 2026.8.1 시행) | `data/penalties.json` (version·items) |
| 상시근로자 수 | 근로기준법 시행령 제7조의2 | `apps/headcount.body.html` |
| 직무·조문 원문 | 산안법(2026.8.1)·시행령·시행규칙(고용노동부령 제477호)·기준규칙(제450호)·중처법 시행령 — 원문 확인 2026-09-29 | `data/lawref.json` (조문별 원문, 별표 2·3 표) |
| 교육시간 | 시행규칙 별표 4(2025.5.30 개정) | `data/edu_hours.json` |
| 보존기간·벌칙 | 법 제164조, 규칙 제241조, 기준규칙 제619조의2, 법 제167조~제173조 | `data/retention.json` |
| 주기업무 | 각 업무의 `basis`·`status`(verified=원문 확인 / check=확인 필요 / practice=권장) | `data/schedule.json` |
| 작업계획서·점검표 | 기준규칙 제38조·별표 4, 제35조·별표 3 | `data/forms.json`, 별표 3은 `data/lawref.json` 의 `byl3` |
| 기계·기구 의무 | 법 제80·84·89·93조, 영 제70·74·77·78조·별표 20, 규칙 제98·126조 — 원문 확인 2026-10-01 | `data/machines.json` |
| 유해위험방지계획서 | 법·영·규칙 제42조, 고용노동부고시 제2023-50호 제2·3·6·7조 — 원문 확인 2026-10-01 | `data/hpp.json` |
| 적용범위(공통의무·공시·중처법) | 법 제10조의2·제14조·제36조·부칙(법률 제21374호), 영 제12조의2·제13조, 중처법 제3~7조·영 제4·5조 | `apps/selection.body.html` 의 calc() |
| 서류 체계 | 각 서류의 `basis` | `data/docmap.json` |

- 위험요인은 `data/hazards.json` 한 곳만 고치면 두 도구에 같이 반영됩니다(업종 `groups`, 항목 `items`).
- 회의록 도구의 화면 클래스(Tailwind)를 바꿨다면 CSS를 다시 만들어야 합니다:
  `npx tailwindcss@3.4.19 -c tools-src/tailwind.config.js -i tools-src/tailwind.in.css -o apps/committee.tailwind.css --minify`
- 도구는 입력 내용을 서버로 보내지 않습니다. TBM만 회사명·공종 등을 그 브라우저(localStorage)에 기억합니다.
- 회의록 도구는 Vue 3.5.43, Phosphor 아이콘 2.1.2, html2pdf 0.10.1을 CDN에서 버전 고정으로 불러옵니다.

## v2.4 화면 구성 (KISCOB 벤치마킹)

- 주 메뉴 `무료 도구`·`법령`에 펼침 메뉴(데스크톱, 마우스 올림·키보드 포커스). 메뉴 문구는 `config/site.json` 의 `menu`, 판정·진단 묶음은 `build.py` 의 `DIAG_TOOLS`.
- 홈 판정 띠: 업종·인원 입력 → `/tools/selection/?ind=..&n=..` 로 바로 판정. 유해위험방지계획서·기계 의무·서류 자가점검 바로가기.
- 홈 사이드: 이번 달 안전보건 일정(`data/schedule.json` 의 매월·연간 업무), 질의·상담 바로가기(`data/sites.json` 의 `counsel`).
- 법령 허브 `고시·관련 법령 원문`에 화관법·위험물·고압가스·소방시설법 등 관련 법령 추가(`data/laws.json`).
- 서식 엔진 자동 계산에 `product`(빈도×강도=위험성, 등급 표시) 추가 — `data/form_auto.json` 의 `calc`.

## v2.5 — 안전 브리핑 · 채용공고 직접 등록 · 홈 게시판 블록

### 안전 브리핑 (`data/briefs/YYYY-MM-DD.json` → `/brief/`, `/brief/<날짜>/`)
하루 한 파일. 파일 이름과 `date` 값이 같아야 하고, 항목마다 `title`·`summary`·`sources[{name,url(https)}]` 가 있어야 합니다(없으면 그 항목만 빠지고 경고).

```json
{"date": "2026-10-05", "title": "…", "lead": "…",
 "items": [{"cat": "법령|정책|감독|사고|화학물질|보건|자료", "date": "2026-10-01", "title": "…", "summary": "직접 쓴 요약", "point": "실무 포인트",
            "sources": [{"name": "경향신문", "url": "https://…"}]}],
 "todo": [{"text": "…", "href": "tools/risk/"}], "by": "SafePlum 리포터", "checked": "2026-10-05"}
```
원칙: 기사·보도자료 문장을 옮겨 적지 않고 직접 요약, 출처 링크 필수, 사진 없음, 확인 안 된 숫자는 쓰지 않음.

### 채용공고 직접 등록 (`/jobs/post/`)
1. 구글 설문지를 만듭니다. 질문 제목에 다음 낱말이 들어가야 합니다: `요청 종류`(신규 등록/수정/삭제), `회사명`, `공고 제목`, `기업분류`, `업종`, `직무`, `근무지`, `경력`, `고용형태`, `마감일`, `공고 원문 주소`, `지원 방법`, `한 줄 요약`, `주요 업무`, `자격 요건`. 개인 연락처처럼 공개하면 안 되는 질문은 넣지 않습니다.
2. 응답 시트 맨 오른쪽에 `승인` 열을 만들고, 게시할 행에만 `Y` 를 적습니다.
3. 응답 시트 탭을 [파일 → 공유 → 웹에 게시 → 해당 탭 → CSV]로 게시하고, 그 주소를 저장소 Settings → Variables 의 `JOB_POSTS_CSV` 에 넣습니다(저장소에 주소가 남지 않음).
4. 설문지 주소(`…/viewform`)를 `config/site.json` 의 `job_form.url` 에 넣으면 등록 페이지에 양식이 들어갑니다.

`scripts/sync_sheets.py` 가 매일 승인된 신규 요청만 `data/job_posts.json` 으로 옮깁니다. 공고 원문 주소가 없으면 `지원 방법`을 그대로 보여 주고 이메일이 있으면 지원 버튼을 만듭니다.

### 홈
판정 띠 → 기관 바로가기 띠(`data/sites.json` 의 `official`+`quick`) → 게시판 블록 6개(브리핑·채용·법령 개정·서식 작성기·법정 서식·자료실) + 이번 달 달력 → 도구 카드. 상단 "기기에만 저장" 띠와 하단 "내 데이터 관리" 안내는 없앴고, 백업 창은 푸터의 `작성 내용 백업`으로만 엽니다.

## 서버비를 안 쓰는 방법

| 기능 | 방법 |
|---|---|
| 페이지 | 빌드할 때 HTML을 미리 만들어 둠(검색엔진이 그대로 읽음) |
| 서식 파일 | 올리지 않고 국가법령정보센터 원본으로 연결 — 서식이 개정돼도 같은 링크가 현행본을 엶 |
| 내용 편집 | 구글 시트 → 매일 새벽 자동 반영 |
| 검색·필터 | 방문자 브라우저에서 처리 |
| 즐겨찾기 | 방문자 브라우저(localStorage)에만 저장 |
| 안전관리 기록 | Mallo가 각자 PC에 저장 |

## 처음 올리기 (GitHub Pages)

1. GitHub에 새 저장소 `safetake`(공개)를 만들고 이 폴더 전체를 올립니다.
2. 저장소 **Settings → Pages → Source**를 **GitHub Actions**로 바꿉니다.
3. `config/site.json`에서 `base_url`을 실제 주소로, `tools[0].url`을 Mallo 주소로 바꿉니다.
4. Actions 탭에서 "빌드·배포"가 끝나면 사이트가 열립니다.

> **Mallo는 지금 주소에서 옮기지 마세요.** 기록은 주소(도메인)별로 저장되므로 주소가 바뀌면 사용자에게 빈 화면으로 보입니다. 포털은 링크만 겁니다.

## 채용공고 올리기 (구글 시트)

1. 구글 시트를 만들고 `templates/jobs_template.csv`의 머리글을 1행에 붙입니다(예시 행은 지웁니다).
2. **파일 → 공유 → 웹에 게시 → 해당 탭 → CSV**로 게시하고 주소를 `config/sources.json`의 `jobs_csv`에 넣습니다.
3. 매일 오전 6시 10분에 반영됩니다. 급하면 Actions → "빌드·배포" → Run workflow.

| 칸 | 규칙 |
|---|---|
| id | 영문 소문자·숫자·하이픈 (주소가 됨: `/jobs/<id>/`). 바꾸면 기존 주소가 끊김 |
| job | `안전\|보건` 처럼 `\|`로 여러 개 |
| deadline | `2026-10-15` / `상시` / `채용 시` |
| source_url | 공고 원문. https 가 아니면 그 줄은 빠짐 |
| duties, requirements | 줄 구분은 `\|` |

안전장치: 시트를 못 읽으면 어제 데이터로 배포하고, 행 수가 절반 넘게 줄면 반영하지 않습니다(실수로 지운 경우 대비). 형식이 틀린 줄은 빠지고 Actions 로그에 사유가 남습니다.

법령 개정 소식(`law_updates_csv`), 서식·자료(`resources_csv`)도 같은 방식입니다.

## 서식 자동화

| 기능 | 적용 서식 | 데이터 |
|---|---|---|
| 사업장 정보(회사·대표자·책임자·안전/보건관리자·관리감독자) 한 번 입력 → 모든 서식 자동 기입 | 전 서식(해당 칸) | 브라우저 localStorage `safetake.profile` |
| 교육과정 선택 → 법정 교육시간·교육내용, 특별교육 39개 작업 개별내용 | 교육일지 | `data/edu_contents.json`(규칙 별표 5, HWP 원본 추출), `data/edu_hours.json`(별표 4) |
| 작업 종류 선택 → 법정 확인 항목 | 작업허가서(화기·밀폐·고소·전기·굴착·중장비) | `data/form_auto.json` (기준규칙 조문) |
| 예방대책·작업방법 자동 기입 | 작업계획서 4종 | `data/form_auto.json` |
| 다음 기한 자동 표시 | 협의체(매월), 순회점검(2일/1주), 합동점검(2개월/분기) | 시행규칙 제79·80·82조 |
| 자동 계산 | 참석 인원, 예산 합계·집행률, 직무교육 보수교육 기한(±6개월·기한 경과) | 시행규칙 제29조 |
| 날짜 칸 오늘, 작업시작 전 점검표 점검자 = 관리감독자 | 해당 서식 | 기준규칙 제35조제2항 |

- 자동으로 들어간 값은 모두 고칠 수 있고, 사용자가 고친 계산 칸은 다시 덮어쓰지 않습니다.
- 법령이 바뀌면 `data/lawtext/*.json`(조문 전문), `data/form_auto.json`, `data/edu_contents.json`을 다시 확인하세요.

## 결재란·서명·사진·내 데이터 (assets/docs.js)

모든 페이지 `<head>`에서 불러오는 공통 모듈입니다. 서버 없이 이 기기에만 저장합니다.

| 기능 | 저장 위치 | 쓰는 곳 |
|---|---|---|
| 결재란(기본 담당·검토·승인, 칸 이름·칸 수·성명 수정) | localStorage `safetake.appr.<문서>` / 기본값 `safetake.appr.default` | 서식 작성기 42종, TBM, 위험성평가, 직무분장표, 폭염 기록부, 안전검사 관리대장 |
| 인쇄용 서명 이미지(손글씨·성명 도장, 서명일 표시) | 결재란과 같은 곳(PNG, 240×100 이하로 축소) | 결재란 서명 칸 |
| 사진 첨부(사진마다 개별 칸, 설명·관련 항목·촬영일, 인쇄 시 사진대지) | IndexedDB `safetake`/`photos` (긴 변 1600px JPEG로 축소) | 서식 작성기(점검 항목별 📷 포함), TBM, 위험성평가 |
| 내 데이터 관리(JSON 내보내기·불러오기) | `safetake.*` localStorage 전부 + 사진 | 상단 알림바·푸터 버튼 |

## 법령 전문 (lawpages.py)

`data/lawraw/<key>.txt`(국가법령정보센터 본문 페이지 텍스트) → `python3 scripts/parse_lawtext.py` → `data/lawtext/<key>.json`(편·장·절 목차, 조문, 별표 목록).
빌드하면 `laws/<key>/`(act·yeong·rule·krule·sapa·sapa_dec) 전문 페이지와 `assets/data/lawidx.js`(법령 홈 전체 검색 색인)가 생깁니다.
법령이 개정되면 본문 페이지 텍스트를 다시 받아 lawraw 파일을 바꾸고 파서를 다시 돌리세요(lsiSeq는 parse_lawtext.py 의 LAWS).

## SafePlum 안내 게시물 (data/duck_signs.json)

이미지를 `assets/img/`에 넣고 `data/duck_signs.json`의 items에 한 줄 추가하면 표지 페이지 상단 목록과 A4 인쇄 페이지(`resources/signs/duck-<id>/`)가 생깁니다. 웹용은 WebP(1000px), 인쇄용은 PNG 원본을 씁니다.

## 채용·뉴스 자동 수집 (공공데이터포털 공식 API) — 현재 꺼 둠

켜는 방법: `config/site.json`의 `features.public_api`를 `true`로, 저장소 Settings → Variables에 `PUBLIC_API` = `true`. 끄면 수집 단계와 "안전뉴스" 메뉴·페이지가 모두 빠집니다.


민간 채용사이트·언론사·다른 커뮤니티의 글은 가져오지 않습니다. 아래 세 가지 **공식 공개 API**만 씁니다(이용조건 확인 2026-09-30).

| 화면 | API (공공데이터포털) | 이용허락범위 | 승인 |
|---|---|---|---|
| 채용정보 (공공기관) | 재정경제부_공공기관 채용정보 조회서비스 | 제한 없음 | 개발 자동승인 |
| 안전뉴스 – 정책뉴스 | 문화체육관광부_정책브리핑_정책뉴스_API | 공공누리 제1유형(출처표시) | 자동승인 |
| 안전뉴스 – 사고사망 속보 | 한국산업안전보건공단_사고사망 게시판 정보 조회서비스 | 제한 없음 | 개발 자동승인 |

설정 (한 번만)
1. data.go.kr 회원가입 → 위 세 API 페이지에서 각각 **활용신청** (개인 회원 가능, 자동승인).
2. 마이페이지 → 개발계정 → **일반 인증키(Encoding)** 복사. 세 API가 같은 키를 씁니다.
3. GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret
   이름 `DATA_GO_KR_KEY`, 값에 인증키 붙여넣기.
4. Actions → 빌드·배포 → Run workflow. 이후 매일 오전 6시 10분 자동 갱신.

- 키는 빌드 서버에서만 쓰이고 사이트 파일에는 들어가지 않습니다.
- 키가 없거나 API가 실패해도 빌드는 계속되고, 화면에는 "자동 수집 설정 전" 안내가 나옵니다.
- 기사·공고 본문은 저장하지 않습니다. 제목·기관·날짜·원문 링크만 싣습니다.
- 개발계정 트래픽은 API별 하루 1,000회. 이 사이트는 하루 약 45회 씁니다(채용 최대 30회, 뉴스 10회, 사고 1회).
- 운영계정 전환은 활용사례 등록 후 신청(채용·사고 API는 심의).

민간 기업 채용공고(고용24)는 고용24 **기업회원** 인증키가 필요하고 이용허락이 공공누리 제4유형(비상업)이라 기본으로 넣지 않았습니다.

## 로컬에서 확인

```
python3 build.py
python3 -m http.server -d _site 8000   # http://localhost:8000
python3 build.py --local --out _preview  # 더블클릭으로 여는 미리보기(폴더 링크를 index.html로 바꿈)
```

## v2.6 — 법령 버전·판정·표현 전수 감사 (2026-10-05)

| 구분 | 내용 |
|---|---|
| 법령 버전 | `data/law_manifest.json` 이 법령별 현재 시행본·시행 예정본·최근 개정·확인일·사용 도구(`used_by`)·고시(`notices`)·입법 동향(`bills`)·미확인 항목(`open_items`)을 관리 |
| 조문별 시행일 | `scripts/parse_lawtext.py` 가 본문의 `[시행일: …]` 표기를 읽어 현행 문언과 시행 예정 문언(`pending`)을 분리. 법령 페이지에서 기준일을 고르면 적용 문언이 바뀜 |
| 판정 | 적용범위 판정은 적용·조건부·확인 필요·적용 제외 4단계 + 시행령 별표 1(일부 적용 제외) 반영 |
| 표기 | 도구·서식 하단에 법적 근거 확인일·적용 법령 버전·원문 링크(`build.py` `lawver_html`), 홈 최상단에 법령 데이터 기준일 |
| 양식 지위 | 웹 서식·TBM·산보위·위험성평가·LOTO 는 "SafePlum 자체 제공 양식 · 법정 지정서식이 아님" |
| MSDS | 자동 추출 → 원문 대조 → 확인 체크 후에만 경고표지 인쇄 |
| 브리핑 | 공식 1차 출처가 없는 항목은 빌드에서 제외. 예약 작업은 초안을 PR로만 올리고 사람이 확인 후 병합 |
| 안내 | `/legal/` 법령정보·면책 안내, 푸터 운영·신고 채널(`config/site.json` 의 `operator`, `contact_email`) |

### 감사 스크립트

```
python3 scripts/verify_tables.py        # 적용범위 데이터 ↔ 별표 원본(PDF) 대조
python3 scripts/audit.py _site          # 버전·시행일·출처·금지 표현·필수 안내 (오류면 배포 중단)
python3 scripts/audit.py --online       # 국가법령정보센터 연혁과 공포번호 비교 (주 1회, 실패는 경고)
```

법령이 개정되면: ① `data/lawraw/*.txt` 교체 → `scripts/parse_lawtext.py` ② `data/law_manifest.json` 의 current/upcoming/checked_at 갱신 ③ 영향받는 도구 데이터(`used_by`) 재대조 ④ `audit.py` 통과 확인. 확인일이 `stale_after_days`(45일)를 넘기면 화면에 "공식 원문 재확인 필요"가 표시됩니다.


## 게시판 열기 (커뮤니티 · Q&A, 이메일 인증 회원가입)

글·회원은 정적 사이트에 저장할 수 없어 Supabase(인증 + Postgres)를 씁니다. 사이트는 그대로 GitHub Pages 에 있고, 게시판 화면(`assets/community.js`)만 브라우저에서 Supabase 로 직접 연결합니다. 설정 전에는 게시판이 "준비 중"으로 표시됩니다.

| 파일 | 역할 |
|---|---|
| `supabase/schema.sql` | 테이블·권한 규칙(RLS)·기능 함수. 누가 무엇을 쓸 수 있는지는 전부 여기서 결정 |
| `assets/community.js` | 목록·글 보기·글쓰기·로그인/가입/내 계정 화면 |
| `assets/vendor/supabase.js` | supabase-js 2.117.2 (MIT). CDN 이 아니라 사이트 안에 둠 |
| `config/site.json` → `community` | Supabase 주소·anon 키, 게시판 분류, 처리방침에 나가는 값 |

### 순서

1. supabase.com 에서 프로젝트를 만듭니다. Region 은 Seoul 을 권장합니다.
2. SQL Editor 에 `supabase/schema.sql` 전체를 붙여 실행합니다(다시 실행해도 글은 지워지지 않습니다). 이어서 `supabase/purge.sql` 을 실행합니다(삭제한 글을 3개월 뒤 자동 파기하는 예약 작업).
3. Authentication 설정
   - Email 로그인: 켜기, **Confirm email: 켜기**(이게 꺼져 있으면 인증 없이 가입됩니다), 비밀번호 최소 8자.
   - URL Configuration: Site URL 에 사이트 주소, Redirect URLs 에 `https://도메인/board/account/` 를 추가합니다.
   - SMTP: Supabase 기본 발송은 시험용이라 발송 한도가 매우 낮습니다. 실제 회원을 받으려면 직접 연결한 SMTP(메일 발송 서비스)가 필요하고, 보통 발신 도메인 인증이 필요합니다 → 도메인을 먼저 정해야 합니다.
   - 메일 문구(Templates)를 한국어로 바꿉니다.
4. `config/site.json` 의 `community.supabase_url`, `community.supabase_anon_key` 를 채웁니다. **anon(publishable) 키만** 넣습니다. service_role(secret) 키를 넣으면 빌드가 멈춥니다.
5. `operator.contact_url`(문의·삭제 요청 창구)과 `community.privacy` 값(시행일, DB 리전, 메일 발송 서비스, 삭제 글 보관 기간)을 채웁니다. 비어 있으면 처리방침에 "확인 필요"로 나갑니다. 회원을 받기 전에 반드시 채우세요.
6. 직접 가입한 뒤 SQL Editor 에서 운영자로 지정합니다: `update public.profiles set role = 'admin' where id = (select id from auth.users where email = '운영자 이메일');`

### 운영

- 신고 확인: Table Editor → `reports`. 조치했으면 `handled_at`, `handled_note` 를 적습니다.
- 글·댓글 삭제: 운영자 계정으로 로그인하면 모든 글에 "삭제(운영자)"가 보입니다. 삭제는 `deleted_at` 만 찍는 방식이라 복구하려면 그 값을 지우면 됩니다.
- 공지: Table Editor 에서 해당 글의 `notice` 를 true 로 바꾸면 목록 맨 위에 고정됩니다.
- 이용 정지: Authentication → Users 에서 해당 회원을 Ban 합니다.
- 제한값(글 30초 간격·하루 30건, 댓글 10초 간격·하루 100건, 닉네임 7일 1회)은 `schema.sql` 의 트리거·함수에 있습니다.

### 아직 없는 것

- 글 본문 검색(지금은 제목만), 이미지·파일 첨부, 댓글 수정, 추천·조회수, 알림, 운영자 전용 관리 화면(신고 처리는 Supabase 대시보드에서).
- 검색엔진 노출: 글은 브라우저에서 불러오므로 검색엔진에 잘 잡히지 않습니다. 필요해지면 빌드 때 글 목록을 정적 페이지로 함께 만드는 방식으로 보완할 수 있습니다.
- 자동 스팸 차단(캡차). 가입 남용이 보이면 Supabase Auth 의 CAPTCHA 설정을 켭니다.

## 회원 채용공고 게시판 · 사진 첨부 열기

게시판을 이미 연 프로젝트라면 Supabase → SQL Editor 에 `supabase/jobs.sql` 을 한 번 붙여 넣고 Run 합니다(기존 글·회원은 그대로, 여러 번 실행해도 안전). 새로 만드는 프로젝트는 `supabase/schema.sql` 에 이미 들어 있습니다. 같은 파일이 사진 첨부용 저장소(Storage 버킷 `post-images`, 공개 읽기·본인 폴더만 쓰기·한 장 1MB·JPEG)도 만듭니다. 실행 전에는 사진 첨부가 "준비하고 있습니다"로 안내되고, '채용공고' 탭이 "준비하고 있습니다"로 표시됩니다.

홍보용 오픈채팅방 배너는 `config/site.json` 의 `community.openchat.url` 로 켜고 끕니다(문의 창구 `operator.contact_url` 과 별개).
