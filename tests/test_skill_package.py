import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import build_skill_package
from scripts.build_skill_package import REQUIRED_FILES, build_zip

SOURCE_ROOT = Path(__file__).resolve().parents[1]


class SkillPackageTests(unittest.TestCase):
    def setUp(self):
        quiet_builds = patch("scripts.build_skill_package.print")
        quiet_builds.start()
        self.addCleanup(quiet_builds.stop)

    def test_default_package_preserves_codex_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "skill.zip"
            build_zip(output)
            with zipfile.ZipFile(output) as archive:
                skill_md = archive.read("SKILL.md").decode("utf-8")

        frontmatter = skill_md.split("---", 2)[1]
        self.assertNotIn("\nslug:", frontmatter)
        self.assertNotIn("\nversion:", frontmatter)
        self.assertNotIn("\ndisplay_name", frontmatter)
        self.assertNotIn("\ndescription_zh:", frontmatter)
        self.assertNotIn("\ndescription_en:", frontmatter)

    def test_skillhub_package_promotes_required_metadata(self):
        source = (SOURCE_ROOT / "SKILL.md").read_text(encoding="utf-8")
        version = re.search(r"(?m)^  version:[ \t]*(.+)$", source).group(1).strip()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "skillhub.zip"
            build_zip(output, skillhub=True)
            with zipfile.ZipFile(output) as archive:
                skill_md = archive.read("SKILL.md").decode("utf-8")
                self.assertEqual(
                    set(archive.namelist()),
                    {path.as_posix() for path in REQUIRED_FILES},
                )

        frontmatter = skill_md.split("---", 2)[1]
        self.assertIn("\nslug: lynse", frontmatter)
        self.assertIn("\n  slug: lynse", frontmatter)
        self.assertNotIn("\n  slug: lynse-cli", frontmatter)
        self.assertIn("\ndisplayName: 灵光记Lynse", frontmatter)
        self.assertIn(f"\nversion: {version}", frontmatter)
        self.assertIn("\nsummary:", frontmatter)

    def test_workbuddy_package_promotes_required_metadata(self):
        source = (SOURCE_ROOT / "SKILL.md").read_text(encoding="utf-8")
        version = re.search(r"(?m)^  version:[ \t]*(.+)$", source).group(1).strip()
        package = json.loads((SOURCE_ROOT / "package.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "workbuddy.zip"
            build_zip(output, workbuddy=True)
            with zipfile.ZipFile(output) as archive:
                skill_md = archive.read("SKILL.md").decode("utf-8")
                self.assertEqual(
                    set(archive.namelist()),
                    {path.as_posix() for path in REQUIRED_FILES},
                )
                for name in archive.namelist():
                    if name.endswith(".md"):
                        with self.subTest(document=name):
                            self.assertNotRegex(
                                archive.read(name).decode("utf-8"),
                                r"(?i)\bX-API-Key\b|/api/(?:auth|business|session|usage)/",
                            )

        frontmatter = skill_md.split("---", 2)[1]
        self.assertIn(f"\nversion: {version}", frontmatter)
        self.assertIn("\ndisplay_name: 灵光记Lynse", frontmatter)
        self.assertIn("\ndisplay_name_en: Lynse CLI", frontmatter)
        self.assertIn("\ndescription_zh: ", frontmatter)
        self.assertIn("\ndescription_en: Easily query and access", frontmatter)
        self.assertIn(f'\nauthor: {json.dumps(package["author"])}', frontmatter)
        for path in REQUIRED_FILES:
            if path.parent == Path("references"):
                self.assertIn(f"\n@{path.as_posix()}", skill_md)

    def test_codex_marketplace_and_manifests_resolve_to_packaged_skill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / "codex-plugin.zip"
            build_zip(output, codex=True)
            marketplace_root = (root / "codex").resolve()
            catalog = json.loads(
                (marketplace_root / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
            )
            entry = catalog["plugins"][0]
            self.assertEqual(entry["source"]["source"], "local")
            self.assertTrue(entry["source"]["path"].startswith("./"))
            plugin_root = (marketplace_root / entry["source"]["path"]).resolve()
            self.assertTrue(plugin_root.is_relative_to(marketplace_root))
            manifest = json.loads((plugin_root / "plugin.json").read_text(encoding="utf-8"))
            overlay = json.loads(
                (plugin_root / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["name"], entry["name"])
            self.assertEqual(manifest["version"], json.loads(
                (SOURCE_ROOT / "package.json").read_text(encoding="utf-8")
            )["version"])
            self.assertEqual(overlay["interface"], manifest["extensions"]["com.openai"]["interface"])
            skills_root = (plugin_root / overlay["skills"]).resolve()
            self.assertEqual(skills_root, plugin_root / "skills")
            skill_root = skills_root / "lynse-cli"
            with zipfile.ZipFile(output) as archive:
                for name in archive.namelist():
                    self.assertEqual(archive.read(name), (plugin_root / name).read_bytes())
            for path in REQUIRED_FILES:
                self.assertEqual((skill_root / path).read_bytes(), (SOURCE_ROOT / path).read_bytes())
            # Each local documentation link must survive extraction at its relative path.
            for match in re.finditer(r"\]\(([^)]+)\)", (skill_root / "SKILL.md").read_text(encoding="utf-8")):
                target = match.group(1)
                if not target.startswith(("https://", "http://", "#")):
                    self.assertTrue((skill_root / target).is_file(), target)

    def test_all_extracted_variants_run_offline_from_unrelated_cwd(self):
        runner = """
import runpy, socket, sys
from pathlib import Path
from unittest.mock import patch
class NetworkAttempt(BaseException):
    pass
def deny_network(*args, **kwargs):
    raise NetworkAttempt("packaging smoke tests must not use the network")
socket.getaddrinfo = deny_network
socket.socket.connect = deny_network
socket.create_connection = deny_network
config_home, sys.argv = Path(sys.argv[1]), sys.argv[2:]
with patch.object(Path, "home", return_value=config_home):
    runpy.run_path(sys.argv[0], run_name="__main__")
"""
        env = {key: value for key, value in os.environ.items() if not key.startswith("LYNSE_")}
        local_commands = (
            (["--help"], "lynse cli"),
            (["meetings", "--help"], "meetings organize"),
            (["meetings", "organize", "--help"], "--days 90"),
            (["help", "meetings", "organize"], "--include-no-conclusion"),
            (["auth", "logout", "-h"], "--tokens-only"),
            (["version", "--json"], '"requests":"not installed"'),
            (["auth", "status", "--json"], '"api_key":"(not set)"'),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cwd = root / "unrelated"
            cwd.mkdir()
            for variant in (None, "skillhub", "workbuddy", "codex"):
                with self.subTest(variant=variant or "standalone"):
                    output = root / f"{variant}.zip"
                    build_zip(output, **({variant: True} if variant else {}))
                    extracted = root / f"extracted-{variant}"
                    with zipfile.ZipFile(output) as archive:
                        archive.extractall(extracted)
                    skill_root = extracted / "skills/lynse-cli" if variant == "codex" else extracted
                    config_home = root / "empty-home"
                    invocation = ["-c", runner, str(config_home), str(skill_root / "lynse.py")]
                    for args, expected in local_commands:
                        with self.subTest(command=args):
                            result = subprocess.run(
                                [sys.executable, "-I", "-S", *invocation, *args],
                                cwd=cwd, env=env, capture_output=True, text=True, timeout=15,
                            )
                            self.assertEqual(result.returncode, 0, result.stderr)
                            self.assertEqual(result.stderr, "")
                            self.assertIn(expected, result.stdout.lower())
                    missing_key = subprocess.run(
                        [sys.executable, *invocation, "meetings", "organize", "--days", "90", "--json"],
                        cwd=cwd, env=env, capture_output=True, text=True, timeout=15,
                    )
                    self.assertEqual(missing_key.returncode, 2, missing_key.stderr)
                    self.assertIn("LYNSE_API_KEY is not configured", missing_key.stderr)
                    self.assertIn("auth login", missing_key.stderr)
                    self.assertFalse((config_home / ".lynse").exists())
                    self.assertFalse((skill_root / ".token_cache").exists())

    def test_allowlist_excludes_credentials_and_duplicate_installations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = Path(tmpdir) / "source"
            for path in (*REQUIRED_FILES, Path("codex/plugin.json"), Path("codex/marketplace.json"), Path("package.json")):
                target = source_root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SOURCE_ROOT / path, target)
            for path in (".env", ".token_cache", ".npmrc", ".agents/skills/lynse-cli/lynse.py",
                         "tests/secret.txt", "autoresearch-lynse-cli/secret.txt", "references/private.md"):
                target = source_root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("PACKAGE_SECRET_SENTINEL", encoding="utf-8")
            with patch.object(build_skill_package, "ROOT", source_root):
                for codex in (False, True):
                    output = Path(tmpdir) / f"plugin-{codex}.zip"
                    build_zip(output, codex=codex)
                    prefix = "skills/lynse-cli/" if codex else ""
                    expected = {prefix + path.as_posix() for path in REQUIRED_FILES}
                    if codex:
                        expected.update({"plugin.json", ".codex-plugin/plugin.json"})
                    with zipfile.ZipFile(output) as archive:
                        self.assertEqual(set(archive.namelist()), expected)
                        for name in archive.namelist():
                            self.assertNotIn(b"PACKAGE_SECRET_SENTINEL", archive.read(name))

    def test_archives_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for codex in (False, True):
                with self.subTest(codex=codex):
                    first = Path(tmpdir) / f"first-{codex}.zip"
                    second = Path(tmpdir) / f"second-{codex}.zip"
                    build_zip(first, codex=codex)
                    build_zip(second, codex=codex)
                    self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_cli_rejects_conflicting_variant_flags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "unexpected.zip"
            for flags in (("--codex", "--skillhub"), ("--codex", "--workbuddy"), ("--skillhub", "--workbuddy")):
                with self.subTest(flags=flags):
                    result = subprocess.run(
                        [sys.executable, str(SOURCE_ROOT / "scripts/build_skill_package.py"),
                         "--output", str(output), *flags],
                        capture_output=True, text=True, timeout=15,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("not allowed with argument", result.stderr)
                    self.assertFalse(output.exists())

    def test_codex_rejects_version_mismatch_before_writing_archive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = Path(tmpdir) / "source"
            for path in (*REQUIRED_FILES, Path("package.json")):
                target = source_root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SOURCE_ROOT / path, target)
            package_path = source_root / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["version"] = "0.0.0"
            package_path.write_text(json.dumps(package), encoding="utf-8")
            output = Path(tmpdir) / "unexpected.zip"
            with patch.object(build_skill_package, "ROOT", source_root):
                with self.assertRaisesRegex(SystemExit, "version must match"):
                    build_zip(output, codex=True)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
