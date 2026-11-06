from fastapi import HTTPException
from pydantic import BaseModel
from modules.flow.db import get_db_connection
from fastapi import APIRouter

router = APIRouter()


# --- Pydantic Models ---

class BlacklistRuleCreate(BaseModel):
    type: str  # 'author' ou 'field'
    value: str


class BlacklistRuleUpdate(BaseModel):
    value: str | None = None
    enabled: bool | None = None


# --- Blacklist CRUD ---

@router.get("/api/settings/blacklist")
def get_blacklist_rules():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, type, value, enabled, created_at FROM blacklist_rules ORDER BY type, value")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@router.post("/api/settings/blacklist", status_code=201)
def create_blacklist_rule(rule: BlacklistRuleCreate):
    if rule.type not in ('author', 'field'):
        raise HTTPException(status_code=400, detail="type deve ser 'author' ou 'field'")
    if not rule.value.strip():
        raise HTTPException(status_code=400, detail="value não pode ser vazio")

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verifica duplicata
    cursor.execute(
        "SELECT id FROM blacklist_rules WHERE type = ? AND value = ?",
        (rule.type, rule.value.strip())
    )
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Regra já existe")

    cursor.execute(
        "INSERT INTO blacklist_rules (type, value, enabled) VALUES (?, ?, 1)",
        (rule.type, rule.value.strip())
    )
    conn.commit()
    new_id = cursor.lastrowid
    cursor.execute("SELECT id, type, value, enabled, created_at FROM blacklist_rules WHERE id = ?", (new_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)


@router.put("/api/settings/blacklist/{rule_id}")
def update_blacklist_rule(rule_id: int, update: BlacklistRuleUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM blacklist_rules WHERE id = ?", (rule_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    if update.value is not None:
        cursor.execute("UPDATE blacklist_rules SET value = ? WHERE id = ?", (update.value.strip(), rule_id))
    if update.enabled is not None:
        cursor.execute("UPDATE blacklist_rules SET enabled = ? WHERE id = ?", (1 if update.enabled else 0, rule_id))

    conn.commit()
    cursor.execute("SELECT id, type, value, enabled, created_at FROM blacklist_rules WHERE id = ?", (rule_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)


@router.delete("/api/settings/blacklist/{rule_id}")
def delete_blacklist_rule(rule_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM blacklist_rules WHERE id = ?", (rule_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    cursor.execute("DELETE FROM blacklist_rules WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()
    return {"message": "Regra removida com sucesso"}
