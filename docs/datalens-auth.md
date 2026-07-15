# DataLens Auth

The API client uses:

- `https://api.datalens.tech`
- `Authorization: Bearer <IAM_TOKEN>`
- `x-dl-org-id`
- `x-dl-api-version: 2` for the first `auto` request; only an actual
  version-specific read failure is retried once under legacy version 1
- JSON `accept` and `content-type`

Auth retry is centralized in `datalens_dev_mcp.api.auth.request_with_auth_refresh`:

1. Run the intended request, or run `dl_probe_auth` when the operation is only an
   auth check.
2. If the request succeeds, keep the current token.
3. If the request fails with auth expiration, refresh once.
4. Retry the original request once.
5. If refresh or retry fails, return a sanitized actionable auth error.

No tool should duplicate token-expiry or API-version prechecks. Runtime refresh is enabled only
through the centralized client hook. Set `DATALENS_ENABLE_TOKEN_REFRESH_ON_401=1`
to let the client run `yc iam create-token` in memory on auth failure, or inject
a test/operator refresh callback.
