# Command Reference

Examples use `python3 lynse.py` for readability. Resolve `lynse.py` relative to the
loaded `SKILL.md` and pass its quoted absolute path; use the interpreter selected
in the entrypoint instructions. Run `help` if the installed command set differs.

### Friendly Aliases (Preferred)

```
python3 lynse.py me                                    # Current user info
python3 lynse.py meetings list [--days 7]              # Recent meetings (past N days)
python3 lynse.py meetings month <YYYY-MM>              # Meetings in a specific month
python3 lynse.py meetings week <YYYY-Wnn>              # Meetings in a specific ISO week
python3 lynse.py meetings range <start> <end>          # Meetings in a date range (YYYY-MM-DD)
python3 lynse.py meetings search <keyword> [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--page N] [--size N]  # Search by title/date
python3 lynse.py meetings transcript <id>              # Get transcription
python3 lynse.py meetings transcript-text <id>         # Get transcription text
python3 lynse.py meetings audio <id>                   # Get audio download metadata
python3 lynse.py meetings summary <id> [--all]         # Get first AI summary; --all returns every summary
python3 lynse.py meetings outline <id>                 # Get outline
python3 lynse.py meetings info <id>                    # Meeting details
python3 lynse.py meetings organize [--days N] [--execute] [--yes]   # Auto-classify meetings into folders (dry-run by default; --execute applies)
python3 lynse.py folders list                          # List folders/groups
python3 lynse.py folders create <json>                 # Create folder
python3 lynse.py folders move <json>                   # Move files to folder
python3 lynse.py folders count                         # Count files by folder
python3 lynse.py folders delete <ids>                  # Delete server-verified empty folders only
python3 lynse.py todos list [all|open|done] [page] [size] # List todos; defaults to page 1, size 20
python3 lynse.py todos add <content> [--file ID] [--deadline 'YYYY-MM-DD HH:MM:SS'] [--weight N] [--owner NAME] [--sync 0|1]  # Insert todo(s); repeat --content or pass a JSON array for batch (max 100)
python3 lynse.py todos count                           # Deadline statistics: week/month/later/no-date/expired
python3 lynse.py todos range [start] [end] [--status 0|1] [--page N] [--size N]  # Query todos by expected completion time
python3 lynse.py todos delete <ids>                    # Delete todos
python3 lynse.py todos clear                           # Clear completed todos
python3 lynse.py todos reschedule <id> <deadline>      # Change todo deadline; pass a JSON array to batch-update content/status/owner/time
python3 lynse.py devices list                          # List bound devices
python3 lynse.py devices info <id>                     # Device details
python3 lynse.py devices unbind <id>                   # Unbind device
```

Todo deadlines use `YYYY-MM-DD HH:MM:SS`; `todos range` also accepts date-only bounds (the end bound is exclusive and expands to the next day 00:00:00). `todos add` inherits the cloud-sync marker of the linked file server-side when `--file` is given; `--sync 0` marks a todo offline-only.

`meetings search` matches titles only. To find text inside transcripts, first
list meetings in the requested scope, then retrieve their `transcript-text` and
filter locally; do not claim title search covers transcript content. For the
complete file inventory, `python3 lynse.py listFilesPaged 100 --json` fetches
all pages. Prefer a requested date range to avoid unnecessary transcript reads.

Search date filtering scans the paginated title matches and then applies the date range locally. It may take longer for broad searches.

**Date query flexibility** (`meetings month`/`week`):
```
python3 lynse.py meetings month 2026-04          # All April 2026 meetings
python3 lynse.py meetings month 4                # April of current year
python3 lynse.py meetings week 2026-W16          # ISO week 16 of 2026
python3 lynse.py meetings range 2026-04-01 2026-04-30   # Custom date range
```

**Auto-organize meetings into folders** (`meetings organize`):
```
python3 lynse.py meetings organize                       # Dry-run: print a folder plan, change nothing
python3 lynse.py meetings organize --days 90             # Plan only for the last 90 days
python3 lynse.py meetings organize --execute --yes       # Apply: create folders + move meetings (non-interactive)
```
Classifies meetings (with a summary) into topic folders by title, **reusing existing folders** where they match and creating new ones (icon + ≤6-char name) otherwise; caps at 10 folders + 🗂其他. Default is a safe **dry-run**. `--execute` applies changes; in a non-interactive/agent context it **requires `--yes`** (it refuses otherwise). Meetings without a summary are listed but not moved unless `--include-no-conclusion` is given.

**JSON mutations** (POSIX shell examples; keep each JSON payload one literal argument):
```bash
python3 lynse.py folders create '{"folderName":"项目A","color":"#EEEEEE"}' --json
python3 lynse.py folders move '{"oldFolderId":"OLD","newFolderId":"NEW","fileIds":["FILE_ID"]}' --json
python3 lynse.py todos update '[{"todoId":"TODO_ID","isCompleted":1}]' --json
python3 lynse.py todos reschedule TODO_ID '2026-10-08 09:00:00' --json
```
`todos update` is an alias of `reschedule` and accepts a JSON array of updates.
Only supplied fields are changed; `expectedCompleteTime: null` clears a deadline.
Use the selected shell's quoting rules on Windows, or pass an argument array when
supported. An organization execution may return exit code 0 with per-item failures;
inspect `results.folders_failed`, `results.errors`, and move counts before
reporting full success.

**Folder deletion safety** (`folders delete`):
- Every target ID must exist and be confirmed empty from fresh service data immediately before deletion.
- Prefer `folderStats[].count == 0`. Because the service may omit empty folders from `folderStats`, an omitted target is checked against the complete paginated server file inventory; any matching `folderId` blocks deletion.
- If any target is non-empty, unknown, has an invalid count, or cannot be verified, the entire batch is rejected and no `DELETE` request is sent.
- Never infer emptiness from a local organization plan, cached folder state, or completed move records.

### Auth & System

First-time setup: no key is hardcoded — each user inputs their own, saved locally to `~/.lynse/config.json`. The public production API host defaults to `https://api.lynse.cn`; custom hosts must be HTTPS origins.

```
python3 lynse.py auth login                    # Interactive prompt for your API key (recommended)
python3 lynse.py auth status                                  # Show auth config
python3 lynse.py auth logout                                  # Remove local token and saved API key
python3 lynse.py auth logout --tokens-only                    # Clear token cache only; key can renew it
python3 lynse.py auth doctor                                  # Diagnose auth issues
python3 lynse.py version    # Version, Python, OS, requests info
python3 lynse.py doctor     # Full environment diagnostics
python3 lynse.py update --check     # Report a newer npm version
python3 lynse.py update             # Update a standalone install only when requested
```

### Output Format Control

```
--json             Compact JSON (default when piped)
--pretty           Pretty-printed JSON
--text             Human-readable output (default in terminal)
--table            ASCII table for list results
-o, --output <file> Save output to file; summary/transcript use text unless JSON is explicit
```

Combine: `python3 lynse.py meetings list --table --output meetings.txt`


For plugin installs, refresh the plugin through its marketplace; `update` is the
standalone npm updater and does not refresh the plugin manifest or cached install.
Use `LYNSE_NO_UPDATE_CHECK=1` for diagnostics that should stay offline. `doctor`
and `auth doctor` can contact the configured host.
