import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.build_skill_package import REQUIRED_FILES, build_zip


class SkillPackageTests(unittest.TestCase):
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
        source = Path("SKILL.md").read_text(encoding="utf-8")
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
        source = Path("SKILL.md").read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
