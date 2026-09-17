#!/usr/bin/env python3
"""Build the minimal Lynse agent-skill ZIP for SkillHub or WorkBuddy."""

import argparse
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "lynse-cli-skill.zip"
REQUIRED_FILES = (
    Path("SKILL.md"),
    Path("lynse.py"),
    Path("requirements.txt"),
    Path("references/auth-and-security.md"),
    Path("references/error-handling.md"),
    Path("references/platform-paths.md"),
)
FORBIDDEN_CONTENT = {
    r"\.zshrc": "shell startup file reference",
    r"\.bashrc": "shell startup file reference",
    r"\.bash_profile": "shell startup file reference",
    r"LYNSE_HTTP_DEBUG_LOG_TOKEN": "credential logging override",
    r"LYNCLAW_HTTP_DEBUG": "undeclared external debug integration",
    r"runtime\.log_config": "undeclared external runtime integration",
}
SKILLHUB_FIELD_SOURCES = (
    ("slug", "skillhubSlug"),
    ("displayName", "displayName"),
    ("version", "version"),
    ("summary", "summary"),
)
WORKBUDDY_FIELD_SOURCES = (
    ("version", "version"),
    ("display_name", "displayName"),
    ("display_name_en", "displayNameEn"),
    ("description_zh", "summary"),
    ("description_en", "summaryEn"),
)


def validate_sources() -> None:
    missing = [str(path) for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit(f"Missing required skill file(s): {', '.join(missing)}")
    for relative_path in REQUIRED_FILES:
        source = ROOT / relative_path
        text = source.read_text(encoding="utf-8")
        for pattern, description in FORBIDDEN_CONTENT.items():
            if re.search(pattern, text, flags=re.IGNORECASE):
                raise SystemExit(
                    f"Refusing to package {relative_path}: found {description} ({pattern})"
                )


def skillhub_skill_md() -> bytes:
    """Return SKILL.md with SkillHub publishing fields promoted to the root."""
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SystemExit("SKILL.md must start with YAML frontmatter")

    promoted = []
    promoted_values = {}
    for field, metadata_field in SKILLHUB_FIELD_SOURCES:
        match = re.search(rf"(?m)^  {re.escape(metadata_field)}:[ \\t]*(.+)$", text)
        if not match:
            raise SystemExit(f"SKILL.md metadata is missing {metadata_field}")
        value = match.group(1).strip()
        promoted_values[field] = value
        promoted.append(f"{field}: {value}")

    first_line_end = text.find("\n", len("---\n"))
    if first_line_end == -1:
        raise SystemExit("SKILL.md frontmatter is incomplete")
    transformed = (
        text[: first_line_end + 1]
        + "\n".join(promoted)
        + "\n"
        + text[first_line_end + 1 :]
    )
    transformed = re.sub(
        r"(?m)^  slug:[ \\t]*.+$",
        f"  slug: {promoted_values['slug']}",
        transformed,
        count=1,
    )
    return transformed.encode("utf-8")


def workbuddy_skill_md() -> bytes:
    """Return SKILL.md with WorkBuddy-required fields promoted to the top level.

    WorkBuddy rejects packages whose frontmatter lacks version / display_name /
    display_name_en / description_zh / description_en as top-level keys; the
    default (Codex) variant must NOT carry them, so they are injected at pack time.
    """
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SystemExit("SKILL.md must start with YAML frontmatter")

    promoted = []
    for field, metadata_field in WORKBUDDY_FIELD_SOURCES:
        match = re.search(rf"(?m)^  {re.escape(metadata_field)}:[ \t]*(.+)$", text)
        if not match:
            raise SystemExit(f"SKILL.md metadata is missing {metadata_field}")
        promoted.append(f"{field}: {match.group(1).strip()}")

    first_line_end = text.find("\n", len("---\n"))
    if first_line_end == -1:
        raise SystemExit("SKILL.md frontmatter is incomplete")
    transformed = (
        text[: first_line_end + 1]
        + "\n".join(promoted)
        + "\n"
        + text[first_line_end + 1 :]
    )
    return transformed.encode("utf-8")


def build_zip(output: Path, *, skillhub: bool = False, workbuddy: bool = False) -> None:
    validate_sources()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path in REQUIRED_FILES:
            if relative_path == Path("SKILL.md") and skillhub:
                data = skillhub_skill_md()
            elif relative_path == Path("SKILL.md") and workbuddy:
                data = workbuddy_skill_md()
            else:
                data = (ROOT / relative_path).read_bytes()
            info = zipfile.ZipInfo(relative_path.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    print(f"Built {output}")
    for relative_path in REQUIRED_FILES:
        print(f"  {relative_path.as_posix()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a minimal, allowlisted Lynse skill ZIP."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"output ZIP path (default: {DEFAULT_OUTPUT}, or its -workbuddy sibling with --workbuddy)",
    )
    parser.add_argument(
        "--skillhub",
        action="store_true",
        help="promote SkillHub publishing fields in the packaged SKILL.md",
    )
    parser.add_argument(
        "--workbuddy",
        action="store_true",
        help="promote WorkBuddy-required fields in the packaged SKILL.md",
    )
    args = parser.parse_args()
    output = args.output
    if output is None:
        name = "lynse-cli-skill-workbuddy.zip" if args.workbuddy else None
        output = DEFAULT_OUTPUT if name is None else DEFAULT_OUTPUT.with_name(name)
    build_zip(
        output.expanduser().resolve(),
        skillhub=args.skillhub,
        workbuddy=args.workbuddy,
    )


if __name__ == "__main__":
    main()
