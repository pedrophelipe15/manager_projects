"""CLI para extrair issues, comentários e changelogs do Jira e salvar em JSONL."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from jira_client import JiraClient
from jira_comments import normalize_jira_comments
from jira_mapper import map_issue


load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extrator Jira standalone para uso em outros projetos")
    parser.add_argument(
        "--jql",
        default=os.getenv("JIRA_JQL_BASE", "").strip('"'),
        help="Consulta JQL ou caminho para arquivo .txt com a JQL. Se omitido, usa JIRA_JQL_BASE do .env",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Diretório de saída para os arquivos JSONL",
    )
    parser.add_argument(
        "--with-comments",
        action="store_true",
        help="Extrai comentários de cada issue e gera comments.jsonl",
    )
    parser.add_argument(
        "--with-changelog",
        action="store_true",
        help="Extrai changelog completo de cada issue e gera changelogs.jsonl",
    )
    parser.add_argument(
        "--db-cache",
        default=None,
        help="Path para issues.db — pula extração de changelog para issues que não mudaram desde a última sync",
    )
    parser.add_argument(
        "--skip-test",
        action="store_true",
        help="Pula test_connection (já validado pelo caller)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Também salva payload bruto das issues em issues_raw.jsonl",
    )
    return parser.parse_args()


def resolve_jql(jql_arg: str) -> str:
    """Resolve a JQL literal or loads JQL text from a file path."""
    jql_value = (jql_arg or "").strip()
    if not jql_value:
        return ""

    candidate_path = Path(jql_value)
    if candidate_path.is_file():
        content = candidate_path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"Arquivo de JQL vazio: {candidate_path}")
        return content

    return jql_value


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def _normalize_ts(ts: str | None) -> datetime | None:
    """Normaliza timestamp para datetime comparável (ignora diferenças de formato Z/+00:00/trailing zeros)."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def main() -> None:
    args = parse_args()
    jql_query = resolve_jql(args.jql)

    if not jql_query:
        raise ValueError("JQL não informado. Use --jql ou configure JIRA_JQL_BASE no .env.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = JiraClient()

    total_steps = 2 + int(args.with_changelog) + int(args.with_comments)
    if not args.skip_test:
        total_steps += 1
    step = 0

    # 4.6 — Pula test_connection quando chamado pela pipeline (--skip-test)
    if not args.skip_test:
        step += 1
        print(f"[{step}/{total_steps}] Validando conexão Jira...")
        user = client.test_connection()
        print(f"Conectado como: {user.get('displayName')} ({user.get('emailAddress')})")

    step += 1
    print(f"[{step}/{total_steps}] Buscando issues...")
    # Se temos cache, buscamos SEM expand=changelog (payload menor, mais rápido).
    # Changelog será buscado apenas para cache-miss issues depois.
    # Sem cache, usamos expand=changelog para embutir na resposta (elimina N requests).
    use_expand = args.with_changelog and not args.db_cache
    raw_issues = client.fetch_issues_raw(
        jql_query,
        fields="key,summary,status,project,assignee,reporter,issuetype,created,updated,resolutiondate,duedate,parent,labels",
        expand="changelog" if use_expand else None,
    )
    print(f"Issues retornadas: {len(raw_issues)}")

    step += 1
    print(f"[{step}/{total_steps}] Mapeando issues...")
    mapped_issues = [map_issue(issue) for issue in raw_issues]
    issues_file = output_dir / "issues_mapped.jsonl"
    write_jsonl(issues_file, mapped_issues)
    print(f"Arquivo gerado: {issues_file}")

    if args.raw:
        raw_file = output_dir / "issues_raw.jsonl"
        write_jsonl(raw_file, raw_issues)
        print(f"Arquivo gerado: {raw_file}")

    if args.with_changelog:
        step += 1
        print(f"[{step}/{total_steps}] Extraindo changelogs...")

        # 4.3 — Carrega cache do banco (1 conexão, 1 cursor reutilizado)
        cached_updated: dict[str, datetime | None] = {}
        cache_conn = None
        cache_cur = None
        if args.db_cache and os.path.exists(args.db_cache):
            import sqlite3
            try:
                cache_conn = sqlite3.connect(args.db_cache, timeout=10)
                cache_cur = cache_conn.cursor()
                cache_cur.execute("SELECT key, updated_at FROM issues")
                for row in cache_cur.fetchall():
                    # 4.2 — Normaliza timestamps ao carregar (comparação segura)
                    cached_updated[row[0]] = _normalize_ts(row[1])
                print(f"  Cache carregado: {len(cached_updated)} issues no banco")
            except Exception as e:
                print(f"  WARN: Não foi possível carregar cache: {e}")
                cache_conn = None
                cache_cur = None

        all_changelogs: list[dict[str, Any]] = []
        # 4.1 — Contadores de cache hit/miss
        cache_hits = 0
        cache_misses = 0
        fetched_from_embed = 0
        fetched_from_api = 0

        # 4.4 — Rastreia issues com cache-hit para pular na ingestão
        cache_hit_keys: list[str] = []

        # Separa issues em: cache-hit vs need-fetch vs already-embedded
        issues_needing_full_fetch = []  # Issues que precisam buscar changelog da API

        for i, issue in enumerate(mapped_issues):
            issue_key = issue.get("jira_key")
            if not issue_key:
                continue

            # 1) Cache hit — issue não mudou desde última sync
            if cached_updated and issue_key in cached_updated:
                # 4.2 — Compara datetime normalizado, não string
                issue_updated_dt = _normalize_ts(issue.get("updated_at_jira", ""))
                cached_dt = cached_updated.get(issue_key)

                if issue_updated_dt and cached_dt and issue_updated_dt == cached_dt:
                    # 4.4 — Cache hit: NÃO carrega changelogs do banco para reescrever em JSONL.
                    # Apenas marca a key como cache-hit. A ingestão vai pular essas issues.
                    cache_hit_keys.append(issue_key)
                    cache_hits += 1
                    continue
                else:
                    cache_misses += 1
            else:
                cache_misses += 1

            # 2) Cache miss — precisa buscar changelog
            if use_expand:
                # expand=changelog ativo (sem db-cache): extrai do payload embutido
                raw_issue = raw_issues[i]
                changelog_data = raw_issue.get("changelog", {})
                total_changelog = changelog_data.get("total", 0)
                histories = changelog_data.get("histories", [])

                if histories:
                    for history in histories:
                        author = history.get("author", {})
                        items = history.get("items", [])
                        for item in items:
                            all_changelogs.append({
                                "issue_key": issue_key,
                                "project_key": issue.get("project_id"),
                                "project_name": issue.get("project_name"),
                                "author_name": author.get("displayName"),
                                "author_avatar_url": (author.get("avatarUrls") or {}).get("48x48", ""),
                                "event_date": history.get("created"),
                                "field": item.get("field"),
                                "from_value": item.get("fromString"),
                                "to_value": item.get("toString"),
                            })
                    fetched_from_embed += 1

                    # Overflow: issue tem mais entries que o embed retornou
                    if total_changelog > len(histories):
                        issues_needing_full_fetch.append(issue)
                else:
                    issues_needing_full_fetch.append(issue)
            else:
                # Sem expand (com db-cache): todas as cache-miss vão para fetch via API
                issues_needing_full_fetch.append(issue)

        if cache_conn:
            cache_conn.close()

        # Fetch paralelo via endpoint dedicado para cache-miss issues (ou overflow quando expand ativo)
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        lock = threading.Lock()
        fetch_errors = []

        def fetch_changelog_for_issue(issue):
            """Busca changelog COMPLETO de uma issue via endpoint dedicado."""
            issue_key = issue.get("jira_key")
            try:
                histories = client.fetch_issue_changelog(str(issue_key))
                results = []
                for history in histories:
                    author = history.get("author", {})
                    items = history.get("items", [])
                    for item in items:
                        results.append({
                            "issue_key": issue_key,
                            "project_key": issue.get("project_id"),
                            "project_name": issue.get("project_name"),
                            "author_name": author.get("displayName"),
                            "author_avatar_url": (author.get("avatarUrls") or {}).get("48x48", ""),
                            "event_date": history.get("created"),
                            "field": item.get("field"),
                            "from_value": item.get("fromString"),
                            "to_value": item.get("toString"),
                        })
                return results
            except Exception as e:
                return {"error": str(e), "issue_key": issue_key}

        if issues_needing_full_fetch:
            # Se expand foi usado, remove changelogs parciais (overflow) antes do fetch completo
            if use_expand:
                overflow_keys = {issue.get("jira_key") for issue in issues_needing_full_fetch}
                all_changelogs = [c for c in all_changelogs if c.get("issue_key") not in overflow_keys]

            max_workers = min(8, len(issues_needing_full_fetch))
            label = "overflow" if use_expand else "cache-miss"
            print(f"  Issues para fetch ({label}): {len(issues_needing_full_fetch)} (workers: {max_workers})")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(fetch_changelog_for_issue, issue): issue for issue in issues_needing_full_fetch}
                done_count = 0

                for future in as_completed(futures):
                    done_count += 1
                    result = future.result()
                    if isinstance(result, dict) and "error" in result:
                        fetch_errors.append(result)
                        print(f"  WARN: Erro em {result['issue_key']}: {result['error'][:100]}")
                    else:
                        with lock:
                            all_changelogs.extend(result)
                            fetched_from_api += 1

                    if done_count % 50 == 0:
                        print(f"  progresso: {done_count}/{len(issues_needing_full_fetch)}")

        if fetch_errors:
            print(f"  WARN: {len(fetch_errors)} issues com erro na extração de changelog")

        changelogs_file = output_dir / "changelogs.jsonl"
        write_jsonl(changelogs_file, all_changelogs)
        print(f"Arquivo gerado: {changelogs_file} ({len(all_changelogs)} eventos)")

        # 4.1 — Log de hit/miss rate
        total_issues = cache_hits + cache_misses
        hit_rate = (cache_hits / total_issues * 100) if total_issues > 0 else 0
        print(f"  Cache: {cache_hits} hits, {cache_misses} misses ({hit_rate:.0f}% hit rate)")
        print(f"  Resumo: {fetched_from_embed} via expand (embutido), {fetched_from_api} via API (overflow), {cache_hits} do cache (pular ingestão)")

        # 4.4 — Salva lista de cache-hit keys para que ingest_to_db pule essas issues
        if cache_hit_keys:
            cache_hits_file = output_dir / "cache_hit_keys.json"
            with cache_hits_file.open("w", encoding="utf-8") as fp:
                json.dump(cache_hit_keys, fp)

    if args.with_comments:
        step += 1
        print(f"[{step}/{total_steps}] Extraindo comentários...")
        all_comments: list[dict[str, Any]] = []
        for idx, issue in enumerate(mapped_issues, start=1):
            issue_id_or_key = issue.get("jira_issue_id") or issue.get("jira_key")
            if not issue_id_or_key:
                continue
            comments = client.fetch_issue_comments(str(issue_id_or_key))
            all_comments.extend(normalize_jira_comments(str(issue.get("jira_key") or ""), comments))
            if idx % 50 == 0:
                print(f"  progresso: {idx}/{len(mapped_issues)} issues")

        comments_file = output_dir / "comments.jsonl"
        write_jsonl(comments_file, all_comments)
        print(f"Arquivo gerado: {comments_file} ({len(all_comments)} comentários)")

    print("Extração concluída.")


if __name__ == "__main__":
    main()
