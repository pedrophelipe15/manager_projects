"""Mapeamento de issue Jira (raw) para estrutura estável de exportação."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

JIRA_STORY_POINTS_FIELD = os.getenv("JIRA_STORY_POINTS_FIELD", "customfield_10497").strip('"')
JIRA_START_DATE_FIELD = os.getenv("JIRA_START_DATE_FIELD", "customfield_10015").strip('"')
JIRA_START_DATETIME_FIELD = os.getenv("JIRA_START_DATETIME_FIELD", "customfield_10008").strip('"')
JIRA_DUE_DATE_FALLBACK_FIELD = os.getenv("JIRA_DUE_DATE_FALLBACK_FIELD", "customfield_10009").strip('"')
JIRA_TEAM_FIELD = os.getenv("JIRA_TEAM_FIELD", "customfield_10001").strip('"')
JIRA_EXECUTOR_TEAMS_FIELD = os.getenv("JIRA_EXECUTOR_TEAMS_FIELD", "customfield_10104").strip('"')
JIRA_PAGSEGURO_TEAMS_FIELD = os.getenv("JIRA_PAGSEGURO_TEAMS_FIELD", "customfield_10173").strip('"')
JIRA_BUSINESS_UNIT_FIELD = os.getenv("JIRA_BUSINESS_UNIT_FIELD", "customfield_10256").strip('"')
JIRA_SEVERITY_FIELD = os.getenv("JIRA_SEVERITY_FIELD", "customfield_10130").strip('"')
JIRA_UNAVAILABILITY_FIELD = os.getenv("JIRA_UNAVAILABILITY_FIELD", "customfield_10085").strip('"')
JIRA_REQUEST_TYPE_FIELD = os.getenv("JIRA_REQUEST_TYPE_FIELD", "customfield_10010").strip('"')
JIRA_QUARTER_FIELD = os.getenv("JIRA_QUARTER_FIELD", "").strip('"')
JIRA_SERVICE_NAME_FIELD = os.getenv("JIRA_SERVICE_NAME_FIELD", "").strip('"')


def map_issue(raw_issue: dict[str, Any]) -> dict[str, Any]:
    fields = raw_issue.get("fields", {})
    labels = fields.get("labels", []) or []
    labels_csv = ",".join(labels)
    parent_key = safe_nested(fields, "parent", "key")

    start_date = fields.get(JIRA_START_DATE_FIELD) or extract_date(fields.get(JIRA_START_DATETIME_FIELD))
    created_at = fields.get("created")

    quarter_value = None
    if JIRA_QUARTER_FIELD:
        quarter_value = extract_custom_field_value(fields.get(JIRA_QUARTER_FIELD))
    if not quarter_value:
        quarter_value = derive_quarter(start_date) or derive_quarter(created_at)

    service_name = None
    if JIRA_SERVICE_NAME_FIELD:
        service_name = extract_custom_field_value(fields.get(JIRA_SERVICE_NAME_FIELD))
    if not service_name:
        service_name = extract_array_names(fields.get("components"))

    return {
        "jira_key": raw_issue.get("key"),
        "jira_issue_id": raw_issue.get("id"),
        "project_id": safe_nested(fields, "project", "id"),
        "project_name": safe_nested(fields, "project", "name"),
        "summary": fields.get("summary", ""),
        "description": extract_text_from_adf(fields.get("description")),
        "issue_type": safe_nested(fields, "issuetype", "name"),
        "status": safe_nested(fields, "status", "name"),
        "priority": safe_nested(fields, "priority", "name"),
        "assignee": extract_user_name(fields.get("assignee")),
        "reporter": extract_user_name(fields.get("reporter")),
        "created_at_jira": created_at,
        "updated_at_jira": fields.get("updated"),
        "resolved_at_jira": fields.get("resolutiondate"),
        "start_date": start_date,
        "due_date": fields.get("duedate") or extract_date(fields.get(JIRA_DUE_DATE_FALLBACK_FIELD)),
        "story_points": safe_float(fields.get(JIRA_STORY_POINTS_FIELD)),
        "labels": labels_csv,
        "label": labels_csv,
        "parent_key": parent_key,
        "parent": parent_key,
        "quarter": quarter_value,
        "service_name": service_name,
        "team": safe_nested(fields, JIRA_TEAM_FIELD, "name") or safe_nested(fields, JIRA_TEAM_FIELD, "value"),
        "executor_teams": extract_array_names(fields.get(JIRA_EXECUTOR_TEAMS_FIELD)),
        "pagseguro_teams": extract_array_names(fields.get(JIRA_PAGSEGURO_TEAMS_FIELD)),
        "business_unit": extract_array_names(fields.get(JIRA_BUSINESS_UNIT_FIELD)),
        "severity": extract_array_names(fields.get(JIRA_SEVERITY_FIELD)),
        "unavailability": safe_nested(fields, JIRA_UNAVAILABILITY_FIELD, "name")
        or safe_nested(fields, JIRA_UNAVAILABILITY_FIELD, "value"),
        "request_type": extract_request_type_name(fields.get(JIRA_REQUEST_TYPE_FIELD)),
        "raw_payload_json": json.dumps(raw_issue, ensure_ascii=False),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }


def safe_nested(obj: dict[str, Any], key1: str, key2: str) -> Any:
    nested = obj.get(key1)
    if isinstance(nested, dict):
        return nested.get(key2)
    return None


def extract_user_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None

    for key in ("displayName", "name", "emailAddress", "accountId"):
        v = value.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def extract_request_type_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    request_type = value.get("requestType")
    if isinstance(request_type, dict):
        name = request_type.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def extract_date(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:10]


def derive_quarter(value: str | None) -> str | None:
    date_str = extract_date(value)
    if not date_str:
        return None
    try:
        year = int(date_str[0:4])
        month = int(date_str[5:7])
    except (ValueError, IndexError):
        return None

    quarter = ((month - 1) // 3) + 1
    return f"{year}Q{quarter}"


def extract_custom_field_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("value", "name", "displayName", "label"):
            v = value.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            extracted = extract_custom_field_value(item)
            if extracted:
                parts.append(extracted)
        return ",".join(parts) if parts else None
    return str(value)


def extract_array_names(arr: Any) -> str | None:
    if not isinstance(arr, list) or not arr:
        return None

    names: list[str] = []
    for item in arr:
        if isinstance(item, dict):
            name = item.get("name") or item.get("value") or item.get("displayName")
            if name:
                names.append(str(name))
        elif isinstance(item, str):
            names.append(item)

    return ",".join(names) if names else None


def extract_text_from_adf(adf_doc: Any, max_len: int = 5000) -> str | None:
    """Extrai texto plano de um documento ADF (Atlassian Document Format).

    Percorre a árvore e concatena todos os nós de texto. Trunca em `max_len`
    caracteres (default 5000; comentários usam um limite maior).
    """
    if not isinstance(adf_doc, dict):
        return None

    texts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text":
                text = node.get("text", "")
                if text:
                    texts.append(text)
            for child in node.get("content", []):
                walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(adf_doc)
    result = " ".join(texts).strip()
    return result[:max_len] if result else None
