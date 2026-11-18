# Command Reference

Examples use `python3 lynse.py` for readability. Resolve `lynse.py` relative to the
loaded `SKILL.md` and pass its quoted absolute path. Use the interpreter selected
in the entrypoint instructions. Run `help`, `meetings --help`, or
`meetings organize --help` to inspect the installed command set offline.

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
python3 lynse.py meetings transcribe <id> [--template ID] [--model ID] [--language ID]  # Submit cloud transcription + summary (uses credits)
python3 lynse.py meetings transcribe-status <ids...>   # Query status for 1-100 file IDs
python3 lynse.py meetings auto-transcribe [--once] [--interval 60] [--state-file PATH] [--template ID] [--model ID] [--language ID]  # Watch new cloud audio recordings
python3 lynse.py meetings audio <id>                   # Get audio download metadata
python3 lynse.py meetings marks <id>                   # Get recording marks and image records
python3 lynse.py meetings mark-images <md5>            # List mark images by recording MD5
python3 lynse.py meetings mark-image <image-id>        # Get a temporary image URL
python3 lynse.py meetings summary <id> [--all] [--include-mind-map]  # Get the first AI summary or all with --all
python3 lynse.py meetings outline <id>                 # Get outline
python3 lynse.py meetings info <id>                    # Meeting details
python3 lynse.py meetings organize [--days N] [--include-no-conclusion] [--execute [--yes --plan-id ID]]
python3 lynse.py folders list                          # List folders/groups
python3 lynse.py folders create <json>                 # Create folder
python3 lynse.py folders move <json>                   # Move files to folder
python3 lynse.py folders count                         # Count files by folder
python3 lynse.py folders delete <ids> --check          # Check current emptiness without writing
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

Summary requests omit mind map content by default. Use `--include-mind-map --json` to retrieve `mindMapText`.

`meetings marks` returns `recordMarks`, `recordMarkResults`, and `markImages`.
Use `meetings mark-images <md5>` to find image records when you only have the recording's MD5.
For a private image, pass its `imageId` to `meetings mark-image`.
Use `--text` for the URL alone and request a fresh URL after it expires.

Todo deadlines use `YYYY-MM-DD HH:MM:SS`; `todos range` also accepts date-only bounds (the end bound is exclusive and expands to the next day 00:00:00). `todos add` inherits the cloud-sync marker of the linked file server-side when `--file` is given; `--sync 0` marks a todo offline-only.

`meetings search` matches titles only. To find text inside transcripts, first
list meetings in the requested scope, then retrieve their `transcript-text` and
filter locally; do not claim title search covers transcript content. For the
complete file inventory, `python3 lynse.py listFilesPaged 100 --json` fetches
all pages. Prefer a requested date range to avoid unnecessary transcript reads.

Search date filtering scans the paginated title matches and then applies the date range locally. It may take longer for broad searches.

**Automatically transcribe new cloud recordings**:
```bash
python3 lynse.py meetings auto-transcribe --text         # Keep running; scan every 60 seconds
python3 lynse.py meetings auto-transcribe --once --json  # One scan, suitable for a scheduler
python3 lynse.py meetings transcribe FILE_ID --json      # Explicitly submit an existing recording
python3 lynse.py meetings transcribe-status FILE_ID --json
```
The first scan records the complete current file inventory and submits nothing.
Later scans submit newly observed **audio** files after upload completion and
after verifying that no transcription task already exists. Uploads in progress
are checked again on later scans. Existing, running, completed, and failed tasks
are skipped. This invokes the backend's transcription **and summary** pipeline;
it uses the account's normal credits/allowance. A returned `taskId` means the task
was submitted, not that transcription has finished.

Keep the process running, or schedule repeated `--once` calls with the same state
file. The interval is at least 10 seconds. This CLI does not create a server-side
automatic-transcription setting or install a background service. It does not
watch local folders or upload local audio. Streaming `--json` emits one JSON object
per scan; `--output` requires `--once`.

State defaults to `~/.lynse/auto-transcribe/<account-host-hash>.json`, scoped to the
account returned by the authenticated current-customer endpoint and API origin.
An administrator can set `LYNSE_AUTO_TRANSCRIBE_STATE_DIR` to a persistent server
directory; account/origin isolation is retained. CLI and MCP share this setting.
It stores file/task IDs and submission outcomes, without credentials or recording
content. Preserve this file across runs; a missing state file establishes a new
baseline. A custom `--state-file` cannot be reused for another account or origin.
Concurrent scans using the same state file are rejected; use one state file per
account to retain deduplication across scheduled jobs.

Before a charged submission, the CLI saves an attempt marker. Network errors,
missing task IDs, or interruption during submission never cause automatic
resubmission. `needsReview` stops the watcher with exit code 6. A later scan checks
the server: if an existing task is confirmed, it clears that review condition
without submitting again. Otherwise inspect `transcribe-status` and `meetings info`
to determine whether the request was accepted. After resolving the cause, submit
explicitly with `meetings transcribe` only when the user authorizes the retry; the
next scan reconciles the confirmed task. Corrupt state is rejected without reset.

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
python3 lynse.py meetings organize --help
python3 lynse.py meetings organize --days 90 --json
python3 lynse.py meetings organize --days 90 --execute --yes --plan-id PLAN_ID --json
```
The preview reads the account's meetings and folders using configured credentials.
The CLI classifies meetings by title and proposes reusing or creating folders.
Use a positive integer for `--days`. It limits the plan to the requested rolling
window and reports records with unknown dates in `scope.skipped_unknown_date`.
Use `--include-no-conclusion` to move meetings that have no summary. After
authorization, keep the same filters and pass the preview's `plan_id` with
`--execute --yes --plan-id` for non-interactive execution. The CLI rejects changes
to the approved plan and reads back the current folder assignments after writes.
Exit 6 with an execution result indicates errors. Review
`results.folders_failed`, `results.errors`, and move counts before retrying.

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
supported.

**Folder emptiness check** (`folders delete <ids> --check`):
The CLI confirms that each target exists and is currently empty. If the service
omits a folder count, the CLI verifies the complete paginated file inventory.
The check returns `mode: "check"` and `data.empty: true` when every target is
verified empty. Actual deletion requires an atomic empty-folder operation on
the service.

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

### Lynclaw usage

`usage summary`, `usage attempts`, `usage steps`, `usage jobs`, and `usage orders`
read records from the trusted service configured in `LYNCLAW_API_URL`. Each
query sends the current account token to that service. Use the origin supplied
by the user or administrator and run `usage --help` for the available filters.

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
Use `version --json` to check the installed HTTP dependencies and `auth status`
to check local credential configuration. `doctor` and
`auth doctor` can contact the configured host.
