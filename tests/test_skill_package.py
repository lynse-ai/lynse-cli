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
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "workbuddy.zip"
            build_zip(output, workbuddy=True)
            with zipfile.ZipFile(output) as archive:
                skill_md = archive.read("SKILL.md").decode("utf-8")
                self.assertEqual(
                    set(archive.namelist()),
                    {path.as_posix() for path in REQUIRED_FILES},
                )

        frontmatter = skill_md.split("---", 2)[1]
        self.assertIn(f"\nversion: {version}", frontmatter)
        self.assertIn("\ndisplay_name: 灵光记Lynse", frontmatter)
        self.assertIn("\ndisplay_name_en: Lynse CLI", frontmatter)
        self.assertIn("\ndescription_zh: ", frontmatter)
        self.assertIn("\ndescription_en: Easily query and access", frontmatter)

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
def deny_network(*args, **kwargs):
    raise AssertionError("packaging smoke tests must not use the network")
socket.socket.connect = deny_network
socket.create_connection = deny_network
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
"""
        env = {key: value for key, value in os.environ.items() if not key.startswith("LYNSE_")}
        env["LYNSE_NO_UPDATE_CHECK"] = "1"
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
                    for command in ("help", "version"):
                        result = subprocess.run(
                            [sys.executable, "-c", runner, str(skill_root / "lynse.py"), command],
                            cwd=cwd, env=env, capture_output=True, text=True, timeout=15,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn("lynse cli" if command == "help" else "lynse-cli", result.stdout.lower())
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
