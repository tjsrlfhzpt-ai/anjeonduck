#!/usr/bin/env bash
# 상태 브랜치(social-data)를 _social/ 폴더로 받아 오고(pull), 바뀐 것을 올린다(push).
# 장부·원고·카드 이미지·성과·보고서를 main 과 분리해 두는 이유: main 에 올리면 그때마다 사이트가 다시 빌드·배포된다.
set -euo pipefail
BR=social-data
DIR=_social
case "${1:-}" in
  pull)
    rm -rf "$DIR"; git worktree prune
    if git fetch --depth=1 origin "$BR" 2>/dev/null; then
      git worktree add -B "$BR" "$DIR" FETCH_HEAD
    else
      echo "상태 브랜치가 아직 없어 새로 만듭니다."
      git worktree add --detach "$DIR"
      ( cd "$DIR" && git checkout --orphan "$BR" && git rm -rf --quiet . && \
        printf '# 세이프플럼 SNS 자동 운영 — 상태 저장소\n\n이 브랜치는 자동으로 관리됩니다. 손으로 고치지 마세요.\n\n- `ledger.csv` 게시 이력 표\n- `reports/` 월간 보고서\n- `queue/` 원고 전문 · `media/` 카드 이미지 · `metrics/` 일별 성과 · `logs/` 오류 기록\n' > README.md )
    fi
    ;;
  push)
    cd "$DIR"
    # 45일 지난 카드 이미지는 작업 폴더에서 지운다(블로그 표지 cover.jpg 는 글에 계속 쓰이므로 남긴다). 지난 커밋에는 그대로 남아 예전 주소는 계속 열린다.
    if [ -d media ]; then
      CUT=$(date -d '45 days ago' +%Y%m%d)
      for d in media/*/; do
        id=$(basename "$d"); day=${id:0:8}
        if [[ "$day" =~ ^[0-9]{8}$ ]] && [ "$day" -lt "$CUT" ]; then find "$d" -name '[0-9][0-9].jpg' -delete; fi
      done
    fi
    git add -A
    if git diff --cached --quiet; then echo "바뀐 것 없음"; exit 0; fi
    git -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" commit --quiet -m "${2:-상태 저장}"
    for i in 1 2 3; do
      if git push --quiet origin "HEAD:$BR"; then echo "저장 완료"; exit 0; fi
      echo "올리기 실패 — 다시 받아서 재시도($i)"; sleep $((i * 5))
      git fetch --depth=20 origin "$BR" && git rebase FETCH_HEAD || { git rebase --abort || true; }
    done
    echo "상태를 저장하지 못했습니다."; exit 1
    ;;
  *) echo "사용법: state.sh pull | push [메시지]"; exit 2 ;;
esac
