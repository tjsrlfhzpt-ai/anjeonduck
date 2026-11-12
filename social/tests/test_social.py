"""SNS 자동 운영 시험 — 외부 API 없이(모의 원고·드라이런) 전 구간을 돌린다.   python3 -m unittest social.tests.test_social -v"""
import os, shutil, tempfile, unittest

TMP = tempfile.mkdtemp(prefix="social-test-")
os.environ.update(SOCIAL_STATE_DIR=TMP, SOCIAL_MOCK="1", SOCIAL_DRY="1", SOCIAL_NOW="2026-11-12T08:00")
for k in ("OPENAI_API_KEY", "META_PAGE_TOKEN", "GOOGLE_REFRESH_TOKEN", "SOCIAL_STATS_KEY", "GH_TOKEN", "GITHUB_TOKEN"):
    os.environ.pop(k, None)

from social import evidence as ev, compose, verify, cards, store, run, report   # noqa: E402
from social.common import STATE   # noqa: E402

GOOD = {"blog": {"title": "TBM, 법으로 꼭 해야 할까? 작업 전 안전점검회의 근거와 진행 방법", "meta_description": "작업 전 안전점검회의의 근거와 운영 방법을 정리했습니다.",
                 "intro": "아침 조회 때 TBM을 하긴 하는데, 법에 있는 의무인지 회사 방침인지 헷갈립니다.\n\n법은 위험요인을 근로자에게 알리는 방법의 하나로 작업 전 안전점검회의를 들고 있습니다. " * 6,
                 "law_basis": [{"ref": "산업안전보건법 제36조", "explain": "사업주는 유해·위험 요인을 찾아 개선대책을 세워 이행해야 합니다."}],
                 "key_points": [{"heading": "매일 하는 주기는 권장 운영", "body": "법 조문은 매일이라는 주기를 정하지 않았습니다. " * 8}],
                 "how_to": ["오늘 작업 내용을 공유한다", "위험요인을 함께 찾는다", "대책과 담당을 정한다"],
                 "checklist": ["위험요인을 작업자가 직접 말했는가", "대책이 전달됐는가", "참석자 서명이 있는가"],
                 "faq": [{"q": "매일 해야 하나요?", "a": "매일 하는 주기는 권장 운영입니다."}], "labels": ["TBM", "위험성평가"]},
        "instagram": {"cover_title": "TBM, 법으로 꼭 해야 할까?", "cover_sub": "매일 하는 이유를 묻는 관리감독자에게",
                      "cards": [{"heading": "법 조문부터", "lines": ["산업안전보건법 제36조제4항", "근로자에게 상시 알리도록 노력"]},
                                {"heading": "매일은 권장 운영", "lines": ["법정 주기가 아님", "현장 운영에 맞춘 방식"]},
                                {"heading": "이렇게 진행하세요", "lines": ["작업 내용 공유", "위험요인 함께 찾기"]}],
                      "caption": "TBM은 서류를 채우려고 하는 회의가 아닙니다. 위험요인을 그날 작업에 맞춰 다시 알리는 자리입니다.", "hashtags": ["TBM", "위험성평가"]},
        "facebook": {"text": "아침마다 하는 TBM, 이게 법에 있는 거냐고 물으면 뭐라고 답하시나요.\n\n산업안전보건법은 위험요인을 근로자에게 알리는 방법으로 작업 전 안전점검회의를 들고 있습니다. 매일 하라는 주기까지 정한 것은 아닙니다.\n\n그래도 작업이 날마다 바뀌는 현장이라면 그날 아침에 말해 주는 것이 확실합니다.",
                     "question": "여러분 현장의 TBM은 누가 진행하고 있나요?"}}


def item_for(topic, raw):
    import copy
    return {"id": "20261112a", "date": "2026-11-12", "topic_id": topic["id"], "cat": topic["cat"], "risk": topic["risk"], "title": topic["title"],
            "tools": topic["tools"], "sources": topic["sources"], "raw": copy.deepcopy(raw)}


class Evidence(unittest.TestCase):
    def test_pool_is_grounded(self):
        pool = ev.pool()
        self.assertGreater(len(pool), 1500)
        routes = ev.valid_routes()
        for t in pool.values():
            self.assertTrue(t["facts"], t["id"])
            for tl in t["tools"]:
                self.assertIn(tl["path"], routes, f"{t['id']} → 사이트에 없는 페이지 {tl['path']}")
        cats = {t["cat"] for t in pool.values()}
        self.assertEqual(cats, set(ev.CATS))                      # 요청서의 10개 분야(+질의회시)가 모두 주제를 갖는다

    def test_pick(self):
        import datetime
        d = datetime.date(2026, 11, 12)
        a, b = ev.pick(2, set(), d), ev.pick(2, set(), d)
        self.assertEqual([t["id"] for t in a], [t["id"] for t in b])     # 같은 날은 같은 주제(재실행해도 안 바뀜)
        self.assertEqual(len({t["id"] for t in a}), 2)
        c = ev.pick(2, {t["id"] for t in a}, d)
        self.assertFalse({t["id"] for t in a} & {t["id"] for t in c})    # 이미 쓴 주제는 다시 안 고름
        self.assertFalse(any(t["hold_reason"] for t in a + c))           # 검토 전 소식은 정규 주제가 아님
        self.assertFalse(any("폭염" in t["title"] for t in a + c))         # 11월에 폭염 주제를 고르지 않음

    def test_ai_tool_condition(self):
        self.assertTrue(any("Gemini API 키" in f for f in ev.pool()["tool:law-ai"]["facts"]))


class Compose(unittest.TestCase):
    def test_utm_and_cta(self):
        t = ev.pool()["sched:tbm"]
        it = item_for(t, GOOD)
        u = compose.utm_link("instagram", it, "tools/tbm/")
        self.assertEqual(u, "https://safeplum.com/tools/tbm/?utm_source=instagram&utm_medium=social&utm_campaign=risk_assessment&utm_content=20261112a")
        self.assertIn("&utm_source=facebook", compose.utm_link("facebook", it, "board/?b=qna"))
        self.assertTrue(compose.utm_link("blogger", it, "laws/act/#j36").endswith("#j36"))
        self.assertNotEqual(compose.utm_link("blogger", it), compose.utm_link("facebook", it))   # 게시물·플랫폼마다 다른 추적 주소
        self.assertEqual(compose.josa("위험성평가서", "이가"), "가")
        self.assertEqual(compose.josa("TBM 일지", "은는"), "는")
        self.assertEqual(compose.josa("회의록", "을를"), "을")
        self.assertNotIn("{tool}", compose.cta(it, 1))
        html = compose.blog_html(it, "https://example.com/c.jpg")
        for h in ("관련 법령과 공식 근거", "실무자가 알아야 할 핵심", "실제 업무에 적용하는 순서", "체크리스트", "자주 묻는 질문", "세이프플럼 무료 도구", "근거 자료"):
            self.assertIn(h, html)
        self.assertIn("utm_source=blogger", html)
        specs = compose.card_specs(it)
        self.assertTrue(5 <= len(specs) <= 8)
        self.assertEqual(specs[-1]["title"], "안전보건 실무에 필요한 무료 자료와 작성 도구는 세이프플럼에서 확인하세요.")
        self.assertLessEqual(len(compose.ig_caption(it)), 2200)


class Verify(unittest.TestCase):
    def setUp(self):
        self.t = ev.pool()["sched:tbm"]

    def test_good_passes(self):
        self.assertEqual(verify.rule_check(item_for(self.t, GOOD), self.t), [])

    def bad(self, text, expect):
        it = item_for(self.t, GOOD)
        it["raw"]["blog"]["faq"][0]["a"] = text
        issues = " ".join(verify.rule_check(it, self.t))
        self.assertIn(expect, issues, issues)

    def test_catches_invented_facts(self):
        self.bad("제175조에 따라 과태료가 나옵니다.", "제175조")
        self.bad("과태료는 500만원입니다.", "500만원")
        self.bad("매일 30분을 해야 합니다.", "30분")
        self.bad("2027년 3월 1일부터 시행됩니다.", "2027-03-01")
        self.bad("별표 9에 정해져 있습니다.", "별표9")
        self.bad("무조건 매일 해야 합니다.", "무조건")
        self.bad("자세한 내용은 https://example.com 에서.", "인터넷 주소")

    def test_copy_between_platforms(self):
        it = item_for(self.t, GOOD)
        it["raw"]["facebook"]["text"] = verify.compose.flat_text(it)["instagram"]
        self.assertIn("거의 같음", " ".join(verify.rule_check(it, self.t)))

    def test_duplicate_title(self):
        it = item_for(self.t, GOOD)
        self.assertIn("제목이 거의 같음", " ".join(verify.rule_check(it, self.t, [GOOD["blog"]["title"]])))


class Cards(unittest.TestCase):
    def test_render(self):
        from PIL import Image
        t = ev.pool()["sched:tbm"]
        it = item_for(t, GOOD)
        it["raw"]["instagram"]["cards"][0]["lines"] = ["아주 긴 문장이 들어와도 카드 밖으로 넘치지 않고 줄바꿈되어야 합니다 " * 2] * 4
        ps = cards.render_all(compose.card_specs(it), os.path.join(TMP, "c"))
        for p in ps:
            im = Image.open(p)
            self.assertEqual((im.size, im.format), ((1080, 1350), "JPEG"))       # 인스타그램 API 는 JPEG 만 받는다
            self.assertLess(os.path.getsize(p), 8 * 1024 * 1024)
        self.assertEqual(Image.open(cards.render_cover("제목 " * 30, "분야", os.path.join(TMP, "c", "cover.jpg"))).size, (1200, 630))


class Flow(unittest.TestCase):
    def test_plan_publish_decide_report(self):
        shutil.rmtree(STATE / "state", ignore_errors=True)
        self.assertEqual(run.cmd_plan(), 0)
        lg = store.ledger()
        self.assertGreaterEqual(len(lg["items"]), 1)
        n = len(lg["items"])
        run.cmd_plan()                                                  # 다시 불러도 늘지 않음
        self.assertEqual(len(store.ledger()["items"]), n)
        first = lg["items"][0]
        self.assertTrue((STATE / "queue" / f"{first['id']}.json").exists())
        self.assertTrue((STATE / "media" / first["id"] / "01.jpg").exists())
        self.assertTrue((STATE / "ledger.csv").exists())
        for p in store.PLATFORMS:
            run.cmd_publish(p)                                          # 드라이런: 상태가 바뀌지 않아야 함
        self.assertTrue(all(ps["status"] == "queued" for i in store.ledger()["items"] for ps in i["platforms"].values()))
        held = [i for i in store.ledger()["items"] if i["status"] == "held"]
        if held:
            run.cmd_decide(held[0]["id"], "discard")
            self.assertEqual([i for i in store.ledger()["items"] if i["id"] == held[0]["id"]][0]["status"], "discarded")
        month, text = report.build("2026-11")
        self.assertIn("게시 현황", text)
        self.assertIn("미연결", text)                                    # 유입 집계 열쇠가 없으면 0 이 아니라 '수집하지 못함'으로 적는다

    def test_unconnected_platform_is_not_an_error(self):
        os.environ["SOCIAL_DRY"] = ""
        try:
            self.assertEqual(run.cmd_publish("facebook"), 0)
        finally:
            os.environ["SOCIAL_DRY"] = "1"


if __name__ == "__main__":
    unittest.main()
