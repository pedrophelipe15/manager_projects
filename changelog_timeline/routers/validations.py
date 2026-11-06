from fastapi import HTTPException
from pydantic import BaseModel
from core.db import get_db_connection
from fastapi import APIRouter

router = APIRouter()


class ValidationRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    statuses: str | None = None


@router.get("/api/settings/validations")
def get_validation_rules():
    """Lista regras de validação."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description, enabled, statuses, query_type FROM validation_rules ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@router.put("/api/settings/validations/{rule_id}")
def update_validation_rule(rule_id: str, update: ValidationRuleUpdate):
    """Atualiza uma regra de validação."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM validation_rules WHERE id = ?", (rule_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    if update.name is not None:
        cursor.execute("UPDATE validation_rules SET name = ? WHERE id = ?", (update.name, rule_id))
    if update.description is not None:
        cursor.execute("UPDATE validation_rules SET description = ? WHERE id = ?", (update.description, rule_id))
    if update.enabled is not None:
        cursor.execute("UPDATE validation_rules SET enabled = ? WHERE id = ?", (1 if update.enabled else 0, rule_id))
    if update.statuses is not None:
        cursor.execute("UPDATE validation_rules SET statuses = ? WHERE id = ?", (update.statuses, rule_id))

    conn.commit()
    cursor.execute("SELECT id, name, description, enabled, statuses, query_type FROM validation_rules WHERE id = ?", (rule_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)
