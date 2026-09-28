# 안전duck

안전관리자를 위한 채용·서식·법령 포털. **서버 없음, 운영비 0원**인 정적 사이트입니다.

## 구조

```
config/site.json      사이트 이름·주소·도구(SAFE 덕희) 링크
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

- 위험요인은 `data/hazards.json` 한 곳만 고치면 두 도구에 같이 반영됩니다(업종 `groups`, 항목 `items`).
- 회의록 도구의 화면 클래스(Tailwind)를 바꿨다면 CSS를 다시 만들어야 합니다:
  `npx tailwindcss@3.4.19 -c tools-src/tailwind.config.js -i tools-src/tailwind.in.css -o apps/committee.tailwind.css --minify`
- 도구는 입력 내용을 서버로 보내지 않습니다. TBM만 회사명·공종 등을 그 브라우저(localStorage)에 기억합니다.
- 회의록 도구는 Vue 3.5.43, Phosphor 아이콘 2.1.2, html2pdf 0.10.1을 CDN에서 버전 고정으로 불러옵니다.

## 서버비를 안 쓰는 방법

| 기능 | 방법 |
|---|---|
| 페이지 | 빌드할 때 HTML을 미리 만들어 둠(검색엔진이 그대로 읽음) |
| 서식 파일 | 올리지 않고 국가법령정보센터 원본으로 연결 — 서식이 개정돼도 같은 링크가 현행본을 엶 |
| 내용 편집 | 구글 시트 → 매일 새벽 자동 반영 |
| 검색·필터 | 방문자 브라우저에서 처리 |
| 즐겨찾기 | 방문자 브라우저(localStorage)에만 저장 |
| 안전관리 기록 | SAFE 덕희가 각자 PC에 저장 |

## 처음 올리기 (GitHub Pages)

1. GitHub에 새 저장소 `anjeonduck`(공개)를 만들고 이 폴더 전체를 올립니다.
2. 저장소 **Settings → Pages → Source**를 **GitHub Actions**로 바꿉니다.
3. `config/site.json`에서 `base_url`을 실제 주소로, `tools[0].url`을 SAFE 덕희 주소로 바꿉니다.
4. Actions 탭에서 "빌드·배포"가 끝나면 사이트가 열립니다.

> **SAFE 덕희는 지금 주소에서 옮기지 마세요.** 기록은 주소(도메인)별로 저장되므로 주소가 바뀌면 사용자에게 빈 화면으로 보입니다. 포털은 링크만 겁니다.

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

## 로컬에서 확인

```
python3 build.py
python3 -m http.server -d _site 8000   # http://localhost:8000
```
