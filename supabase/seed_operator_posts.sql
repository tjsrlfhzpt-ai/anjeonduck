-- SafePlum 운영팀 안내 글 (선택 사항)
-- 게시판이 비어 보이지 않도록 '운영자 계정'으로 안내 글을 올린다. 가짜 회원·가짜 닉네임은 만들지 않는다.
-- 사용법: 아래 이메일을 운영자(admin) 계정 이메일로 맞춘 뒤 SQL Editor 에 통째로 붙여 넣고 Run.
--         다시 실행하면 같은 제목의 글은 건너뛴다. 올라간 글은 사이트에서 평소처럼 수정·삭제할 수 있다.
do $$
declare
  uid uuid := (select id from auth.users where email = 'tjsrlfhzpt@gmail.com');
  r record;
begin
  if uid is null then raise exception '이 이메일로 가입한 계정이 없습니다. 이메일을 확인하세요.'; end if;
  if not exists (select 1 from public.profiles where id = uid and role = 'admin') then raise exception '이 계정은 운영자(admin)가 아닙니다.'; end if;
  -- 글 등록 규칙(트리거)이 로그인 사용자를 보도록, 이 실행 안에서만 운영자 계정으로 표시한다.
  perform set_config('request.jwt.claim.sub', uid::text, true);
  perform set_config('request.jwt.claims', json_build_object('sub', uid::text, 'role', 'authenticated')::text, true);
  for r in
    select * from (values
      ('free', '정보 공유', true,  '[운영팀] SafePlum 게시판을 열었습니다 — 이용 안내',
       E'안녕하세요, SafePlum 운영팀입니다.\n\n현장 안전·보건 담당자들이 편하게 묻고 나누는 공간을 열었습니다.\n\n· 커뮤니티: 현장 이야기, 정보 공유, 자료 요청\n· Q&A: 실무·법령 질문과 답변 (질문자가 답변을 채택할 수 있습니다)\n· 채용공고: 회원이 직접 올리는 안전·보건 직무 공고\n\n읽기는 누구나, 쓰기는 이메일 인증을 마친 회원이면 됩니다. 이름·전화번호는 받지 않고 닉네임만 공개됩니다.\n\n사람·회사를 알아볼 수 있는 정보(이름, 연락처, 사업장명, 얼굴·차량번호가 찍힌 사진)는 올리지 말아 주세요. 자세한 내용은 이용수칙에 있습니다.\nhttps://safeplum.com/board/rules/'),
      ('free', '자료 요청', false, '[운영팀] 필요한 서식·자료는 이 글에 댓글로 요청해 주세요',
       E'자료실에서 찾지 못한 서식이나, 작성기로 만들어 주었으면 하는 문서가 있으면 댓글로 남겨 주세요.\n\n· 어떤 업무에 쓰는 문서인지\n· 근거가 되는 법령·고시를 알고 있다면 함께\n\n요청이 많은 것부터 검토해서 자료실과 작성기에 반영하겠습니다. 반영 여부와 시기는 약속드리기 어렵지만, 댓글은 모두 읽습니다.\n\n지금 있는 서식·자료: https://safeplum.com/resources/\n작성 도구: https://safeplum.com/tools/'),
      ('free', '정보 공유', false, '[운영팀] 오류 신고·개선 제안은 여기에 남겨 주세요',
       E'도구 계산이 이상하거나, 법령·서식 내용이 현행과 다르거나, 화면이 깨지는 곳을 발견하면 댓글로 알려 주세요.\n\n· 어느 화면인지 (주소를 붙여 주시면 가장 좋습니다)\n· 무엇을 눌렀을 때 어떻게 되었는지\n· PC인지 휴대폰인지\n\nSafePlum의 법령 정보와 계산 결과는 참고 자료입니다. 틀린 곳을 알려 주시면 원문과 대조해 고치겠습니다.'),
      ('qna', '기타 실무', true,  '[운영팀] 질문을 올릴 때 이렇게 적어 주시면 답변이 빨라집니다',
       E'Q&A는 회원끼리 묻고 답하는 공간입니다. 아래 내용을 함께 적어 주시면 답변하는 분이 상황을 이해하기 쉽습니다.\n\n· 업종과 상시근로자 수 (예: 제조업, 약 80명) — 회사 이름은 적지 마세요\n· 도급·하도급 관계가 있는지\n· 이미 찾아본 조문이나 자료\n· 무엇이 헷갈리는지 한 문장으로\n\n답변은 회원 개인의 경험과 의견이며, SafePlum의 공식 견해나 법령 해석이 아닙니다. 법 적용 여부는 법령 원문과 고용노동부 등 소관 기관에서 확인해 주세요.\n\n답변해 주실 때는 근거(조문·고시·공식 자료)를 함께 적어 주시면 큰 도움이 됩니다.\n법령 원문: https://safeplum.com/laws/')
    ) as t(board, category, notice, title, body)
  loop
    if not exists (select 1 from public.posts where author_id = uid and title = r.title and deleted_at is null) then
      insert into public.posts (board, category, title, body, author_id, notice) values (r.board, r.category, r.title, r.body, uid, r.notice);
    end if;
  end loop;
end $$;
