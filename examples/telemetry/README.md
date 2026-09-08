# Telemetry diagnostics — a complete restmcp example

A runnable server that exposes the **same logic over REST and MCP** from one
codebase. It walks the full stack — `DataSource → Entity → Repository → Service
→ Endpoint` — and exercises every feature the framework offers, with **no
external database**: the DataSource fabricates a small, deterministic device
fleet in memory, so `python main.py` just works.

## What it demonstrates

| Feature | Where |
|---|---|
| `DataSource` (swap for a real DB later) | [datasources/telemetry.py](datasources/telemetry.py) |
| `Entity` + custom `serialize()` | [entities/reading.py](entities/reading.py) |
| `Repository` with dependency injection | [repositories/reading.py](repositories/reading.py) |
| `Service` orchestration | [services/battery.py](services/battery.py) |
| `cached_method(ttl=...)` (works with list args) | [services/battery.py](services/battery.py) |
| `Endpoint` auto-registration | [endpoints/](endpoints/) |
| Array params + manual ISO date coercion in the callback | [endpoints/check_battery.py](endpoints/check_battery.py) |
| Automatic `datetime` → ISO 8601 serialization | [endpoints/get_device.py](endpoints/get_device.py) |
| `expose = "rest"` (tool invisível ao MCP) + `returns` schema no OpenAPI | [endpoints/purge_readings.py](endpoints/purge_readings.py) |
| `success_code = 202` (aceito ≠ pronto; o OpenAPI documenta o código real) | [endpoints/recalibrate_fleet.py](endpoints/recalibrate_fleet.py) |
| `raw_response = True` (download CSV cru; erros seguem no envelope; exige `expose="rest"`) | [endpoints/export_readings.py](endpoints/export_readings.py) |
| `NotFoundError` / `ValidationError` → HTTP 404/400 | [endpoints/get_device.py](endpoints/get_device.py) |
| One ASGI app for REST **and** MCP via `asgi_app()` | [main.py](main.py) |
| Bearer auth over REST + MCP (`AUTH_API_KEY`) | [main.py](main.py) |
| Identidade da chave (`current_auth`) + `required_scope` — chega ao callback sync via REST **e** MCP | [endpoints/whoami.py](endpoints/whoami.py) |
| Dependency-injection testing | [test_telemetry.py](test_telemetry.py) |

## Run it

```bash
cd examples/telemetry
pip install -r requirements.txt
python main.py            # http://localhost:8000  (set PORT to change)
```

## Call it (REST)

```bash
# Public, no auth:
curl http://localhost:8000/health
curl http://localhost:8000/mcp/tools          # lists every tool/endpoint

# Latest reading for one device (datetime serialized to ISO 8601):
curl -X POST http://localhost:8000/api/get-device \
  -H 'content-type: application/json' -d '{"device_id": 3}'

# Whole fleet grouped by battery status:
curl -X POST http://localhost:8000/api/check-battery \
  -H 'content-type: application/json' -d '{}'

# A subset, within a window ending at a given instant (string is coerced):
curl -X POST http://localhost:8000/api/check-battery \
  -H 'content-type: application/json' \
  -d '{"device_id_list":[1,3,99],"reference_date":"2026-06-10T00:00:00Z","days_window":3}'

# Cached rollup — call twice within 30s, the server logs "computing" only once:
curl -X POST http://localhost:8000/api/fleet-report \
  -H 'content-type: application/json' -d '{}'

# 202 Accepted (success_code): the envelope carries a TICKET, not a result —
# watch the status line with -i:
curl -i -X POST http://localhost:8000/api/recalibrate-fleet \
  -H 'content-type: application/json' -d '{}'

# Raw CSV download (raw_response): no envelope — the body IS the file, with
# content-disposition. Invisible to MCP (expose="rest"):
curl -OJ "http://localhost:8000/api/export-readings?device_id=1"

# Error on a raw endpoint still uses the standard error envelope (lock 3):
curl "http://localhost:8000/api/export-readings?device_id=99"

# Who am I? (run with AUTH_API_KEY="painel:sk_read:read,campo:sk_full:read+write")
# The key's name/scopes reach the callback — same answer over MCP tools/call:
curl http://localhost:8000/api/whoami -H 'Authorization: Bearer sk_read'
```

Every enveloped response uses the framework shape (raw endpoints excepted —
their success is whatever `Response` they return; their **errors** still use
the error envelope):

```json
{ "tool": "check_battery", "result": { "...": [] }, "success": true }
```

## Call it (MCP)

MCP is served at **`http://localhost:8000/mcp-protocol/`** (note the trailing
slash). Any MCP client works; with the bundled `fastmcp`:

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://localhost:8000/mcp-protocol/") as c:
        print([t.name for t in await c.list_tools()])
        res = await c.call_tool("check_battery", {"device_id_list": [1, 3]})
        print(res.data)

asyncio.run(main())
```

## Turn on auth

```bash
AUTH_API_KEY=dev-secret python main.py
```

Now every route requires `Authorization: Bearer dev-secret` **except**
`/health` and `/mcp/tools`, which stay public. The MCP endpoint is protected
too. Multiple keys: `AUTH_API_KEY=key-a,key-b`. See [.env.example](.env.example).

## Test it

```bash
cd examples/telemetry
python -m pytest        # injects a fake DataSource — no server, no network
```

## Make it real

Replace [datasources/telemetry.py](datasources/telemetry.py) with a class that talks
to your actual database or API (it just has to return dicts). Nothing in the
Repository, Service, or Endpoint layers changes — that is the point of the
layering.
