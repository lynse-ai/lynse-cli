# Error Handling

Read the CLI exit status, stderr, and any JSON it returned. Use the bundled CLI
for recovery.

| Exit | Meaning | Recovery |
|------|---------|----------|
| 0 | Success | Check result fields for completed writes, including move counts and errors in an organize result. |
| 1 | Invalid input or local error | Inspect `help` or the command's `--help` offline and correct the invocation. |
| 2 | Authentication required or expired | Run `auth status --json`. Configure a missing or rejected key privately with `auth login` or the host's credential injection, then retry the original operation. |
| 3 / 4 | Connection error or timeout | Check connectivity. After a write request, verify the service state before retrying. |
| 5 | Permission denied | Verify the account and ask the administrator for the required access. If the error specifically says the key was rejected, check the key privately. |
| 6 | Service rejected the request or returned an error | Use the CLI message to identify the cause. The CLI already retries safe reads on transient errors. Inspect state before retrying any write. |

## Reporting Errors to Users

1. State what went wrong
2. Suggest likely cause
3. Provide actionable next step
