"""Dados iniciais (seed): regras de blacklist e regras de validação padrão.

Regra preservada do código antigo: só semeia se a tabela estiver VAZIA; e garante
a regra 'story_stale_active_subtask' em bancos já populados.
Diferença intencional: antes o seed rodava a CADA subida do servidor (regras
apagadas pelo usuário voltavam ao reiniciar); agora roda uma única vez.
"""

BLACKLIST_DEFAULTS = [
    ("author", "Checklists for Jira (Pro) by HeroCoders"),
    ("field", "Attachment"),
    ("field", "labels"),
    ("field", "IssueParentAssociation"),
    ("field", "Checklist Text"),
    ("field", "Checklist Completed"),
    ("field", "Checklist Text (view only)"),
]

_STALE = (
    "story_stale_active_subtask", "Story parada com subtask ativa",
    "Stories em status não-ativo (Open, To do, Backlog, Refinement) que possuem ao menos uma "
    "subtask em andamento. Indica que a story deveria ter sido iniciada no Jira.",
    "In Progress,Blocked,Test,Waiting for Delivery", "story_stale_active_subtask",
)

VALIDATION_DEFAULTS = [
    ("due_date_parent_vs_subtask", "Due Date: Story anterior às Subtasks",
     "Issues onde a due date da Story/parent é anterior à due date de subtasks em andamento.",
     "In Progress,Blocked,Waiting for Delivery", "due_date_parent"),
    ("due_date_empty", "Due Date: Sem preenchimento",
     "Issues ativas sem due date definida.",
     "In Progress,Blocked", "due_date_empty"),
    ("done_without_metrics", "Done: Sem Lead Time e Cycle Time",
     "Issues Done sem métricas calculadas.",
     "Done", "done_no_metrics"),
    ("active_without_cycle", "In Progress/Blocked: Sem Cycle Time",
     "Issues ativas sem cycle time calculado.",
     "In Progress,Blocked", "active_no_cycle"),
    ("active_without_assignee", "In Progress/Blocked: Sem Assignee",
     "Issues ativas sem responsável atribuído.",
     "In Progress,Blocked", "active_no_assignee"),
    _STALE,
]

_INSERT_RULE = (
    "INSERT INTO validation_rules (id, name, description, statuses, query_type) VALUES (?, ?, ?, ?, ?)"
)


def upgrade(conn):
    if conn.execute("SELECT COUNT(*) FROM blacklist_rules").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO blacklist_rules (type, value, enabled) VALUES (?, ?, 1)", BLACKLIST_DEFAULTS
        )
    if conn.execute("SELECT COUNT(*) FROM validation_rules").fetchone()[0] == 0:
        conn.executemany(_INSERT_RULE, VALIDATION_DEFAULTS)
    if conn.execute("SELECT COUNT(*) FROM validation_rules WHERE id = ?", (_STALE[0],)).fetchone()[0] == 0:
        conn.execute(_INSERT_RULE, _STALE)
