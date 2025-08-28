# youtrack_queries.py
from __future__ import annotations
import os
from typing import Dict, List, Any
import requests
import os
from urllib.parse import quote
from period_utils import get_created_filter
from period_utils import get_period_range
from urllib.parse import quote


# Optional .env loader (safe no-op if not installed)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# Read from config safely (EXCLUDED_TYPES might not exist yet)
import config
ACTIVE_PROJECTS = [p.strip().upper() for p in getattr(config, "ACTIVE_PROJECTS", []) if p.strip()]
EXCLUDED_TYPES = {t.strip().lower() for t in getattr(config, "EXCLUDED_TYPES", []) if isinstance(t, str) and t.strip()}

from period_utils import get_created_filter

YOUTRACK_URL: str = os.getenv("YOUTRACK_URL", "").rstrip("/")
YOUTRACK_TOKEN: str = os.getenv("YOUTRACK_TOKEN", "")

if not YOUTRACK_URL or not YOUTRACK_TOKEN:
    raise RuntimeError("YOUTRACK_URL or YOUTRACK_TOKEN not found in environment (.env).")

# ---- HTTP session ----
_SESSION = requests.Session()
_SESSION.headers.update({
    "Authorization": f"Bearer {YOUTRACK_TOKEN}",
    "Accept": "application/json",
})
_TIMEOUT = 20  # seconds

def _get(path: str, params: Dict[str, Any] | None = None) -> Any:
    url = f"{YOUTRACK_URL.rstrip('/')}/{path.lstrip('/')}"
    r = _SESSION.get(url, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()

# ---- Core issue fetcher (paged) ----
def _iter_issues_minimal(yt_query: str, page_size: int = 100):
    """
    Iterate through issues matching query.
    We request only fields needed for "by type" aggregation.
    (Subtasks are already excluded in the query via `has: -{subtask of}`.)
    """
    fields = (
        "idReadable,"
        "project(shortName),"
        "created,"
        "customFields(name,value(name,localizedName))"
    )
    skip = 0
    while True:
        params = {
            "query": yt_query,
            "fields": fields,
            "$top": page_size,
            "$skip": skip,
        }
        batch = _get("/api/issues", params=params)
        if not batch:
            break
        for item in batch:
            yield item
        if len(batch) < page_size:
            break
        skip += page_size

# ---- Helpers ----


# youtrack_queries.py

from datetime import date
from calendar import monthrange

def get_monthly_task_counts_by_type(project: str, year: int) -> Dict[str, Dict[str, int]]:
    """
    Returns mapping: "YYYY-MM" -> { type -> count } for the given project and year.
    Months included: Jan..current month (dynamic), missing months => {} (handled as 0 in UI).
    Respects EXCLUDED_TYPES (case-insensitive) and excludes subtasks.
    """
    if not project or not YOUTRACK_URL or not YOUTRACK_TOKEN:
        return {}

    # Build month keys in order (Jan..current month)
    current_month = date.today().month if year == date.today().year else 12
    month_keys = [f"{year}-{m:02d}" for m in range(1, current_month + 1)]

    out: Dict[str, Dict[str, int]] = {}

    for m in range(1, current_month + 1):
        start = date(year, m, 1)
        end = date(year, m, monthrange(year, m)[1])  # last day of month

        created_clause = f"created: {{{start.isoformat()}}} .. {{{end.isoformat()}}}"
        proj_clause = f"project: {{{project}}}"
        no_subtasks_clause = "has: -{subtask of}"

        yt_query = f"{proj_clause} {created_clause} {no_subtasks_clause}".strip()

        month_key = f"{year}-{m:02d}"
        per_type: Dict[str, int] = {}

        for issue in _iter_issues_minimal(yt_query):
            itype = _extract_type_from_issue(issue) or "Unspecified"
            if itype.strip().lower() in EXCLUDED_TYPES:
                continue
            per_type[itype] = per_type.get(itype, 0) + 1

        out[month_key] = per_type

    # Ensure stable order (optional – dict keeps insertion order in Py3.7+)
    return {k: out.get(k, {}) for k in month_keys}


def _qt(val: str) -> str:
    """Quote UI query values only if they contain spaces."""
    val = (val or "").strip()
    return f'"{val}"' if val and any(c.isspace() for c in val) else val



def yt_issues_url(project: str, period_key: str,
                  issue_type: str | None = None,
                  state: str | None = None) -> str:
    """
    Build YouTrack URL for the /issues endpoint (with braces style).
    Example:
      /issues?q=Project:{Argaam Plus} created:2025-08-01 .. 2025-08-31 type:{New Requirement} has:-{Subtask of}
    """
    base = os.getenv("YOUTRACK_URL", "").rstrip("/")
    if not base:
        return "#"

    start, end = get_period_range(period_key)

    parts = [
        f"Project:{{{project}}}",
        f"created:{start.isoformat()} .. {end.isoformat()}",
        "has:-{Subtask of}",
    ]
    if issue_type:
        parts.append(f"Type:{{{issue_type}}}")
    if state:
        parts.append(f"State:{{{state}}}")

    query = " ".join(parts)
    return f"{base}/issues?q={quote(query)}"





def _extract_type_from_issue(issue: Dict[str, Any]) -> str | None:
    """
    Pull a type-like value.
    Matches 'Type', 'Issue Type' (case-insensitive). Falls back to None.
    """
    for cf in issue.get("customFields", []):
        cf_name = (cf.get("name") or "").strip().lower()
        if cf_name in ("type", "issue type", "issuetype"):
            val = cf.get("value")
            if isinstance(val, dict):
                name = (val.get("name") or val.get("localizedName") or "").strip()
                return name or None
            return None
    return None

def _extract_state_from_issue(issue: Dict[str, Any]) -> str | None:
    for cf in issue.get("customFields", []):
        if (cf.get("name") or "").strip().lower() == "state":
            val = cf.get("value")
            if isinstance(val, dict):
                return (val.get("name") or val.get("localizedName") or "").strip() or None
            return None
    return None

def get_task_counts_by_type_and_state(period_key: str) -> Dict[str, Dict[str, Dict[str, int]]]:
    """
    Returns nested counts:
      {
        "per_project": {
          "APLUS": {
            "Bug": {"Open": 5, "In Progress": 3, ...},
            "Enhancement": {"Open": 2, ...},
            ...
          },
          ...
        },
        "overall": {
          "Bug": {"Open": 8, "In Progress": 4, ...},
          "Enhancement": {...},
          ...
        },
        "debug": { "query": "...", "raw": N, "after_exclude": M }
      }
    - Uses same filters as before: projects from config, period on Created Date,
      and subtasks excluded via `has: -{subtask of}`.
    - Respects EXCLUDED_TYPES (case-insensitive).
    """
    if not ACTIVE_PROJECTS:
        return {"per_project": {}, "overall": {}, "debug": {"query": "", "raw": 0, "after_exclude": 0}}

    created_clause = get_created_filter(period_key)
    proj_clause = _build_projects_or_clause(ACTIVE_PROJECTS)
    no_subtasks_clause = "has: -{subtask of}"
    yt_query = f"{proj_clause} {created_clause} {no_subtasks_clause}".strip()

    per_project: Dict[str, Dict[str, Dict[str, int]]] = {p: {} for p in ACTIVE_PROJECTS}
    overall: Dict[str, Dict[str, int]] = {}

    raw_matches = 0
    after_exclude = 0

    for issue in _iter_issues_minimal(yt_query):
        raw_matches += 1

        itype = _extract_type_from_issue(issue) or "Unspecified"
        if itype.strip().lower() in EXCLUDED_TYPES:
            continue

        istate = _extract_state_from_issue(issue) or "Unspecified"
        proj = ((issue.get("project") or {}).get("shortName") or "").strip().upper()
        if not proj:
            continue

        # per project
        per_project.setdefault(proj, {})
        per_project[proj].setdefault(itype, {})
        per_project[proj][itype][istate] = per_project[proj][itype].get(istate, 0) + 1

        # overall
        overall.setdefault(itype, {})
        overall[itype][istate] = overall[itype].get(istate, 0) + 1

        after_exclude += 1

    return {
        "per_project": per_project,
        "overall": overall,
        "debug": {"query": yt_query, "raw": raw_matches, "after_exclude": after_exclude},
    }


def _build_projects_or_clause(projects: List[str]) -> str:
    """
    Build a project filter. In YouTrack, repeating the same attribute is OR.
    Example: project:{APLUS} project:{AT}
    """
    parts = [f"project:{{{p}}}" for p in projects if p]
    return " ".join(parts) if parts else ""



# ---- Public: counts by Type (subtasks excluded in query) ----
def get_task_counts_by_type(period_key: str) -> Dict[str, Dict[str, Any]]:
    """
    Return counts by Type for all configured projects, with:
      • Created-date period filter
      • Subtasks excluded via query:  has: -{subtask of}
      • Types in config.EXCLUDED_TYPES removed (case-insensitive)

    Output:
      {
        "per_project": { "APLUS": {"Bug": 12, "Enhancement": 5, ...}, ... },
        "overall":     { "Bug": 18, "Enhancement": 9, ... },
        "debug":       { "query": "...", "raw": 0, "after_exclude": 0 }
      }
    """
    if not ACTIVE_PROJECTS:
        return {"per_project": {}, "overall": {}, "debug": {"query": "", "raw": 0, "after_exclude": 0}}

    created_clause = get_created_filter(period_key)  # e.g., "created: {2025-08-01} .. {2025-08-31}"
    proj_clause = _build_projects_or_clause(ACTIVE_PROJECTS)

    # Exclude subtasks directly in the YouTrack query
    no_subtasks_clause = "has: -{subtask of}"

    # Final query (AND is implied by spaces)
    yt_query = f"{proj_clause} {created_clause} {no_subtasks_clause}".strip()

    per_project: Dict[str, Dict[str, int]] = {p: {} for p in ACTIVE_PROJECTS}
    overall: Dict[str, int] = {}

    raw_matches = 0
    after_exclude = 0

    for issue in _iter_issues_minimal(yt_query):
        raw_matches += 1

        itype = _extract_type_from_issue(issue)
        if not itype:
            itype = "Unspecified"

        # Exclude by configured types (case-insensitive)
        if itype.strip().lower() in EXCLUDED_TYPES:
            continue
        after_exclude += 1

        proj = ((issue.get("project") or {}).get("shortName") or "").strip().upper()
        if not proj:
            continue

        per_project.setdefault(proj, {})
        per_project[proj][itype] = per_project[proj].get(itype, 0) + 1
        overall[itype] = overall.get(itype, 0) + 1

    return {
        "per_project": per_project,
        "overall": overall,
        "debug": {
            "query": yt_query,
            "raw": raw_matches,
            "after_exclude": after_exclude,
        },
    }
