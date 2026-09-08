# Changelog

All notable changes to **restmcp** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning:
[SemVer](https://semver.org/). Every PR/commit that changes behavior, API or
docs-that-ship must add an entry under **Unreleased**; the release flow moves
that block under the new version heading (the version in `pyproject.toml` and
this file move together — the publish workflow releases whatever version is in
`pyproject.toml`).

## [Unreleased]

## [0.6.1] - 2026-09-08

### Fixed
- `/mcp/tools` returned **500** when any registered endpoint carried a
  hand-written `mcp_definition` without a `parameters` key — a shape
  `_validate_mcp_definition` accepts (the OpenAPI and MCP builders already
  tolerated it). The catalog now publishes `{"properties": {}}` for it.

### Added
- Tests pin that the key identity (#15) reaches the callback over a real MCP
  `tools/call` through `asgi_app()`, sync and async — the contextvar hop fix
  (#16) was only covered on REST and in isolation; the MCP path depends on
  FastMCP executing the tool inside the request task.
- `examples/telemetry`: `whoami` endpoint + `IdentityService` reading
  `restmcp.auth.current_auth` (with `required_scope = "read"`), README rows,
  curl walkthrough, named-keys sample in `.env.example`, and an end-to-end
  test over REST and MCP.

## [0.6.0] - 2026-08-13

Issue #18, both halves — the status code stops being hardwired.

### Added
- **`success_code`** (#18): class-level declaration of the success envelope's
  HTTP status (default 200 — no existing endpoint changes). One declaration
  feeds the `JSONResponse` AND the OpenAPI document, so a frozen contract
  cannot disagree with the server. 2xx only, validated at class definition;
  204 rejected (No Content forbids a body, the envelope always has one).
  Errors keep coming from exception classes. Born for ReconcilIA's
  `POST /runs` → 202 Accepted.
- **`raw_response`** (#18): the FastAPI escape hatch — the callback returns a
  Starlette `Response` and it passes through verbatim (files, redirects,
  conditional codes, custom headers). Three locks: requires `expose="rest"`
  (raw has no MCP representation — import-time error otherwise, and
  `success_code` alongside it is rejected as conflicting); opt-in declared
  (a `Response` returned without the flag is a 500 with a pointed log message,
  never a silent passthrough — and raw returning plain data errors
  symmetrically); success only (exceptions still produce the standard error
  envelope, and the request pipeline — auth, scopes, body cap, validation —
  applies unchanged). In OpenAPI a raw operation documents one honest
  `default`; FastAPI's automatic success block is pruned via the `openapi()`
  override in `RestApp`.
- `examples/telemetry`: two new endpoints exercising both features through all
  layers — `recalibrate_fleet` (202 ticket) and `export_readings` (raw CSV
  download with the 404 path proving errors stay enveloped) — plus README
  rows, curl walkthrough and service-level tests.

### Changed
- Routes are now registered with FastAPI's `status_code` parameter derived
  from `success_code`, so FastAPI's automatic OpenAPI success block lands on
  the declared code instead of leaving a phantom `"200"` beside a custom one.

## [0.5.1] - 2026-08-11

### Fixed
- **CORS preflight passes through auth** (#17): with `AUTH_API_KEY` set,
  `AuthMiddleware` wraps the whole app — including `CORSMiddleware` — so the
  browser's `OPTIONS` preflight (which never carries `Authorization`, per the
  CORS spec) got 401 before CORS could answer, blocking every cross-origin
  call even with a valid token. A request is only exempt when it is strictly
  a preflight (`OPTIONS` + `Access-Control-Request-Method`); a bare `OPTIONS`
  still authenticates, and so does the actual request. Found on ReconcilIA's
  first real browser-to-authenticated-backend session.
- `examples/telemetry/README.md`: feature table now lists the
  `purge_readings` endpoint (expose + returns) added in 0.4.1.

## [0.5.0] - 2026-08-03

Six tracked issues closed in one pass (#11-#16), all TDD.

### Changed (breaking)
- **CORS safe default** (#11): absent `CORS_ORIGINS` now **denies**
  cross-origin requests (was `*` — any origin, silently); effectively-empty
  values (`""`, `","`) also deny instead of producing the
  blocks-everything-silently `[""]`. Both cases log a warning. Set
  `CORS_ORIGINS='*'` explicitly to restore the old behavior.
- **Malformed JSON is now HTTP 400** (#13): a body that is present but not
  valid JSON raises `ValidationError` instead of being silently treated as
  empty (defaults could turn a truncated payload into a different,
  "successful" call). Absent/empty bodies remain tolerated.

### Added
- **Request-body ceiling with 413** (#12): global `MAX_BODY_BYTES` (default
  1 MiB) enforced before buffering — declared Content-Length is refused
  upfront, streams are cut at the limit; per-endpoint override via the
  `max_body_bytes` class attribute. New `PayloadTooLargeError` (413).
- **Key identity and scopes** (#15): `AUTH_API_KEY` accepts `name:key:scope`
  entries (plain `key` keeps full scope); the matched principal
  `{"name", "scopes"}` is published as `request.state.auth` and via the
  `restmcp.auth.current_auth` contextvar; `Endpoint.required_scope` returns
  403 (`ForbiddenError`) before the callback. Bearer parsing unified in
  `token_from_authorization` (two subtly-different copies before).
- **Service DI beyond Repository** (#14): any declared non-callable,
  non-underscore class attribute is injectable via the constructor (webhook
  publishers, clocks, aggregation sources); Repositories keep the
  per-instance `copy.copy`; the at-least-one-Repository rule is unchanged.

### Fixed
- **contextvars survive the thread hop** (#16): sync callbacks now run via
  `asyncio.to_thread` (copies the caller's context) instead of a bare
  `run_in_executor` — identity/correlation vars set by middleware reach the
  callback.

## [0.4.1] - 2026-08-03

### Added
- README: `Endpoint` section now documents transport selection (`expose`) and
  the OpenAPI request/response schemas, with examples.
- `examples/telemetry`: new `purge_readings` endpoint demonstrating
  `expose = "rest"` (invisible to MCP agents) plus a declared `returns`
  schema, implemented through all three layers (the in-memory DataSource keeps
  purge state) with a DI-style test.
- `RAG_KNOWLEDGE_BASE.md`: full pass to 0.4.1 — new §11.8 (expose) and §11.9
  (OpenAPI schemas), catalog/MCP-build notes, all version scopes updated.

### Changed
- `serves_mcp()` (`restmcp/rest.py`) is now the single expose predicate,
  consumed by both the `/mcp/tools` catalog and `Server.mcp_handlers` — the
  filter previously existed as two copies.

## [0.4.0] - 2026-08-03

### Added
- **Response schemas in `/openapi.json`**: `mcp_definition["returns"]` — the
  slot the `/mcp/tools` catalog already published — is now the JSON Schema of
  the callback's return value. The `200` response documents the
  `{tool, result, success}` envelope with `result` typed by it (open when
  undeclared; the envelope alone already types the skeleton). Errors are
  documented once under `default` with the error envelope
  `{tool, error, success, error_type}`. A non-dict `returns` raises
  `TypeError` at class-definition time.

## [0.3.0] - 2026-08-02

### Added
- **Request schemas in `/openapi.json`**: `requestBody` (`POST/PUT/PATCH`) and
  query `parameters` (other methods) derived from `mcp_definition` — the same
  source the MCP side publishes, so REST and MCP cannot drift. Includes
  `operationId` (tool name) and `description`; `required` mirrors validation
  (property without a `default` key); `additionalProperties: false` documents
  the extra-key rejection. Before this, every operation was empty and
  generated clients (`openapi-typescript` etc.) produced no types.
- **Per-endpoint transport selection**: `expose = "rest" | "mcp" | "both"`
  (default `"both"`). `"rest"` keeps the tool out of the MCP server and the
  `/mcp/tools` catalog (structural guarantee for write/destructive endpoints an
  agent must not see); `"mcp"` registers no public HTTP route (agent-only
  tools). Invalid values raise at class definition.

## [0.2.0] - 2026-07-02

### Changed (breaking)
- Definition errors fail at **registration (import time)** instead of
  per-request, always naming the endpoint class or tool:
  - parameter names starting with `_`/`model_` (or invalid identifiers) are
    rejected — pydantic silently dropped or refused them before;
  - a declared `default` that does not match its declared type is rejected
    (defaults are validated and coerced at registration);
  - the callback signature must accept every declared property (defaults
    included) — on 0.1.x this worked on REST and broke only on MCP.
- Unknown query-string parameters are now ignored (previously HTTP 400).
- REST and MCP validate identically via one shared pydantic model
  (`build_arg_model`); HTTP 400 messages are pydantic-style.
- Explicit JSON `null` accepted only when the property's default is `null`;
  pydantic-lax boolean inputs accepted (`1`/`0`, `"on"`/`"off"`, `"yes"`/`"no"`).

## [0.1.7] - 2026-07-02 · [0.1.6] - 2026-06-29 · [0.1.5] - 2026-06-16 and earlier

Early development line: layered scaffolding (`DataSource`/`Entity`/
`Repository`/`Service`/`Endpoint` with auto-registration and discovery), REST +
MCP from one definition, Bearer auth middleware (`AUTH_API_KEY`), method cache,
CLI (`restmcp new`), `Returns:` docstring requirement for inferred definitions,
publish workflow (PyPI + GitHub Releases). See git history for the
commit-level record.

[Unreleased]: https://github.com/JorgeHSantana/restmcp/compare/v0.6.1...HEAD
[0.6.1]: https://github.com/JorgeHSantana/restmcp/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/JorgeHSantana/restmcp/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/JorgeHSantana/restmcp/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.1.7...v0.2.0
