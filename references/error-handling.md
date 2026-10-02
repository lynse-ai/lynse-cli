# Error Handling

## Error Response Format

```json
{"code": 403, "message": "error details", "data": null}
```

## HTTP / Business Error Mapping

| Scenario | HTTP Code | Action |
|----------|-----------|--------|
| Token expired | 401 | Auto-refresh and retry safe reads once when an API Key is available; do not resubmit writes automatically. |
| Insufficient permissions | 403 | "Insufficient permissions. Contact admin to upgrade." |
| Rate limited | 429 | Retry reads with a short backoff; report writes for manual review. |
| Not found | 404 | "Resource not found." |
| Server error | 500/502/503 | Retry safe reads; report writes, including writes exposed as GET endpoints, without automatic retry. |
| Token refresh failed | — | For rejected credentials (401/403), ask the user to check their key privately. For 429/5xx/network errors, report a transient auth-service failure; do not label the key invalid. |
| Business error (code != 200) | — | Show error message with possible cause and fix |

## Reporting Errors to Users

1. State what went wrong
2. Suggest likely cause
3. Provide actionable next step
