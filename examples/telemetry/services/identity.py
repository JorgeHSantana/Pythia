"""Identity service — reads the caller from the `current_auth` contextvar.

The principal is set by the framework (AuthMiddleware / REST dependency) and
survives into sync code paths, so a Service can read it without the endpoint
threading it through as a parameter. Tests inject a principal via the
constructor instead of touching the contextvar.
"""

from restmcp import Service
from restmcp.auth import current_auth

from repositories.reading import ReadingRepository


class IdentityService(Service):
    readings = ReadingRepository()   # a Service must own at least one Repository
    principal = None                 # injectable (issue #14); None = read contextvar

    def describe_caller(self) -> dict:
        p = self.principal if self.principal is not None else current_auth.get()
        if not p:
            return {"who": None, "scopes": []}
        return {"who": p["name"], "scopes": sorted(p["scopes"])}
