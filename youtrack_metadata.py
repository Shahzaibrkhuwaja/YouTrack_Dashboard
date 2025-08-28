from __future__ import annotations

import os
import time
import typing as t
import requests
from functools import wraps
from urllib.parse import urljoin

# --- Optional: load .env (no-op if python-dotenv isn't installed) ---
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# --- Config from environment ---
YOUTRACK_URL: str = os.getenv("YOUTRACK_URL", "").rstrip("/")
YOUTRACK_TOKEN: str = os.getenv("YOUTRACK_TOKEN", "")

if not YOUTRACK_URL or not YOUTRACK_TOKEN:
    raise RuntimeError("YOUTRACK_URL or YOUTRACK_TOKEN not found in environment (.env).")

# --- Simple TTL cache decorator (default 30 minutes) ---
def ttl_cache(ttl_seconds: int = 1800):
    def decorator(func):
        _cache: dict[tuple, tuple[float, t.Any]] = {}

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            if key in _cache:
                ts, value = _cache[key]
                if now - ts < ttl_seconds:
                    return value
            value = func(*args, **kwargs)
            _cache[key] = (now, value)
            return value

        # expose a way to clear cache
        wrapper.cache_clear = _cache.clear  # type: ignore[attr-defined]
        return wrapper
    return decorator

# --- Requests session with retries/timeouts ---
def _make_session() -> requests.Session:
    session = requests.Session()
    # Retry on transient errors
    try:
        from urllib3.util import Retry  # type: ignore
        from requests.adapters import HTTPAdapter
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"])
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
    except Exception:
        # If urllib3 Retry not available, continue without it.
        pass
    session.headers.update({
        "Authorization": f"Bearer {YOUTRACK_TOKEN}",
        "Accept": "application/json"
    })
    return session

_SESSION = _make_session()
_DEFAULT_TIMEOUT = 20  # seconds

# --- Helpers ---
def _get(url_path: str, params: dict | None = None) -> t.Any:
    url = urljoin(YOUTRACK_URL + "/", url_path.lstrip("/"))
    resp = _SESSION.get(url, params=params, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.json()

def _find_bundle_id_for_field(project_id: str, field_name: str) -> str | None:
    """
    Given a project and a custom field name ("Type", "State", etc.),
    return the bundle id for that field or None if not found.
    """
    path = f"/api/admin/projects/{project_id}/customFields"
    params = {"fields": "field(name),bundle(id)"}
    data = _get(path, params)
    for f in data:
        fld = (f.get("field") or {}).get("name", "")
        if fld.lower() == field_name.lower():
            b = f.get("bundle") or {}
            return b.get("id")
    return None

def _get_enum_bundle_values(bundle_id: str) -> list[str]:
    """
    Fetch values from an Enum bundle (e.g., Type).
    """
    path = f"/api/admin/customFieldSettings/bundles/enum/{bundle_id}"
    params = {"fields": "values(name)"}
    data = _get(path, params)
    return sorted([v["name"] for v in data.get("values", []) if "name" in v])

def _get_state_bundle_values(bundle_id: str) -> list[str]:
    """
    Fetch values from a State bundle.
    """
    path = f"/api/admin/customFieldSettings/bundles/state/{bundle_id}"
    params = {"fields": "values(name)"}
    data = _get(path, params)
    return [v["name"] for v in data.get("values", []) if "name" in v]

# --- Public API ---

@ttl_cache(1800)
def fetch_projects() -> dict[str, list[str]]:
    """
    Returns mapping: project shortName -> list of lowercase synonyms.
    Example:
        {
          "APLUS": ["aplus", "argaam plus", "plus", "argaam", "ar", ...],
          "AT": ["at", "argaam tools", "tools", ...],
        }
    """
    path = "/api/admin/projects"
    params = {"fields": "shortName,name", "$top": 1000}
    projects = _get(path, params)
    project_map: dict[str, list[str]] = {}

    for p in projects:
        short = p.get("shortName")
        name = p.get("name", "")
        if not short:
            continue
        synonyms: list[str] = [short.lower()]
        if name:
            n = name.lower().strip()
            synonyms.append(n)
            # Add tokens excluding "argaam" to support quick matches
            tokens = [tok for tok in n.replace("argaam", "").split() if tok]
            synonyms.extend(tokens)
        # Deduplicate while preserving order
        seen = set()
        uniq = [s for s in synonyms if not (s in seen or seen.add(s))]
        project_map[short] = uniq

    return project_map

@ttl_cache(1800)
def fetch_task_types(project_id: str = "APLUS") -> list[str]:
    """
    Returns the list of Type values for the given project (defaults to APLUS).
    """
    bundle_id = _find_bundle_id_for_field(project_id, "Type")
    if not bundle_id:
        return []
    return _get_enum_bundle_values(bundle_id)

@ttl_cache(1800)
def fetch_task_states(project_id: str = "APLUS") -> list[str]:
    """
    Returns the list of State values for the given project (defaults to APLUS).
    Order preserved as defined in bundle (no sorting).
    """
    bundle_id = _find_bundle_id_for_field(project_id, "State")
    if not bundle_id:
        return []
    return _get_state_bundle_values(bundle_id)

@ttl_cache(1800)
def fetch_assignees(max_users: int = 5000) -> dict[str, str]:
    """
    Returns a mapping that helps resolve assignee names to their login.
      - key: login in lowercase (maps to itself)
      - key: full name in lowercase (maps to login)
    Handles paging beyond 100 results.
    """
    mapping: dict[str, str] = {}
    page = 0
    page_size = 100
    total_fetched = 0

    while total_fetched < max_users:
        params = {
            "fields": "login,name",
            "$top": page_size,
            "$skip": page * page_size,
        }
        users = _get("/api/users", params)
        if not users:
            break
        for user in users:
            login = (user.get("login") or "").strip()
            name = (user.get("name") or "").strip()
            if login:
                lwr_login = login.lower()
                mapping[lwr_login] = lwr_login
                if name and name.lower() != lwr_login:
                    mapping[name.lower()] = lwr_login
        fetched = len(users)
        total_fetched += fetched
        if fetched < page_size:  # last page
            break
        page += 1

    return mapping

# --- Convenience: quick sanity probe (optional) ---
if __name__ == "__main__":
    # Quick self-test (safe GETs)
    print("Projects:", list(fetch_projects().keys())[:10])
    print("Types (APLUS):", fetch_task_types("APLUS"))
    print("States (APLUS):", fetch_task_states("APLUS"))
    assignees = fetch_assignees()
    print("Assignees sample:", list(assignees.items())[:10])
