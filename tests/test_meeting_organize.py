"""Tests for the `meetings organize` feature.

Covers the pure classification/plan logic (no network) and the
`LynseAPI.organize_meetings()` orchestration (plan mode + execute mode +
the non-TTY safety gate), using the `__new__` + fake-method pattern.
"""

import contextlib
import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import lynse
from lynse import (
    LynseAPI,
    _classify_meeting_title,
    _normalize_folder_name,
    _match_existing_folder,
    build_organize_plan,
    _extract_folder_id,
    _MOVE_CHUNK,
)


def _meeting(mid, title, conclusion_id="c1", folder_id=None):
    return {
        "id": mid,
        "originalFilename": title,
        "conclusionId": conclusion_id,
        "folderId": folder_id,
        "recordStartTime": "2026-06-01 10:00:00",
    }


class ClassifyTests(unittest.TestCase):
    def test_prefix_wins_over_content_keywords(self):
        # "产品" appears in the suffix, but the declared prefix is 销售 -> 销售
        self.assertEqual(_classify_meeting_title("销售：产品售价与分成谈判"), "销售")
        self.assertEqual(_classify_meeting_title("营销：新品电商营销及产品迭代"), "市场")

    def test_content_fallback_when_no_recognized_prefix(self):
        self.assertEqual(_classify_meeting_title("UI交互设计讨论：AI聊天界面基础交互逻辑"), "设计")

    def test_extended_categories(self):
        self.assertEqual(_classify_meeting_title("法务：智能硬件出海数据合规"), "法务")
        self.assertEqual(_classify_meeting_title("面试：前端岗位候选人沟通"), "面试")

    def test_unknown_goes_to_overflow(self):
        self.assertEqual(_classify_meeting_title("乱七八糟的标题"), "其他")
        self.assertEqual(_classify_meeting_title(""), "其他")

    def test_english_prefix(self):
        self.assertEqual(_classify_meeting_title("Product：Markdown export feature discussion"), "产品")
        self.assertEqual(_classify_meeting_title("Marketing：Product launch campaign"), "市场")


class NormalizeAndMatchTests(unittest.TestCase):
    def test_normalize_strips_leading_icon(self):
        self.assertEqual(_normalize_folder_name("🏗️产品研发"), "产品研发")
        self.assertEqual(_normalize_folder_name("💼 销售商务"), "销售商务")
        self.assertEqual(_normalize_folder_name("📚教育"), "教育")

    def test_match_reuses_by_prefix(self):
        existing = [
            {"id": "a", "folderName": "🏗️产品研发"},
            {"id": "b", "folderName": "💼销售商务"},
            {"id": "d", "folderName": "⚖️法务合规"},
            {"id": "e", "folderName": "👤面试"},
        ]
        self.assertEqual(_match_existing_folder("产品", existing), "a")
        self.assertEqual(_match_existing_folder("销售", existing), "b")
        self.assertEqual(_match_existing_folder("法务", existing), "d")
        self.assertEqual(_match_existing_folder("面试", existing), "e")

    def test_match_no_false_positive(self):
        # 技术 must not reuse 产品研发 (even though 研发 is a 技术 keyword)
        existing = [{"id": "a", "folderName": "🏗️产品研发"}]
        self.assertIsNone(_match_existing_folder("技术", existing))
        # 销售 must not reuse 产品研发
        self.assertIsNone(_match_existing_folder("销售", existing))

    def test_match_overflow_folder(self):
        existing = [{"id": "x", "folderName": "🗂其他"}]
        self.assertEqual(_match_existing_folder("其他", existing), "x")
        self.assertIsNone(_match_existing_folder("其他", []))


class BuildPlanTests(unittest.TestCase):
    def test_skips_already_in_place_and_reports_totals(self):
        meetings = [
            _meeting("m1", "产品：功能评审", folder_id="fa"),      # already in 产品 folder -> in place
            _meeting("m2", "产品：另一个", folder_id=None),         # needs move
            _meeting("m3", "random noise"),                        # has conclusion, unclassified -> 其他
        ]
        existing = [{"id": "fa", "folderName": "🏗️产品研发"}]
        plan = build_organize_plan(meetings, existing)
        self.assertEqual(plan["mode"], "plan")
        self.assertEqual(plan["totals"]["scanned"], 3)
        self.assertEqual(plan["totals"]["with_conclusion"], 3)
        self.assertEqual(plan["totals"]["already_organized"], 1)  # m1
        self.assertEqual(plan["totals"]["to_move"], 2)            # m2 + m3
        product = next(f for f in plan["folders"] if f["category"] == "产品")
        self.assertEqual(product["action"], "REUSE")
        self.assertEqual(product["target_folder_id"], "fa")
        self.assertEqual(product["meeting_ids"], ["m2"])          # m1 excluded (in place)

    def test_separates_no_conclusion_meetings(self):
        meetings = [
            _meeting("m1", "产品：x", conclusion_id="c"),
            _meeting("m2", "产品：y", conclusion_id=None),  # no conclusion
        ]
        plan = build_organize_plan(meetings, [])
        self.assertEqual(plan["totals"]["with_conclusion"], 1)
        self.assertEqual(plan["totals"]["no_conclusion"], 1)
        self.assertEqual([s["id"] for s in plan["skipped_no_conclusion"]], ["m2"])

    def test_caps_categories_and_overflows(self):
        titles = [
            "产品：a", "市场：b", "销售：c", "战略：d", "旅游：e",
            "教育：f", "技术：g", "设计：h", "客服：i", "运营：j",
            "法务：k", "面试：l",
        ]
        meetings = [_meeting(f"m{i}", t) for i, t in enumerate(titles)]
        plan = build_organize_plan(meetings, [])
        non_overflow = [f for f in plan["folders"] if not f["is_overflow"]]
        overflow = [f for f in plan["folders"] if f["is_overflow"]]
        self.assertLessEqual(len(non_overflow), 10)
        self.assertEqual(len(overflow), 1)
        # two categories folded into overflow
        self.assertEqual(overflow[0]["meeting_count"], 2)
        # nothing dropped
        self.assertEqual(sum(f["meeting_count"] for f in plan["folders"]), 12)

    def test_create_folder_naming_uses_icon_plus_name(self):
        plan = build_organize_plan([_meeting("m1", "市场：推广")], [])
        f = plan["folders"][0]
        self.assertEqual(f["action"], "CREATE")
        self.assertEqual(f["target_folder_name"], "📣市场")
        self.assertIsNone(f["target_folder_id"])


class ExtractFolderIdTests(unittest.TestCase):
    def test_dict_data(self):
        self.assertEqual(_extract_folder_id({"data": {"id": "abc"}}), "abc")

    def test_scalar_data(self):
        self.assertEqual(_extract_folder_id({"data": "xyz"}), "xyz")

    def test_missing(self):
        self.assertIsNone(_extract_folder_id({"data": None}))


class OrganizeMeetingsTests(unittest.TestCase):
    def setUp(self):
        self.api = LynseAPI.__new__(LynseAPI)
        self.api.api_host = lynse.DEFAULT_API_HOST
        self.api.get_current_customer = lambda: {"data": {"id": "owner-1"}}
        self.calls = {"create": [], "change": []}

    def _wire(self, meetings, folders):
        self.api.list_files_paged = lambda **k: {"data": meetings}
        self.api.list_folders = lambda: {"data": folders}

        def fake_create(payload):
            self.calls["create"].append(payload)
            return {"code": 200, "data": {"id": "new-" + payload["folderName"]}}

        def fake_change(payload):
            self.calls["change"].append(payload)
            for meeting in meetings:
                if meeting["id"] in payload["fileIds"]:
                    meeting["folderId"] = payload["newFolderId"]
            return {"code": 200, "data": True}

        self.api.create_folder = fake_create
        self.api.change_folder = fake_change

    def test_plan_mode_makes_no_writes(self):
        meetings = [_meeting("m1", "产品：x"), _meeting("m2", "市场：y")]
        self._wire(meetings, [{"id": "fa", "folderName": "🏗️产品研发"}])
        result = self.api.organize_meetings()
        self.assertEqual(result["mode"], "plan")
        self.assertEqual(self.calls["create"], [])
        self.assertEqual(self.calls["change"], [])

    def test_90_day_window_only_moves_records_with_matching_dates(self):
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(days=1)).isoformat()
        records = [
            {**_meeting("recent", "产品：x"), "recordStartTime": recent},
            {**_meeting("from-create", "产品：y"), "recordStartTime": "", "createTime": recent},
            {**_meeting("old", "产品：old"), "recordStartTime": (now - timedelta(days=91)).isoformat()},
            {**_meeting("future", "产品：future"), "recordStartTime": (now + timedelta(days=1)).isoformat()},
            {**_meeting("undated", "产品：z"), "recordStartTime": "unknown"},
        ]
        self._wire(records, [])
        plan = self.api.organize_meetings(days=90)
        self.assertEqual(plan["scope"]["days"], 90)
        self.assertEqual(plan["scope"]["skipped_unknown_date"], 1)
        self.assertEqual(plan["folders"][0]["meeting_ids"], ["recent", "from-create"])
        self.assertEqual(self.calls, {"create": [], "change": []})

        result = self.api.organize_meetings(days=90, execute=True, yes=True, plan_id=plan["plan_id"])
        self.assertEqual(result["results"]["moves_succeeded"], 2)
        self.assertEqual(self.calls["change"][0]["fileIds"], ["recent", "from-create"])

    def test_changed_scope_rejects_the_approved_plan_before_writes(self):
        meetings = [_meeting("m1", "产品：x", folder_id="original")]
        self._wire(meetings, [])
        approved = self.api.organize_meetings()["plan_id"]
        meetings[0]["folderId"] = "changed"
        with self.assertRaisesRegex(lynse.LynseAPIError, "plan has changed"):
            self.api.organize_meetings(execute=True, yes=True, plan_id=approved)
        self.assertEqual(self.calls, {"create": [], "change": []})

    def test_reports_only_moves_verified_by_receipt_and_readback(self):
        self._wire([_meeting("m1", "产品：x")], [{"id": "target", "folderName": "产品"}])
        approved = self.api.organize_meetings()["plan_id"]
        for receipt in ({"code": 200, "data": False}, {"code": 200, "data": True}):
            with self.subTest(receipt=receipt), mock.patch.object(self.api, "change_folder", return_value=receipt):
                result = self.api.organize_meetings(execute=True, yes=True, plan_id=approved)
                self.assertEqual(result["code"], 500)
                self.assertEqual(result["results"]["moves_succeeded"], 0)
                self.assertEqual(result["results"]["errors"][0]["meeting_id"], "m1")

    def test_invalid_day_counts_are_rejected_before_reading_files(self):
        self.api.list_files_paged = mock.Mock()
        for days in (0, -1, 10**9):
            with self.subTest(days=days), self.assertRaisesRegex(lynse.LynseAPIError, "positive integer"):
                self.api.organize_meetings(days=days)
        self.api.list_files_paged.assert_not_called()

    def test_execute_yes_creates_and_moves_with_chunking(self):
        # 60 product meetings -> must be chunked (>50) into >=2 change_folder calls
        meetings = [_meeting(f"m{i}", "产品：item{i}") for i in range(60)]
        self._wire(meetings, [])  # no existing 产品 folder -> CREATE
        result = self.api.organize_meetings(execute=True, yes=True)
        self.assertEqual(result["mode"], "execute")
        self.assertTrue(result["results"]["folders_created"])
        self.assertEqual(result["results"]["moves_succeeded"], 60)
        # exactly 2 chunks of 50 + 10
        product_moves = [c for c in self.calls["change"]]
        chunk_sizes = sorted(len(c["fileIds"]) for c in product_moves)
        self.assertEqual(chunk_sizes, [10, 50])
        for c in product_moves:
            self.assertLessEqual(len(c["fileIds"]), _MOVE_CHUNK)

    def test_execute_refuses_non_tty_without_yes(self):
        self._wire([_meeting("m1", "产品：x")], [])
        with mock.patch("sys.stdout") as m_stdout:
            m_stdout.isatty.return_value = False
            with self.assertRaises(SystemExit):
                self.api.organize_meetings(execute=True, yes=False)
        # refused before any writes
        self.assertEqual(self.calls["create"], [])

    def test_execute_surfaces_create_failures(self):
        # 战略 is not an existing folder -> CREATE; make create_folder fail and
        # confirm the failure is reported (not swallowed) and no move happens.
        self._wire([_meeting("m1", "战略：投资讨论")], [])
        self.api.create_folder = lambda payload: (_ for _ in ()).throw(RuntimeError("server 503"))
        approved = self.api.organize_meetings()["plan_id"]
        args = ["lynse", "meetings", "organize", "--execute", "--yes", "--plan-id", approved, "--json"]
        output = io.StringIO()
        with mock.patch.object(lynse.sys, "argv", args), \
                mock.patch.object(lynse, "LynseAPI", return_value=self.api), \
                mock.patch.object(lynse, "_maybe_print_update_notice"), \
                contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as failure:
            lynse.main()
        self.assertEqual(failure.exception.code, lynse.EXIT_SERVER)
        result = json.loads(output.getvalue())
        self.assertEqual(result["mode"], "execute")
        self.assertEqual(result["results"]["folders_created"], [])
        self.assertTrue(result["results"]["folders_failed"])
        self.assertEqual(result["results"]["folders_failed"][0]["name"], "🎯战略")
        self.assertEqual(self.calls["change"], [])  # no target id -> no move


if __name__ == "__main__":
    unittest.main()
