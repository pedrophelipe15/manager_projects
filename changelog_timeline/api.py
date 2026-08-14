from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "issues.db")

app = FastAPI(title="Manager Projects API")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/issues")
def get_issues():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Join issues and metrics to get required fields for dashboard
    query = """
        SELECT 
            i.key,
            i.parent_key,
            i.project_key,
            i.assignee_name as assignee,
            i.summary,
            i.status,
            i.created_at,
            i.updated_at,
            i.due_date,
            i.resolved_at,
            m.lead_time_ms,
            m.cycle_time_ms
        FROM issues i
        LEFT JOIN metrics m ON i.key = m.issue_key
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

@app.get("/api/issues/{key}/timeline")
def get_issue_timeline(key: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT 
            author_name,
            author_avatar_url,
            event_date,
            field,
            from_value,
            to_value,
            is_cycle_time_interval
        FROM parsed_changelogs
        WHERE issue_key = ?
        ORDER BY event_date ASC
    """
    cursor.execute(query, (key,))
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

# Serve static files from current directory
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
