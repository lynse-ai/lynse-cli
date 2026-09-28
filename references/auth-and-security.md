# Auth & Security

> **Agent note**: the endpoints below are implemented internally by `lynse.py` and documented
> for troubleshooting only. Always invoke the CLI (`python3 lynse.py <command>`) — never call
> these endpoints directly with `curl`, `fetch`, or any other HTTP client.

## Two-Layer Auth

Lynse uses **API Key + temporary Token**:

```
Step 1: Exchange API Key for Token
POST $LYNSE_API_HOST/api/auth/apikey/token
Header: X-API-Key: $LYNSE_API_KEY

Step 2: Call business APIs with Token
Header: Authorization: <accessToken>    (no Bearer prefix)
Header: X-API-Key: $LYNSE_API_KEY
```

- **API Key format**: `dk_xxx` (obtained from system console)
- **Token TTL**: 2 hours, auto-refreshes on expiry
- **API Key config**: `~/.lynse/config.json`, file permission 600 (owner read/write only)
- **Token cache**: `~/.lynse/tokens.json`, file permission 600 (owner read/write only)

## Config Resolution Order (v1.4.0+)

1. CLI flags (`--api-key`, `--host`)
2. Environment variables (`LYNSE_API_KEY`, `LYNSE_API_HOST`)
3. User config (`~/.lynse/config.json`)
4. Install `.env` file (lowest precedence, backward compatible)
5. Public production host default (`https://api.lynse.cn`); there is no default API key

A stale install `.env` key **never** overrides the key saved via `auth login`
(user config) or an explicit shell export. Prefer `auth login` — no key is
hardcoded or shipped.

## Auth Flow

```
User calls lynse.py
  → Use the official host or resolve a configured HTTPS custom host
  → Resolve LYNSE_API_KEY
    → Not found → Check ~/.lynse/config.json
      → Not found → Check .env
        → Not found → Prompt user to configure
  → Found → Check cached token (~/.lynse/tokens.json)
    → Valid → Use directly
    → Expired → POST /api/auth/apikey/token for new token
      → Success → Cache (chmod 600) → Call business API
      → Failure → Prompt to check API Key
```

**Before every call**: a valid API key + host must be resolvable. Recommended setup (key saved locally to `~/.lynse/config.json`, never hardcoded):

```bash
python3 lynse.py auth login                 # interactive prompt for your key
# Or set env vars (e.g. when injected by the platform):
export LYNSE_API_HOST="https://api.lynse.cn"
export LYNSE_API_KEY="dk_xxx"
```

Token-exchange failures are classified: HTTP 401/403 means the key was rejected
(check your key); 5xx/429/network errors are retried automatically and reported as
transient — they do **not** mean your key is wrong.

## Security Rules

### Sensitive data protection
- Never proactively show phone numbers, points, or other sensitive fields in group chats
- Default to non-sensitive fields (nickname, ID) unless user explicitly requests more
- In group chats, mask phone numbers (`138****1234`), hide points
- If `LYNSE_OWNER_ID` is set, verify current user matches; if not, reply: "Access denied: this is a private account."

### Auth security
- Cached tokens refresh when expired; HTTP 401 reads refresh and retry once when an API Key is available. Writes are never resubmitted automatically.
- `auth logout` removes the local token and saved API key; it does not revoke credentials on the server. `--tokens-only` keeps the key, so the token can be renewed. Remove environment or install `.env` credentials at their source.
- When `LYNSE_OWNER_ID` is set, verify the account ID before business requests; reject mismatches and unverifiable identities.
- Custom API hosts must be HTTPS origins.
- User config file must have 600 permissions (owner read/write only)
- Token cache file must have 600 permissions (owner read/write only)

### Input safety
- All user inputs are sanitized against injection
- Space create/edit operations by 1+ minute to avoid server rate limits
- Before deleting folders, verify every target against fresh server-side folder counts; if an empty folder is omitted from the count response, confirm it has no matching `folderId` in the complete paginated server file inventory. Reject the whole batch when any target cannot be verified empty.
