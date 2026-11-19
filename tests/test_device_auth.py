import contextlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import lynse


class DeviceAuthTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(lynse, "_get_user_config_dir", return_value=Path(directory)))
        self.session_path = lynse._device_path("workbuddy")
        self.session = {
            "session_id": "s" * 43, "access_token": "a" * 43, "refresh_token": "b" * 43 + "." + "c" * 64,
            "access_expires_at": int(time.time()) + 300, "client_id": "lynse-cli",
            "resource": "https://api.lynse.cn", "gateway": "https://mcp.lynse.cn", "business_proxy": True,
        }
        self.stdout = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def run_cli(self, *args):
        with patch.object(lynse.sys, "argv", ["lynse", *args]):
            try:
                lynse.main()
            except SystemExit as exit:
                return exit.code
        return 0

    def test_read_only_status_uses_persisted_session_and_never_rotates(self):
        args = ("auth", "status", "--device", "--profile", "workbuddy", "--json")
        with patch.object(lynse, "_device_request") as request:
            self.assertEqual(self.run_cli(*args), lynse.EXIT_AUTH)
            self.assertEqual(json.loads(self.stdout.getvalue()), {"authenticated": False})
            request.assert_not_called()
            self.assertFalse(self.session_path.parent.exists())
            lynse._write_private_json(self.session_path, self.session)
            before = self.session_path.read_bytes()
            request.return_value = {"active": True, "expires_at": int(time.time()) + 3600}
            self.assertEqual(self.run_cli(*args), 0)
            self.assertEqual(self.session_path.read_bytes(), before)
            self.assertEqual(request.call_args.args[1], "session")
            request.return_value = {"active": False}
            self.assertEqual(self.run_cli(*args), lynse.EXIT_AUTH)

    def test_login_prints_separate_code_and_link_and_disconnects_only_selected_session(self):
        url = "https://www.lynse.cn/login/device"
        flow = {
            "resource": "https://api.lynse.cn", "verification_uri": url, "user_code": "BCD-FGH",
            "device_code": "d" * 43, "interval": 5, "expires_in": 300, "business_proxy": True,
        }
        tokens = self.session | {"expires_in": 900}
        other = lynse._device_path("default")
        lynse._write_private_json(other, self.session)
        with (
            patch.object(lynse, "_device_request", side_effect=[flow, tokens, {}]) as request,
            patch.object(lynse.time, "sleep"),
        ):
            self.assertEqual(self.run_cli("auth", "login", "--device", "--profile", "workbuddy"), 0)
            self.assertEqual(self.stdout.getvalue().splitlines(), ["Device code: BCD-FGH", url])
            self.assertEqual(request.call_args_list[0].args[2]["user_code_length"], "6")
            self.assertEqual(request.call_args_list[0].args[2]["scope"], "lynse:read")
            self.assertNotIn("write_optional", request.call_args_list[0].args[2])
            self.assertEqual(lynse._load_device_session(self.session_path)["refresh_token"], self.session["refresh_token"])
            for _ in range(2):
                self.assertEqual(self.run_cli("auth", "logout", "--device", "--profile", "workbuddy"), 0)
            self.assertEqual([call.args[1] for call in request.call_args_list], ["device-code", "token", "revoke"])
        self.assertFalse(self.session_path.exists())
        self.assertTrue(other.exists())

    def test_device_login_can_offer_optional_write_access(self):
        flow = {
            "resource": "https://api.lynse.cn", "verification_uri": "https://www.lynse.cn/login/device",
            "user_code": "BCD-FGH", "device_code": "d" * 43, "interval": 5, "expires_in": 300, "business_proxy": True,
        }
        tokens = self.session | {"expires_in": 900, "scope": "lynse:read"}
        with (
            patch.object(lynse, "_device_request", side_effect=[flow, tokens]) as request,
            patch.object(lynse.time, "sleep"),
        ):
            self.assertEqual(self.run_cli("auth", "login", "--device", "--profile", "workbuddy", "--request-write"), 0)
            fields = request.call_args_list[0].args[2]
            self.assertEqual((fields["scope"], fields["write_optional"]), ("lynse:read lynse:write", "1"))

    def test_business_client_refreshes_and_uses_the_bound_api_origin(self):
        lynse._write_private_json(self.session_path, self.session | {"access_expires_at": 1})
        rotated = {
            "access_token": "x" * 43, "refresh_token": "b" * 43 + "." + "y" * 64, "expires_in": 900,
        }
        with patch.object(lynse, "_device_request", return_value=rotated) as request:
            api = lynse.DeviceLynseAPI("workbuddy")
            self.assertEqual(api.api_host, "https://mcp.lynse.cn")
            self.assertEqual(api._get_token(), rotated["access_token"])
            self.assertEqual(api._get_token(), rotated["access_token"])
            request.assert_called_once()
            headers = api._build_auth_headers(rotated["access_token"])
            self.assertEqual(headers["Authorization"], "Bearer " + rotated["access_token"])
            self.assertNotIn("X-API-Key", headers)

    def test_meeting_query_uses_gateway_with_device_credential(self):
        lynse._write_private_json(self.session_path, self.session)
        api = lynse.DeviceLynseAPI("workbuddy")
        response = Mock(status_code=200)
        response.json.return_value = {"code": 200, "data": []}
        with patch.object(api._http, "request", return_value=response) as request:
            self.assertEqual(api.list_files_by_time_range(1)["code"], 200)
        method, url = request.call_args.args
        self.assertEqual(method, "GET")
        self.assertEqual(url, "https://mcp.lynse.cn" + lynse._DEVICE_API + "/business/api/business/file/timeRange/list")
        self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Bearer " + self.session["access_token"])
