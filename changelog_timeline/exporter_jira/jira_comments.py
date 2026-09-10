"""Normalização de comentários Jira para payload flat."""

from __future__ import annotations

from typing import Any

from jira_mapper import extract_text_from_adf


def extract_text_from_comment_adf(adf_doc: Any) -> str | None:
    """Extrai texto de um ADF de comentário (limite maior que o de descrição)."""
    return extract_text_from_adf(adf_doc, max_len=10000)


def normalize_jira_comments(issue_key: str, comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for comment in comments:
        visibility = comment.get("visibility") if isinstance(comment.get("visibility"), dict) else {}
        author = comment.get("author") if isinstance(comment.get("author"), dict) else {}
        body = comment.get("body")

        normalized.append(
            {
                "jira_comment_id": str(comment.get("id") or ""),
                "jira_key": issue_key,
                "author_display_name": author.get("displayName"),
                "author_account_id": author.get("accountId"),
                "body_text": extract_text_from_comment_adf(body),
                "body_adf": body,
                "created_at_jira": comment.get("created"),
                "updated_at_jira": comment.get("updated"),
                "visibility_type": visibility.get("type"),
                "visibility_value": visibility.get("value"),
            }
        )

    return normalized
