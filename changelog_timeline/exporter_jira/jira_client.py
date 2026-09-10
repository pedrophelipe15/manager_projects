"""Cliente Jira API v3 com paginação, retry robusto e autenticação Basic."""

from __future__ import annotations

import os
import time
import threading
from base64 import b64encode
from typing import Any

import requests
from requests.exceptions import ConnectionError, Timeout
from dotenv import load_dotenv

load_dotenv()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "").strip('"')
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "").strip('"')
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "").strip('"')
JIRA_PAGE_SIZE = int(os.getenv("JIRA_PAGE_SIZE", "100"))
JIRA_TIMEOUT = int(os.getenv("JIRA_REQUEST_TIMEOUT_SECONDS", "30"))
JIRA_MAX_RETRIES = int(os.getenv("JIRA_MAX_RETRIES", "4"))
JIRA_BACKOFF_BASE = float(os.getenv("JIRA_BACKOFF_BASE", "2.0"))


class JiraClient:
    # Semáforo global compartilhado entre threads — freia todos os workers quando 429 chega
    _rate_limit_event = threading.Event()
    _rate_limit_event.set()  # Começa liberado (set = pode prosseguir)

    def __init__(self, base_url: str | None = None, email: str | None = None, api_token: str | None = None) -> None:
        self.base_url = (base_url or JIRA_BASE_URL).rstrip("/")
        self.email = email or JIRA_EMAIL
        self.api_token = api_token or JIRA_API_TOKEN

        if not self.base_url or not self.email or not self.api_token:
            raise ValueError(
                "Credenciais Jira incompletas. Configure JIRA_BASE_URL, JIRA_EMAIL e JIRA_API_TOKEN no .env."
            )

        # Session reutilizada (mantém conexão TCP/TLS aberta)
        self._session = requests.Session()
        credentials = f"{self.email}:{self.api_token}"
        token = b64encode(credentials.encode()).decode()
        self._session.headers.update({
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _headers(self) -> dict[str, str]:
        """Mantido para compatibilidade, mas session já tem os headers."""
        return dict(self._session.headers)

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """Executa request com retry robusto: backoff exponencial para 5xx, timeout e connection errors.
        
        Semáforo global freia todos os workers quando um 429 é recebido.
        """
        kwargs.setdefault("timeout", JIRA_TIMEOUT)
        last_exception: Exception | None = None

        for attempt in range(JIRA_MAX_RETRIES + 1):
            # Espera se rate limit global está ativo (outro thread recebeu 429)
            self._rate_limit_event.wait(timeout=120)

            try:
                response = self._session.request(method, url, **kwargs)

                # 429 — Rate limit: freia todos os workers
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "10"))
                    self._rate_limit_event.clear()  # Bloqueia todos os threads
                    time.sleep(retry_after)
                    self._rate_limit_event.set()  # Libera todos
                    continue

                # 5xx — Server error: retry com backoff
                if response.status_code >= 500:
                    if attempt < JIRA_MAX_RETRIES:
                        wait = JIRA_BACKOFF_BASE ** attempt
                        time.sleep(wait)
                        continue
                    # Última tentativa — retorna a response para o caller tratar
                    return response

                return response

            except (Timeout, ConnectionError) as e:
                last_exception = e
                if attempt < JIRA_MAX_RETRIES:
                    wait = JIRA_BACKOFF_BASE ** attempt
                    time.sleep(wait)
                    continue
                raise RuntimeError(
                    f"Falha após {JIRA_MAX_RETRIES + 1} tentativas em {url}: {e}"
                ) from e

        # Não deveria chegar aqui, mas safety net
        if last_exception:
            raise RuntimeError(f"Falha após retries em {url}: {last_exception}") from last_exception
        raise RuntimeError(f"Falha após retries em {url}")

    def test_connection(self) -> dict[str, Any]:
        url = f"{self.base_url}/rest/api/3/myself"
        response = self._request_with_retry("GET", url)
        if response.status_code != 200:
            raise RuntimeError(f"Falha na autenticação Jira: HTTP {response.status_code} - {response.text[:200]}")
        return response.json()

    def fetch_issues_raw(self, jql: str, fields: str = "*all", expand: str | None = None) -> list[dict[str, Any]]:
        url = f"{self.base_url}/rest/api/3/search/jql"
        all_issues: list[dict[str, Any]] = []
        next_page_token: str | None = None

        while True:
            params: dict[str, Any] = {
                "jql": jql,
                "fields": fields,
                "maxResults": JIRA_PAGE_SIZE,
            }
            if expand:
                params["expand"] = expand
            if next_page_token:
                params["nextPageToken"] = next_page_token

            response = self._request_with_retry("GET", url, params=params)

            if response.status_code != 200:
                raise RuntimeError(f"Erro Jira API: HTTP {response.status_code} - {response.text[:300]}")

            payload = response.json()
            issues = payload.get("issues", [])
            all_issues.extend(issues)

            is_last = payload.get("isLast", True)
            next_page_token = payload.get("nextPageToken")
            if is_last or not next_page_token or not issues:
                break

        return all_issues

    def fetch_issue_changelog(self, issue_id_or_key: str) -> list[dict[str, Any]]:
        """Busca changelog completo de uma issue via endpoint dedicado (paginado)."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_id_or_key}/changelog"
        all_histories: list[dict[str, Any]] = []
        start_at = 0

        while True:
            params = {"startAt": start_at, "maxResults": 100}
            response = self._request_with_retry("GET", url, params=params)

            if response.status_code != 200:
                raise RuntimeError(
                    f"Erro Jira API changelog: HTTP {response.status_code} - {response.text[:300]}"
                )

            payload = response.json()
            values = payload.get("values", [])
            all_histories.extend(values)

            total = payload.get("total", 0)
            max_results = payload.get("maxResults", 100)
            if not values or (start_at + max_results) >= total:
                break
            start_at += max_results

        return all_histories

    def fetch_issue_comments(self, issue_id_or_key: str) -> list[dict[str, Any]]:
        url = f"{self.base_url}/rest/api/3/issue/{issue_id_or_key}/comment"
        comments: list[dict[str, Any]] = []
        start_at = 0

        while True:
            params = {"startAt": start_at, "maxResults": 100, "orderBy": "created"}
            response = self._request_with_retry("GET", url, params=params)

            if response.status_code != 200:
                raise RuntimeError(
                    f"Erro Jira API comentarios: HTTP {response.status_code} - {response.text[:300]}"
                )

            payload = response.json()
            values = payload.get("comments", [])
            comments.extend(values)

            total = payload.get("total", 0)
            max_results = payload.get("maxResults", 0)
            if not values or (start_at + max_results) >= total:
                break
            start_at += max_results

        return comments
