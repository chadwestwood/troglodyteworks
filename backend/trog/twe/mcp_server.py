from contextvars import ContextVar

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from .config import load_config
from .db import Database, execute, fetch_one
from .security import hash_session_token
from .services.mcp_tools import McpReadTools, McpToolError

_mcp_identity = ContextVar("twe_mcp_identity", default=None)


def create_mcp_server(config=None, database=None):
    twe_config = config or load_config()
    twe_database = database or Database(twe_config.database_url)
    tools = McpReadTools(twe_database, twe_config)
    server = FastMCP(
        "Troglodyte Works",
        instructions=(
            "Read authorized Troglodyte Works Community and game-instance information. "
            "All results are tenant-scoped and all calls are audited. This server exposes no action tools."
        ),
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(twe_config.mcp_allowed_hosts),
        ),
    )

    @server.tool()
    def twe_list_instances() -> dict:
        """List game instances the authenticated TWE user may access."""
        return _call(tools.list_instances)

    @server.tool()
    def twe_get_server_status(instance_id: str) -> dict:
        """Read current hosting-provider status for one authorized game instance."""
        return _call(tools.get_server_status, instance_id)

    @server.tool()
    def twe_get_active_players(instance_id: str) -> dict:
        """Read active-player count; include names only when separately authorized."""
        return _call(tools.get_active_players, instance_id)

    @server.tool()
    def twe_get_installed_mods(instance_id: str) -> dict:
        """Read installed mods for an instance when the user has mod-name access."""
        return _call(tools.get_installed_mods, instance_id)

    @server.tool()
    def twe_get_operation_history(instance_id: str, limit: int = 20) -> dict:
        """Read recent operation outcomes for an authorized game instance."""
        return _call(tools.get_operation_history, instance_id, limit)

    return server, twe_database


def authenticated_mcp_app(config=None, database=None):
    server, twe_database = create_mcp_server(config, database)
    app = server.streamable_http_app()

    async def authenticated(scope, receive, send):
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        if scope.get("path") == "/health":
            await JSONResponse({"status": "ok"})(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        if not authorization.startswith("Bearer "):
            await JSONResponse(
                {"error": {"code": "UNAUTHENTICATED", "message": "A TWE MCP bearer token is required."}},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
            return
        raw_token = authorization[7:].strip()
        if not raw_token.startswith("twe_mcp_"):
            identity = None
        else:
            with twe_database.connect() as conn:
                identity = fetch_one(
                    conn,
                    """
                    SELECT u.id::text AS user_id, u.email, u.display_name,
                           mat.id::text AS token_id
                    FROM mcp_access_tokens mat
                    JOIN users u ON u.id = mat.user_id
                    WHERE mat.token_hash = %s
                      AND mat.revoked_at IS NULL
                      AND (mat.expires_at IS NULL OR mat.expires_at > now())
                    """,
                    (hash_session_token(raw_token),),
                )
                if identity:
                    execute(conn, "UPDATE mcp_access_tokens SET last_used_at = now() WHERE id = %s", (identity["token_id"],))
        if not identity:
            await JSONResponse(
                {"error": {"code": "UNAUTHENTICATED", "message": "The TWE MCP bearer token is invalid or expired."}},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
            return
        token = _mcp_identity.set(identity)
        try:
            await app(scope, receive, send)
        finally:
            _mcp_identity.reset(token)

    return authenticated


def _call(method, *args):
    identity = _mcp_identity.get()
    if not identity:
        return {"ok": False, "error": {"code": "UNAUTHENTICATED", "message": "Authentication is required."}}
    try:
        return {"ok": True, "data": method(identity, *args)}
    except McpToolError as error:
        return {"ok": False, "error": {"code": error.code, "message": str(error)}}
