# Platform Paths and Setup

Python 3.11+ and `requests` from the bundled `requirements.txt` are required.
Resolve the script beside the loaded `SKILL.md`; installation paths are not a
calling convention. The installed npm `lynse` shim is for end-user shells;
agents use the Python entrypoint directly.

## Codex

For local standalone skills, Codex discovers `<repo>/.agents/skills/lynse-cli/`
and `~/.agents/skills/lynse-cli/`. Existing installations may use another path,
including `~/.codex/skills/`; always use the path Codex actually supplies.
The optional `agents/openai.yaml` supplies UI metadata and keeps implicit
invocation enabled. It declares no MCP dependency because this skill calls the
bundled CLI.

For distribution, build a plugin from the repository:

```bash
python3 scripts/build_skill_package.py --codex
codex plugin marketplace add ./dist/codex
```

The build creates `dist/lynse-cli-codex-plugin.zip` and a local marketplace at
`dist/codex/.agents/plugins/marketplace.json`. The marketplace points to
`dist/codex/plugins/lynse-cli`, which contains portable `plugin.json`, a Codex
compatibility manifest, and the complete `skills/lynse-cli/` payload. Keep the
marketplace directory in place after adding it. Install Lynse CLI from that
marketplace in the desktop Plugins Directory; on clients with CLI installation,
use `codex plugin add lynse-cli@lynse-local`.

Codex loads an installed plugin's cached skill copy. Resolve that copy's script
from its `SKILL.md`; do not hardcode a cache path or execute the source repository
instead. When changing source files, rebuild and refresh the marketplace/plugin,
then test in a new chat. Avoid enabling a standalone and plugin copy of the same
skill together: Codex does not merge skills with duplicate names.

The plugin packages instructions and code, not Python, dependencies, or account
credentials. Installing it does not sign into Lynse. It requires a local Codex
execution environment with Python, network access, and the configured Lynse key;
a remote/cloud environment must have its own runtime and credentials.

## Python setup

Prefer an existing environment with the required packages. Otherwise create a
virtual environment in a writable workspace, outside the plugin cache:

```bash
# macOS / Linux; replace /absolute/skill/path with the loaded skill directory
python3 -m venv .venv
.venv/bin/python -m pip install -r "/absolute/skill/path/requirements.txt"
LYNSE_NO_UPDATE_CHECK=1 .venv/bin/python "/absolute/skill/path/lynse.py" version --json
```

```powershell
# Windows PowerShell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r "C:\absolute\skill\path\requirements.txt"
$env:LYNSE_NO_UPDATE_CHECK = "1"
.venv\Scripts\python.exe "C:\absolute\skill\path\lynse.py" version --json
```

Use the selected virtual-environment interpreter for subsequent commands.
The user's own terminal can run `auth login` at that script path to enter the key
privately. Credentials are saved outside the plugin in `~/.lynse/config.json`;
transient tokens use `~/.lynse/tokens.json`. A restart or refreshed cache preserves
those user files. An injected environment can supply `LYNSE_API_KEY` instead.
Do not copy secrets into the plugin or its ZIP.

## Other assistant environments

| Environment | Typical standalone directory | Credentials |
|-------------|------------------------------|-------------|
| Claude Code | `~/.claude/skills/lynse-cli/` | User config or process environment |
| Cursor | `~/.cursor/skills/lynse-cli/` | User config or process environment |
| Hermes | `~/.hermes/skills/lynse-cli/` | User config or process environment |
| OpenClaw | `~/.openclaw/workspace/skills/lynse-cli/` | Platform-injected environment or user config |

The CLI also supports a legacy `.env` beside its script at lowest precedence.
A project `.env` in the current working directory is not automatically loaded,
and Codex does not inject credentials from OpenClaw's `primaryEnv` metadata.
See [auth-and-security.md](auth-and-security.md) for resolution and host trust.

Sources: [Codex skill discovery](https://learn.chatgpt.com/docs/build-skills) and
[OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins).

OpenClaw accepts `python3`, `python`, or `py` through `requires.anyBins`; the
skill still verifies Python 3.11+ at runtime. `primaryEnv` supports platform key
injection, while no required-env discovery gate blocks saved-config login.
OpenClaw host env injection does not automatically reach sandbox containers;
configure runtime credentials in the actual execution environment when sandboxed.
See the [OpenClaw skill format](https://docs.openclaw.ai/tools/skills).
