import sqlite3
import random
import datetime

# Database setup
DB_PATH = 'issues.db'

def setup_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create issues table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS issues (
        key TEXT PRIMARY KEY,
        summary TEXT,
        issuetype_name TEXT,
        issuetype_hierarchy_level INTEGER,
        status TEXT,
        project_key TEXT,
        project_name TEXT,
        parent_key TEXT,
        assignee_name TEXT,
        reporter_name TEXT,
        labels TEXT,
        created_at TEXT,
        updated_at TEXT,
        due_date TEXT,
        resolved_at TEXT,
        executors_teams TEXT,
        pagseguro_teams TEXT,
        start_date TEXT
    )
    ''')
    
    # Create metrics table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS metrics (
        issue_key TEXT PRIMARY KEY,
        project_key TEXT,
        project_name TEXT,
        parent_key TEXT,
        status TEXT,
        created_at TEXT,
        updated_at TEXT,
        due_date TEXT,
        resolved_at TEXT,
        lead_time_ms INTEGER,
        cycle_time_ms INTEGER,
        FOREIGN KEY(issue_key) REFERENCES issues(key)
    )
    ''')
    
    # Create parsed_changelogs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS parsed_changelogs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        issue_key TEXT,
        project_key TEXT,
        project_name TEXT,
        author_name TEXT,
        author_avatar_url TEXT,
        event_date TEXT,
        field TEXT,
        from_value TEXT,
        to_value TEXT,
        is_cycle_time_interval BOOLEAN,
        FOREIGN KEY(issue_key) REFERENCES issues(key)
    )
    ''')
    
    # Clear existing data for fresh mock
    cursor.execute('DELETE FROM parsed_changelogs')
    cursor.execute('DELETE FROM metrics')
    cursor.execute('DELETE FROM issues')
    
    conn.commit()
    return conn

def generate_random_date(start_date, end_date):
    time_between_dates = end_date - start_date
    days_between_dates = time_between_dates.days
    if days_between_dates <= 0:
        return start_date
    random_number_of_days = random.randrange(days_between_dates)
    random_date = start_date + datetime.timedelta(days=random_number_of_days, hours=random.randint(0,23))
    return random_date

def run_mock_load():
    print("Iniciando Carga Full de 5.000 registros...")
    conn = setup_db()
    cursor = conn.cursor()
    
    now = datetime.datetime.now()
    one_year_ago = now - datetime.timedelta(days=365)
    
    statuses = ['Open', 'In Progress', 'Blocked', 'Done']
    users = ['João Silva', 'Maria Souza', 'Carlos Oliveira', 'Ana Lima']
    projects = [
        {"key": "STN", "name": "PS - San Antonio"},
        {"key": "CBL", "name": "Core Banking"},
        {"key": "PAY", "name": "Payments Flow"},
        {"key": "MNG", "name": "Management Tools"}
    ]
    
    issues_data = []
    metrics_data = []
    changelogs_data = []
    
    # Arrays para guardar chaves de pais
    epics_by_project = {"STN": [], "CBL": [], "PAY": [], "MNG": []}
    stories_by_project = {"STN": [], "CBL": [], "PAY": [], "MNG": []}
    
    issue_counter = 1
    
    for i in range(1, 5001):
        project = random.choice(projects)
        p_key = project["key"]
        p_name = project["name"]
        
        key = f"{p_key}-{issue_counter}"
        issue_counter += 1
        
        # Decide hierarchylevel based on ID to simulate tree
        # 5% Epics, 65% Stories, 30% Subtasks
        rand_type = random.random()
        parent_key = None
        
        if rand_type < 0.05:
            issuetype_name = "Epic"
            issuetype_hierarchy_level = 1
            epics_by_project[p_key].append(key)
        elif rand_type < 0.70:
            issuetype_name = "Story"
            issuetype_hierarchy_level = 0
            # Link to random epic of the same project if exists
            if epics_by_project[p_key]:
                parent_key = random.choice(epics_by_project[p_key])
            stories_by_project[p_key].append(key)
        else:
            issuetype_name = "Sub-task"
            issuetype_hierarchy_level = -1
            # Link to random story of the same project if exists
            if stories_by_project[p_key]:
                parent_key = random.choice(stories_by_project[p_key])
        
        # Randomize core dates
        created_at = generate_random_date(one_year_ago, now - datetime.timedelta(days=30))
        
        is_resolved = random.choice([True, True, True, False]) # 75% resolved
        status = 'Done' if is_resolved else random.choice(['Open', 'In Progress', 'Blocked'])
        
        resolved_at = None
        if is_resolved:
            resolved_at = generate_random_date(created_at, now)
            updated_at = resolved_at
        else:
            updated_at = generate_random_date(created_at, now)
            
        assignee = random.choice(users)
        
        # Calculate Mock Metrics
        lead_time_ms = 0
        if is_resolved:
            lead_time_ms = int((resolved_at - created_at).total_seconds() * 1000)
            
        cycle_time_ms = 0
        if lead_time_ms > 0:
            cycle_time_ms = int(lead_time_ms * random.uniform(0.2, 0.8))
        elif status == 'In Progress' or status == 'Blocked':
            elapsed = int((now - created_at).total_seconds() * 1000)
            cycle_time_ms = int(elapsed * random.uniform(0.1, 0.5))

        # Prepare Issue (18 columns total now because we split issuetype)
        issues_data.append((
            key, f"Mocked {issuetype_name} {issue_counter}", issuetype_name, issuetype_hierarchy_level, status, p_key, p_name, parent_key, assignee, "Reporter X", 
            '["stn_demanda_interna"]', created_at.isoformat(), updated_at.isoformat(), None, 
            resolved_at.isoformat() if resolved_at else None, "Team A", "PagSeguro B", created_at.isoformat()
        ))
        
        # Prepare Metric
        metrics_data.append((
            key, p_key, p_name, parent_key, status, created_at.isoformat(), updated_at.isoformat(), None, 
            resolved_at.isoformat() if resolved_at else None, lead_time_ms, cycle_time_ms
        ))
        
        # Prepare Changelog (just 1 or 2 events to prove structure)
        changelogs_data.append((
            key, p_key, p_name, assignee, "", created_at.isoformat(), "status", "Open", "In Progress", True
        ))
        
        if is_resolved:
            changelogs_data.append((
                key, p_key, p_name, assignee, "", resolved_at.isoformat(), "status", "In Progress", "Done", True
            ))
            
    # Bulk Insert
    cursor.executemany('''
        INSERT INTO issues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', issues_data)
    
    cursor.executemany('''
        INSERT INTO metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', metrics_data)
    
    cursor.executemany('''
        INSERT INTO parsed_changelogs (issue_key, project_key, project_name, author_name, author_avatar_url, event_date, field, from_value, to_value, is_cycle_time_interval)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', changelogs_data)
    
    conn.commit()
    conn.close()
    print("Carga Full concluída com sucesso! 5.000 registros criados no banco SQLite local.")

if __name__ == '__main__':
    run_mock_load()
