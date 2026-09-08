# restmcp - Knowledge Base for Retrieval-Augmented Generation (RAG)

Technical reference document for the Python framework **restmcp**.

- Framework version documented: **0.4.1**
- PyPI package: `restmcp`
- License: MIT
- Supported Python: 3.11, 3.12, 3.13
- Repository: https://github.com/JorgeHSantana/restmcp
- Author: Jorge Henrique Moreira Santana

## How to use this document

This file is a self-contained knowledge base about the restmcp framework, written to be consumed by an AI agent through a Retrieval-Augmented Generation (RAG) pipeline. It is meant to be ingested by a RAG system (chunked, embedded, and indexed) so that an agent can retrieve the relevant passages and answer questions about restmcp grounded in this text, rather than from memory.

Guidance for the agent and for whoever maintains this file:

- **Source of truth.** Answer questions about restmcp using the content below. When a question is not covered here, say so instead of guessing.
- **Self-contained sections.** Each numbered section is written to stand on its own, so a chunk retrieved in isolation still carries enough context to be useful.
- **Concrete examples.** Most concepts are paired with runnable code examples and, where relevant, the exact inferred output. Prefer citing these examples when explaining a concept.
- **Version-scoped.** Everything here describes restmcp at version 0.4.1 specifically: schema inference rules, the required `Returns:` docstring section, the tool catalog, and the layered architecture. If the framework version in use differs, treat these details as potentially outdated and verify against the source code.

---

## 1. What restmcp is

restmcp is a Python framework for building **MCP servers** (Model Context Protocol) with a layered architecture and simultaneous REST compatibility. From a single class definition, the same code is exposed as:

- an **MCP tool** (consumed by AI agents over the MCP protocol), and
- a **REST HTTP endpoint** (consumed by any HTTP client).

Core principles:

- **Auto-registration:** defining the class already registers the route; there is no manual wiring.
- **Dependency injection:** each layer receives the layer below it and can receive mocks in tests.
- **Sync/async agnostic:** synchronous callbacks run in a thread pool; asynchronous ones are awaited directly.
- **Suffix convention:** the name of each base class ends with a mandatory suffix, validated at import time.

In one sentence: annotated classes become MCP tools and HTTP endpoints, auto-registered, dependency-injected, and indifferent to sync/async.

---

## 2. Layered architecture

The data flow traverses five layers, each knowing only the layer immediately below it.

```mermaid
graph LR
    LLM["LLM / HTTP Client"] -->|"HTTP or MCP"| EP["Endpoint"]
    EP --> SV["Service"]
    SV --> RP["Repository"]
    RP --> DS["DataSource"]
    DS --> EX[("External API / DB")]
```

**Explanation:** the client (an AI agent over MCP, or an HTTP client over REST) calls the `Endpoint`. The `Endpoint` delegates business logic to the `Service`. The `Service` orchestrates one or more `Repository` objects. Each `Repository` accesses exactly one `DataSource`, which is the bridge to the external system (database, REST API, file). Each layer knows only the one below it: the `Endpoint` does not talk to the `DataSource` directly, and the `Repository` does not know the `Service`. Class names have a mandatory suffix validated at import, so a typo raises `TypeError` before the server starts.

Responsibility of each layer:

| Layer | Responsibility | Required suffix |
|---|---|---|
| DataSource | Raw connection to the external system (HTTP, database, file). Returns raw data (dicts). | `*DataSource` |
| Entity | Typed domain model (Pydantic). Validates and serializes data. | `*Entity` |
| Repository | Data access: uses a DataSource and turns raw data into Entities. | `*Repository` |
| Service | Business logic: joins, transformations, multi-source rules. | `*Service` |
| Endpoint | HTTP route and MCP tool. Receives the request and delegates to the Service. | `*Endpoint` |

---

## 3. Request lifecycle

```mermaid
sequenceDiagram
    participant C as Client / LLM
    participant E as Endpoint
    participant S as Service
    participant R as Repository
    participant D as DataSource

    C->>E: POST /api/get-product {"product_id": "1"}
    E->>S: service.execute(product_id="1")
    S->>R: repo.get(product_id="1")
    R->>D: data_source.fetch("1")
    D-->>R: raw dict
    R-->>S: ProductEntity
    S-->>E: result dict
    E-->>C: {"tool": "get_product", "result": {...}, "success": true}
```

**Explanation:** the client sends a POST whose JSON body contains the parameters. The `Endpoint` validates the received parameters against the inferred schema, invokes the `Service`, which calls the `Repository`, which asks the `DataSource` for the raw data. The `DataSource` returns a raw dict; the `Repository` converts it into an `Entity`; the `Service` applies the business rule and returns a dict; the `Endpoint` wraps the response in the standard envelope (`tool`, `result`, `success`) and replies to the client. The same path applies to MCP protocol calls: the MCP layer invokes the same `callback`.

---

## 4. Installation and requirements

Install via PyPI:

```bash
pip install restmcp
```

Dependencies installed automatically:

| Dependency | Minimum version | Role |
|---|---|---|
| fastapi | >= 0.100 | REST layer (HTTP routes, validation, CORS). |
| uvicorn[standard] | >= 0.20 | ASGI server to run the application. |
| fastmcp | >= 2.0 | MCP protocol implementation. 3.x is recommended for full Streamable HTTP. |
| pydantic | >= 2.0 | Data models (Entity) and validation. |
| click | >= 8.0 | CLI (`restmcp new`). |

Installing `fastmcp` also brings `starlette` as a transitive dependency. The development extras (`restmcp[dev]`) include `pytest`, `pytest-cov`, `httpx`, and `requests`.

---

## 5. CLI: create a new project

The `restmcp new` command creates a project with the standard folder structure.

```bash
restmcp new my-server
cd my-server
pip install -e .
python main.py
```

Generated structure:

```
my-server/
  datasources/    external connections (APIs, databases)
  entities/       domain models (Pydantic)
  repositories/   data access layer
  services/       business logic
  utils/          internal helpers
  endpoints/      endpoint definitions (auto-discovered)
  main.py
  pyproject.toml
```

Each folder receives an empty `__init__.py`. Folder names are free: only class suffixes are mandatory, not directory names. The generated `main.py` calls `autodiscover("endpoints")` and exposes `app = Server.get_instance().asgi_app()`.

---

## 6. Naming conventions

All base classes enforce a suffix. Violating the suffix raises `TypeError` at import time, before the server starts.

| Base class | Required suffix | Valid example |
|---|---|---|
| DataSource | `*DataSource` | `ProductApiDataSource` |
| Entity | `*Entity` | `ProductEntity` |
| Repository | `*Repository` | `ProductRepository` |
| Service | `*Service` | `GetProductService` |
| Endpoint | `*Endpoint` | `GetProductEndpoint` |

The check runs in each base class's `__init_subclass__`, which executes when the subclass is defined (imported). Only the class suffix is checked; file and folder names are free.

---

## 7. DataSource layer

Abstracts the connection to an external source (REST API, database, file). Returns raw data (dicts), never Entities.

Rules:
- Class name must end with `DataSource`.
- It is abstract: `DataSource` cannot be instantiated directly (raises `TypeError`).

```python
import httpx
from restmcp import DataSource

class ProductApiDataSource(DataSource):
    base_url = "https://api.example.com"

    async def fetch(self, product_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self.base_url}/products/{product_id}")
            r.raise_for_status()
            return r.json()
```

`DataSource` does not define a mandatory fixed-signature method: each implementation exposes whatever methods make sense (`fetch`, `fetch_readings`, `make_query`, etc.). The contract is only the suffix and the prohibition on instantiating the base class.

---

## 8. Entity layer

`Entity` is a Pydantic model (`BaseModel`) with automatic type validation and the mandatory `*Entity` suffix.

Provided methods:

| Method | Kind | Behavior |
|---|---|---|
| `serialize()` | instance | JSON-safe representation via `model_dump(mode="json")`: datetime becomes ISO 8601, Decimal becomes string, etc. |
| `deserialize(data)` | class | Builds the entity from a dict of raw data (`cls(**data)`). |

```python
import datetime as dt
from typing import Literal
from restmcp import Entity

BatteryStatus = Literal["healthy", "degraded", "critical"]

class DeviceReadingEntity(Entity):
    device_id: int
    device_name: str
    firmware: str
    battery_level: float
    signal_dbm: int
    recorded_at: dt.datetime

    @property
    def status(self) -> BatteryStatus:
        if self.battery_level >= 60:
            return "healthy"
        if self.battery_level >= 20:
            return "degraded"
        return "critical"

    def serialize(self) -> dict:
        data = self.model_dump(mode="json")
        data["status"] = self.status
        return data
```

Overriding `serialize()` is optional: the framework serializes any callback return value with `jsonable_encoder`. Override only when the output JSON must differ from the model's fields (here, to add the derived `status` field). You can return an `Entity` (or a `datetime`) directly from a callback and get correct JSON without calling `.isoformat()` manually.

---

## 9. Repository layer

Fetches data via a `DataSource` and returns `Entity` objects (or lists of Entities). One source, one data type.

Rules:
- Class name must end with `Repository`.
- Must declare `data_source` as a class attribute.
- Must implement the abstract `get()` method.

```python
import datetime as dt
from restmcp import Repository
from datasources.telemetry import TelemetryDataSource
from entities.reading import DeviceReadingEntity

class ReadingRepository(Repository):
    data_source = TelemetryDataSource()

    def get(self, device_id_list=None, since=None, until=None) -> list[DeviceReadingEntity]:
        until = until or dt.datetime.now()
        since = since or (until - dt.timedelta(days=7))
        rows = self.data_source.fetch_readings(device_id_list, since=since, until=until)
        return [DeviceReadingEntity(**row) for row in rows]
```

### 9.1 Dependency injection

```python
repo = ProductRepository()                              # uses the real DataSource
repo = ProductRepository(data_source=MockDataSource())  # injects a mock in tests
```

The `Repository.__init__` resolves `data_source` from the argument, or, in its absence, makes a `copy.copy()` of the class attribute. Each instance gets its own copy, so instances never share state. If the resolved `data_source` is missing or is not a `DataSource` instance, the constructor raises `ValueError`.

---

## 10. Service layer

Orchestrates business logic: joins, transformations, and rules that span multiple sources.

Rules:
- Class name must end with `Service`.
- Must declare at least one `Repository` as a class attribute (checked via MRO in `__init_subclass__`; absence raises `TypeError`).

```python
from restmcp import Service, cached_method, NotFoundError
from repositories.reading import ReadingRepository

class BatteryHealthService(Service):
    readings = ReadingRepository()

    def latest_reading(self, device_id: int):
        items = self.readings.get(device_id_list=[device_id])
        if not items:
            raise NotFoundError(f"No telemetry for device {device_id}")
        return max(items, key=lambda r: r.recorded_at)
```

### 10.1 Dependency injection

```python
svc = GetProductService()                       # production
svc = GetProductService(repo=MockRepository())  # test
```

The `Service.__init__` walks the class MRO, finds every attribute that is a `Repository` instance, and assigns each instance an isolated copy (`copy.copy`), or the override passed as an argument. This allows injecting mocks in tests without affecting other instances.

---

## 11. Endpoint layer

HTTP route and MCP tool. **Auto-registers at class-definition time**: there is no manual wiring.

Rules:
- Class name must end with `Endpoint`.
- Must declare `url`, `method`, and `callback`.
- `mcp_definition` is inferred from the `callback` when not provided explicitly.
- `expose` selects the transport: `"rest"`, `"mcp"` or `"both"` (default) — see 11.8.
- `success_code` declares the HTTP code of the success envelope (default 200) — see 11.10.
- `raw_response` opens the FastAPI escape hatch on REST-only endpoints — see 11.11.

```python
from typing import Annotated
from restmcp import Endpoint
from services.product import GetProductService

class GetProductEndpoint(Endpoint):
    url    = "/api/get-product"
    method = "POST"

    async def callback(self, product_id: Annotated[str, "Product ID"]) -> dict:
        """Get a product by ID.

        Returns: the product object (id, name, price, currency).
        """
        return await GetProductService().execute(product_id)
```

Defining the class is enough: the route is registered on the `Server` singleton the moment Python processes the class body.

### 11.1 Inferring mcp_definition

When the `mcp_definition` attribute is not declared, restmcp infers it from the `callback`:

| Field | Source |
|---|---|
| `name` | Class name without the `Endpoint` suffix, converted from CamelCase to snake_case (`GetDeviceEndpoint` becomes `get_device`). An explicit `name` class attribute takes priority. |
| `description` | The full callback docstring (not just the first line). If the callback has no docstring, the class docstring is used; if neither exists, the tool name is used. |
| `parameters` | Inferred from the callback signature: each parameter (except `self`, `*args`, `**kwargs`) becomes a property with type, description, and default. |

### 11.2 The Returns docstring requirement

**The callback docstring must include a `Returns:` section** when `mcp_definition` is inferred. Reason: the MCP client only sees the tool description, so an inferred tool is required to spell out what it returns in that text. The Portuguese variants `Retorna:` and `Retorno:` are also accepted (case-insensitive regex match on any line of the docstring).

Defining an inferred endpoint without that section raises `TypeError` at class-definition time. The requirement does **not** apply to a hand-written `mcp_definition`.

Example of a valid docstring:

```python
def callback(self, ...):
    """One-line summary.

    Returns: what the tool returns.
    """
```

### 11.3 Annotating parameters with Annotated

The type and description of each parameter come from the `typing.Annotated` annotation:

```python
from typing import Annotated, Optional

def callback(
    self,
    device_id: Annotated[int, "Device id (1-5)"],
    device_id_list: Annotated[Optional[list[int]], "Subset of devices; omit for the whole fleet"] = None,
    days_window: Annotated[int, "How many days back to look"] = 7,
) -> dict:
    ...
```

Python-to-JSON-Schema type mapping rules:

| Python annotation | Generated JSON Schema |
|---|---|
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `list[T]` / `List[T]` | `{"type": "array", "items": <schema of T>}` |
| `dict` / `Dict` | `{"type": "object"}` |
| No annotation or unknown type | `{"type": "string"}` (permissive fallback) |

Additional behavior:
- `Annotated[T, "text"]` extracts `T` as the type and the first string metadata item as the `description`.
- `Optional[X]` (or `X | None`) is reduced to `X` for schema purposes.
- A parameter with a default value carries that value under the `"default"` key; without a default, it is treated as required (no `"default"` key).

### 11.4 Disabling an endpoint

```python
class GetProductEndpoint(Endpoint):
    disabled = True   # skips auto-registration; can still be instantiated manually
    ...
```

### 11.5 Abstract base classes

Classes that do not declare all required attributes are never auto-registered. This allows creating shared bases.

```python
class BaseAuthEndpoint(Endpoint):
    method = "POST"
    def callback(self, **kwargs): ...
# not registered: url is missing

class GetUserEndpoint(BaseAuthEndpoint):
    url = "/api/get-user"
    def callback(self, user_id: str) -> dict: ...
# registered automatically: url, method, and callback all present
```

### 11.6 The sync/async contract

Both synchronous and asynchronous callbacks are supported; restmcp detects and handles each case. The contract is identical for REST and MCP:

- A **synchronous** callback runs in a thread pool, so blocking work (synchronous DB driver, `requests`, file I/O) never stalls the event loop. Writing your `Repository`/`DataSource` synchronously is the simple, correct default.
- An **asynchronous** callback is awaited directly. Inside it, keep the I/O asynchronous (`httpx`, an async DB driver): calling blocking code from inside an async callback stalls the loop, because it is not moved to a thread.

Rule of thumb: synchronous from top to bottom, or asynchronous from top to bottom. Do not place blocking calls inside an `async def` callback.

```python
# sync: runs in a thread pool, does not block the event loop
def callback(self, product_id: str) -> dict:
    return requests.get(f"https://api.example.com/products/{product_id}").json()

# async: awaited directly; use asyncio.gather for parallel I/O
async def callback(self, product_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://api.example.com/products/{product_id}")
        return r.json()
```

### 11.7 Response format

Success:

```json
{ "tool": "get_product", "result": { }, "success": true }
```

Error:

```json
{ "tool": "get_product", "error": "not found", "error_type": "NotFoundError", "success": false }
```

REST and MCP share one validation engine: `mcp_definition` is compiled to a pydantic model (`restmcp/schema.py: build_arg_model`), and both transports validate against it, so they never diverge. Parameters are accepted from the query string and/or the JSON body (body wins on conflicts). Coercion is lax — `"5"`, `5.0` and `"5.0"` all become integer `5`, and boolean fields accept pydantic's lax inputs (`1`/`0`, `"on"`/`"off"`, `"yes"`/`"no"`, `"true"`/`"false"`) — with one deliberate guard: a boolean is rejected where a number is expected. Every declared property is passed to the callback (defaults included), so the callback signature must accept them all — checked at registration. Declared defaults are validated and coerced at registration; an explicit `null` is accepted only when the property's default is `null`. Parameter names must be valid Python identifiers and must not start with `_` or `model_` (registration error otherwise). An unknown key in the JSON body is a `ValidationError` (HTTP 400); unknown keys in the query string are ignored. A missing required parameter (a property with no `default`) or a non-object body are also 400. A body that is present but is not valid JSON is a `ValidationError` (HTTP 400) since 0.5.0 — it is no longer silently treated as empty; an absent/empty body remains tolerated (query-string-only calls). Bodies above the ceiling (`MAX_BODY_BYTES`, default 1 MiB, or the endpoint's `max_body_bytes`) are HTTP 413 before buffering. Any other exception becomes HTTP 500 with a generic message (the traceback goes to the server log, never the response).

### 11.8 Choosing the transport (expose) — 0.3.0+

`expose` selects which transports serve the endpoint:

```python
class PurgeReadingsEndpoint(Endpoint):
    expose = "rest"   # "rest" | "mcp" | "both" (default)
    ...
```

- `"rest"` — the HTTP route exists, but the tool is absent from the `/mcp/tools`
  catalog **and** from the MCP server itself. Use it for endpoints an agent must
  not even see: write/destructive actions, binary downloads. This is a
  structural guarantee, not a permission check — the tool does not exist on the
  MCP side.
- `"mcp"` — the tool exists for agents, but no public HTTP route is registered.
- `"both"` — the default; identical to pre-0.3.0 behavior.

An invalid value raises `TypeError` at class-definition time. The filter is a
single predicate (`restmcp.rest.serves_mcp`), consumed by both the catalog and
`Server.mcp_handlers`, so the two can never disagree. See
`examples/telemetry/endpoints/purge_readings.py` for a worked example.

### 11.9 OpenAPI schemas (0.3.0 request, 0.4.0 response)

`/openapi.json` documents every operation from the same `mcp_definition` that
the MCP side publishes — REST and OpenAPI cannot drift:

- **Request** (0.3.0): `POST/PUT/PATCH` get a `requestBody` schema; other
  methods get query `parameters`. `operationId` is the tool name and
  `description` is the tool description. `required` mirrors validation (a
  property without a `default` key); `additionalProperties: false` documents
  the extra-key rejection.
- **Response** (0.4.0): declare `mcp_definition["returns"]` as the JSON Schema
  of the callback's return value — the same slot the `/mcp/tools` catalog
  publishes. The `200` response documents the `{tool, result, success}`
  envelope with `result` typed by it; when `returns` is not declared, `result`
  stays open but the envelope itself is still typed. Errors are documented once
  under `default` with the error envelope
  (`{tool, error, success, error_type}`). A non-dict `returns` raises
  `TypeError` at class-definition time.

Generated clients (`openapi-typescript`, `openapi-python-client`) therefore get
full request/response types: a renamed response field becomes a codegen diff
instead of silently empty client data.

### 11.10 Success status code (`success_code`) — 0.6.0+

The HTTP code of the success envelope is a class-level declaration, in the
same idiom as `expose`/`max_body_bytes`/`required_scope`:

```python
class StartRunEndpoint(Endpoint):
    success_code = 202     # default 200; nothing changes for existing endpoints
```

- One declaration feeds BOTH the `JSONResponse` and the OpenAPI document
  (`"202"` replaces the `"200"` key), so a frozen contract cannot disagree
  with the server.
- Validated at class definition: int in 200..299; **204 is rejected** (No
  Content forbids a body; the `{tool, result, success}` envelope always has
  one).
- Errors ignore it — their code comes from the exception class. The complete
  rule of thumb: **error code = exception type, success code = endpoint
  declaration.**
- MCP is unaffected: HTTP status codes do not exist on that transport, so any
  `expose` mode may declare a custom code.

### 11.11 Raw responses (`raw_response`) — 0.6.0+

The FastAPI escape hatch for responses that do not fit the envelope — file
downloads, redirects, conditional codes, custom headers. Three locks:

```python
class ExportCsvEndpoint(Endpoint):
    expose = "rest"        # lock 1: REQUIRED — raw has no MCP representation
    raw_response = True    # lock 2: opt-in declared, never inferred
    ...
    def callback(self, device_id):
        return PlainTextResponse(csv, media_type="text/csv",
                                 headers={"content-disposition": "attachment"})
```

1. `raw_response=True` with `expose="both"`/`"mcp"` raises at class definition.
   Combining it with an explicit `success_code` also raises — in raw mode the
   `Response` object owns the status.
2. A callback returning a Starlette `Response` WITHOUT the flag is a
   programming error (500 with a pointed message in the log); declared raw but
   returning plain data errors symmetrically. No silent dual mode.
3. Success only: exceptions raised in a raw endpoint still produce the
   standard error envelope with the exception's `status_code` — clients keep
   one error format. The request-side pipeline (auth, scopes, body limit,
   parameter validation from `mcp_definition`) applies unchanged.

OpenAPI: a raw operation documents a single honest `default` ("code, headers
and body defined by the endpoint; errors use the standard error envelope") —
FastAPI's automatic success block is pruned for these routes by the
`openapi()` override installed in `RestApp`.

---

## 12. Server

Singleton that serves the REST layer (FastAPI/uvicorn) and the MCP protocol (FastMCP) from the same code. The recommended entry point is `asgi_app()`, which mounts both.

```python
import uvicorn
from restmcp import Server, autodiscover

autodiscover("endpoints")  # imports each endpoint module, registering all of them

app = Server.get_instance().asgi_app()  # REST at "/", MCP at "/mcp-protocol/"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Main methods:

| Method | Behavior |
|---|---|
| `asgi_app(mcp_path, transport, public_paths)` | Returns a single ASGI app serving REST at `/` and MCP at `mcp_path`. Holds the FastMCP lifespan in the parent app (avoids the "Task group is not initialized" error). If `AUTH_API_KEY` is set, it wraps everything in the auth middleware. |
| `start(host, port, reload)` | Starts only the REST application via uvicorn (no MCP). `reload=True` raises `ValueError` — uvicorn needs an import string for reload; run `uvicorn main:app --reload` instead. |
| `get_mcp()` | Returns the raw FastMCP instance (escape hatch for advanced use). Memoized. |
| `get_instance()` | Returns the Server singleton. |

Parameters of `asgi_app()`:

| Parameter | Default | Description |
|---|---|---|
| `mcp_path` | `/mcp-protocol` | Exact path where the MCP endpoint is served (MCP clients connect there). |
| `transport` | `http` | MCP transport: `http` (Streamable HTTP, fastmcp 3.x default), `streamable-http` (fastmcp 2.x alias), or `sse`. |
| `public_paths` | `("/health", "/mcp/tools")` | Routes exempt from authentication when `AUTH_API_KEY` is set. |

`asgi_app()` is idempotent: `get_mcp()` memoizes the FastMCP instance, so calling it more than once reuses the same MCP server.

Important: do **not** call `server.app.mount(...)` directly to mount MCP; that raises "Task group is not initialized" on the first MCP request. Always use `asgi_app()`.

---

## 13. REST layer and default routes

The REST application is a FastAPI with configurable CORS and default routes. CORS origins come from the `CORS_ORIGINS` variable (comma-separated). Since 0.5.0 the safe default is **deny**: absent or effectively-empty values add no CORS middleware (cross-origin browser requests are refused) and a warning is logged; set `CORS_ORIGINS='*'` explicitly to allow any origin (the pre-0.5.0 default).

Built-in routes:

| Route | Method | Authentication | Response |
|---|---|---|---|
| `/health` | GET | No | `{"status": "healthy", "timestamp": "<ISO 8601>"}` |
| `/mcp/tools` | GET | No | Tool catalog: list of `{name, description, parameters, returns}`, plus `server` and `version`. A definition without `parameters` is listed with `{"properties": {}}`. Lists only the MCP surface — endpoints with `expose = "rest"` are omitted (11.8). |
| `/mcp/tools/<name>` | POST | Yes (if `AUTH_API_KEY` set) | Executes the corresponding tool. |
| User endpoints | per `method` | Yes (if `AUTH_API_KEY` set) | Envelope `{tool, result, success}`. |

Important note about path-based authentication: `/mcp/tools` (the catalog) is public by exact match, but `/mcp/tools/<name>` (each tool's execution) remains protected. Exposing the catalog does not expose execution.

The `/mcp/tools` route returns the `version` field read from the installed package metadata (`importlib.metadata.version("restmcp")`); useful to confirm which version is in production.

---

## 14. MCP layer

The MCP server is built by the `McpApp` class, which creates a `FastMCP("restmcp")` and registers each handler as a tool. Only handlers on the MCP surface participate (`Server.mcp_handlers` — endpoints with `expose = "rest"` are excluded, see 11.8). For each endpoint, restmcp dynamically builds a typed wrapper function from the `mcp_definition`:

- The JSON type of each property is mapped to the Python type (`string` to `str`, `integer` to `int`, `number` to `float`, `boolean` to `bool`, `object` to `dict`, `array` to `List[item]`).
- A property whose `default` is `None` becomes `Optional[...]`.
- Each parameter is exposed as keyword-only, with the description embedded via `pydantic.Field`.
- The async wrapper invokes the same `run_callback`, keeping the sync/async contract identical to REST.

The function name (`__name__`), the documentation (`__doc__`, equal to the description), and the signature (`__signature__`) are set from the `mcp_definition`, so the MCP client sees the tool correctly typed and described.

---

## 15. Authentication

Since 0.5.0, `AUTH_API_KEY` entries accept `name:key:scope` (scope = `+`-joined
set, e.g. `read+write`) alongside the plain `key` form (full scope). The
matched principal `{"name", "scopes"}` is published as `request.state.auth` and
via the `restmcp.auth.current_auth` contextvar — visible in sync callbacks
(run_callback copies the context into the worker thread). This holds on BOTH
transports: over REST and over an MCP `tools/call` served by `asgi_app()`
(FastMCP runs the tool inside the request task, where `AuthMiddleware` set the
contextvar) — pinned by `tests/test_auth_mcp_identity.py` and shown in
`examples/telemetry/endpoints/whoami.py`. An `Endpoint` may
declare `required_scope = "write"`: enforced before the callback on the REST
path, returning 403 with `error_type: ForbiddenError`. Original section:


Authentication is via Bearer token, enabled only when the environment variable `AUTH_API_KEY` is defined. When absent, all routes are open.

How it works:
- The client sends the header `Authorization: Bearer <token>`.
- The token is compared, with `hmac.compare_digest` (constant-time comparison), against the configured keys.
- Multiple keys are supported, comma-separated in `AUTH_API_KEY`.
- Routes in `public_paths` (default `/health` and `/mcp/tools`) and paths under `/.well-known/` (MCP OAuth discovery) remain public.
- **CORS preflight passes through auth** (0.5.1): a request that is strictly a preflight (`OPTIONS` + `Access-Control-Request-Method` header) is exempt from authentication, because the browser never sends `Authorization` on preflights (CORS spec) — blocking it would 401 before `CORSMiddleware` could answer, killing every cross-origin call even with a valid token. A bare `OPTIONS` gets no free pass, and the actual request still authenticates.

There are two complementary protection layers:
- In REST, each endpoint route gets an authentication dependency (`_auth_dependency`) that responds 401 without a valid token.
- In `asgi_app()`, a pure-ASGI middleware (`AuthMiddleware`) wraps both REST and the mounted MCP, without buffering SSE.

```python
# protects REST and MCP; multiple keys comma-separated
# export AUTH_API_KEY="sk_key_1,sk_key_2"
```

---

## 16. Exceptions

Exceptions raised inside the `callback` are caught by the `Endpoint` and converted to HTTP responses automatically.

```mermaid
graph TD
    RestMCPException --> ValidationError["ValidationError (HTTP 400)"]
    RestMCPException --> NotFoundError["NotFoundError (HTTP 404)"]
```

**Explanation:** `RestMCPException` is the base, carrying a message and a `status_code`. `ValidationError` sets status 400 (invalid request) and `NotFoundError` sets status 404 (resource not found). When you raise one of these inside the callback, the `Endpoint` responds with the correct status and the error envelope. Exceptions that do not derive from `RestMCPException` result in HTTP 500 with `error_type` "InternalServerError".

```python
from restmcp import ValidationError, NotFoundError

raise ValidationError("product_id is required")  # HTTP 400
raise NotFoundError("Product not found")          # HTTP 404
```

---

## 17. Method cache

The `cached_method` decorator memoizes a method's return value for a time window (TTL), with a bounded store.

```python
from restmcp import cached_method

class BatteryHealthService(Service):
    readings = ReadingRepository()

    @cached_method(ttl=30)
    def fleet_report(self, device_id_list: list[int] | None = None) -> dict:
        ...
```

Parameters and behavior:

| Aspect | Detail |
|---|---|
| `ttl` | Seconds of validity per entry. After the TTL, the entry is ignored on read and removed on the next write. |
| `maxsize` | Maximum live entries per decorated method (default 128). When exceeded, the oldest entry is dropped (FIFO). |
| Cache key | Built from `(class, repr(args), repr(sorted kwargs))`. Works with non-hashable arguments such as `list` and `dict`. |
| Thread-safety | Yes; uses double-checked locking on the write path; the read is a single dict lookup. |
| Clock | Monotonic, immune to wall-clock adjustments. |

Important limitation: the key is derived from `repr()`. Use the cache only with plain-data arguments (str, int, float, bool, None, and lists/dicts of those). Do not cache methods whose arguments are rich objects without a value-based `__repr__`: two distinct objects with the same default repr ("<Foo at 0x...>") would collide, and a repr that includes the memory address would never hit.

---

## 18. Endpoint auto-discovery

The `autodiscover` function imports all public modules of a package, which triggers the auto-registration of each `Endpoint`.

```python
from restmcp import autodiscover
autodiscover("endpoints")
```

Behavior:
- Imports each module of the given package; importing the module is what runs the class body and registers the endpoint on the `Server`.
- Modules whose name starts with `_` are skipped.
- Raises `ValueError` if the argument is not a package (no `__path__`).

In practice: just add a new `.py` file to the `endpoints/` folder and it goes live on the next start, with no import list to maintain.

---

## 19. Logger

`Logger` is a thin wrapper over Python's `logging` module.

```python
from restmcp import Logger
log = Logger("my_module")
log.info("message")
log.warning("warning")
log.error("error")
log.debug("detail")
```

The log level is configurable via the `LOG_LEVEL` variable (default `INFO`; accepted values `DEBUG`, `INFO`, `WARNING`, `ERROR`). The format includes timestamp, level, and logger name.

---

## 20. Serialization

Values returned by callbacks are serialized with FastAPI's `jsonable_encoder`:

- `datetime` becomes an ISO 8601 string.
- `Decimal` becomes a string.
- Pydantic models (including `Entity`) become dicts.

The conversion is automatic: you can return an `Entity` or a `datetime` directly from the callback. To customize an entity's output format, override `serialize()` on the `Entity`.

Watch out for typed parameters: a parameter declared with `{"type": "string", "format": "date-time"}` arrives at the callback as a **string**; convert it to `datetime` if needed before use.

---

## 21. Environment variables

| Variable | Default | Description |
|---|---|---|
| `AUTH_API_KEY` | (disabled) | Bearer token. Multiple keys comma-separated. When absent, authentication is off. |
| `CORS_ORIGINS` | `*` | Allowed CORS origins. Multiple values comma-separated. |
| `LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

---

## 22. Auxiliary types

The `McpDefinition` type is a `TypedDict` that describes the structure of the tool definition dictionary, useful for those who write `mcp_definition` by hand:

```python
from restmcp import McpDefinition

mcp_definition: McpDefinition = {
    "name": "get_product",            # required
    "description": "Get a product.",  # required
    "parameters": {                   # optional
        "properties": {
            "product_id": {"type": "string", "description": "Product ID"},
        }
    },
    "returns": {                      # optional
        "type": "object",
        "description": "The product.",
    },
}
```

Validation of a hand-written `mcp_definition` (performed in `_validate_mcp_definition`):
- Must be a dict.
- `name` and `description` must be non-empty strings.
- `parameters`, if present, must be a dict; `parameters["properties"]`, if present, must be a dict.

---

## 23. Complete example (telemetry)

Telemetry diagnostics server, no database (in-memory DataSource). Demonstrates the five layers and the main features.

### 23.1 In-memory DataSource

```python
import datetime as dt
import random
from restmcp import DataSource

_FLEET = {
    1: {"device_name": "north-gate-sensor", "firmware": "2.4.1"},
    2: {"device_name": "pump-station-a", "firmware": "2.4.1"},
}

class TelemetryDataSource(DataSource):
    def known_device_ids(self) -> list[int]:
        return sorted(_FLEET)

    def fetch_readings(self, device_id_list, since, until) -> list[dict]:
        ids = device_id_list or self.known_device_ids()
        rows = []
        day = since.date()
        while day <= until.date():
            for device_id in ids:
                if device_id in _FLEET:
                    rng = random.Random(f"{device_id}-{day.isoformat()}")
                    rows.append({
                        "device_id": device_id,
                        "device_name": _FLEET[device_id]["device_name"],
                        "firmware": _FLEET[device_id]["firmware"],
                        "battery_level": round(max(0.0, min(100.0, 80 + rng.uniform(-8, 4))), 1),
                        "signal_dbm": rng.randint(-110, -60),
                        "recorded_at": dt.datetime.combine(day, dt.time(hour=rng.randint(0, 23))),
                    })
            day += dt.timedelta(days=1)
        return rows
```

### 23.2 Endpoint with inferred schema and optional parameters

```python
from typing import Annotated, Optional
from restmcp import Endpoint, ValidationError
from services.battery import BatteryHealthService
from utils.dates import coerce_reference_date

class CheckBatteryEndpoint(Endpoint):
    url = "/api/check-battery"
    method = "POST"

    def callback(
        self,
        device_id_list: Annotated[Optional[list[int]], "Devices to inspect; omit for the whole fleet"] = None,
        reference_date: Annotated[Optional[str], "Window end (ISO 8601); defaults to now"] = None,
        days_window: Annotated[int, "How many days back to look"] = 7,
    ) -> dict:
        """Group devices by battery status within a time window.

        Returns: a map of battery status -> list of device ids.
        """
        if days_window <= 0:
            raise ValidationError("days_window must be positive")
        ref = coerce_reference_date(reference_date)
        return BatteryHealthService().battery_map(
            device_id_list=device_id_list,
            reference_date=ref,
            days_window=days_window,
        )
```

Notes from the example:
- The tool name is inferred as `check_battery` (class without the `Endpoint` suffix, in snake_case).
- The description is the full docstring, which includes the required `Returns:` section.
- `reference_date` arrives as a string (date-time format) and is converted before use.

### 23.3 main.py

```python
import os
import uvicorn
from restmcp import Server, autodiscover

autodiscover("endpoints")
app = Server.get_instance().asgi_app(mcp_path="/mcp-protocol")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
```

### 23.4 Test calls

```bash
curl http://localhost:8000/health
curl http://localhost:8000/mcp/tools
curl -X POST http://localhost:8000/api/check-battery \
  -H 'content-type: application/json' -d '{}'
```

MCP clients connect to `http://localhost:8000/mcp-protocol`.

---

## 24. Testing with dependency injection

Dependency injection at each layer lets you replace the real `DataSource` with a fake, with no infrastructure.

```python
from restmcp import DataSource
from repositories.product import ProductRepository
from services.product import GetProductService

class FakeProductApiDataSource(DataSource):
    async def fetch(self, product_id: str) -> dict:
        return {"id": product_id, "name": "Test Widget", "price": 1.99}

def test_get_product():
    svc = GetProductService(repo=ProductRepository(data_source=FakeProductApiDataSource()))
    result = svc.execute(product_id="1")
    assert result["name"] == "Test Widget"
```

The `Service` accepts the `repo=...` override; the `Repository` accepts the `data_source=...` override. Because each layer isolates its dependency by copy, tests do not leak state between each other.

---

## 25. Production checklist

- **Running REST and MCP together:** use `app = server.asgi_app()`, which mounts both and wires the FastMCP lifespan. Do not use `server.app.mount(...)` directly.
- **Authentication:** set `AUTH_API_KEY` (Bearer). `asgi_app()` protects REST and the mounted MCP; `/health` and `/mcp/tools` stay public. Multiple keys comma-separated.
- **Serialization:** callback return values are serialized with `jsonable_encoder` (datetime to ISO 8601, Decimal to string, Pydantic models to dict). Override `serialize()` per entity when needed.
- **Typed parameters:** a `{"type": "string", "format": "date-time"}` parameter arrives as a string; convert it to datetime.
- **Caching:** wrap expensive Service methods with `@cached_method(ttl=seconds, maxsize=128)`. The key comes from the arguments (via repr), so it works with list/dict arguments. The store is bounded and self-purging. Cache plain data, not rich objects.
- **Folders vs suffixes:** only class suffixes are mandatory; folder names are free.
- **Dependencies:** `fastmcp` 3.x is recommended (the package requires `fastmcp>=2.0`; 3.x provides full Streamable HTTP support).

---

## 26. Common errors and troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `TypeError` mentioning a suffix at import | Class name without the required suffix (`*Endpoint`, `*Service`, etc.). | Rename the class to end with the correct suffix. |
| `TypeError` requiring a `Returns:` section when defining an Endpoint | Inferred `mcp_definition` without a `Returns:`/`Retorna:`/`Retorno:` section in the callback docstring. | Add the return section to the docstring, or define `mcp_definition` explicitly. |
| "Task group is not initialized" on the first MCP request | MCP mounted manually with `server.app.mount(...)`. | Use `server.asgi_app()`, which wires the FastMCP lifespan. |
| HTTP 401 on all protected routes | `AUTH_API_KEY` set and token missing or incorrect in the header. | Send `Authorization: Bearer <key>` with a valid key. |
| Endpoint not showing up in `/mcp/tools` | Missing `autodiscover("endpoints")`, or the file starts with `_`, or `url`/`method`/`callback` missing, or `disabled = True`. | Ensure autodiscover, the file name, and the required attributes. |
| `ValidationError` "Extra inputs are not permitted" | The JSON body contains a key not present in the schema properties. | Send only the parameters declared in the callback. |
| `TypeError` "invalid parameter name" at import | A property name starts with `_`/`model_` or is not a valid identifier. | Rename the parameter (pydantic reserves those forms). |
| Event loop stalling under load | A blocking call inside an `async def` callback. | Use async I/O in the async callback, or make the callback synchronous (runs in a thread pool). |

---

## 27. Quick reference of the public API

Symbols exported by `restmcp` (via `from restmcp import ...`):

| Symbol | Kind | Use |
|---|---|---|
| `DataSource` | base class | Connection to an external source. Suffix `*DataSource`. |
| `Entity` | base class | Pydantic domain model. Suffix `*Entity`. |
| `Repository` | base class | Data access. Suffix `*Repository`. Implements `get()`. |
| `Service` | base class | Business logic. Suffix `*Service`. |
| `Endpoint` | base class | HTTP route and MCP tool. Suffix `*Endpoint`. |
| `Server` | singleton | Composes REST and MCP. `get_instance()`, `asgi_app()`, `start()`, `get_mcp()`. |
| `Logger` | class | Logging wrapper. |
| `ValidationError` | exception | HTTP 400. |
| `NotFoundError` | exception | HTTP 404. |
| `McpDefinition` | TypedDict | Structure of the tool definition dictionary. |
| `cached_method` | decorator | Memoization with TTL and maxsize. |
| `autodiscover` | function | Imports a package's modules to register endpoints. |

---

## 28. Example catalog by scenario

This section collects short, focused recipes, one per common need. All examples apply to restmcp 0.4.1.

### 28.1 Minimal endpoint with one required parameter

```python
from typing import Annotated
from restmcp import Endpoint
from services.product import GetProductService

class GetProductEndpoint(Endpoint):
    url = "/api/get-product"
    method = "POST"

    def callback(self, product_id: Annotated[str, "Product ID"]) -> dict:
        """Get a product by ID.

        Returns: product object (id, name, price).
        """
        return GetProductService().execute(product_id)
```

### 28.2 Optional parameters with default values

```python
from typing import Annotated, Optional

class CheckBatteryEndpoint(Endpoint):
    url = "/api/check-battery"
    method = "POST"

    def callback(
        self,
        reference_date: Annotated[Optional[str], "Window end (ISO 8601); default now"] = None,
        days_window: Annotated[int, "How many days back to look"] = 7,
    ) -> dict:
        """Group devices by battery status within the window.

        Returns: map of status -> list of device_ids.
        """
        ...
```

### 28.3 Integer list parameter

```python
from typing import Annotated, Optional

class FleetReportEndpoint(Endpoint):
    url = "/api/fleet-report"
    method = "POST"

    def callback(
        self,
        device_id_list: Annotated[Optional[list[int]], "Subset; omit for the whole fleet"] = None,
    ) -> dict:
        """Fleet-wide battery rollup.

        Returns: aggregate stats (total, average, range).
        """
        ...
```

### 28.4 String list parameter (category filters)

```python
from typing import Annotated, Optional

class GetPicsEndpoint(Endpoint):
    url = "/api/get-pics"
    method = "POST"

    def callback(
        self,
        status_list: Annotated[Optional[list[str]], "Status filter: online, offline, standby"] = None,
        model_list: Annotated[Optional[list[str]], "Model filter: lora, cellular, wifi"] = None,
    ) -> dict:
        """List devices filtered by status and model.

        Returns: object grouped by model and status.
        """
        ...
```

### 28.5 Boolean parameter

```python
from typing import Annotated

class GetPicsEndpoint(Endpoint):
    url = "/api/get-pics"
    method = "POST"

    def callback(self, visible: Annotated[bool, "If True, only visible devices"] = True) -> dict:
        """List devices.

        Returns: list of devices according to visibility.
        """
        ...
```

### 28.6 Endpoint with no parameters

```python
class PingEndpoint(Endpoint):
    url = "/api/ping"
    method = "POST"

    def callback(self) -> dict:
        """Check whether the service is alive.

        Returns: object with a fixed status field.
        """
        return {"status": "ok"}
```

### 28.7 Async callback with httpx

```python
import httpx
from typing import Annotated

class GetWeatherEndpoint(Endpoint):
    url = "/api/get-weather"
    method = "POST"

    async def callback(self, city: Annotated[str, "City name"]) -> dict:
        """Current weather for a city.

        Returns: object with temperature and condition.
        """
        async with httpx.AsyncClient() as client:
            r = await client.get(f"https://api.example.com/weather/{city}")
            r.raise_for_status()
            return r.json()
```

### 28.8 Sync callback with requests

```python
import requests
from typing import Annotated

class GetWeatherEndpoint(Endpoint):
    url = "/api/get-weather"
    method = "POST"

    def callback(self, city: Annotated[str, "City name"]) -> dict:
        """Current weather for a city.

        Returns: object with temperature and condition.
        """
        # sync callback runs in a thread pool; blocking requests is safe here
        return requests.get(f"https://api.example.com/weather/{city}").json()
```

### 28.9 Input validation with ValidationError

```python
from restmcp import Endpoint, ValidationError
from typing import Annotated

class CheckBatteryEndpoint(Endpoint):
    url = "/api/check-battery"
    method = "POST"

    def callback(self, days_window: Annotated[int, "Days back"] = 7) -> dict:
        """Battery diagnostics.

        Returns: map of status -> device_ids.
        """
        if days_window <= 0:
            raise ValidationError("days_window must be positive")  # becomes HTTP 400
        ...
```

### 28.10 Resource not found with NotFoundError

```python
from restmcp import Service, NotFoundError
from repositories.reading import ReadingRepository

class BatteryHealthService(Service):
    readings = ReadingRepository()

    def latest_reading(self, device_id: int):
        items = self.readings.get(device_id_list=[device_id])
        if not items:
            raise NotFoundError(f"No telemetry for device {device_id}")  # HTTP 404
        return max(items, key=lambda r: r.recorded_at)
```

### 28.11 Explicit mcp_definition (manual override)

When you want to control the schema by hand, declare `mcp_definition`. In that case the `Returns:` docstring requirement does not apply.

```python
class LegacyEndpoint(Endpoint):
    mcp_definition = {
        "name": "legacy_tool",
        "description": "Tool with a hand-written schema.",
        "parameters": {
            "properties": {
                "x": {"type": "string", "description": "Some value"},
            }
        },
    }
    url = "/api/legacy"
    method = "POST"

    def callback(self, x: str) -> dict:
        return {"x": x}
```

### 28.12 Setting the tool name explicitly

```python
class GetProductEndpoint(Endpoint):
    name = "search_products"          # overrides the inferred name (get_product)
    url = "/api/get-product"
    method = "POST"

    def callback(self, product_id: Annotated[str, "ID"]) -> dict:
        """Search a product.

        Returns: the product.
        """
        ...
```

### 28.13 Disabled endpoint

```python
class GetProductEndpoint(Endpoint):
    disabled = True   # skips auto-registration
    url = "/api/get-product"
    method = "POST"
    def callback(self, product_id: str) -> dict: ...
```

### 28.14 Abstract base and concrete subclasses

```python
class BaseAuthEndpoint(Endpoint):
    method = "POST"
    def callback(self, **kwargs): ...
# not registered: url is missing

class GetUserEndpoint(BaseAuthEndpoint):
    url = "/api/get-user"
    def callback(self, user_id: Annotated[str, "User ID"]) -> dict:
        """Get a user.

        Returns: the user.
        """
        ...
# registered: url, method, and callback present
```

### 28.15 Async HTTP DataSource

```python
import httpx
from restmcp import DataSource

class ProductApiDataSource(DataSource):
    base_url = "https://api.example.com"

    async def fetch(self, product_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self.base_url}/products/{product_id}")
            r.raise_for_status()
            return r.json()
```

### 28.16 Synchronous SQL DataSource

```python
import psycopg2
from restmcp import DataSource

class CropnetDataSource(DataSource):
    dsn = "postgresql://user:pass@host:5432/db"

    def make_query(self, sql: str, params: list) -> list[tuple]:
        # synchronous driver: safe because the sync callback runs in a thread pool
        with psycopg2.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
```

### 28.17 File DataSource (CSV)

```python
import csv
from restmcp import DataSource

class CatalogFileDataSource(DataSource):
    path = "data/catalog.csv"

    def read_all(self) -> list[dict]:
        with open(self.path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
```

### 28.18 Entity with validation and computed field

```python
import datetime as dt
from typing import Literal
from restmcp import Entity

class DeviceReadingEntity(Entity):
    device_id: int
    battery_level: float
    recorded_at: dt.datetime

    @property
    def status(self) -> Literal["healthy", "degraded", "critical"]:
        if self.battery_level >= 60:
            return "healthy"
        if self.battery_level >= 20:
            return "degraded"
        return "critical"
```

### 28.19 Nested Entity

```python
from restmcp import Entity

class AddressEntity(Entity):
    street: str
    city: str

class CustomerEntity(Entity):
    id: int
    name: str
    address: AddressEntity   # nested entity, validated by Pydantic
```

### 28.20 Synchronous Repository

```python
from restmcp import Repository
from datasources.catalog import CatalogFileDataSource
from entities.product import ProductEntity

class ProductRepository(Repository):
    data_source = CatalogFileDataSource()

    def get(self, product_id: str) -> ProductEntity:
        rows = self.data_source.read_all()
        row = next(r for r in rows if r["id"] == product_id)
        return ProductEntity(**row)
```

### 28.21 Asynchronous Repository

```python
from restmcp import Repository
from datasources.product_api import ProductApiDataSource
from entities.product import ProductEntity

class ProductRepository(Repository):
    data_source = ProductApiDataSource()

    async def get(self, product_id: str) -> ProductEntity:
        raw = await self.data_source.fetch(product_id)
        return ProductEntity(**raw)
```

### 28.22 Service with cached_method and a list argument

```python
from restmcp import Service, cached_method
from repositories.reading import ReadingRepository

class BatteryHealthService(Service):
    readings = ReadingRepository()

    @cached_method(ttl=30, maxsize=128)
    def fleet_report(self, device_id_list: list[int] | None = None) -> dict:
        # the cache key uses repr of the arguments, so the (non-hashable) list works
        mapping = self.battery_map(device_id_list=device_id_list)
        return {"by_status": mapping, "total": sum(len(v) for v in mapping.values())}
```

### 28.23 Service orchestrating multiple repositories

```python
from restmcp import Service
from repositories.product import ProductRepository
from repositories.inventory import InventoryRepository

class ProductDetailService(Service):
    products = ProductRepository()
    inventory = InventoryRepository()

    async def execute(self, product_id: str) -> dict:
        product = await self.products.get(product_id=product_id)
        stock = await self.inventory.get(product_id=product_id)
        data = product.model_dump()
        data["in_stock"] = stock.quantity > 0
        return data
```

### 28.24 Test injecting a fake DataSource

```python
from restmcp import DataSource
from repositories.product import ProductRepository
from services.product import GetProductService

class FakeProductApiDataSource(DataSource):
    async def fetch(self, product_id: str) -> dict:
        return {"id": product_id, "name": "Test Widget", "price": 1.99}

def test_get_product():
    svc = GetProductService(repo=ProductRepository(data_source=FakeProductApiDataSource()))
    result = svc.execute(product_id="1")
    assert result["name"] == "Test Widget"
```

### 28.25 Test injecting a fake Repository

```python
from unittest.mock import MagicMock
from services.product import GetProductService

def test_service_with_mock_repo():
    fake_repo = MagicMock()
    fake_repo.get.return_value.model_dump.return_value = {"id": "1", "name": "X"}
    svc = GetProductService(repo=fake_repo)
    assert svc.execute(product_id="1")["name"] == "X"
```

### 28.26 HTTP calls with and without authentication

```bash
# no auth (AUTH_API_KEY not set), or public routes
curl http://localhost:8000/health
curl http://localhost:8000/mcp/tools

# execute a tool without a token (protected route) -> HTTP 401
curl -X POST http://localhost:8000/api/get-product \
  -H 'content-type: application/json' -d '{"product_id": "1"}'

# execute a tool with a Bearer token
curl -X POST http://localhost:8000/api/get-product \
  -H 'authorization: Bearer sk_your_key' \
  -H 'content-type: application/json' \
  -d '{"product_id": "1"}'
```

### 28.27 asgi_app with custom MCP path and auth

```python
from restmcp import Server, autodiscover

autodiscover("endpoints")

app = Server.get_instance().asgi_app(
    mcp_path="/mcp-protocol",                 # where MCP clients connect
    transport="http",                         # Streamable HTTP (fastmcp 3.x default)
    public_paths=("/health", "/mcp/tools"),   # routes without auth
)
```

---

## 29. Inference examples: input and output

This section shows, side by side, a `callback` and the `mcp_definition` that restmcp infers from it. Useful to understand exactly how types, defaults, and the docstring become the tool schema.

### 29.1 Required parameter, no default

Input:

```python
class GetDeviceEndpoint(Endpoint):
    url = "/api/get-device"
    method = "POST"

    def callback(self, device_id: Annotated[int, "Device id (1-5)"]) -> dict:
        """Latest telemetry reading for one device.

        Returns: the device's most recent reading.
        """
        ...
```

Inferred output:

```json
{
  "name": "get_device",
  "description": "Latest telemetry reading for one device.\n\nReturns: the device's most recent reading.",
  "parameters": {
    "properties": {
      "device_id": { "type": "integer", "description": "Device id (1-5)" }
    }
  }
}
```

Note that `device_id` has no `"default"` key: with no default value, it is treated as required.

### 29.2 Optional list and integer with default

Input:

```python
def callback(
    self,
    device_id_list: Annotated[Optional[list[int]], "Subset; omit for the whole fleet"] = None,
    days_window: Annotated[int, "How many days back"] = 7,
) -> dict:
    """Group devices by status.

    Returns: map of status -> device_ids.
    """
    ...
```

Inferred output (properties):

```json
{
  "device_id_list": {
    "type": "array",
    "items": { "type": "integer" },
    "description": "Subset; omit for the whole fleet",
    "default": null
  },
  "days_window": {
    "type": "integer",
    "description": "How many days back",
    "default": 7
  }
}
```

`Optional[list[int]]` becomes an `array` of `integer`, and the default `None` appears as `"default": null`.

### 29.3 Name inferred from the class

| Class | Inferred tool name |
|---|---|
| `GetDeviceEndpoint` | `get_device` |
| `CheckBatteryEndpoint` | `check_battery` |
| `GetPicGapsEndpoint` | `get_pic_gaps` |
| `ListProductsEndpoint` | `list_products` |

The `Endpoint` suffix is removed and CamelCase is converted to snake_case. An explicit `name` class attribute, when present, takes priority over this rule.

---

## 30. Second complete example: product catalog via external API

A server that exposes a product fetched from an external HTTP API, using asynchronous callbacks end to end. Shows a different flavor from the telemetry example (which was synchronous and in-memory).

### 30.1 DataSource (async HTTP)

```python
# datasources/product_api.py
import httpx
from restmcp import DataSource

class ProductApiDataSource(DataSource):
    base_url = "https://api.example.com"

    async def fetch(self, product_id: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{self.base_url}/products/{product_id}")
            r.raise_for_status()
            return r.json()
```

### 30.2 Entity

```python
# entities/product.py
from restmcp import Entity

class ProductEntity(Entity):
    id: str
    name: str
    price: float
    currency: str = "USD"
```

### 30.3 Repository (async)

```python
# repositories/product.py
from restmcp import Repository
from datasources.product_api import ProductApiDataSource
from entities.product import ProductEntity

class ProductRepository(Repository):
    data_source = ProductApiDataSource()

    async def get(self, product_id: str) -> ProductEntity:
        raw = await self.data_source.fetch(product_id)
        return ProductEntity(**raw)
```

### 30.4 Service

```python
# services/product.py
from restmcp import Service, NotFoundError
from repositories.product import ProductRepository

class GetProductService(Service):
    products = ProductRepository()

    async def execute(self, product_id: str) -> dict:
        if not product_id:
            raise NotFoundError("product_id is required")
        product = await self.products.get(product_id=product_id)
        return product.model_dump()
```

### 30.5 Endpoint

```python
# endpoints/get_product.py
from typing import Annotated
from restmcp import Endpoint
from services.product import GetProductService

class GetProductEndpoint(Endpoint):
    url = "/api/get-product"
    method = "POST"

    async def callback(self, product_id: Annotated[str, "Product ID"]) -> dict:
        """Get a product by ID from an external API.

        Returns: product object with id, name, price, and currency.
        """
        return await GetProductService().execute(product_id)
```

### 30.6 main.py

```python
# main.py
import os
import uvicorn
from restmcp import Server, autodiscover

autodiscover("endpoints")
app = Server.get_instance().asgi_app(mcp_path="/mcp-protocol")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
```

### 30.7 Exercising the server

```bash
# REST
curl -X POST http://localhost:8000/api/get-product \
  -H 'content-type: application/json' -d '{"product_id": "1"}'

# response:
# {"tool": "get_product", "result": {"id": "1", "name": "...", "price": 9.9, "currency": "USD"}, "success": true}

# tool catalog
curl http://localhost:8000/mcp/tools

# MCP client connects to:
# http://localhost:8000/mcp-protocol
```

The whole chain is asynchronous: the `async def` callback is awaited directly, the `Service` and `Repository` use `await`, and the `DataSource` uses `httpx.AsyncClient`. This follows the "async from top to bottom" rule.

---

## 31. The sync/async contract in depth

restmcp accepts synchronous and asynchronous callbacks transparently, and the same contract applies to REST and MCP. This section details the behavior with examples, including what to do and what to avoid.

### 31.1 How restmcp decides

Internally, when executing a callback, restmcp checks whether it is a coroutine:

- If the callback is `async def` (a coroutine function), it is **awaited directly** (`await callback(...)`).
- If the callback is `def` (synchronous), it is run in a **thread pool** (`run_in_executor`), so blocking work does not stall the event loop.

The practical consequence is the golden rule: **synchronous from top to bottom, or asynchronous from top to bottom.** Do not mix blocking calls inside an `async def`.

### 31.2 Synchronous callback: blocking is safe

Because the synchronous callback runs in a separate thread, using blocking libraries (`requests`, synchronous DB drivers such as `psycopg2`, file reading) is correct and simple. It is the recommended default when you have no reason to use async.

```python
import requests
from typing import Annotated
from restmcp import Endpoint

class GetProductEndpoint(Endpoint):
    url = "/api/get-product"
    method = "POST"

    def callback(self, product_id: Annotated[str, "Product ID"]) -> dict:
        """Get a product (blocking HTTP client, runs in a thread pool).

        Returns: the product.
        """
        r = requests.get(f"https://api.example.com/products/{product_id}", timeout=10)
        r.raise_for_status()
        return r.json()
```

### 31.3 Asynchronous callback: keep the I/O async

An `async def` callback is awaited on the event loop. Inside it, use only async I/O (`httpx.AsyncClient`, async DB drivers, `asyncio`). That way the server handles many concurrent requests efficiently.

```python
import httpx
from typing import Annotated
from restmcp import Endpoint

class GetProductEndpoint(Endpoint):
    url = "/api/get-product"
    method = "POST"

    async def callback(self, product_id: Annotated[str, "Product ID"]) -> dict:
        """Get a product (async HTTP client).

        Returns: the product.
        """
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://api.example.com/products/{product_id}")
            r.raise_for_status()
            return r.json()
```

### 31.4 Parallel I/O with asyncio.gather

The biggest advantage of async appears when firing several I/O calls at the same time. Use `asyncio.gather` to wait on all of them in parallel instead of one after another.

```python
import asyncio
import httpx
from typing import Annotated
from restmcp import Endpoint

class GetProductBundleEndpoint(Endpoint):
    url = "/api/get-product-bundle"
    method = "POST"

    async def callback(self, product_ids: Annotated[list[str], "Product IDs"]) -> dict:
        """Fetch several products in parallel.

        Returns: object with the list of found products.
        """
        async with httpx.AsyncClient(timeout=10) as client:
            async def one(pid: str) -> dict:
                r = await client.get(f"https://api.example.com/products/{pid}")
                r.raise_for_status()
                return r.json()

            products = await asyncio.gather(*(one(pid) for pid in product_ids))
        return {"products": list(products)}
```

**Explanation:** `asyncio.gather(*tasks)` schedules all coroutines at once and returns when all complete. For N calls taking ~200 ms each, the total time is close to 200 ms (parallel), not N × 200 ms (sequential). This only works because the I/O is genuinely asynchronous.

### 31.5 End-to-end async chain

When the callback is asynchronous, keep `Service`, `Repository`, and `DataSource` asynchronous too, with `await` at each hop.

```python
# DataSource
class ProductApiDataSource(DataSource):
    async def fetch(self, product_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"https://api.example.com/products/{product_id}")
            return r.json()

# Repository
class ProductRepository(Repository):
    data_source = ProductApiDataSource()
    async def get(self, product_id: str) -> ProductEntity:
        raw = await self.data_source.fetch(product_id)
        return ProductEntity(**raw)

# Service
class GetProductService(Service):
    products = ProductRepository()
    async def execute(self, product_id: str) -> dict:
        product = await self.products.get(product_id=product_id)
        return product.model_dump()

# Endpoint
class GetProductEndpoint(Endpoint):
    url = "/api/get-product"
    method = "POST"
    async def callback(self, product_id: Annotated[str, "ID"]) -> dict:
        """Get a product.

        Returns: the product.
        """
        return await GetProductService().execute(product_id)
```

### 31.6 Anti-pattern: blocking inside an async callback

Calling blocking code inside an `async def` stalls the event loop, because that work is not moved to a thread. This degrades the concurrency of the entire server.

```python
import time
import requests

# WRONG: blocks the event loop
async def callback(self, product_id: str) -> dict:
    time.sleep(2)                                  # freezes the whole loop
    return requests.get(f"...{product_id}").json() # blocking client in async
```

To fix it, choose one of the two options:

```python
# OPTION A: make the callback synchronous (runs in a thread pool; blocking is ok)
def callback(self, product_id: str) -> dict:
    return requests.get(f"...{product_id}").json()

# OPTION B: keep it async and use async I/O
async def callback(self, product_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"...{product_id}")
        return r.json()
```

### 31.7 Decision table

| Situation | Use | Why |
|---|---|---|
| Synchronous DB driver (psycopg2), `requests`, file reading | `def` callback (synchronous) | Runs in a thread pool; blocking does not affect the event loop. |
| Async HTTP client (httpx async), async DB driver | `async def` callback | Awaited on the loop; high concurrency. |
| Several independent I/O calls at the same time | `async def` + `asyncio.gather` | Runs in parallel, reduces total latency. |
| Mixing blocking and async in the same callback | Avoid | Blocking inside `async def` stalls the loop. Standardize the whole chain. |

---

## 32. Summary

restmcp 0.4.1 turns annotated Python classes into MCP tools and REST endpoints simultaneously, with a five-layer architecture (DataSource, Entity, Repository, Service, Endpoint), auto-registration at class definition, dependency injection by isolated copy, and transparent support for synchronous and asynchronous callbacks. The MCP tool definition is inferred from the callback signature and docstring, requiring a `Returns:` section that describes the return value for the MCP client. A single `asgi_app()` serves REST and MCP with optional Bearer authentication, and the tool catalog is available at `/mcp/tools`.
