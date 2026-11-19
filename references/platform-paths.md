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
execution environment with Python, HTTPS access to Lynse, and a device session;
a remote/cloud environment must authorize in its own runtime.

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
The user can run `auth login --device --profile default` in the CLI runtime.
Use the same profile in `--device-session default` for account commands.
A session is saved in the execution environment's user directory, outside the
skill folder. The CLI binary and Skill can be copied independently of the session.

## Other assistant environments

- **Claude Code:** place the complete `lynse-cli` directory under
  `.claude/skills/` in the project or `~/.claude/skills/` for that user.
  [Claude Code Skills](https://code.claude.com/docs/en/skills)
- **Muse Code:** install the extracted directory with
  `muse skills install ./skills/lynse-cli --scope user`.
  [Muse Code Skills](https://dev.meta.ai/docs/muse-code/extending)
- **WorkBuddy:** use the dedicated CLI + Skill connector ZIP for managed
  installation and browser authorization.
  [WorkBuddy connector](https://open.workbuddy.cn/docs/connector)
- **Other agents:** install the directory in the host's skill location, or
  invoke the CLI through its shell tool with Python and HTTPS access.

Use [auth-and-security.md](auth-and-security.md) when an administrator has
explicitly configured a legacy API Key.
