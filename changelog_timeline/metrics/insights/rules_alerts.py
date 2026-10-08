"""Regras de alertas proativos (Onda 5).

Transforma o dashboard de passivo para ativo: detecta situações que
requerem ação imediata sem que o usuário precise procurar.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from .engine import InsightsEngine, Insight


# Configurações padrão (podem ser tornadas configuráveis no futuro)
STALE_DAYS_THRESHOLD = 14       # Issue parada há mais de N dias
NO_ASSIGNEE_DAYS_THRESHOLD = 3  # Issue ativa sem assignee há mais de N dias


def register_alert_rules(engine: InsightsEngine) -> None:
    """Registra todas as regras de alertas na engine."""
    engine.register("alert_stale_issues", rule_stale_issues)
    engine.register("alert_no_assignee", rule_no_assignee)
    engine.register("alert_throughput_dropping", rule_throughput_dropping)
    engine.register("alert_epic_overdue", rule_epic_overdue)
    engine.register("alert_wip_explosion", rule_wip_explosion)


# --- Rules ---

def rule_stale_issues(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Alerta: issues em estado ativo sem mudança de status há N+ dias."""
    cursor = conn.cursor()
    now = datetime.now()
    cutoff = (now - timedelta(days=STALE_DAYS_THRESHOLD)).isoformat()

    active_states = ("In Progress", "Blocked", "Test", "Waiting for Delivery")
    placeholders = ",".join(f"'{s}'" for s in active_states)

    # Busca issues ativas cuja última transição de status foi há muito tempo
    cursor.execute(f'''
        SELECT i.key, i.summary, i.status, i.assignee_name, i.updated_at
        FROM issues i
        WHERE i.project_key = ? AND i.status IN ({placeholders})
          AND i.updated_at IS NOT NULL AND i.updated_at < ?
        ORDER BY i.updated_at ASC
    ''', (project_key, cutoff))
    rows = cursor.fetchall()

    if not rows:
        return []

    stale_count = len(rows)
    top_issues = rows[:5]
    details = ", ".join(f"{r[0]} ({r[2]}, {_days_since(r[4])}d)" for r in top_issues)

    if stale_count >= 5:
        return [Insight(
            category="alert",
            severity="critical",
            title=f"{stale_count} issues paradas há mais de {STALE_DAYS_THRESHOLD} dias",
            description=f"Issues ativas sem atualização recente: {details}"
                        f"{' e mais...' if stale_count > 5 else ''}. "
                        f"Podem estar bloqueadas sem registro ou esquecidas.",
            metric="stale_active_issues",
            value=stale_count,
            threshold=STALE_DAYS_THRESHOLD,
            recommendation="Verificar com os assignees se estão bloqueadas (atualizar status para Blocked) "
                           "ou se o trabalho foi concluído (mover para Done).",
        )]
    elif stale_count >= 2:
        return [Insight(
            category="alert",
            severity="warning",
            title=f"{stale_count} issue(s) sem atualização há {STALE_DAYS_THRESHOLD}+ dias",
            description=f"Issues possivelmente paradas: {details}.",
            metric="stale_active_issues",
            value=stale_count,
            threshold=STALE_DAYS_THRESHOLD,
            recommendation="Verificar status real dessas issues com os responsáveis.",
        )]
    return []


def rule_no_assignee(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Alerta: issues em estado ativo sem assignee."""
    cursor = conn.cursor()

    active_states = ("In Progress", "Blocked", "Test", "Waiting for Delivery")
    placeholders = ",".join(f"'{s}'" for s in active_states)

    cursor.execute(f'''
        SELECT key, summary, status, updated_at
        FROM issues
        WHERE project_key = ? AND status IN ({placeholders})
          AND (assignee_name IS NULL OR assignee_name = '')
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return []

    count = len(rows)
    details = ", ".join(f"{r[0]} ({r[2]})" for r in rows[:4])

    return [Insight(
        category="alert",
        severity="warning" if count <= 3 else "critical",
        title=f"{count} issue(s) ativa(s) sem responsável",
        description=f"Issues em andamento sem assignee: {details}"
                    f"{' e mais...' if count > 4 else ''}. "
                    f"Ninguém está formalmente responsável pelo andamento.",
        metric="active_no_assignee",
        value=count,
        recommendation="Atribuir responsável imediatamente. Issues sem dono tendem a ficar paradas.",
    )]


def rule_throughput_dropping(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Alerta: throughput caindo >40% nas últimas 2 semanas vs média."""
    cursor = conn.cursor()

    cursor.execute('''
        SELECT resolved_at FROM issues
        WHERE project_key = ? AND status = 'Done'
          AND resolved_at IS NOT NULL AND resolved_at != ''
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return []

    by_week: dict[str, int] = defaultdict(int)
    for (resolved_at,) in rows:
        try:
            dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
            iso = dt.isocalendar()
            wk = f"{iso[0]}-W{iso[1]:02d}"
            by_week[wk] += 1
        except (ValueError, TypeError):
            continue

    sorted_weeks = sorted(by_week.keys())
    if len(sorted_weeks) < 6:
        return []

    # Média das 4 semanas anteriores vs últimas 2 semanas
    recent_2 = [by_week[w] for w in sorted_weeks[-2:]]
    prior_4 = [by_week[w] for w in sorted_weeks[-6:-2]]

    avg_recent = sum(recent_2) / len(recent_2) if recent_2 else 0
    avg_prior = sum(prior_4) / len(prior_4) if prior_4 else 0

    if avg_prior == 0:
        return []

    drop_pct = ((avg_prior - avg_recent) / avg_prior) * 100

    if drop_pct >= 50:
        return [Insight(
            category="alert",
            severity="critical",
            title=f"Throughput caiu {drop_pct:.0f}% nas últimas 2 semanas",
            description=f"Média recente: {avg_recent:.1f} items/semana vs média anterior: {avg_prior:.1f}/semana. "
                        f"Queda de mais de 50% na capacidade de entrega.",
            metric="throughput_drop_pct",
            value=round(drop_pct, 0),
            threshold=50,
            recommendation="Investigar causa urgente: bloqueios generalizados, ausências, "
                           "mudança de prioridade, ou issues maiores entrando no fluxo.",
        )]
    elif drop_pct >= 30:
        return [Insight(
            category="alert",
            severity="warning",
            title=f"Throughput em queda: -{drop_pct:.0f}% nas últimas 2 semanas",
            description=f"Média recente: {avg_recent:.1f} items/semana vs anterior: {avg_prior:.1f}/semana. "
                        f"Tendência de desaceleração.",
            metric="throughput_drop_pct",
            value=round(drop_pct, 0),
            threshold=30,
            recommendation="Monitorar na próxima semana. Se persistir, investigar causas.",
        )]
    return []


def rule_epic_overdue(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Alerta: épicos com due date já vencida e itens restantes."""
    cursor = conn.cursor()
    now = datetime.now()

    cursor.execute('''
        SELECT 
            parent.key, parent.summary, parent.due_date, parent.issuetype_name,
            COUNT(child.key) as total,
            SUM(CASE WHEN child.status = 'Done' THEN 1 ELSE 0 END) as done
        FROM issues child
        INNER JOIN issues parent ON child.parent_key = parent.key
        WHERE child.project_key = ?
          AND parent.status != 'Done'
          AND parent.due_date IS NOT NULL AND parent.due_date != ''
        GROUP BY parent.key
        HAVING total > done
    ''', (project_key,))
    rows = cursor.fetchall()

    overdue = []
    for key, summary, due_date, issue_type, total, done in rows:
        try:
            due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00")).replace(tzinfo=None)
            days_overdue = (now - due_dt).days
            if days_overdue > 0:
                overdue.append((key, summary, total - done, days_overdue, issue_type))
        except (ValueError, TypeError):
            continue

    if not overdue:
        return []

    overdue.sort(key=lambda x: -x[3])
    details = ", ".join(f"{e[0]} ({e[2]} restantes, {e[3]}d atrasado)" for e in overdue[:3])
    type_label = overdue[0][4] or "item"

    return [Insight(
        category="alert",
        severity="critical",
        title=f"{len(overdue)} {type_label}(s) com prazo vencido",
        description=f"Issues-pai atrasadas com itens pendentes: {details}"
                    f"{' e mais...' if len(overdue) > 3 else ''}.",
        metric="parent_overdue",
        value=len(overdue),
        recommendation="Renegociar prazo com stakeholder ou reduzir escopo (mover itens para próximo ciclo).",
    )]


def rule_wip_explosion(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Alerta: WIP total do projeto muito alto (>2x throughput semanal)."""
    cursor = conn.cursor()

    active_states = ("In Progress", "Blocked", "Test", "Waiting for Delivery")
    placeholders = ",".join(f"'{s}'" for s in active_states)

    cursor.execute(f'''
        SELECT COUNT(*) FROM issues
        WHERE project_key = ? AND status IN ({placeholders})
    ''', (project_key,))
    wip_total = cursor.fetchone()[0]

    if wip_total == 0:
        return []

    # Throughput médio semanal (últimas 8 semanas)
    cutoff = (datetime.now() - timedelta(weeks=8)).isoformat()
    cursor.execute('''
        SELECT COUNT(*) FROM issues
        WHERE project_key = ? AND status = 'Done'
          AND resolved_at IS NOT NULL AND resolved_at >= ?
    ''', (project_key, cutoff))
    done_8w = cursor.fetchone()[0]
    throughput_weekly = done_8w / 8 if done_8w > 0 else 0

    if throughput_weekly == 0:
        return []

    ratio = wip_total / throughput_weekly

    if ratio > 3:
        return [Insight(
            category="alert",
            severity="warning",
            title=f"WIP total elevado: {wip_total} itens ativos ({ratio:.1f}x throughput semanal)",
            description=f"O projeto tem {wip_total} issues em andamento mas entrega ~{throughput_weekly:.0f}/semana. "
                        f"WIP {ratio:.1f}x maior que throughput gera filas longas e lead time alto.",
            metric="wip_ratio",
            value=round(ratio, 1),
            threshold=3.0,
            recommendation="Limitar WIP: priorizar conclusão dos itens atuais antes de iniciar novos. "
                           "Meta: WIP ≤ 2x throughput semanal.",
        )]
    return []


# --- Helpers ---

def _days_since(date_str: str) -> int:
    """Calcula dias desde uma data ISO."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
        return (datetime.now() - dt).days
    except (ValueError, TypeError):
        return 0
