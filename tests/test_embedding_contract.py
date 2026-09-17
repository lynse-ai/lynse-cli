import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import lynse


class FakeHttp:
    def request(self, *args, **kwargs):  # pragma: no cover - network sentinel
        raise AssertionError("unexpected network request")


class EmbeddingContractTests(unittest.TestCase):
    def make_api(self):
        with patch.dict(
            "os.environ",
            {
                "LYNSE_API_HOST": "https://api.lynse.cn",
                "LYNSE_API_KEY": "",
                "LYNSE_ACCESS_TOKEN": "",
            },
            clear=False,
        ):
            return lynse.LynseAPI(
                api_host="https://api.lynse.cn",
                access_token="a.b.c",
                owner_id="owner-1",
                http_client=FakeHttp(),
            )

    def test_version_matches_package_and_skill_metadata(self):
        package = json.loads(Path("package.json").read_text(encoding="utf-8"))
        skill_metadata = re.search(
            r"(?m)^  version:[ \t]*(.+)$", Path("SKILL.md").read_text(encoding="utf-8")
        )
        self.assertEqual(lynse.CLI_VERSION, package["version"])
        self.assertEqual(lynse.CLI_VERSION, skill_metadata.group(1).strip().strip('"'))

    def test_constructor_supports_embedded_consumers(self):
        api = self.make_api()
        self.assertEqual(api.owner_id, "owner-1")
        self.assertEqual(api._get_token(), "a.b.c")
        self.assertIsInstance(api._http, FakeHttp)

    def test_injected_token_does_not_leak_saved_api_key(self):
        with patch.object(
            lynse,
            "_load_user_config",
            return_value={"api_host": "https://api.lynse.cn", "api_key": "saved-key"},
        ):
            api = lynse.LynseAPI(
                api_host="https://api.lynse.cn",
                access_token="a.b.c",
                http_client=FakeHttp(),
            )
        headers = api._build_auth_headers("a.b.c")
        self.assertNotIn("X-API-Key", headers)

    def test_environment_token_does_not_leak_saved_api_key(self):
        with patch.dict("os.environ", {"LYNSE_ACCESS_TOKEN": "a.b.c"}, clear=False):
            with patch.object(
                lynse,
                "_load_user_config",
                return_value={"api_host": "https://api.lynse.cn", "api_key": "saved-key"},
            ):
                api = lynse.LynseAPI(api_host="https://api.lynse.cn")
            headers = api._build_auth_headers("a.b.c")
        self.assertNotIn("X-API-Key", headers)

    def test_todo_write_contracts(self):
        api = self.make_api()
        calls = []
        api._request = lambda method, path, **kwargs: calls.append(
            (method, path, kwargs)
        ) or {"code": 200}

        api.reschedule_todo("todo-1", "2026-08-14")
        api.delete_todos(["todo-1", "todo-2"])
        api.clear_completed_todos()

        self.assertEqual(calls[0][1], "/api/business/file/todo/update")
        self.assertEqual(
            calls[0][2]["json_data"],
            {
                "todoUpdateList": [
                    {
                        "todoId": "todo-1",
                        "expectedCompleteTime": "2026-08-14",
                    }
                ]
            },
        )
        self.assertEqual(
            calls[1][2]["json_data"],
            {"todoIds": ["todo-1", "todo-2"]},
        )
        self.assertEqual(calls[2][1], "/api/business/file/todo/clear")

    def test_folder_extension_contracts(self):
        api = self.make_api()
        calls = []
        api._request = lambda method, path, **kwargs: calls.append(
            (method, path, kwargs)
        ) or {"code": 200}

        api.count_files_by_folder()
        api.change_folder({
            "oldFolderId": "folder-1",
            "newFolderId": "folder-2",
            "fileIds": ["file-1", "file-2"],
        })

        self.assertEqual(calls[0][:2], ("GET", "/api/business/file/category/count"))
        self.assertEqual(
            calls[1][2]["params"],
            {
                "oldFolderId": "folder-1",
                "newFolderId": "folder-2",
                "fileIds": "file-1,file-2",
            },
        )

    def test_delete_folders_allows_server_count_zero(self):
        api = self.make_api()
        api.list_folders = lambda: {
            "code": 200,
            "data": [{"id": "folder-1"}, {"id": "folder-2"}],
        }
        api.count_files_by_folder = lambda: {
            "code": 200,
            "data": {
                "folderStats": [
                    {"folderId": "folder-1", "count": 0},
                    {"folderId": "folder-2", "count": "0"},
                ]
            },
        }
        calls = []
        api._request = lambda method, path, **kwargs: calls.append(
            (method, path, kwargs)
        ) or {"code": 200}

        api.delete_folders(["folder-1", "folder-2"])

        self.assertEqual(calls[0][0], "DELETE")
        self.assertEqual(
            calls[0][2]["params"],
            {"folderIds": "folder-1,folder-2"},
        )

    def test_delete_folders_rejects_batch_when_any_folder_is_nonempty(self):
        api = self.make_api()
        api.list_folders = lambda: {
            "code": 200,
            "data": [{"id": "folder-1"}, {"id": "folder-2"}],
        }
        api.count_files_by_folder = lambda: {
            "code": 200,
            "data": {
                "folderStats": [
                    {"folderId": "folder-1", "count": 0},
                    {"folderId": "folder-2", "count": 3},
                ]
            },
        }
        api._request = lambda *_args, **_kwargs: self.fail(
            "DELETE must not run for a mixed safe/unsafe batch"
        )

        with self.assertRaisesRegex(lynse.LynseAPIError, "not zero"):
            api.delete_folders(["folder-1", "folder-2"])

    def test_delete_folders_rejects_unknown_folder(self):
        api = self.make_api()
        api.list_folders = lambda: {"code": 200, "data": [{"id": "folder-1"}]}
        api.count_files_by_folder = lambda: self.fail(
            "count query must not run for an unknown folder"
        )
        api._request = lambda *_args, **_kwargs: self.fail(
            "DELETE must not run for an unknown folder"
        )

        with self.assertRaisesRegex(lynse.LynseAPIError, "unknown folders"):
            api.delete_folders(["missing-folder"])

    def test_delete_folders_rejects_invalid_server_count(self):
        api = self.make_api()
        api.list_folders = lambda: {"code": 200, "data": [{"id": "folder-1"}]}
        api.count_files_by_folder = lambda: {
            "code": 200,
            "data": {
                "folderStats": [
                    {"folderId": "folder-1", "count": "unknown"},
                ]
            },
        }
        api._request = lambda *_args, **_kwargs: self.fail(
            "DELETE must not run when the server count is invalid"
        )

        with self.assertRaisesRegex(lynse.LynseAPIError, "invalid server counts"):
            api.delete_folders(["folder-1"])

    def test_delete_folders_double_checks_uncounted_folder_inventory(self):
        api = self.make_api()
        api.list_folders = lambda: {"code": 200, "data": [{"id": "folder-1"}]}
        api.count_files_by_folder = lambda: {
            "code": 200,
            "data": {"folderStats": []},
        }
        api.list_files_paged = lambda **_kwargs: {
            "code": 200,
            "total": 2,
            "data": [
                {"id": "file-1", "folderId": "other-folder"},
                {"id": "file-2", "folderId": ""},
            ],
        }
        calls = []
        api._request = lambda method, path, **kwargs: calls.append(
            (method, path, kwargs)
        ) or {"code": 200}

        api.delete_folders(["folder-1"])

        self.assertEqual(calls[0][0], "DELETE")

    def test_delete_folders_rejects_uncounted_folder_with_matching_file(self):
        api = self.make_api()
        api.list_folders = lambda: {"code": 200, "data": [{"id": "folder-1"}]}
        api.count_files_by_folder = lambda: {
            "code": 200,
            "data": {"folderStats": []},
        }
        api.list_files_paged = lambda **_kwargs: {
            "code": 200,
            "total": 1,
            "data": [{"id": "file-1", "folderId": "folder-1"}],
        }
        api._request = lambda *_args, **_kwargs: self.fail(
            "DELETE must not run when inventory contains a target-folder file"
        )

        with self.assertRaisesRegex(lynse.LynseAPIError, "non-empty"):
            api.delete_folders(["folder-1"])

    def test_device_info_uses_current_users_bound_device_list(self):
        api = self.make_api()
        api._request = lambda method, path, **kwargs: {
            "code": 200,
            "data": [
                {
                    "id": "device-1",
                    "serialNumber": "SN-1",
                    "macAddress": "AA:BB:CC:DD:EE:FF",
                }
            ],
        }

        result = api.get_device_info("device-1")

        self.assertEqual(result["data"]["serialNumber"], "SN-1")

    def test_device_unbind_resolves_mac_and_uses_current_endpoint(self):
        api = self.make_api()
        calls = []

        def fake_request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            if path == "/api/business/device/mine":
                return {
                    "code": 200,
                    "data": [
                        {
                            "id": "device-1",
                            "macAddress": "AA:BB:CC:DD:EE:FF",
                        }
                    ],
                }
            return {"code": 200}

        api._request = fake_request

        api.unbind_device("device-1")

        self.assertEqual(
            calls,
            [
                ("GET", "/api/business/device/mine", {}),
                (
                    "GET",
                    "/api/business/device/unbind",
                    {"params": {"macAddress": "AA:BB:CC:DD:EE:FF"}},
                ),
            ],
        )

    def test_audio_contract_uses_presigned_download(self):
        api = self.make_api()
        api.get_file_info = lambda file_id: {
            "code": 200,
            "data": {
                "id": file_id,
                "originalFilename": "meeting.wav",
                "contentType": "audio/wav",
                "size": 4096,
            },
        }
        calls = []
        api._request = lambda method, path, params=None: calls.append(
            (method, path, params)
        ) or {
            "code": 200,
            "data": "https://files.example.test/meeting.wav?signature=short-lived",
        }

        result = api.get_audio_file("meeting-1")

        self.assertEqual(
            calls,
            [
                (
                    "GET",
                    "/api/business/file/presign/download",
                    {"fileId": "meeting-1"},
                )
            ],
        )
        self.assertEqual(result["data"]["mimeType"], "audio/wav")
        self.assertEqual(result["data"]["size"], 4096)

    def test_summary_returns_first_conclusion_by_default(self):
        api = self.make_api()
        api._request = lambda method, path, params=None: {
            "code": 200,
            "data": [
                {"id": "summary-1", "content": "First summary"},
                {"id": "summary-2", "content": "Second summary"},
            ],
        }

        result = api.get_conclusion("meeting-1")

        self.assertEqual(result["data"]["id"], "summary-1")

    def test_summary_all_preserves_conclusion_list(self):
        api = self.make_api()
        conclusions = [
            {"id": "summary-1", "content": "First summary"},
            {"id": "summary-2", "content": "Second summary"},
        ]
        api._request = lambda method, path, params=None: {
            "code": 200,
            "data": conclusions,
        }

        result = api.get_conclusion("meeting-1", first_only=False)

        self.assertEqual(result["data"], conclusions)

    def test_summary_empty_list_normalizes_to_none(self):
        api = self.make_api()
        api._request = lambda method, path, params=None: {"code": 200, "data": []}

        result = api.get_conclusion("meeting-1")

        self.assertIsNone(result["data"])

    def test_summary_alias_maps_all_flag_to_full_list(self):
        calls = []

        class FakeApi:
            def get_conclusion(self, file_id, first_only=True):
                calls.append((file_id, first_only))
                return {"code": 200}

        lynse._ALIAS_HANDLERS["getConclusion"](FakeApi(), ["meeting-1"])
        lynse._ALIAS_HANDLERS["getConclusion"](
            FakeApi(), ["meeting-1", "--all"]
        )

        self.assertEqual(calls, [("meeting-1", True), ("meeting-1", False)])


if __name__ == "__main__":
    unittest.main()
