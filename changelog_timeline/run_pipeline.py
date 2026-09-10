"""Pipeline completa: lê projects.yaml, executa extração do Jira e ingestão no SQLite.

Entrypoint CLI para automação/cron. Espelha a lógica do sync HTTP (`_run_sync` em
api.py): para cada projeto, combina as pipelines (active/done/delta) numa única JQL
com OR (eliminando duplicatas), extrai uma única vez com changelog + cache de banco,
e ingere aplicando os exclude_statuses do projeto.

Formato esperado do projects.yaml (novo):

    projects:
      - key: REYK
        name: PS - REYKJAVIK
        enabled: true            # opcional (default True)
        exclude_statuses: [Canceled, Reject, ...]
        pipelines:
          active: {name: "...", jql: "..."}
          done:   {name: "...", jql: "..."}
          delta:  {name: "...", jql: "..."}
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_YAML = BASE_DIR / "projects.yaml"
EXPORTER_DIR = BASE_DIR / "exporter_jira"
DB_PATH = BASE_DIR / "issues.db"

# Ordem canônica das pipelines a combinar (mesma usada pelo sync HTTP)
PIPELINE_ORDER = ["active", "done", "delta"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Orquestra extração Jira + ingestão no SQLite a partir do projects.yaml"
    )
    parser.add_argument(
        "--projects-file",
        default=str(PROJECTS_YAML),
        help="Caminho para o arquivo projects.yaml (default: projects.yaml na raiz)",
    )
    parser.add_argument(
        "--project-key",
        default=None,
        help="Executa apenas o projeto com esta key (default: todos os habilitados)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Limpa o banco antes da ingestão (full reload de todos os projetos)",
    )
    parser.add_argument(
        "--with-comments",
        action="store_true",
        help="Também extrai comentários das issues",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Também salva payload bruto das issues",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Desativa o cache de changelog por banco (--db-cache). Força re-extração completa.",
    )
    return parser.parse_args()


def load_projects(yaml_path: str, filter_key: str | None = None) -> list[dict[str, Any]]:
    """Carrega projetos do YAML, filtrando por key se especificado."""
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de projetos não encontrado: {path}")

    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}

    projects = data.get("projects", [])

    # Filtra apenas habilitados
    enabled = [p for p in projects if p.get("enabled", True)]

    if filter_key:
        enabled = [p for p in enabled if p.get("key") == filter_key]
        if not enabled:
            raise ValueError(f"Projeto com key '{filter_key}' não encontrado ou desabilitado.")

    return enabled


def build_merged_jql(project: dict[str, Any]) -> tuple[str, list[str]]:
    """Combina as pipelines (active/done/delta) numa única JQL com OR.

    Retorna (merged_jql, nomes_das_pipelines). A JQL combinada elimina
    duplicatas automaticamente numa única extração.
    """
    pipelines = project.get("pipelines", {}) or {}
    jql_parts: list[str] = []
    pipeline_names: list[str] = []

    for pipe_key in PIPELINE_ORDER:
        pipe = pipelines.get(pipe_key)
        if not pipe:
            continue
        pipe_jql = (pipe.get("jql") or "").strip()
        if pipe_jql:
            jql_parts.append(f"({pipe_jql})")
            pipeline_names.append(pipe.get("name", pipe_key))

    merged = " OR ".join(jql_parts)
    return merged, pipeline_names


def run_extraction(
    project: dict[str, Any],
    output_dir: Path,
    with_comments: bool,
    raw: bool,
    use_cache: bool,
) -> bool:
    """Executa export_jira.py para um projeto usando a JQL combinada das pipelines."""
    key = project.get("key", "unknown")
    merged_jql, pipeline_names = build_merged_jql(project)

    if not merged_jql:
        print(f"  AVISO: Projeto {key} sem JQLs válidas nas pipelines. Pulando.")
        return False

    print(f"  Pipelines combinadas ({len(pipeline_names)}): {', '.join(pipeline_names)}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # export_jira.py aceita a JQL como literal OU caminho de arquivo .txt.
    # Gravamos em arquivo para evitar problemas de quoting/escape na linha de comando.
    jql_file = EXPORTER_DIR / f"_pipeline_{key}_{os.getpid()}.txt"
    jql_file.write_text(merged_jql, encoding="utf-8")

    cmd = [
        sys.executable,
        str(EXPORTER_DIR / "export_jira.py"),
        "--jql", str(jql_file),
        "--output-dir", str(output_dir),
        "--with-changelog",
    ]
    if use_cache:
        cmd.extend(["--db-cache", str(DB_PATH)])
    if with_comments:
        cmd.append("--with-comments")
    if raw:
        cmd.append("--raw")

    print(f"  Comando: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, cwd=str(EXPORTER_DIR), capture_output=True, text=True, timeout=1800
        )
    finally:
        try:
            jql_file.unlink()
        except OSError:
            pass

    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            print(f"    {line}")

    if result.returncode != 0:
        print(f"  ERRO na extração (exit code {result.returncode}):")
        if result.stderr:
            for line in result.stderr.strip().split("\n"):
                print(f"    {line}")
        return False

    return True


def run_ingestion(input_dir: Path, exclude_statuses: list[str], clear: bool) -> bool:
    """Executa ingest_to_db.py para popular o SQLite."""
    cmd = [
        sys.executable,
        str(BASE_DIR / "ingest_to_db.py"),
        "--input-dir", str(input_dir),
        "--db-path", str(DB_PATH),
    ]
    if clear:
        cmd.append("--clear")
    if exclude_statuses:
        cmd.extend(["--exclude-statuses", ",".join(exclude_statuses)])

    print(f"  Comando: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)

    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            print(f"    {line}")

    if result.returncode != 0:
        print(f"  ERRO na ingestão (exit code {result.returncode}):")
        if result.stderr:
            for line in result.stderr.strip().split("\n"):
                print(f"    {line}")
        return False

    return True


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("  PIPELINE: Extração Jira → Ingestão SQLite")
    print("=" * 60)

    projects = load_projects(args.projects_file, args.project_key)
    print(f"\nProjetos a processar: {len(projects)}")
    for p in projects:
        print(f"  - [{p.get('key')}] {p.get('name')}")

    # Diretório base para output dos extratos
    output_base = BASE_DIR / "output"
    output_base.mkdir(parents=True, exist_ok=True)

    success_count = 0
    error_count = 0

    for idx, project in enumerate(projects, start=1):
        key = project.get("key", "unknown")
        name = project.get("name", "")

        print(f"\n{'─' * 60}")
        print(f"[{idx}/{len(projects)}] Processando: [{key}] {name}")
        print(f"{'─' * 60}")

        # Cada projeto gera output em subpasta própria
        project_output_dir = output_base / key
        project_output_dir.mkdir(parents=True, exist_ok=True)

        # Fase 1: Extração (JQL combinada das pipelines)
        print("\n  ► Fase 1: Extração do Jira")
        extraction_ok = run_extraction(
            project,
            project_output_dir,
            with_comments=args.with_comments,
            raw=args.raw,
            use_cache=not args.no_cache,
        )

        if not extraction_ok:
            print(f"  ✗ Extração falhou para [{key}]. Pulando ingestão.")
            error_count += 1
            continue

        # Fase 2: Ingestão
        print("\n  ► Fase 2: Ingestão no SQLite")
        # --clear apenas no primeiro projeto quando solicitado
        should_clear = args.clear and idx == 1
        exclude_statuses = project.get("exclude_statuses", []) or []
        ingestion_ok = run_ingestion(project_output_dir, exclude_statuses, clear=should_clear)

        if not ingestion_ok:
            print(f"  ✗ Ingestão falhou para [{key}].")
            error_count += 1
            continue

        print(f"\n  ✓ [{key}] processado com sucesso.")
        success_count += 1

    # Resumo final
    print(f"\n{'=' * 60}")
    print(f"  RESUMO")
    print(f"{'=' * 60}")
    print(f"  Sucesso: {success_count}/{len(projects)}")
    if error_count:
        print(f"  Erros:   {error_count}/{len(projects)}")
    print(f"  Banco:   {DB_PATH}")
    print(f"{'=' * 60}")

    if error_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
