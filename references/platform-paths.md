# Platform Paths (AI Assistant Environments)

The skill runs the same way in every AI assistant; only the install directory differs. Registry
installs place the minimal skill bundle directly into that directory. The standalone npm package
ships the same skill files plus a `lynse` shim for end-user shells, but an agent must call the
Python entrypoint directly. Python 3.11 or newer is required in every environment.

## Skill Install Directories

| Environment | Skills Directory | Env Vars |
|-------------|------------------|----------|
| Codex | Agent-selected Codex Skill directory | Manual `.env` or env vars |
| Claude Code | `~/.claude/skills/lynse-cli/` | Manual `.env` or env vars |
| Cursor | `~/.cursor/skills/lynse-cli/` | Manual `.env` or env vars |
| Hermes | `~/.hermes/skills/lynse-cli/` | Manual `.env` or env vars |
| OpenClaw | `~/.openclaw/workspace/skills/lynse-cli/` | Auto-injected by platform |

## How the Skill Is Invoked in Each Environment

All environments invoke the skill the same way once installed — the AI assistant runs the Python entrypoint inside its skills directory:

```bash
python3 lynse.py <command> [args...]   # macOS / Linux
python lynse.py <command> [args...]    # Windows (or: py -3 lynse.py)
```

No single interpreter name works on every platform — modern macOS (Homebrew) and recent
Ubuntu/Debian ship only `python3`, while Windows exposes `python` (not `python3`). Pick by
environment; if unsure, run `<candidate> lynse.py version` and use whichever prints a version
string.

The other difference across environments is **how env vars reach the process**:

- **OpenClaw**: injects `LYNSE_API_HOST` and `LYNSE_API_KEY` automatically.
- **Codex and other environments**: read from `.env`, `~/.lynse/config.json`, or exported env vars (see `references/auth-and-security.md`).

## Cross-Platform Execution Rules

1. Use `python3` on macOS/Linux, `python` (or `py -3`) on Windows. Never assume one name works everywhere.
2. Never wrap commands in shell scripts — they don't run on Windows. Call `lynse.py` directly.
3. The `lynse` npm shim, `npx`, and npm installers are end-user tools; an agent must never invoke them. Always call the Python entrypoint instead.
4. Never call the Lynse HTTP API directly (`curl` / `fetch` / requests against `$LYNSE_API_HOST`) — `lynse.py` subcommands are the only supported interface.
5. On Windows, call `python lynse.py ...` or `py -3 lynse.py ...` directly from the skill directory. For npm installs, the `lynse` command is provided by `bin/lynse.js`, and npm creates the Windows `.cmd` shim automatically.
