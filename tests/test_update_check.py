import base64
import contextlib
import hashlib
import io
import json
import os
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import lynse


def _make_tgz(members: dict) -> bytes:
    """Build an npm-style .tgz (members keyed by archive path) in memory."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _release(payload: bytes, version: str = "9.9.9") -> dict:
    integrity = base64.b64encode(hashlib.sha512(payload).digest()).decode()
    return {
        "version": version,
        "tarball": f"https://registry.npmjs.org/@lynse.ai/lynse-cli/-/lynse-cli-{version}.tgz",
        "integrity": f"sha512-{integrity}",
    }


def _download(payload: bytes, status_code: int = 200):
    return contextlib.nullcontext(SimpleNamespace(
        status_code=status_code, iter_content=lambda **_kwargs: [payload],
    ))


class VersionCompareTests(unittest.TestCase):
    def test_version_is_newer(self):
        self.assertTrue(lynse._version_is_newer("1.8.2", "1.8.1"))
        self.assertTrue(lynse._version_is_newer("1.10.0", "1.9.0"))
        self.assertTrue(lynse._version_is_newer("2.0", "1.99.9"))
        self.assertFalse(lynse._version_is_newer("1.8.1", "1.8.1"))
        self.assertFalse(lynse._version_is_newer("1.8.0", "1.8.1"))
        self.assertFalse(lynse._version_is_newer("abc", "1.0.0"))

    def test_prerelease_suffix_is_ignored(self):
        self.assertTrue(lynse._version_is_newer("1.9.0-beta.1", "1.8.9"))
        self.assertFalse(lynse._version_is_newer("1.8.1-beta.1", "1.8.1"))


class UpdateStateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state_file = Path(tmp.name) / "update-check.json"
        patcher = patch.object(lynse, "_update_state_path", return_value=self.state_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fresh_cache_skips_network(self):
        lynse._save_update_state({
            "last_check": time.time(),
            "latest_version": "9.9.9",
            "tarball": "https://registry.npmjs.org/x/-/x-9.9.9.tgz",
        })
        with patch.object(lynse, "_fetch_npm_release", side_effect=AssertionError("network touched")):
            info = lynse._check_npm_for_update()
        self.assertEqual(info["latest"], "9.9.9")
        self.assertTrue(info["update_available"])

    def test_stale_cache_hits_network_and_saves(self):
        lynse._save_update_state({"last_check": 0, "latest_version": "0.0.1", "tarball": ""})
        release = {"version": "0.0.2", "tarball": "https://registry.npmjs.org/x/-/x-0.0.2.tgz"}
        with patch.object(lynse, "_fetch_npm_release", return_value=release) as fetch:
            info = lynse._check_npm_for_update()
        fetch.assert_called_once()
        saved = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["latest_version"], "0.0.2")
        self.assertEqual(info["latest"], "0.0.2")

    def test_fetch_failure_returns_none(self):
        lynse._save_update_state({"last_check": 0})
        with patch.object(lynse, "_fetch_npm_release", side_effect=RuntimeError("boom")):
            self.assertIsNone(lynse._check_npm_for_update())

    def test_notice_respects_kill_switch(self):
        with patch.dict(os.environ, {"LYNSE_NO_UPDATE_CHECK": "1"}, clear=False):
            with patch.object(lynse, "_check_npm_for_update", side_effect=AssertionError("checked")):
                lynse._maybe_print_update_notice()

    def test_notice_prints_when_outdated(self):
        info = {"current": "1.0.0", "latest": "1.1.0", "update_available": True}
        with patch.object(lynse, "_check_npm_for_update", return_value=info):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                lynse._maybe_print_update_notice()
        self.assertIn("v1.1.0", err.getvalue())
        self.assertIn("update", err.getvalue())


class FetchNpmReleaseTests(unittest.TestCase):
    def test_rejects_tarball_outside_the_official_registry(self):
        release = _release(b"fixture")
        release["tarball"] = "https://example.test/lynse-cli.tgz"
        response = SimpleNamespace(status_code=200, json=lambda: {
            "name": lynse.NPM_PACKAGE, "version": release["version"], "dist": release,
        })
        with patch.object(lynse.requests, "get", return_value=response) as fetch:
            with self.assertRaisesRegex(lynse.LynseAPIError, "official npm package URL"):
                lynse._fetch_npm_release()
        self.assertFalse(fetch.call_args.kwargs["allow_redirects"])

    def test_rejects_malformed_metadata(self):
        response = SimpleNamespace(status_code=200, json=lambda: {"unexpected": True})
        with patch.object(lynse.requests, "get", return_value=response):
            with self.assertRaises(lynse.LynseAPIError):
                lynse._fetch_npm_release()

    def test_unknown_update_flags_fail_before_any_registry_call(self):
        with patch.object(lynse.sys, "argv", ["lynse", "update", "--check-only"]), \
                patch.object(lynse, "_check_npm_for_update") as check, \
                patch.object(lynse, "_apply_self_update") as update, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as failure:
                lynse.main()
        self.assertEqual(failure.exception.code, lynse.EXIT_INVALID)
        check.assert_not_called()
        update.assert_not_called()


class TarballExtractionTests(unittest.TestCase):
    def test_extracts_only_allowlisted_files(self):
        payload = _make_tgz({
            "package/lynse.py": b'print("new")',
            "package/SKILL.md": b"# skill",
            "package/requirements.txt": b"requests>=2.28.0",
            "package/references/auth-and-security.md": b"auth",
            "package/bin/lynse.js": b"// shim",
            "package/scripts/build.py": b"x",
            "package/package.json": b"{}",
        })
        files = lynse._extract_skill_files(payload)
        self.assertEqual(
            set(files),
            {"lynse.py", "SKILL.md", "requirements.txt", "references/auth-and-security.md"},
        )

    def test_rejects_path_traversal_and_absolute_paths(self):
        payload = _make_tgz({
            "package/lynse.py": b"ok",
            "package/references/../../evil.md": b"evil",
            "/package/absolute.md": b"evil",
            "./package/./SKILL.md": b"ok",
            r"package/references\commands.md": b"unsupported archive path",
        })
        files = lynse._extract_skill_files(payload)
        self.assertEqual(set(files), {"lynse.py", "SKILL.md"})

    def test_requires_lynse_py(self):
        payload = _make_tgz({"package/SKILL.md": b"# only docs"})
        with self.assertRaises(lynse.LynseAPIError):
            lynse._extract_skill_files(payload)


class SelfUpdateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.skill_dir = Path(tmp.name)
        (self.skill_dir / "lynse.py").write_bytes(b"OLD")
        patcher = patch.object(lynse, "__file__", str(self.skill_dir / "lynse.py"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_apply_replaces_files_and_keeps_backup(self):
        files = {f"package/{path}": b"new file" for path in lynse.UPDATE_SKILL_FILES}
        files.update({
            "package/lynse.py": b"NEW",
            "package/SKILL.md": b"# new skill",
            "package/references/error-handling.md": b"errors",
        })
        payload = _make_tgz(files)
        with patch.object(lynse.requests, "get", return_value=_download(payload)) as download:
            result = lynse._apply_self_update(_release(payload))
        self.assertFalse(download.call_args.kwargs["allow_redirects"])
        self.assertEqual((self.skill_dir / "lynse.py").read_bytes(), b"NEW")
        self.assertEqual((self.skill_dir / "SKILL.md").read_bytes(), b"# new skill")
        self.assertEqual(
            (self.skill_dir / "references/error-handling.md").read_bytes(), b"errors"
        )
        self.assertEqual((self.skill_dir / "lynse.py.bak").read_bytes(), b"OLD")
        self.assertEqual(result["to_version"], "9.9.9")
        self.assertFalse(list(self.skill_dir.glob("*.tmp-update")))

    def test_integrity_failure_prevents_all_file_replacements(self):
        release = _release(b"original fixture")
        with patch.object(lynse.requests, "get", return_value=_download(b"different fixture")):
            with self.assertRaisesRegex(lynse.LynseAPIError, "SHA-512"):
                lynse._apply_self_update(release)
        self.assertEqual((self.skill_dir / "lynse.py").read_bytes(), b"OLD")
        self.assertFalse((self.skill_dir / "lynse.py.bak").exists())

    def test_redirect_during_download_does_not_replace_files(self):
        with patch.object(lynse.requests, "get", return_value=_download(b"", status_code=302)):
            with self.assertRaisesRegex(lynse.LynseAPIError, "Could not download"):
                lynse._apply_self_update(_release(b"fixture"))
        self.assertEqual((self.skill_dir / "lynse.py").read_bytes(), b"OLD")

    def test_failed_replacement_restores_files_installed_earlier(self):
        payload = _make_tgz({f"package/{path}": b"NEW" for path in lynse.UPDATE_SKILL_FILES})
        replaced = os.replace

        def fail_installing_requirements(source, target):
            if Path(source).name.startswith("new-") and Path(target).name == "requirements.txt":
                raise PermissionError("simulated replacement failure")
            replaced(source, target)

        with patch.object(lynse.requests, "get", return_value=_download(payload)), \
                patch.object(lynse.os, "replace", side_effect=fail_installing_requirements):
            with self.assertRaisesRegex(lynse.LynseAPIError, "failed while replacing files"):
                lynse._apply_self_update(_release(payload))
        self.assertEqual((self.skill_dir / "lynse.py").read_bytes(), b"OLD")
        self.assertFalse((self.skill_dir / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
