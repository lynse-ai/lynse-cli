#!/usr/bin/env python3
"""Build allowlisted Lynse skill ZIPs and a self-contained Codex plugin."""

import argparse
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "lynse-cli-skill.zip"
CODEX_OUTPUT_NAME = "lynse-cli-codex-plugin.zip"
REQUIRED_FILES = (
    Path("SKILL.md"),
    Path("lynse.py"),
    Path("requirements.txt"),
    Path("references/auth-and-security.md"),
    Path("references/error-handling.md"),
    Path("references/platform-paths.md"),
    Path("references/commands.md"),
    Path("agents/openai.yaml"),
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


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _codex_manifests() -> dict[Path, bytes]:
    """Render both manifest formats from one template and the canonical version."""
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)[1] if text.startswith("---\n") else ""
    match = re.search(r"(?m)^  version:[ \t]*([^\n]+)$", frontmatter)
    if not match:
        raise SystemExit("SKILL.md metadata is missing version")
    version = match.group(1).strip().strip("\"'")
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    if version != package["version"]:
        raise SystemExit("SKILL.md metadata version must match package.json version")
    manifest = json.loads((ROOT / "codex/plugin.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    overlay = {field: manifest[field] for field in ("name", "version", "description", "author")}
    overlay["skills"] = "./skills/"
    overlay.update(manifest["extensions"]["com.openai"])
    return {
        Path("plugin.json"): _json_bytes(manifest),
        Path(".codex-plugin/plugin.json"): _json_bytes(overlay),
    }


def _write_zip(output: Path, files: dict[Path, bytes]) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path, data in sorted(files.items()):
            info = zipfile.ZipInfo(relative_path.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)


def build_zip(
    output: Path, *, skillhub: bool = False, workbuddy: bool = False, codex: bool = False
) -> None:
    if sum((skillhub, workbuddy, codex)) > 1:
        raise SystemExit("Choose only one package variant: --skillhub, --workbuddy, or --codex")
    validate_sources()
    files = {path: (ROOT / path).read_bytes() for path in REQUIRED_FILES}
    if skillhub:
        files[Path("SKILL.md")] = skillhub_skill_md()
    elif workbuddy:
        files[Path("SKILL.md")] = workbuddy_skill_md()
    if codex:
        skill_prefix = Path("skills/lynse-cli")
        files = {skill_prefix / path: data for path, data in files.items()}
        files.update(_codex_manifests())

    output.parent.mkdir(parents=True, exist_ok=True)
    _write_zip(output, files)
    if codex:
        marketplace_root = output.parent / "codex"
        for path, data in files.items():
            target = marketplace_root / "plugins/lynse-cli" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        catalog_path = marketplace_root / ".agents/plugins/marketplace.json"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_bytes((ROOT / "codex/marketplace.json").read_bytes())
        print(f"Local Codex marketplace: {marketplace_root}")
    print(f"Built {output}")
    for relative_path in sorted(files):
        print(f"  {relative_path.as_posix()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an allowlisted Lynse skill ZIP or Codex plugin and local marketplace."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output ZIP path (default: dist/lynse-cli-skill.zip; variant-specific name for --workbuddy or --codex)",
    )
    variants = parser.add_mutually_exclusive_group()
    variants.add_argument(
        "--skillhub",
        action="store_true",
        help="promote SkillHub publishing fields in the packaged SKILL.md",
    )
    variants.add_argument(
        "--workbuddy",
        action="store_true",
        help="promote WorkBuddy-required fields in the packaged SKILL.md",
    )
    variants.add_argument(
        "--codex",
        action="store_true",
        help="build a portable plugin ZIP and a codex/ marketplace beside the ZIP",
    )
    args = parser.parse_args()
    output = args.output
    if output is None:
        name = (
            CODEX_OUTPUT_NAME if args.codex else
            "lynse-cli-skill-workbuddy.zip" if args.workbuddy else None
        )
        output = DEFAULT_OUTPUT if name is None else DEFAULT_OUTPUT.with_name(name)
    build_zip(
        output.expanduser().resolve(),
        skillhub=args.skillhub,
        workbuddy=args.workbuddy,
        codex=args.codex,
    )


if __name__ == "__main__":
    main()
