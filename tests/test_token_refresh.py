"""Token-exchange robustness tests.

`_refresh_token` must (a) retry transient failures (5xx / 429 / network) instead
of failing on the first hiccup, and (b) stop reporting server/network errors as
"API Key authentication failed" — that misleads users into thinking their key is
bad. A 401/403 means the key was genuinely rejected; anything else is transient.
"""

import unittest
from unittest import mock

import requests

from lynse import LynseAPI, LynseAPIError


VALID_TOKEN = "aaaa.bbbb.cccc"  # 3-segment JWT shape passes _validate_token


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class TokenRefreshTests(unittest.TestCase):
    def setUp(self):
        # Bare instance — bypass __init__ (no network / files).
        self.api = LynseAPI.__new__(LynseAPI)
        self.api.api_host = "https://api.example.com"
        self.api.api_key = "dk_test_key"
        self.api._save_token = lambda token: None
        self.api._log_lynse_request = lambda *a, **k: None
        self.api._log_lynse_response = lambda *a, **k: None
        # Don't actually sleep during backoff.
        patcher = mock.patch("lynse.time.sleep")
        self.addCleanup(patcher.stop)
        patcher.start()

    @mock.patch("lynse.requests.post")
    def test_retries_transient_503_then_succeeds(self, m_post):
        m_post.side_effect = [
            FakeResponse(503),
            FakeResponse(200, {"data": {"accessToken": VALID_TOKEN}}),
        ]
        token = self.api._refresh_token()
        self.assertEqual(token, VALID_TOKEN)
        self.assertEqual(m_post.call_count, 2)

    @mock.patch("lynse.requests.post")
    def test_retries_transient_network_error_then_succeeds(self, m_post):
        m_post.side_effect = [
            requests.RequestException("connection reset"),
            FakeResponse(200, {"data": {"accessToken": VALID_TOKEN}}),
        ]
        token = self.api._refresh_token()
        self.assertEqual(token, VALID_TOKEN)
        self.assertEqual(m_post.call_count, 2)

    @mock.patch("lynse.requests.post")
    def test_401_means_key_rejected_no_retry(self, m_post):
        m_post.return_value = FakeResponse(401)
        with self.assertRaises(LynseAPIError) as cm:
            self.api._refresh_token()
        self.assertIn("reject", cm.exception.message.lower())
        # A rejected key must not be retried.
        self.assertEqual(m_post.call_count, 1)

    @mock.patch("lynse.requests.post")
    def test_token_exchange_stops_at_redirect(self, m_post):
        m_post.return_value = FakeResponse(302)
        with self.assertRaisesRegex(LynseAPIError, "returned a redirect"):
            self.api._refresh_token()
        m_post.assert_called_once()
        self.assertFalse(m_post.call_args.kwargs["allow_redirects"])

    @mock.patch("lynse.requests.post")
    def test_persistent_503_reports_transient_not_bad_key(self, m_post):
        m_post.return_value = FakeResponse(503)
        with self.assertRaises(LynseAPIError) as cm:
            self.api._refresh_token()
        msg = cm.exception.message.lower()
        self.assertIn("transient", msg)
        self.assertNotIn("check your lynse_api_key", msg)
        self.assertLessEqual(m_post.call_count, 3)


if __name__ == "__main__":
    unittest.main()
