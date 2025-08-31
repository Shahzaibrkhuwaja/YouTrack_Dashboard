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


# ================== Section 3: Deployments on Live (backend) ==================
from period_utils import get_field_period_filter
from datetime import datetime, timezone
import re

# Lock to what your instance shows in debug: Relates, Subtask (skip Duplicate)
_DEPLOYMENT_LINK_TYPES = {"relates", "subtask"}

_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")
def _is_valid_issue_key(s: str) -> bool:
    return bool(s) and bool(_KEY_RE.match(s))


def get_deployments_on_live(
    project: str,
    period_key: str,
    *,
    link_types: set[str] | None = None,
    discover_link_types: bool = False,
) -> dict:
    if not project or not YOUTRACK_URL or not YOUTRACK_TOKEN:
        return {"deployments": [], "debug": {"query": "", "count": 0}}

    # Build the YouTrack query (project + Type:Deployment + Due Date period + exclude subtasks)
    due_clause = get_field_period_filter("due date", period_key)
    proj_clause = f"project: {{{project}}}"
    no_subtasks_clause = "has: -{subtask of}"
    yt_query = f"{proj_clause} Type:{{Deployment}} {due_clause} {no_subtasks_clause}".strip()

    # Include internal id so fallback /links call works
    fields = (
        "idReadable,id,summary,dueDate,"
        "customFields(name,value(name,localizedName,date)),"
        "links(direction,linkType(name),issues("
        "  idReadable,id,summary,created,project(shortName),"
        "  customFields(name,value(name,localizedName))"
        "))"
    )

    # Allowed link types
    allowed = None if discover_link_types else {s.strip().lower() for s in (link_types or _DEPLOYMENT_LINK_TYPES)}
    seen_link_types: set[str] = set()
    deployments: list[dict] = []

    for dep in _iter_issues_with_fields(yt_query, fields=fields, page_size=100):
        dep_id_readable = dep.get("idReadable") or ""
        dep_dbid = dep.get("id") or ""  # internal YouTrack id
        title = dep.get("summary") or ""
        due_iso = _extract_due_date_iso(dep)

        linked_out: list[dict] = []
        seen_ids: set[str] = set()  # track final readable keys to avoid duplicates

        # ---- A) Try inline-expanded links first
        inline_links = dep.get("links") or []
        inline_count = _collect_links_into(
            inline_links, allowed, seen_link_types, seen_ids, linked_out
        )

        # ---- B) Fallback: call /api/issues/{<internal id>}/links if needed
        if inline_count == 0 and dep_dbid:
            try:
                params = {
                    "fields": (
                        "direction,linkType(name),issues("
                        "  idReadable,id,summary,created,project(shortName),"
                        "  customFields(name,value(name,localizedName))"
                        ")"
                    )
                }
                direct_links = _get(f"/api/issues/{dep_dbid}/links", params=params) or []
                _collect_links_into(direct_links, allowed, seen_link_types, seen_ids, linked_out)
            except Exception:
                pass  # still return the deployment row even if fallback fails

        deployments.append({
            "deployment_id": dep_id_readable,
            "deployment_title": title,
            "due_date": due_iso,
            "linked": linked_out,
        })

    debug = {"query": yt_query, "count": len(deployments)}
    if discover_link_types:
        debug["link_types_seen"] = sorted(seen_link_types)
    return {"deployments": deployments, "debug": debug}


def _collect_links_into(links_payload, allowed, seen_link_types, seen_ids, linked_out) -> int:
    """
    Parse a links collection and append resolved linked issues into linked_out.
    - Validates readable keys (e.g., APLUS-1234); resolves weird keys via internal id.
    - Skips items that cannot be resolved to a proper readable key.
    Returns how many linked issues were appended.
    """
    appended = 0
    for link in links_payload or []:
        ltype_raw = ((link.get("linkType") or {}).get("name") or "").strip()
        ltype = ltype_raw.lower()
        if seen_link_types is not None:
            seen_link_types.add(ltype_raw)
        if (allowed is not None) and (ltype not in allowed):
            continue

        for li in (link.get("issues") or []):
            # Raw fields from link payload
            iid_readable = (li.get("idReadable") or "").strip()
            iid_internal = (li.get("id") or "").strip()
            project_short = ((li.get("project") or {}).get("shortName") or "").strip().upper()
            itype = _extract_type_from_issue(li)
            istate = _extract_state_from_issue(li)
            title = (li.get("summary") or "").strip()

            # created_on from ms -> YYYY-MM-DD
            created_iso = ""
            created_ms = li.get("created")
            if isinstance(created_ms, (int, float)) and created_ms > 0:
                created_iso = datetime.fromtimestamp(created_ms / 1000.0, tz=timezone.utc).date().isoformat()

            # Decide whether we must resolve:
            # - weird or missing readable key, or
            # - missing basic fields (project/type/state/title/created_on)
            needs_resolve = (not _is_valid_issue_key(iid_readable)) or (not project_short or not itype or not istate)

            if needs_resolve:
                issue_key = iid_internal or iid_readable  # prefer internal id
                try:
                    resolved = _get(
                        f"/api/issues/{issue_key}",
                        params={
                            "fields": "idReadable,summary,created,project(shortName),"
                                      "customFields(name,value(name,localizedName))"
                        },
                    ) or {}
                    # Fill/override from resolved payload
                    iid_readable = (resolved.get("idReadable") or "").strip() or iid_readable
                    project_short = project_short or ((resolved.get("project") or {}).get("shortName") or "").strip().upper()
                    itype = itype or _extract_type_from_issue(resolved) or "Unspecified"
                    istate = istate or _extract_state_from_issue(resolved) or "Unspecified"
                    title = title or (resolved.get("summary") or "").strip()
                    if not created_iso:
                        r_ms = resolved.get("created")
                        if isinstance(r_ms, (int, float)) and r_ms > 0:
                            created_iso = datetime.fromtimestamp(r_ms / 1000.0, tz=timezone.utc).date().isoformat()
                except Exception:
                    # ignore; we'll validate key below
                    pass

            # If after resolve we still don't have a proper readable key, skip this entry
            if not _is_valid_issue_key(iid_readable):
                continue

            # Dedup on final readable key
            if iid_readable in seen_ids:
                continue
            seen_ids.add(iid_readable)

            linked_out.append({
                "id": iid_readable,
                "project": project_short,
                "type": itype or "Unspecified",
                "state": istate or "Unspecified",
                "title": title,
                "created_on": created_iso,
            })
            appended += 1
    return appended


def _iter_issues_with_fields(yt_query: str, *, fields: str, page_size: int = 100):
    skip = 0
    while True:
        params = {"query": yt_query, "fields": fields, "$top": page_size, "$skip": skip}
        batch = _get("/api/issues", params=params)
        if not batch:
            break
        for item in batch:
            yield item
        if len(batch) < page_size:
            break
        skip += page_size


def _extract_due_date_iso(issue) -> str | None:
    ms = issue.get("dueDate")
    if isinstance(ms, (int, float)) and ms > 0:
        try:
            return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).date().isoformat()
        except Exception:
            pass
    for f in issue.get("customFields", []) or []:
        if (f.get("name") or "").strip().lower() in {"due date", "duedate"}:
            v = f.get("value")
            if isinstance(v, (int, float)) and v > 0:
                try:
                    return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc).date().isoformat()
                except Exception:
                    return None
            if isinstance(v, dict):
                if "date" in v and isinstance(v["date"], (int, float)) and v["date"] > 0:
                    try:
                        return datetime.fromtimestamp(v["date"] / 1000.0, tz=timezone.utc).date().isoformat()
                    except Exception:
                        return None
                s = (v.get("name") or "").strip()
                if s:
                    try:
                        return datetime.fromisoformat(s).date().isoformat()
                    except Exception:
                        return s
            if isinstance(v, str) and v.strip():
                s = v.strip()
                try:
                    return datetime.fromisoformat(s).date().isoformat()
                except Exception:
                    return s
    return None
# ================== /Section 3: Deployments on Live (backend) ==================



# ================== Section 4: Tasks in Business Review ==================
from datetime import datetime, timezone

def get_tasks_in_business_review(project: str) -> dict:
    """
    Top-level issues in Business Review for the given project.
    Period-agnostic (no created filter). Excludes subtasks.
    """
    if not project or not YOUTRACK_URL or not YOUTRACK_TOKEN:
        return {"items": [], "debug": {"query": "", "count": 0}}

    proj_clause = f"project: {{{project}}}"
    no_subtasks_clause = "has: -{subtask of}"

    # Try the OR clause (parenthesized), fall back to single state if the OR form 400s in your instance.
    state_or_clause = "(State:{Business Review} or State:{In Business Review})"
    state_single_clause = "State:{In Business Review}"

    # First attempt with OR
    yt_query = f"{proj_clause} {state_or_clause} {no_subtasks_clause}".strip()

    fields = (
        "idReadable,summary,created,project(shortName),"
        "customFields(name,value(name,localizedName))"
    )

    items: list[dict] = []

    def _collect(query: str) -> list[dict]:
        out = []
        for it in _iter_issues_with_fields(query, fields=fields, page_size=100):
            iid = (it.get("idReadable") or "").strip()
            if not iid:
                continue
            title = (it.get("summary") or "").strip()
            itype = _extract_type_from_issue(it) or "Unspecified"
            istate = _extract_state_from_issue(it) or "Unspecified"
            created_iso = ""
            ms = it.get("created")
            if isinstance(ms, (int, float)) and ms > 0:
                created_iso = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).date().isoformat()
            out.append({
                "id": iid,
                "title": title,
                "type": itype,
                "state": istate,
                "created_on": created_iso,
            })
        return out

    try:
        items = _collect(yt_query)
        debug_query = yt_query
    except requests.HTTPError as e:
        # If the OR form is not accepted, retry with the single-state clause
        yt_query_single = f"{proj_clause} {state_single_clause} {no_subtasks_clause}".strip()
        items = _collect(yt_query_single)
        debug_query = yt_query_single

    return {"items": items, "debug": {"query": debug_query, "count": len(items)}}
# ==================/Section 4 ==================

