"""Extrator hierárquico — cascata de JQLs para Iniciativas, Épicos, Stories e Sub-tasks.

Persiste no hierarchy.db (isolado do issues.db).
- Iniciativas e Épicos: metadados apenas (sem changelog)
- Stories e Sub-tasks: metadados + changelog completo

Uso:
    python export_hierarchy.py --initiative GPPGI-325
    python export_hierarchy.py --epics PSADB-1457,PSADB-1500
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

# Adiciona diretórios ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from jira_client import JiraClient
from hierarchy_db import get_hierarchy_connection, HIERARCHY_DB_PATH


FIELDS_METADATA = "key,summary,status,project,assignee,issuetype,created,updated,resolutiondate,duedate,parent,labels,issuelinks"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extrator hierárquico Jira (Iniciativa → Épico → Story → Sub-task)")
    parser.add_argument("--initiative", default=None, help="Key da iniciativa (ex: GPPGI-325)")
    parser.add_argument("--epics", default=None, help="Keys dos épicos separados por vírgula (ex: PSADB-1457,PSADB-1500)")
    return parser.parse_args()


def map_issue_metadata(raw: dict) -> dict:
    """Extrai metadados de uma issue raw do Jira."""
    fields = raw.get("fields", {})
    
    # Project
    project = fields.get("project", {})
    project_key = project.get("key", "")
    
    # Status
    status_obj = fields.get("status", {})
    status = status_obj.get("name", "") if status_obj else ""
    
    # Issue type
    issuetype = fields.get("issuetype", {})
    issuetype_name = issuetype.get("name", "") if issuetype else ""
    
    # Assignee
    assignee = fields.get("assignee", {})
    assignee_name = assignee.get("displayName", "") if assignee else ""
    
    # Parent
    parent = fields.get("parent", {})
    parent_key = parent.get("key", "") if parent else ""
    
    # Dates
    created = fields.get("created", "")
    updated = fields.get("updated", "")
    resolved = fields.get("resolutiondate", "")
    due_date = fields.get("duedate", "")

    return {
        "key": raw.get("key", ""),
        "summary": fields.get("summary", ""),
        "status": status,
        "issuetype_name": issuetype_name,
        "project_key": project_key,
        "assignee_name": assignee_name,
        "due_date": due_date,
        "created_at": created,
        "updated_at": updated,
        "resolved_at": resolved,
        "parent_key": parent_key,
    }


def extract_changelog_from_raw(raw_issue: dict, issue_meta: dict) -> list[dict]:
    """Extrai changelogs do payload embutido (expand=changelog)."""
    changelog_data = raw_issue.get("changelog", {})
    histories = changelog_data.get("histories", [])
    
    results = []
    for history in histories:
        author = history.get("author", {})
        for item in history.get("items", []):
            results.append({
                "issue_key": issue_meta["key"],
                "project_key": issue_meta["project_key"],
                "author_name": author.get("displayName", ""),
                "author_avatar_url": (author.get("avatarUrls") or {}).get("48x48", ""),
                "event_date": history.get("created", ""),
                "field": item.get("field", ""),
                "from_value": item.get("fromString", ""),
                "to_value": item.get("toString", ""),
            })
    return results


def extract_issue_links(raw_issue: dict, issue_key: str) -> list[dict]:
    """Extrai issue links (blocks, is blocked by, relates to, etc.) do payload raw."""
    fields = raw_issue.get("fields", {})
    links = fields.get("issuelinks", []) or []
    result = []
    for link in links:
        link_type = link.get("type", {})
        if "inwardIssue" in link:
            result.append({
                "issue_key": issue_key,
                "linked_key": link["inwardIssue"].get("key", ""),
                "direction": "inward",
                "relation": link_type.get("inward", ""),
            })
        elif "outwardIssue" in link:
            result.append({
                "issue_key": issue_key,
                "linked_key": link["outwardIssue"].get("key", ""),
                "direction": "outward",
                "relation": link_type.get("outward", ""),
            })
    return result


def main():
    args = parse_args()
    
    if not args.initiative and not args.epics:
        print("ERRO: Forneça --initiative ou --epics")
        sys.exit(1)

    client = JiraClient()
    start_time = time.time()
    
    print("=" * 60)
    print("EXTRATOR HIERÁRQUICO")
    print("=" * 60)

    # Valida conexão
    user = client.test_connection()
    print(f"Conectado como: {user.get('displayName')}")
    print()

    # ===== PASSO 1: Busca Iniciativa (se fornecida) =====
    initiatives_data = []
    epic_keys_to_fetch = []

    if args.initiative:
        print(f"[1/4] Buscando iniciativa: {args.initiative}")
        jql = f"key = {args.initiative}"
        raw_initiatives = client.fetch_issues_raw(jql, fields=FIELDS_METADATA)
        
        if not raw_initiatives:
            print(f"  ERRO: Iniciativa {args.initiative} não encontrada!")
            sys.exit(1)
        
        for raw in raw_initiatives:
            initiatives_data.append(map_issue_metadata(raw))
        
        print(f"  Iniciativa encontrada: {initiatives_data[0]['summary']}")
        print(f"  Status: {initiatives_data[0]['status']}")
        print()

        # Busca épicos filhos da iniciativa
        print(f"[2/4] Buscando épicos filhos de {args.initiative}...")
        jql_epics = f"(parent in ({args.initiative}) OR linkedissue in ({args.initiative})) AND issuetype = Epic"
        raw_epics = client.fetch_issues_raw(jql_epics, fields=FIELDS_METADATA)
        
        for raw in raw_epics:
            meta = map_issue_metadata(raw)
            meta["parent_key"] = args.initiative  # Força parent para a iniciativa
            epic_keys_to_fetch.append(meta["key"])
            initiatives_data.append(None)  # placeholder
        
        epics_data = [map_issue_metadata(raw) for raw in raw_epics]
        for epic in epics_data:
            epic["parent_key"] = args.initiative
        
        print(f"  Épicos encontrados: {len(epics_data)}")
        for e in epics_data:
            print(f"    - {e['key']}: {e['summary']} [{e['status']}]")
        print()
    else:
        # Épicos fornecidos diretamente
        epic_keys_list = [k.strip() for k in args.epics.split(",") if k.strip()]
        print(f"[1/4] Buscando {len(epic_keys_list)} épico(s)...")
        jql = f"key in ({','.join(epic_keys_list)})"
        raw_epics = client.fetch_issues_raw(jql, fields=FIELDS_METADATA)
        epics_data = [map_issue_metadata(raw) for raw in raw_epics]
        epic_keys_to_fetch = [e["key"] for e in epics_data]
        
        print(f"  Épicos encontrados: {len(epics_data)}")
        for e in epics_data:
            print(f"    - {e['key']}: {e['summary']} [{e['status']}]")
        print()

    # ===== PASSO 2: Busca Stories filhas dos Épicos (COM changelog) =====
    if not epic_keys_to_fetch:
        print("  Nenhum épico encontrado. Encerrando.")
        sys.exit(0)

    step = 3 if args.initiative else 2
    print(f"[{step}/4] Buscando stories filhas dos épicos (com changelog)...")
    
    # Busca em batches de 50 épicos (limite JQL)
    all_stories_raw = []
    for i in range(0, len(epic_keys_to_fetch), 50):
        batch = epic_keys_to_fetch[i:i+50]
        keys_str = ",".join(batch)
        jql_stories = f"(parent in ({keys_str}) OR linkedissue in ({keys_str})) AND issuetype in (Story, Task, Improvement, Bug, Kaizen, Support, Spikes)"
        raw_stories = client.fetch_issues_raw(jql_stories, fields=FIELDS_METADATA, expand="changelog")
        all_stories_raw.extend(raw_stories)
    
    stories_data = []
    stories_changelogs = []
    story_keys = []
    
    for raw in all_stories_raw:
        meta = map_issue_metadata(raw)
        # Se parent_key não veio preenchido, tentar inferir do épico
        if not meta["parent_key"]:
            # Tenta encontrar qual épico é parent via a busca
            for ek in epic_keys_to_fetch:
                if meta["key"].startswith(ek.split("-")[0]):
                    meta["parent_key"] = ek
                    break
        stories_data.append(meta)
        story_keys.append(meta["key"])
        
        # Extrai changelog embutido
        changelogs = extract_changelog_from_raw(raw, meta)
        stories_changelogs.extend(changelogs)
        
        # Verifica overflow (>100 changelog entries)
        changelog_data = raw.get("changelog", {})
        total_cl = changelog_data.get("total", 0)
        histories_count = len(changelog_data.get("histories", []))
        if total_cl > histories_count:
            # Precisa buscar changelog completo via endpoint dedicado
            try:
                full_histories = client.fetch_issue_changelog(meta["key"])
                # Substitui changelogs parciais
                stories_changelogs = [c for c in stories_changelogs if c["issue_key"] != meta["key"]]
                for history in full_histories:
                    author = history.get("author", {})
                    for item in history.get("items", []):
                        stories_changelogs.append({
                            "issue_key": meta["key"],
                            "project_key": meta["project_key"],
                            "author_name": author.get("displayName", ""),
                            "author_avatar_url": (author.get("avatarUrls") or {}).get("48x48", ""),
                            "event_date": history.get("created", ""),
                            "field": item.get("field", ""),
                            "from_value": item.get("fromString", ""),
                            "to_value": item.get("toString", ""),
                        })
            except Exception as e:
                print(f"    WARN: Overflow changelog para {meta['key']}: {e}")

    print(f"  Stories encontradas: {len(stories_data)}")
    print(f"  Changelogs extraídos: {len(stories_changelogs)} eventos")
    
    # Distribui stories por épico
    stories_by_epic = {}
    for s in stories_data:
        pk = s.get("parent_key", "?")
        stories_by_epic.setdefault(pk, []).append(s)
    for ek, stories in stories_by_epic.items():
        print(f"    - {ek}: {len(stories)} stories")
    print()

    # ===== PASSO 3: Busca Sub-tasks das Stories (COM changelog) =====
    step = 4 if args.initiative else 3
    print(f"[{step}/4] Buscando sub-tasks das stories (com changelog)...")
    
    all_subtasks_raw = []
    subtasks_changelogs = []
    
    if story_keys:
        for i in range(0, len(story_keys), 100):
            batch = story_keys[i:i+100]
            keys_str = ",".join(batch)
            jql_subtasks = f"parent in ({keys_str})"
            raw_subtasks = client.fetch_issues_raw(jql_subtasks, fields=FIELDS_METADATA, expand="changelog")
            all_subtasks_raw.extend(raw_subtasks)
    
    subtasks_data = []
    for raw in all_subtasks_raw:
        meta = map_issue_metadata(raw)
        subtasks_data.append(meta)
        
        changelogs = extract_changelog_from_raw(raw, meta)
        subtasks_changelogs.extend(changelogs)
        
        # Overflow check
        changelog_data = raw.get("changelog", {})
        total_cl = changelog_data.get("total", 0)
        histories_count = len(changelog_data.get("histories", []))
        if total_cl > histories_count:
            try:
                full_histories = client.fetch_issue_changelog(meta["key"])
                subtasks_changelogs = [c for c in subtasks_changelogs if c["issue_key"] != meta["key"]]
                for history in full_histories:
                    author = history.get("author", {})
                    for item in history.get("items", []):
                        subtasks_changelogs.append({
                            "issue_key": meta["key"],
                            "project_key": meta["project_key"],
                            "author_name": author.get("displayName", ""),
                            "author_avatar_url": (author.get("avatarUrls") or {}).get("48x48", ""),
                            "event_date": history.get("created", ""),
                            "field": item.get("field", ""),
                            "from_value": item.get("fromString", ""),
                            "to_value": item.get("toString", ""),
                        })
            except Exception as e:
                print(f"    WARN: Overflow changelog para {meta['key']}: {e}")

    print(f"  Sub-tasks encontradas: {len(subtasks_data)}")
    print(f"  Changelogs extraídos: {len(subtasks_changelogs)} eventos")
    print()

    # ===== Extrai Issue Links de todos os níveis =====
    all_issue_links = []

    # Links das iniciativas
    if args.initiative:
        for raw in raw_initiatives:
            key = raw.get("key", "")
            all_issue_links.extend(extract_issue_links(raw, key))

    # Links dos épicos
    for raw in raw_epics:
        key = raw.get("key", "")
        all_issue_links.extend(extract_issue_links(raw, key))

    # Links das stories
    for raw in all_stories_raw:
        key = raw.get("key", "")
        all_issue_links.extend(extract_issue_links(raw, key))

    # Links das sub-tasks
    for raw in all_subtasks_raw:
        key = raw.get("key", "")
        all_issue_links.extend(extract_issue_links(raw, key))

    print(f"  Issue links extraídos: {len(all_issue_links)}")

    # ===== PASSO 4: Persiste no hierarchy.db =====
    print("Persistindo no hierarchy.db...")
    conn = get_hierarchy_connection()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()

    # Iniciativas
    for ini in initiatives_data:
        if ini is None:
            continue
        cursor.execute('''
            INSERT OR REPLACE INTO h_initiatives 
            (key, summary, status, issuetype_name, project_key, assignee_name, 
             due_date, created_at, updated_at, resolved_at, children_keys, last_synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ini["key"], ini["summary"], ini["status"], ini["issuetype_name"],
            ini["project_key"], ini["assignee_name"], ini["due_date"],
            ini["created_at"], ini["updated_at"], ini["resolved_at"],
            json.dumps(epic_keys_to_fetch), now_iso,
        ))

    # Épicos
    for epic in epics_data:
        children = [s["key"] for s in stories_data if s.get("parent_key") == epic["key"]]
        cursor.execute('''
            INSERT OR REPLACE INTO h_epics
            (key, summary, status, issuetype_name, project_key, assignee_name,
             due_date, created_at, updated_at, resolved_at, parent_key, children_keys, last_synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            epic["key"], epic["summary"], epic["status"], epic["issuetype_name"],
            epic["project_key"], epic["assignee_name"], epic["due_date"],
            epic["created_at"], epic["updated_at"], epic["resolved_at"],
            epic.get("parent_key", ""), json.dumps(children), now_iso,
        ))

    # Stories
    for story in stories_data:
        cursor.execute('''
            INSERT OR REPLACE INTO h_stories
            (key, summary, status, issuetype_name, project_key, assignee_name,
             due_date, created_at, updated_at, resolved_at, parent_key, last_synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            story["key"], story["summary"], story["status"], story["issuetype_name"],
            story["project_key"], story["assignee_name"], story["due_date"],
            story["created_at"], story["updated_at"], story["resolved_at"],
            story.get("parent_key", ""), now_iso,
        ))

    # Sub-tasks
    for sub in subtasks_data:
        cursor.execute('''
            INSERT OR REPLACE INTO h_subtasks
            (key, summary, status, issuetype_name, project_key, assignee_name,
             due_date, created_at, updated_at, resolved_at, parent_key, last_synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            sub["key"], sub["summary"], sub["status"], sub["issuetype_name"],
            sub["project_key"], sub["assignee_name"], sub["due_date"],
            sub["created_at"], sub["updated_at"], sub["resolved_at"],
            sub.get("parent_key", ""), now_iso,
        ))

    # Changelogs (stories + subtasks)
    all_changelogs = stories_changelogs + subtasks_changelogs
    
    # Delete existing changelogs for these issues
    all_cl_keys = list(set(c["issue_key"] for c in all_changelogs))
    for i in range(0, len(all_cl_keys), 500):
        batch = all_cl_keys[i:i+500]
        ph = ",".join(["?" for _ in batch])
        cursor.execute(f"DELETE FROM h_changelogs WHERE issue_key IN ({ph})", batch)
    
    # Insert changelogs
    if all_changelogs:
        cursor.executemany('''
            INSERT INTO h_changelogs 
            (issue_key, project_key, author_name, author_avatar_url, event_date, field, from_value, to_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', [
            (c["issue_key"], c["project_key"], c["author_name"], c["author_avatar_url"],
             c["event_date"], c["field"], c["from_value"], c["to_value"])
            for c in all_changelogs
        ])

    # Issue Links — delete existing and insert fresh
    all_link_keys = list(set(lk["issue_key"] for lk in all_issue_links))
    for i in range(0, len(all_link_keys), 500):
        batch = all_link_keys[i:i+500]
        ph = ",".join(["?" for _ in batch])
        cursor.execute(f"DELETE FROM h_issue_links WHERE issue_key IN ({ph})", batch)

    if all_issue_links:
        cursor.executemany('''
            INSERT INTO h_issue_links (issue_key, linked_key, direction, relation)
            VALUES (?, ?, ?, ?)
        ''', [
            (lk["issue_key"], lk["linked_key"], lk["direction"], lk["relation"])
            for lk in all_issue_links
        ])

    # Sync history
    elapsed = round(time.time() - start_time, 1)
    cursor.execute('''
        INSERT INTO h_sync_history 
        (initiative_key, started_at, finished_at, duration_seconds,
         initiatives_count, epics_count, stories_count, subtasks_count, changelogs_count, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'success')
    ''', (
        args.initiative or ",".join(epic_keys_to_fetch),
        datetime.now().isoformat(), datetime.now().isoformat(), elapsed,
        len([i for i in initiatives_data if i]), len(epics_data),
        len(stories_data), len(subtasks_data), len(all_changelogs),
    ))

    conn.commit()
    conn.close()

    # ===== RESUMO =====
    print()
    print("=" * 60)
    print("EXTRAÇÃO CONCLUÍDA")
    print("=" * 60)
    print(f"  Tempo total: {elapsed}s")
    print(f"  Iniciativas: {len([i for i in initiatives_data if i])}")
    print(f"  Épicos: {len(epics_data)}")
    print(f"  Stories: {len(stories_data)}")
    print(f"  Sub-tasks: {len(subtasks_data)}")
    print(f"  Changelogs: {len(all_changelogs)} eventos")
    print(f"  Issue Links: {len(all_issue_links)}")
    print(f"  Banco: {HIERARCHY_DB_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
