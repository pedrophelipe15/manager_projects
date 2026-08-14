import sqlite3
import random
import datetime

DB_PATH = 'issues.db'

def run_delta_sync():
    print("Iniciando Simulação de Delta Sync (Atualizando 20 registros)...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Pega 20 chaves aleatórias que não estão como 'Done'
    cursor.execute("SELECT key, created_at, project_key, project_name FROM issues WHERE status != 'Done' LIMIT 20")
    rows = cursor.fetchall()
    
    if not rows:
        print("Nenhum registro pendente para atualizar.")
        return
        
    now = datetime.datetime.now()
    
    for row in rows:
        key = row[0]
        created_at_str = row[1]
        p_key = row[2]
        p_name = row[3]
        created_at = datetime.datetime.fromisoformat(created_at_str)
        
        # Simula fechamento da issue (resolvida agora)
        new_status = 'Done'
        resolved_at = now
        updated_at = now
        
        # 1. UPSERT (Update) na Tabela Pai (issues)
        cursor.execute('''
            UPDATE issues 
            SET status = ?, updated_at = ?, resolved_at = ?
            WHERE key = ?
        ''', (new_status, updated_at.isoformat(), resolved_at.isoformat(), key))
        
        # 2. DELETE nas tabelas filhas (Limpeza para recalcular)
        cursor.execute('DELETE FROM metrics WHERE issue_key = ?', (key,))
        
        # 3. RECALCULAR Métricas
        lead_time_ms = int((resolved_at - created_at).total_seconds() * 1000)
        cycle_time_ms = int(lead_time_ms * 0.5)
        
        # Insert novas métricas
        cursor.execute('''
            INSERT INTO metrics (issue_key, project_key, project_name, status, created_at, updated_at, resolved_at, lead_time_ms, cycle_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (key, p_key, p_name, new_status, created_at.isoformat(), updated_at.isoformat(), resolved_at.isoformat(), lead_time_ms, cycle_time_ms))
        
        # Insert novo changelog event
        cursor.execute('''
            INSERT INTO parsed_changelogs (issue_key, project_key, project_name, author_name, event_date, field, from_value, to_value, is_cycle_time_interval)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (key, p_key, p_name, "Script Delta Sync", updated_at.isoformat(), "status", "In Progress", "Done", True))
        
        print(f"[{key}] Atualizado para Done. Novos Lead/Cycle Times gravados e Changelog inserido.")
        
    conn.commit()
    conn.close()
    print("Delta Sync concluído! Banco de dados atualizado.")

if __name__ == '__main__':
    run_delta_sync()
