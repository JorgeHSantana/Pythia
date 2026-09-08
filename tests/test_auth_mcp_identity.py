"""Issues #15/#16 — the key's identity must reach the callback over the MCP
transport too, not just REST.

The suite proved the contextvar hop for REST (`test_auth_identity.py`) and for
`run_callback` in isolation (`test_body_and_context.py`), but never issued a
real `tools/call` through `asgi_app()`. That path depends on FastMCP running
the tool inside the request task (where `AuthMiddleware` set `current_auth`);
if a FastMCP upgrade moved tool execution to a lifespan task group, identity
would silently become None for every agent call. This pins it.
"""
import json

import pytest
from starlette.testclient import TestClient

from restmcp import Endpoint, Server
from restmcp.auth import current_auth

_H = {"Accept": "application/json, text/event-stream", "Authorization": "Bearer sk_1"}
_INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"}}}


def _who():
    p = current_auth.get()
    return {"who": p["name"] if p else None, "scopes": sorted(p["scopes"]) if p else []}


def _register():
    class WhoSyncEndpoint(Endpoint):
        mcp_definition = {"name": "who_sync", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/who-sync"
        method = "GET"

        def callback(self):
            return _who()

    class WhoAsyncEndpoint(Endpoint):
        mcp_definition = {"name": "who_async", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/who-async"
        method = "GET"

        async def callback(self):
            return _who()


def _call_tool(c, headers, name):
    r = c.post("/mcp-protocol/", headers=headers, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": name, "arguments": {}}})
    assert r.status_code == 200
    data = [l for l in r.text.splitlines() if l.startswith("data:")]
    payload = json.loads(data[-1][len("data:"):]) if data else r.json()
    return payload["result"]["structuredContent"]


@pytest.mark.parametrize("tool", ["who_sync", "who_async"])
def test_identity_reaches_callback_over_mcp(monkeypatch, tool):
    pytest.importorskip("fastmcp")
    monkeypatch.setenv("AUTH_API_KEY", "painel:sk_1:read")
    _register()
    app = Server.get_instance().asgi_app(mcp_path="/mcp-protocol")
    with TestClient(app) as c:
        r = c.post("/mcp-protocol/", json=_INIT, headers=_H)
        assert r.status_code == 200
        sid = r.headers.get("mcp-session-id")
        h = {**_H, **({"mcp-session-id": sid} if sid else {})}
        c.post("/mcp-protocol/", headers=h,
               json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert _call_tool(c, h, tool) == {"who": "painel", "scopes": ["read"]}
