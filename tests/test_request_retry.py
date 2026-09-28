"""Read retries must not duplicate write requests after ambiguous failures."""

import unittest
from unittest import mock

import lynse
from lynse import LynseAPI, LynseAPIError


class FakeResp:
    def __init__(self, status, payload=None, text=None):
        self.status_code = status
        self._p = payload or {}
        self.text = text or "{}"

    def json(self):
        return self._p


class RequestRetryTests(unittest.TestCase):
    def setUp(self):
        self.api = LynseAPI.__new__(LynseAPI)
        self.api.api_host = "https://api.example.com"
        self.api.api_key = "dk_test"
        self.api._get_token = lambda *a, **k: "aaaa.bbbb.cccc"
        self.api._build_auth_headers = lambda token, extra=None: {"Authorization": token}
        self.api._log_lynse_request = lambda *a, **k: None
        self.api._log_lynse_response = lambda *a, **k: None
        patcher = mock.patch("lynse.time.sleep")
        self.addCleanup(patcher.stop)
        patcher.start()

    @mock.patch("lynse.requests.request")
    def test_read_retries_503_then_succeeds(self, m_req):
        m_req.side_effect = [
            FakeResp(503, text="unavailable"),
            FakeResp(200, {"code": 200, "msg": "ok", "data": {"done": True}}),
        ]
        data = self.api._request("GET", "/api/business/x")
        self.assertEqual(m_req.call_count, 2)
        self.assertEqual(data["data"]["done"], True)

    @mock.patch("lynse.requests.request")
    def test_read_gives_up_after_three_attempts(self, m_req):
        m_req.return_value = FakeResp(503, text="unavailable")
        with self.assertRaises(LynseAPIError):
            self.api._request("GET", "/api/business/x")
        # initial attempt + 2 retries = 3
        self.assertEqual(m_req.call_count, 3)

    @mock.patch("lynse.requests.request")
    def test_write_is_not_retried_after_server_error(self, m_req):
        m_req.return_value = FakeResp(503, text="unavailable")
        with self.assertRaises(LynseAPIError):
            self.api._request("POST", "/api/business/file/folder/create", json_data={"name": "A"})
        self.assertEqual(m_req.call_count, 1)

    @mock.patch("lynse.requests.request")
    def test_write_is_not_retried_after_network_error(self, m_req):
        m_req.side_effect = lynse.requests.RequestException("connection reset")
        with self.assertRaises(LynseAPIError):
            self.api._request("POST", "/api/business/file/folder/create", json_data={"name": "A"})
        self.assertEqual(m_req.call_count, 1)

    @mock.patch("lynse.requests.request")
    def test_read_refreshes_expired_token_once(self, m_req):
        m_req.side_effect = [
            FakeResp(401, text="expired"),
            FakeResp(200, {"code": 200, "data": {"ok": True}}),
        ]
        refreshes = []

        def get_token(refresh=False):
            if refresh:
                refreshes.append(True)
            return "aaaa.bbbb.cccc"

        self.api._get_token = get_token
        result = self.api._request("GET", "/api/business/x")
        self.assertTrue(result["data"]["ok"])
        self.assertEqual(refreshes, [True])
        self.assertEqual(m_req.call_count, 2)

    @mock.patch("lynse.requests.request")
    def test_write_401_is_not_resubmitted(self, m_req):
        m_req.return_value = FakeResp(401, text="expired")
        with self.assertRaises(LynseAPIError):
            self.api._request("POST", "/api/business/file/folder/create", json_data={"name": "A"})
        self.assertEqual(m_req.call_count, 1)

    @mock.patch("lynse.requests.request")
    def test_write_over_get_is_not_retried(self, m_req):
        m_req.return_value = FakeResp(503, text="unavailable")
        with self.assertRaises(LynseAPIError):
            self.api._request("GET", "/api/business/file/changeFolder",
                              params={"fileIds": "file-1"}, _retry_safe=False)
        self.assertEqual(m_req.call_count, 1)

    @mock.patch("lynse.requests.request")
    def test_does_not_retry_4xx(self, m_req):
        m_req.return_value = FakeResp(404, text="nope")
        with self.assertRaises(LynseAPIError):
            self.api._request("GET", "/api/business/missing")
        self.assertEqual(m_req.call_count, 1)


if __name__ == "__main__":
    unittest.main()
