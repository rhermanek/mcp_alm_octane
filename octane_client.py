"""
ALM Octane HTTP client with session-based authentication.

Authentication flow:
  1. POST /authentication/sign_in with {client_id, client_secret}
  2. Server sets LWSSO_COOKIE_KEY cookie
  3. Cookie is used for all subsequent requests
  4. On 401 response: re-authenticate and retry once
"""

import re
import httpx
from typing import Any

_BASE_URL: str = ""
_SHARED_SPACE_ID: str = ""
_WORKSPACE_ID: str = ""
_CLIENT_ID: str = ""
_CLIENT_SECRET: str = ""
_VERIFY_SSL: bool = False
_SESSION_COOKIE: str | None = None
_HTTP_CLIENT: httpx.AsyncClient | None = None


_OWNER_NULL_PATTERN = re.compile(r"(^|;)\s*owner\s*=\s*null\s*(;|$)", re.IGNORECASE)


def configure(
    base_url: str,
    shared_space_id: str,
    workspace_id: str,
    client_id: str,
    client_secret: str,
    verify_ssl: bool = False,
) -> None:
    global _BASE_URL, _SHARED_SPACE_ID, _WORKSPACE_ID, _CLIENT_ID, _CLIENT_SECRET, _VERIFY_SSL
    _BASE_URL = base_url.rstrip("/")
    _SHARED_SPACE_ID = shared_space_id
    _WORKSPACE_ID = workspace_id
    _CLIENT_ID = client_id
    _CLIENT_SECRET = client_secret
    _VERIFY_SSL = verify_ssl


def workspace_path(resource: str) -> str:
    """Build the workspace-scoped API path for a resource."""
    return (
        f"/api/shared_spaces/{_SHARED_SPACE_ID}"
        f"/workspaces/{_WORKSPACE_ID}/{resource}"
    )


async def _get_client() -> httpx.AsyncClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.AsyncClient(
            base_url=_BASE_URL,
            timeout=30.0,
            verify=_VERIFY_SSL,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
    return _HTTP_CLIENT


async def _sign_in() -> None:
    global _SESSION_COOKIE
    client = await _get_client()
    response = await client.post(
        "/authentication/sign_in",
        json={"client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET},
    )
    response.raise_for_status()
    # Octane returns LWSSO_COOKIE_KEY in cookies
    cookie = response.cookies.get("LWSSO_COOKIE_KEY")
    if not cookie:
        # Some versions return it in Set-Cookie header directly
        for header_value in response.headers.get_list("Set-Cookie"):
            if "LWSSO_COOKIE_KEY" in header_value:
                cookie = header_value.split("LWSSO_COOKIE_KEY=")[1].split(";")[0]
                break
    if not cookie:
        raise RuntimeError("Authentication succeeded but no session cookie received")
    _SESSION_COOKIE = cookie
    client.cookies.set("LWSSO_COOKIE_KEY", _SESSION_COOKIE)


async def _request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json: Any = None,
    retry: bool = True,
) -> Any:
    """Make an authenticated request, re-authenticating on 401."""
    if _SESSION_COOKIE is None:
        await _sign_in()

    client = await _get_client()
    response = await client.request(method, path, params=params, json=json)

    if response.status_code == 401 and retry:
        await _sign_in()
        response = await client.request(method, path, params=params, json=json)

    if response.status_code == 404:
        return None

    if response.status_code == 204:
        return {"status": "deleted"}

    if not response.is_success:
        try:
            error_body = response.json()
        except Exception:
            error_body = response.text
        raise RuntimeError(
            f"Octane API error {response.status_code}: {error_body}"
        )

    if response.content:
        return response.json()
    return {"status": "ok"}


def _normalize_query(query: str) -> str:
    """Normalize common non-Octane OQL forms into Octane-compatible syntax."""
    normalized = query.strip()
    # Common habit: use SQL-style AND/&&. Octane expects ';' as conjunction.
    normalized = re.sub(r"\s+(and|&&)\s+", ";", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*;\s*", ";", normalized)
    normalized = re.sub(r";{2,}", ";", normalized)
    return normalized.strip(";")


def _has_owner_null_filter(query: str) -> bool:
    return _OWNER_NULL_PATTERN.search(query) is not None


def _strip_owner_null_filter(query: str) -> str:
    """Remove owner=null from a conjunctive query; preserves other predicates."""
    stripped = _OWNER_NULL_PATTERN.sub(";", query)
    stripped = re.sub(r"\s*;\s*", ";", stripped)
    stripped = re.sub(r";{2,}", ";", stripped)
    return stripped.strip(";")


async def _list_entities_raw(
    resource: str,
    fields: list[str] | None,
    query: str | None,
    order_by: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if fields:
        params["fields"] = ",".join(fields)
    if query:
        params["query"] = f'"{query}"'
    if order_by:
        params["order_by"] = order_by
    return await _request("GET", workspace_path(resource), params=params)


async def _list_with_owner_null_fallback(
    resource: str,
    fields: list[str] | None,
    query_without_owner_null: str | None,
    order_by: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """
    Octane may fail DQL translation for owner=null on some phase predicates.
    Work around this by querying without owner filter and applying owner-is-null
    filtering client-side.
    """
    server_offset = 0
    page_size = max(limit, 200)
    all_filtered: list[dict[str, Any]] = []

    while True:
        page = await _list_entities_raw(
            resource=resource,
            fields=fields,
            query=query_without_owner_null,
            order_by=order_by,
            limit=page_size,
            offset=server_offset,
        )
        data = page.get("data", [])
        if not data:
            break

        all_filtered.extend(item for item in data if item.get("owner") is None)

        server_offset += len(data)
        if server_offset >= page.get("total_count", 0):
            break

    page_data = all_filtered[offset: offset + limit]
    return {
        "total_count": len(all_filtered),
        "data": page_data,
        "exceeds_total_count": False,
    }


async def list_entities(
    resource: str,
    fields: list[str] | None = None,
    query: str | None = None,
    order_by: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """GET a collection of entities with optional OCL query/field selection."""
    normalized_query = _normalize_query(query) if query else None

    if normalized_query and _has_owner_null_filter(normalized_query):
        query_without_owner_null = _strip_owner_null_filter(normalized_query) or None
        return await _list_with_owner_null_fallback(
            resource=resource,
            fields=fields,
            query_without_owner_null=query_without_owner_null,
            order_by=order_by,
            limit=limit,
            offset=offset,
        )

    return await _list_entities_raw(
        resource=resource,
        fields=fields,
        query=normalized_query,
        order_by=order_by,
        limit=limit,
        offset=offset,
    )


async def get_entity(resource: str, entity_id: str, fields: list[str] | None = None) -> Any:
    """GET a single entity by ID."""
    params: dict[str, Any] = {}
    if fields:
        params["fields"] = ",".join(fields)
    return await _request("GET", f"{workspace_path(resource)}/{entity_id}", params=params)


async def create_entity(resource: str, data: dict[str, Any]) -> dict[str, Any]:
    """POST to create one or more entities. Wraps payload in {data:[...]} format."""
    return await _request("POST", workspace_path(resource), json={"data": [data]})


async def update_entity(resource: str, entity_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """PUT to update an entity by ID."""
    return await _request("PUT", f"{workspace_path(resource)}/{entity_id}", json=data)


async def delete_entity(resource: str, entity_id: str) -> dict[str, Any]:
    """DELETE an entity by ID."""
    return await _request("DELETE", f"{workspace_path(resource)}/{entity_id}")
