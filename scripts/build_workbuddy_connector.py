"""Build the WorkBuddy CLI connector using an immutable first-party wheel."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = ("darwin", "linux", "win32")


def _platforms(command):
    return dict.fromkeys(PLATFORMS, command)


def build(output, wheel, wheel_url, icon):
    version = json.loads((ROOT / "package.json").read_text())["version"]
    expected = f"lynse_cli-{version}-py3-none-any.whl"
    target = urlsplit(wheel_url)
    if (wheel.name != expected or not wheel.is_file() or target.scheme != "https"
            or target.netloc != "www.lynse.cn" or target.query or target.fragment
            or target.path.rsplit("/", 1)[-1] != expected
            or not all(ch.isalnum() or ch in "/-._" for ch in target.path)):
        raise ValueError("Supply the versioned Lynse wheel and its HTTPS URL on www.lynse.cn")
    integrity = hashlib.sha256(wheel.read_bytes()).hexdigest()
    config = {
        "init": _platforms(f'python -m pip install "{wheel_url}#sha256={integrity}"'),
        "runtime": {"type": "python", "version": "3.12"},
        "auth": _platforms("lynse auth login --device --profile workbuddy --request-write"),
        "status": _platforms("lynse auth status --device --profile workbuddy --json"),
        "unAuth": _platforms("lynse auth logout --device --profile workbuddy --json"),
        "statusMatchJson": {"authenticated": True},
        "authUrlDomain": "www.lynse.cn",
        "authDeviceFlow": {
            "uriPattern": r"(https://www\.lynse\.cn/login/device)(?=\s|$)",
            "codePattern": r"Device code:\s*([A-Z0-9]{3}-[A-Z0-9]{3})",
            "codeEmbeddedInUri": False,
            "defaultExpiresInSeconds": 300,
        },
        "versionCheck": {
            "command": _platforms("lynse version --json"), "minVersion": version,
            "versionPattern": r"lynse-cli v(\d+\.\d+\.\d+)",
        },
        "env": {"LYNSE_NO_UPDATE_CHECK": "1"},
    }
    meta = {
        "name": "灵光记 Lynse CLI", "name_en": "Lynse CLI",
        "description": "Query Lynse meetings, notes, and tasks through the Lynse command line.",
        "description_zh": "查询会议、转写和待办，预览会议归档计划，并在取得写权限后执行你确认的归档。",
        "description_en": "Read meetings, transcripts, and tasks. Preview meeting organization and apply approved plans with write access.",
        "source": "lynse-cli", "type": "cli", "version": version, "minWorkbuddyVersion": "5.0.0",
        "examples_zh": ["查看最近七天的会议", "预览最近 90 天的会议归档计划"],
        "examples_en": ["List my meetings from the last seven days", "Preview my 90-day meeting organization plan"],
    }
    files = {
        "connector-meta.json": json.dumps(meta, ensure_ascii=False, indent=2).encode(),
        "cli.json": json.dumps(config, indent=2).encode(),
        "icon.png": icon.read_bytes(),
        "skills/lynse-cli/SKILL.md": (ROOT / "integrations/workbuddy/skills/lynse-cli/SKILL.md").read_bytes(),
    }
    if not files["icon.png"].startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("The connector icon must be a PNG")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--wheel-url", required=True)
    parser.add_argument("--icon", type=Path, default=ROOT.parent / "lynse-mcp/integrations/workbuddy/icon.png")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/lynse-workbuddy-cli-connector.zip")
    args = parser.parse_args()
    build(args.output, args.wheel, args.wheel_url, args.icon)
    print(args.output)


if __name__ == "__main__":
    main()
