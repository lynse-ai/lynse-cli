# Changelog

## 1.8.2 (2026-09-17)

### New Features

- Monitor npm for new releases: at most one `registry.npmjs.org` metadata check per 24 h, cached in `~/.lynse/update-check.json`, printing a non-blocking stderr notice when a newer version exists. Disable with `LYNSE_NO_UPDATE_CHECK=1`.
- Rework `update` into a real self-updater: it queries the npm registry and, by default, downloads the latest tarball and atomically replaces the skill files in place (`lynse.py`, `SKILL.md`, `requirements.txt`, `references/*.md`), backing up the previous `lynse.py`; `update --check` only reports.
- Add a `--workbuddy` packaging variant that promotes `version` / `display_name` / `display_name_en` / `description_zh` / `description_en` to top-level SKILL.md frontmatter fields (WorkBuddy rejects packages without them); the default Codex variant stays free of those fields.

### Changed

- State the agent interface contract explicitly in `SKILL.md` and reference docs: agents must call `lynse.py` subcommands only — never the raw HTTP API, the npm `lynse` shim, or invented commands/flags.
- Remove legacy shell wrappers, standalone installers, and early user guides from the repository; the skill bundle is the Python entrypoint plus its reference docs.
- Replace hardcoded version tests with a cross-file consistency check across `lynse.py`, `package.json`, and `SKILL.md`.
- Extend the `--table` output for meeting lists (`meetings list/month/week/range/all/search`) with the two columns required by the SKILL.md output contract: `Duration` renders `bizDuration` seconds as `mm:ss` (empty while a recording is still processing) and `Folder` renders `folderName` as-is (empty when the meeting is uncategorized).

## 1.8.1 (2026-08-21)

### Security

- Save `~/.lynse/config.json` with owner-only permissions on Unix so locally stored API keys are not readable by other users.
- Guide Agent Skill installations to collect API keys only through the local terminal's hidden interactive prompt.

### Changed

- Recommend the cross-Agent `skills` installer for Codex, Claude Code, Cursor, and other Agent Skills clients; clarify that directly running the npm CLI does not install a Skill.

## 1.8.0 (2026-08-21)

### New Features

- Return the first meeting summary by default; add `meetings summary <id> --all` to return every summary record.
- Allow folder deletion only after every requested folder is confirmed empty using fresh server folder counts and, when needed, the complete paginated file inventory.

### Bug Fixes

- Send folder move and delete IDs in the comma-separated query format expected by the service.
- Resolve device details from the current user's bound-device list and unbind through the current MAC-address endpoint.
- Make doctor commands emit structured output while keeping API keys completely out of diagnostics.

### Changed

- Remove unsupported AI model management, todo creation, and request debug-log commands from the public CLI surface and documentation.
- Restore npm publishing on `v*` tag pushes, with tag/package version validation, package-content checks, credential validation, and registry verification.

## 1.7.0 (2026-08-12)

### New Features

- Add `meetings audio <id>` and `LynseAPI.get_audio_file()` for presigned meeting audio metadata.
- Add todo creation and rescheduling plus server-side folder counts and folder deletion.
- Support injected access tokens, owner IDs, and HTTP clients for embedded consumers such as Lynclaw.

### Changed

- Make `lynse-cli` pip-installable so Lynclaw and `lynse-mcp` can import the same `LynseAPI` implementation instead of maintaining copies.
- Establish this repository as the single source of truth for the Lynse API client and CLI behavior.
- Split the MCP server into the separate `lynse-mcp` repository and remove MCP packaging entries from `lynse-cli`.

## 1.6.6 (2026-07-23)

### Security

- Permanently redact authentication headers and omit command arguments, query values, request bodies, response bodies, and server messages from HTTP debug logs.
- Remove documentation that instructed users to persist aliases in shell startup files.

### Changed

- Build the WorkBuddy/SkillHub artifact from a strict six-file allowlist, excluding legacy shell clients, installers, tests, and npm-only documentation.
- Declare the skill's network destination, data handling, trusted-host rule, and minimal Python tool permissions.

## 1.6.5 (2026-07-19)

### Bug Fixes

- `_format_table` no longer truncates the ID column to 40 chars. Meeting/file IDs are longer than 40 chars, so the previous `str(v)[:40]` cut silently dropped trailing characters and broke downstream `meetings summary/transcript/outline/info` lookups when the ID was copied from the table. The ID column now stays full; other wide columns still truncate but keep an explicit `...` marker (see `tests/test_format_table.py`).

### Changed

- Raise the minimum supported Python version from 3.8 to 3.11 across the CLI, installers, npm wrapper, and skill documentation.
- Add automated test coverage for Python 3.11 through 3.14.

## 1.6.4 (2026-07-05)

### New Features

- Add `meetings transcript-text <id>` to fetch meeting transcription text from the transcription endpoint, including speaker labels and timestamps.

### Changed

- Keep transcription text separate from AI summaries by routing through `getTranscriptionRecord` instead of conclusion APIs.
- Document `getTranscriptionText` under file read permissions.

## 1.6.3 (2026-06-29)

### Changed

- Clarify that Lynse is the English product context and 灵光记 is the Chinese product name, so requests to use 灵光记 route to this CLI skill.
- Remove all OpenAPI-generated docs (`lynse-cli-a/docs/*`, `lynse-cli-b/docs/*`) and associated generated artifacts to reduce repository bloat.
- Remove deprecated `lynse.bat` (Windows batch wrapper), `.env.example`, and old GitHub Actions `npm-publish.yml` workflow.
- Update `lynse.py` CLI version from 1.6.1 to 1.6.3; update `SKILL.md` version from 1.5.1 to 1.6.3.
- Remove `.env.example` from npm package file list.

## 1.6.2 (2026-06-24)

### New Features

- Add `bin/lynse.js` — a cross-platform npm command wrapper that replaces the old Windows batch wrapper, making the `lynse` command work via npm on all platforms (macOS, Linux, Windows).

### Changed

- Update `package.json` entry point to `bin/lynse.js`; include `CHANGELOG.md`, `install-guide.md`, `reference.md`, and `references/` in the npm package files list.
- Update documentation (`SKILL.md`, `reference.md`, `references/platform-paths.md`) to reflect the new npm wrapper and remove batch-wrapper references.
- Clean up `.gitignore` with explicit patterns for generated OpenAPI client artifacts.

## 1.6.1 (2026-06-20)

### Bug Fixes

- Retry transient HTTP 429/5xx in `_request` so every command survives a momentary server hiccup (found when the folder-create endpoint returned a 503 mid-organize).
- `meetings organize --execute` now surfaces folder-creation failures (`folders_failed`) instead of failing silently; affected meetings are skipped and a re-run finishes them once the server recovers.
- `folders list --text/--table` now shows folder names (read `folderName`; previously rendered `?`).

## 1.6.0 (2026-06-20)

### New Features

- **`meetings organize`** — auto-classify meetings into Lynse folders by topic. Dry-run plan by default (changes nothing); `--execute` creates folders and moves meetings. Reuses existing folders where they match and proposes new ones (icon + ≤6-char name), capping at 10 folders + 🗂其他. Flags: `--days N` (scope), `--execute` / `--yes` (apply; non-interactive requires `--yes`), `--include-no-conclusion`.

## 1.5.2 (2026-06-20)

### Bug Fixes

- Stop a stale install `.env` from overriding the API key saved via `auth login` — this caused intermittent `meetings month` failures ("API Key authentication failed") whenever a token refresh was required while a cached token was still valid.
- Token exchange now retries transient server/network errors (5xx, 429, timeouts) with backoff instead of failing on the first hiccup, and no longer reports server errors as "API Key authentication failed". HTTP 401/403 is reported as a rejected key; everything else as a transient error.

### Changed

- Resolve API credentials with one consistent precedence used by every command: `--api-key` param → shell env (`LYNSE_API_KEY`) → `~/.lynse/config.json` → install `.env`. `auth status` now reports the actual source (`config_source`).
- `auth login` prompts for the key interactively (hidden input) in a terminal and requires `--api-key` in non-interactive/agent contexts. No API key is hardcoded or shipped.
- Install scripts (`install.sh`, `install.ps1`) no longer write a placeholder key into `.env`; users are directed to `auth login`.

## 1.5.1 (2026-06-20)

### New Features

- Auto-detect the Python 3 interpreter (`python3` vs `python`) at install time, so `install.sh` prints the right invocation for the user's environment.
- Add reference documentation: `install-guide.md`, `reference.md`, and `references/{auth-and-security,error-handling,platform-paths}.md`.

### Bug Fixes

- Meeting list commands now render `--table` / `--text` output formats correctly.
- Restore executable bit on `install.sh` so `./install.sh` works as documented.

### Changed

- Rewrite `SKILL.md` from Chinese to English and restructure it for AI agent consumption (consolidated cross-platform guidance, explicit interpreter-selection table).
- Move table formatting conventions out of hardcoded CLI code and into the `SKILL.md` prompt convention.
- Update `lynse.py` module docstring to prefer `python3` with a Windows fallback note.
