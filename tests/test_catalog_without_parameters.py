"""`/mcp/tools` must not 500 because one hand-written mcp_definition omits
`parameters` — a shape `_validate_mcp_definition` explicitly accepts (and
`_openapi_params`/mcp.py already tolerate via `.get(...) or {}`)."""
from starlette.testclient import TestClient

from restmcp import Endpoint, Server


def test_catalog_tolerates_definition_without_parameters(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class NoParamsEndpoint(Endpoint):
        mcp_definition = {"name": "no_params", "description": "x"}
        url = "/api/no-params"
        method = "GET"

        def callback(self):
            return {"ok": True}

    with TestClient(server.app) as c:
        assert c.get("/api/no-params").json()["result"] == {"ok": True}
        r = c.get("/mcp/tools")
        assert r.status_code == 200
        tool = next(t for t in r.json()["tools"] if t["name"] == "no_params")
        assert tool["parameters"] == {"properties": {}}
