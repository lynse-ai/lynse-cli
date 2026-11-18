"""Credential resolution tests.

Pins the API key/host precedence so a stale install ``.env`` can never silently
override the key a user saved via ``auth login`` into ``~/.lynse/config.json``.

Precedence (highest → lowest):
    explicit param  >  shell env var  >  user config (~/.lynse/config.json)  >  install .env
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lynse import DEFAULT_API_HOST, LynseAPI, LynseAPIError, _write_user_config


_ENV_KEYS = (
    "LYNSE_API_KEY",
    "LYNSE_API_HOST",
    "LYNSE_OWNER_ID",
    "LYNSE_ACCESS_TOKEN",
)


class CredentialResolutionTests(unittest.TestCase):
    def setUp(self):
        # Snapshot and clear credentials from the caller's environment.
        self._saved = {k: os.environ.get(k) for k in _ENV_KEYS}
        for k in _ENV_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def _env_file(self, key, host="https://api.example.com", owner_id="legacy-owner"):
        f = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False)
        f.write(f"LYNSE_API_KEY={key}\nLYNSE_API_HOST={host}\nLYNSE_OWNER_ID={owner_id}\n")
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    @mock.patch("lynse._load_user_config")
    def test_user_config_key_wins_over_stale_env_file(self, m_ucfg):
        """The bug: stale install .env used to override the valid auth-login key."""
        m_ucfg.return_value = {
            "api_key": "dk_VALID_user_key_9999",
            "api_host": "https://api.example.com",
        }
        env_path = self._env_file("dk_STALE_install_key_0000")

        api = LynseAPI(config_file=env_path)

        self.assertEqual(api.api_key, "dk_VALID_user_key_9999")
        self.assertEqual(api.api_host, "https://api.example.com")

    @mock.patch("lynse._load_user_config")
    def test_explicit_param_wins_over_everything(self, m_ucfg):
        m_ucfg.return_value = {"api_key": "dk_VALID_user_key_9999"}
        env_path = self._env_file("dk_STALE_install_key_0000")

        api = LynseAPI(
            api_key="dk_PARAM_key_1234",
            api_host="https://api.example.com",
            config_file=env_path,
        )

        self.assertEqual(api.api_key, "dk_PARAM_key_1234")

    @mock.patch("lynse._load_user_config")
    def test_shell_env_wins_over_user_config_and_env_file(self, m_ucfg):
        """An explicit shell export is an intentional override and must win."""
        m_ucfg.return_value = {"api_key": "dk_VALID_user_key_9999"}
        env_path = self._env_file("dk_STALE_install_key_0000")
        os.environ["LYNSE_API_KEY"] = "dk_SHELL_key_5555"
        os.environ["LYNSE_API_HOST"] = "https://shell.example.com"
        os.environ["LYNSE_OWNER_ID"] = "shell-owner"

        for _ in range(2):
            api = LynseAPI(config_file=env_path)
            self.assertEqual(api.api_key, "dk_SHELL_key_5555")
            self.assertEqual(api.api_host, "https://shell.example.com")
            self.assertEqual(api.owner_id, "shell-owner")

    @mock.patch("lynse._load_user_config", return_value={
        "api_key": "dk_saved", "api_host": "https://original.example.com",
    })
    def test_host_override_requires_credentials_for_that_origin(self, _load):
        with mock.patch.dict(os.environ, {"LYNSE_API_HOST": "https://alternate.example.com"}):
            with self.assertRaisesRegex(LynseAPIError, "different Lynse origin"):
                LynseAPI()
        with mock.patch.dict(os.environ, {"LYNSE_API_HOST": "https://ORIGINAL.example.com:443/"}):
            api = LynseAPI()
            self.assertEqual(api.api_host, "https://original.example.com")

    @mock.patch("lynse._load_user_config", return_value={"api_key": "dk_saved"})
    def test_hostless_saved_key_uses_production_even_with_legacy_install_host(self, _load):
        env_path = self._env_file("dk_install", host="https://legacy.example.com")
        api = LynseAPI(config_file=env_path)
        self.assertEqual(api.api_host, DEFAULT_API_HOST)
        self.assertEqual(api.api_key, "dk_saved")

    @mock.patch("lynse._load_user_config")
    def test_install_env_used_when_no_user_config(self, m_ucfg):
        """Backward compat: install .env is still the default fallback."""
        m_ucfg.return_value = {}
        env_path = self._env_file("dk_ONLY_env_key_7777")

        api = LynseAPI(config_file=env_path)

        self.assertEqual(api.api_key, "dk_ONLY_env_key_7777")
        self.assertEqual(api.owner_id, "legacy-owner")
        self.assertNotIn("LYNSE_API_KEY", os.environ)

    @mock.patch("lynse._load_user_config")
    def test_resolver_reports_config_source(self, m_ucfg):
        from lynse import _resolve_api_credentials  # added by the fix

        m_ucfg.return_value = {"api_key": "dk_VALID_user_key_9999"}
        env_path = self._env_file("dk_STALE_install_key_0000")

        _, key, source = _resolve_api_credentials(install_env_path=env_path)

        self.assertEqual(key, "dk_VALID_user_key_9999")
        self.assertEqual(source, "config")

    @unittest.skipIf(os.name == "nt", "Unix permission bits are not available on Windows")
    def test_user_config_is_written_with_owner_only_permissions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".lynse"
            config_dir.mkdir()
            config_file = config_dir / "config.json"
            config_file.write_text("{}", encoding="utf-8")
            config_file.chmod(0o644)

            with mock.patch("lynse._get_user_config_dir", return_value=config_dir):
                written = _write_user_config({"api_key": "dk_TEST_key_1234"})

            self.assertEqual(written, config_file)
            self.assertEqual(config_file.stat().st_mode & 0o777, 0o600)

    def test_token_cache_is_used_only_for_the_same_key_and_host(self):
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch("lynse._get_user_config_dir", return_value=Path(tmpdir)), \
                mock.patch("lynse._load_install_env", return_value={}):
            original = LynseAPI(api_host="https://one.example.com", api_key="dk_original")
            original._save_token("aaa.bbb.ccc")
            for host, key, expected in (
                ("https://one.example.com", "dk_original", "aaa.bbb.ccc"),
                ("https://one.example.com", "dk_new", None),
                ("https://two.example.com", "dk_original", None),
            ):
                with self.subTest(host=host, key=key):
                    api = LynseAPI(api_host=host, api_key=key)
                    self.assertEqual(api._get_cached_token(), expected)

            original.token_file.write_text("legacy.saved.token", encoding="utf-8")
            with mock.patch.object(original, "_refresh_token", return_value="new.saved.token") as refresh, \
                    mock.patch("lynse.requests.get") as probe:
                self.assertEqual(original._get_token(), "new.saved.token")
                refresh.assert_called_once()
                probe.assert_not_called()
                self.assertEqual(original._get_cached_token(), "new.saved.token")


if __name__ == "__main__":
    unittest.main()
