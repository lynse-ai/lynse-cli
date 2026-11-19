#!/usr/bin/env python3
"""Build the portable CLI, Agent Skill and WorkBuddy bundle from a release wheel."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from zipfile import ZipFile

from build_skill_package import REQUIRED_FILES, ROOT, _write_zip, validate_sources
from build_workbuddy_connector import build as build_workbuddy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--icon", type=Path, default=ROOT.parent / "lynse-mcp/integrations/workbuddy/icon.png")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    validate_sources()
    version = json.loads((ROOT / "package.json").read_text())["version"]
    output = args.output or ROOT / "dist" / f"lynse-cli-agent-bundle-{version}.zip"
    url = f"https://www.lynse.cn/app/downloads/lynse_cli-{version}-py3-none-any.whl"
    wheel_bytes = args.wheel.read_bytes()
    with ZipFile(args.wheel) as wheel:
        if wheel.read("lynse.py") != (ROOT / "lynse.py").read_bytes():
            raise SystemExit("Release wheel and bundled CLI source differ")

    skill_root = Path("skills/lynse-cli")
    files = {skill_root / path: (ROOT / path).read_bytes() for path in REQUIRED_FILES}
    readme = ROOT / "integrations/agent-bundle/README.md"
    files[Path("README.md")] = readme.read_text(encoding="utf-8").replace(
        "LYNSE_WHEEL_FILENAME", args.wheel.name
    ).encode("utf-8")
    wheel_path = Path("wheel") / args.wheel.name
    connector_path = Path("workbuddy/lynse-workbuddy-cli-connector.zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        stage = Path(directory)
        connector = stage / connector_path.name
        build_workbuddy(connector, args.wheel, url, args.icon)
        files[wheel_path] = wheel_bytes
        files[connector_path] = connector.read_bytes()
        files[Path("SHA256SUMS")] = "".join(
            f"{hashlib.sha256(files[path]).hexdigest()}  {path.as_posix()}\n"
            for path in (wheel_path, connector_path)
        ).encode("ascii")
        bundle = stage / output.name
        _write_zip(bundle, files)
        bundle.replace(output)
    print(output)


if __name__ == "__main__":
    main()
