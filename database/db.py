import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

DB_PATH = 'vuln_tracker.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def clean_field(field, sep="\n"):
    if isinstance(field, list):
        # If it's a list of characters (all single-char strings)
        if all(isinstance(x, str) and len(x) == 1 for x in field):
            return "".join(field)
        # If it's a list of lines/strings
        elif all(isinstance(x, str) for x in field):
            return sep.join(field)
        else:
            return str(field)
    elif isinstance(field, str):
        return field
    else:
        return str(field)

def insert_vulnerability(vuln):
    conn = get_db()
    c = conn.cursor()
    for cve_id in vuln['cves']:
        c.execute('''
            INSERT OR IGNORE INTO vulnerabilities
            (id_bulletin, cve_id, produit_name, Date_de_sortie, description, Niveau_de_risqué, severity, risk, processing_time, mitigation, Référence, Date_de_notification)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                vuln['id_bulletin'], cve_id, vuln['produit_name'], vuln['Date_de_sortie'],
                vuln['description'], vuln.get('Niveau_de_risqué', 'Fort'), vuln['cvss_score'],
                vuln.get('risk', 'Important'), vuln.get('processing_time', 5),
                clean_field(vuln.get('mitigation', [])), clean_field(vuln.get('reference', []), sep=", "),
                vuln.get('Date_de_notification', vuln['Date_de_sortie'])
        ))
    conn.commit()
    conn.close()

def insert_client_tracking(id_bulletin, cve_id, client_data):
    """Insert a client tracking row, skipping duplicates gracefully.

    Returns True if a new row was inserted, False if it already existed.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        # Always set default status to 'Open' if not provided
        status = client_data.get('status', 'Open')
        # Always set default Date_de_traitement to today if not provided
        default_treatment_date = datetime.now().strftime('%Y-%m-%d')
        date_traitement = client_data.get('Date_de_traitement', default_treatment_date)
        c.execute('''
            INSERT OR IGNORE INTO client_vuln_tracking
            (id_bulletin, cve_id, client, status, Responsable_resolution, Date_de_traitement, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?)''', (
            id_bulletin,
            cve_id,
            client_data['client'],
            status,
            client_data['Responsable_resolution'],
            date_traitement,
            client_data.get('comment', '')
        ))
        conn.commit()
        # rowcount == 0 when INSERT OR IGNORE skipped due to unique constraint
        return c.rowcount > 0
    finally:
        conn.close()

def get_clients_from_tracking():
    """Get clients from client_vuln_tracking table (legacy function)"""
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT client FROM client_vuln_tracking").fetchall()
    conn.close()
    return [row['client'] for row in rows]

def get_client_names():
    conn = sqlite3.connect('vuln_tracker.db')
    c = conn.cursor()
    c.execute('SELECT name FROM clients')
    names = [row[0] for row in c.fetchall()]
    conn.close()
    return names

def get_clients():
    conn = sqlite3.connect('vuln_tracker.db')
    c = conn.cursor()
    c.execute('SELECT id, name FROM clients')
    clients = [{'id': row[0], 'name': row[1]} for row in c.fetchall()]
    conn.close()
    return clients

def calculate_age_and_sla(date_sortie, date_traitement, processing_time):
    """Calculate age of alert and SLA status"""
    try:
        # Parse dates
        sortie_date = datetime.strptime(date_sortie, '%Y-%m-%d')
        traitement_date = datetime.strptime(date_traitement, '%Y-%m-%d')
        
        # Calculate age in days
        age_days = (traitement_date - sortie_date).days
        
        # Determine SLA status
        if age_days > processing_time:
            sla_status = "Hors délai de remediation"
        else:
            sla_status = "Traité dans le délai"
            
        return age_days, sla_status
    except:
        return 0, "N/A"

def get_client_vulns(client=None, start_date=None, end_date=None):
    conn = get_db()
    # Strip whitespace from parameters
    if client:
        client = client.strip()
    if start_date:
        start_date = start_date.strip()
    if end_date:
        end_date = end_date.strip()
    # Build date filter condition
    date_condition = ""
    query = '''
        SELECT 
            t.id,
            t.client,
            t.id_bulletin,
            t.cve_id,
            v.produit_name,
            v.description,
            v.Date_de_sortie,
            v.risk,
            v.Niveau_de_risqué,
            v.processing_time,
            v.mitigation,
            v.Référence,
            v.Date_de_notification,
            t.status,
            t.Responsable_resolution,
            t.Date_de_traitement,
            t.comment
        FROM client_vuln_tracking t
        JOIN vulnerabilities v
        ON t.id_bulletin = v.id_bulletin AND t.cve_id = v.cve_id
        WHERE 1=1
    '''
    params = []
    if client:
        query += " AND t.client = ?"
        params.append(client)
    if start_date and end_date:
        query += " AND v.Date_de_sortie BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    elif start_date:
        query += " AND v.Date_de_sortie >= ?"
        params.append(start_date)
    elif end_date:
        query += " AND v.Date_de_sortie <= ?"
        params.append(end_date)
    query += " ORDER BY v.Date_de_sortie DESC, t.id_bulletin, t.client, t.cve_id"
    print('DEBUG SQL QUERY:', query)
    print('DEBUG PARAMS:', params)
    rows = conn.execute(query, params).fetchall()
    print('DEBUG ROWS RETURNED:', len(rows))
    conn.close()
    # Group by (id_bulletin, client)
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['id_bulletin'], row['client'])].append(dict(row))
    processed_rows = []
    # Updated status priority with new statuses
    status_priority = {
        'Open': 1, 
        'WIP': 2, 
        'Pending': 3, 
        'NOK': 4,
        'Clos': 5,
        'Clos (Patch cumulative)': 5,
        'Clos (Non concerné)': 5,
        'Clos (Traité)': 5
    }
    
    # Define closed statuses
    closed_statuses = ['Clos', 'Clos (Patch cumulative)', 'Clos (Non concerné)', 'Clos (Traité)']
    
    for (id_bulletin, client), group_rows in grouped.items():
        cves = ', '.join(sorted(set(r['cve_id'] for r in group_rows)))
        all_statuses = [r['status'] for r in group_rows]
        # Determine group status
        group_status = min((s for s in all_statuses), key=lambda s: status_priority.get(s, 99))
        # For date: most recent Date_de_traitement among non-closed, else latest among all
        if group_status in closed_statuses:
            date_traitement = max(r['Date_de_traitement'] for r in group_rows)
            comment = max((r['comment'] for r in group_rows if r['status'] in closed_statuses), default='')
        else:
            date_traitement = max((r['Date_de_traitement'] for r in group_rows if r['status'] not in closed_statuses), default=max(r['Date_de_traitement'] for r in group_rows))
            comment = max((r['comment'] for r in group_rows if r['status'] == group_status), default='')
        # Use the first row for other fields
        base = group_rows[0]
        row_dict = {
            'id': base['id'],
            'client': client,
            'id_bulletin': id_bulletin,
            'cves': cves,
            'produit_name': base['produit_name'],
            'description': base['description'],
            'Date_de_sortie': base['Date_de_sortie'],
            'risk': clean_field(base['risk'], sep='\n'),
            'Niveau_de_risqué': base['Niveau_de_risqué'],
            'processing_time': base['processing_time'],
            'mitigation': clean_field(base['mitigation'], sep='\n'),
            'Référence': clean_field(base['Référence'], sep='\n'),
            'Date_de_notification': base['Date_de_notification'],
            'status': group_status,
            'Responsable_resolution': base['Responsable_resolution'],
            'Date_de_traitement': date_traitement,
            'comment': comment
        }
        # Calculate age and SLA
        age_days, sla_status = calculate_age_and_sla(
            row_dict['Date_de_sortie'], 
            row_dict['Date_de_traitement'], 
            row_dict['processing_time']
        )
        row_dict['age_alerte'] = age_days
        row_dict['sla'] = sla_status
        processed_rows.append(row_dict)
    return processed_rows

def update_client_vuln(row_id, status, comment, date_traitement=None):
    conn = get_db()
    # Define closed statuses
    closed_statuses = ['Clos', 'Clos (Patch cumulative)', 'Clos (Non concerné)', 'Clos (Traité)']
    
    # If a custom date is provided, always use it (even for closed statuses)
    if date_traitement:
        conn.execute(
            "UPDATE client_vuln_tracking SET status = ?, comment = ?, Date_de_traitement = ? WHERE id = ?",
            (status, comment, date_traitement, row_id)
        )
    # If no date provided and status is Open/WIP/Pending/NOK, set to today
    elif status in ('Open', 'WIP', 'Pending', 'NOK'):
        today = datetime.now().strftime('%Y-%m-%d')
        conn.execute(
            "UPDATE client_vuln_tracking SET status = ?, comment = ?, Date_de_traitement = ? WHERE id = ?",
            (status, comment, today, row_id)
        )
    # If no date provided and status is closed, do not change the date
    elif status in closed_statuses:
        conn.execute(
            "UPDATE client_vuln_tracking SET status = ?, comment = ? WHERE id = ?",
            (status, comment, row_id)
        )
    # For any other status, set to today
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        conn.execute(
            "UPDATE client_vuln_tracking SET status = ?, comment = ?, Date_de_traitement = ? WHERE id = ?",
            (status, comment, today, row_id)
        )
    conn.commit()
    conn.close()

def delete_client_vuln(row_id):
    """Delete a vulnerability tracking entry"""
    conn = get_db()
    conn.execute("DELETE FROM client_vuln_tracking WHERE id = ?", (row_id,))
    conn.commit()
    conn.close()

def update_daily_treatment_dates():
    """Update Date_de_traitement to today for all 'Open', 'WIP', 'Pending', or 'NOK' status vulnerabilities, but never for closed statuses."""
    conn = get_db()
    today = datetime.now().strftime('%Y-%m-%d')
    # Only update if status is Open, WIP, Pending, or NOK, and do NOT update if status is closed
    conn.execute("""
        UPDATE client_vuln_tracking 
        SET Date_de_traitement = ? 
        WHERE status IN ('Open', 'WIP', 'Pending', 'NOK')
    """, (today,))
    conn.commit()
    conn.close()
    print(f"✅ Updated treatment dates to {today} for open/wip/pending/nok vulnerabilities")

def delete_client_vuln_group(id_bulletin, client):
    conn = get_db()
    conn.execute("DELETE FROM client_vuln_tracking WHERE id_bulletin = ? AND client = ?", (id_bulletin, client))
    conn.commit()
    conn.close()

def create_clients_products_tables():
    conn = sqlite3.connect('vuln_tracker.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            client_id INTEGER,
            responsible_resolution TEXT DEFAULT 'SOC Team',
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
    ''')
    # Add responsible_resolution column to existing products table if it doesn't exist
    try:
        c.execute('ALTER TABLE products ADD COLUMN responsible_resolution TEXT DEFAULT "SOC Team"')
    except sqlite3.OperationalError:
        # Column already exists
        pass
    conn.commit()
    conn.close()

# CRUD for clients
def add_client(name):
    conn = sqlite3.connect('vuln_tracker.db')
    c = conn.cursor()
    c.execute('INSERT INTO clients (name) VALUES (?)', (name,))
    conn.commit()
    conn.close()

def get_clients():
    conn = sqlite3.connect('vuln_tracker.db')
    c = conn.cursor()
    c.execute('SELECT * FROM clients')
    clients = c.fetchall()
    conn.close()
    return clients

def update_client(client_id, name):
    conn = sqlite3.connect('vuln_tracker.db')
    c = conn.cursor()
    c.execute('UPDATE clients SET name = ? WHERE id = ?', (name, client_id))
    conn.commit()
    conn.close()

def delete_client(client_id):
    conn = sqlite3.connect('vuln_tracker.db')
    c = conn.cursor()
    c.execute('DELETE FROM clients WHERE id = ?', (client_id,))
    conn.commit()
    conn.close()

# CRUD for products
def add_product(name, client_id, responsible_resolution='SOC Team'):
    conn = sqlite3.connect('vuln_tracker.db')
    c = conn.cursor()
    c.execute('INSERT INTO products (name, client_id, responsible_resolution) VALUES (?, ?, ?)', (name, client_id, responsible_resolution))
    conn.commit()
    conn.close()

def get_products(client_id=None):
    conn = sqlite3.connect('vuln_tracker.db')
    c = conn.cursor()
    if client_id:
        c.execute('SELECT * FROM products WHERE client_id = ?', (client_id,))
    else:
        c.execute('SELECT * FROM products')
    products = c.fetchall()
    conn.close()
    return products

def update_product(product_id, name, client_id, responsible_resolution='SOC Team'):
    conn = sqlite3.connect('vuln_tracker.db')
    c = conn.cursor()
    c.execute('UPDATE products SET name = ?, client_id = ?, responsible_resolution = ? WHERE id = ?', (name, client_id, responsible_resolution, product_id))
    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = sqlite3.connect('vuln_tracker.db')
    c = conn.cursor()
    c.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()

def get_clients_with_products():
    """Get all clients with their associated products and responsible resolution for matching"""
    conn = sqlite3.connect('vuln_tracker.db')
    c = conn.cursor()
    
    try:
        # Check if tables exist
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('clients', 'products')")
        tables = [row[0] for row in c.fetchall()]
        
        if 'clients' not in tables or 'products' not in tables:
            print("⚠️ Clients or products tables not found. Creating them...")
            create_clients_products_tables()
            return {}
        
        c.execute('''
            SELECT c.id, c.name as client_name, p.name as product_name, p.responsible_resolution
            FROM clients c
            LEFT JOIN products p ON c.id = p.client_id
            ORDER BY c.name, p.name
        ''')
        rows = c.fetchall()
        
        # Group by client
        clients_data = {}
        for row in rows:
            client_id, client_name, product_name, responsible_resolution = row
            if client_name not in clients_data:
                clients_data[client_name] = []
            if product_name:  # Only add if product exists
                clients_data[client_name].append({
                    'name': product_name,
                    'responsible_resolution': responsible_resolution or 'SOC Team'
                })
        
        return clients_data
        
    except Exception as e:
        print(f"❌ Error getting clients with products: {e}")
        return {}
    finally:
        conn.close()

# KPI Functions for Dashboard
def get_status_distribution(client=None, month=None):
    """Get distribution of vulnerability statuses - COUNT BY BULLETIN-CLIENT PAIRS, NOT INDIVIDUAL CVEs"""
    conn = get_db()
    
    # Use the same logic as get_client_vulns to count bulletin-client pairs
    # This ensures dashboard matches tracker counts
    query = '''
        SELECT 
            t.client,
            t.id_bulletin,
            MIN(t.status) as status
        FROM client_vuln_tracking t
        JOIN vulnerabilities v ON t.id_bulletin = v.id_bulletin AND t.cve_id = v.cve_id
        WHERE 1=1
    '''
    params = []
    
    # Add filters
    if client:
        query += " AND t.client = ?"
        params.append(client)
    if month:
        query += " AND strftime('%Y-%m', v.Date_de_sortie) = ?"
        params.append(month)
    
    query += " GROUP BY t.client, t.id_bulletin ORDER BY t.client, t.id_bulletin"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    # Count statuses from grouped results (bulletin-client pairs)
    if client:
        # Single client - return simple status count
        result = {}
        for row in rows:
            status = row['status']
            result[status] = result.get(status, 0) + 1
        return result
    else:
        # All clients - return nested structure
        result = {}
        for row in rows:
            client_name = row['client']
            status = row['status']
            if client_name not in result:
                result[client_name] = {}
            result[client_name][status] = result[client_name].get(status, 0) + 1
        return result

def get_monthly_trend(client=None, months=6):
    """Get monthly trend data for vulnerabilities - COUNT BY BULLETIN-CLIENT PAIRS"""
    conn = get_db()
    
    # Get bulletin-client pairs grouped by month
    query = '''
        SELECT 
            strftime('%Y-%m', v.Date_de_sortie) as month,
            t.client,
            t.id_bulletin,
            MIN(t.status) as status
        FROM client_vuln_tracking t
        JOIN vulnerabilities v ON t.id_bulletin = v.id_bulletin AND t.cve_id = v.cve_id
        WHERE v.Date_de_sortie >= date('now', '-{} months')
    '''.format(months)
    
    params = []
    if client:
        query += " AND t.client = ?"
        params.append(client)
    
    query += " GROUP BY month, t.client, t.id_bulletin ORDER BY month"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    # Process results by counting bulletin-client pairs per month/status
    result = {}
    for row in rows:
        month = row['month']
        status = row['status']
        
        if month not in result:
            result[month] = {}
        if status not in result[month]:
            result[month][status] = 0
        result[month][status] += 1
    
    return result

def get_sla_compliance(client=None, month=None):
    """Get SLA compliance metrics - Count the EXACT SLA values from tracker table"""
    
    # Use get_client_vulns with the same filters to get the EXACT same data as tracker
    start_date = end_date = None
    if month:
        # Convert month (YYYY-MM) to date range exactly like tracker does
        start_date = f"{month}-01"
        from calendar import monthrange
        year, m = map(int, month.split('-'))
        last_day = monthrange(year, m)[1]
        end_date = f"{month}-{last_day:02d}"
    
    # Get the EXACT same data that tracker displays
    tracker_rows = get_client_vulns(client, start_date, end_date)
    
    # Count the SLA field values directly from tracker data (what user sees)
    result = {'Traité dans le délai': 0, 'Hors délai de remediation': 0}
    
    for row in tracker_rows:
        sla_status = row.get('sla', 'N/A')
        
        # Count ALL SLA values that have been calculated
        if sla_status == 'Traité dans le délai':
            result['Traité dans le délai'] += 1
        elif sla_status == 'Hors délai de remediation':
            result['Hors délai de remediation'] += 1
        # Skip N/A values (usually open items without SLA calculation)
    
    return result

def get_monthly_evolution(client=None, selected_months=None):
    """Get monthly evolution of vulnerability statuses - COUNT BY BULLETIN-CLIENT PAIRS"""
    conn = get_db()
    
    # First get bulletin-client pairs grouped by month
    query = '''
        SELECT 
            strftime('%Y-%m', v.Date_de_sortie) as month,
            strftime('%Y', v.Date_de_sortie) as year,
            CASE strftime('%m', v.Date_de_sortie)
                WHEN '01' THEN 'January'
                WHEN '02' THEN 'February'
                WHEN '03' THEN 'March'
                WHEN '04' THEN 'April'
                WHEN '05' THEN 'May'
                WHEN '06' THEN 'June'
                WHEN '07' THEN 'July'
                WHEN '08' THEN 'August'
                WHEN '09' THEN 'September'
                WHEN '10' THEN 'October'
                WHEN '11' THEN 'November'
                WHEN '12' THEN 'December'
            END as month_name,
            t.client,
            t.id_bulletin,
            MIN(t.status) as status
        FROM client_vuln_tracking t
        JOIN vulnerabilities v ON t.id_bulletin = v.id_bulletin AND t.cve_id = v.cve_id
        WHERE 1=1
    '''
    
    params = []
    
    # Add month filter if specific months are selected
    if selected_months and len(selected_months) > 0:
        month_placeholders = ','.join(['?' for _ in selected_months])
        query += f" AND strftime('%Y-%m', v.Date_de_sortie) IN ({month_placeholders})"
        params.extend(selected_months)
    else:
        # Default to last 6 months if no specific months selected
        query += " AND v.Date_de_sortie >= date('now', '-6 months')"
    
    if client:
        query += " AND t.client = ?"
        params.append(client)
    
    query += '''
        GROUP BY strftime('%Y-%m', v.Date_de_sortie), t.client, t.id_bulletin
        ORDER BY strftime('%Y-%m', v.Date_de_sortie)
    '''
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    # Process results by counting bulletin-client pairs per month/status
    evolution_data = {}
    all_statuses = set()
    all_months = set()
    
    for row in rows:
        month = row['month']
        month_name = row['month_name']
        year = row['year']
        status = row['status']
        
        # Create display month (e.g., "July")
        display_month = f"{month_name}"
        
        if month not in evolution_data:
            evolution_data[month] = {
                'display_name': display_month,
                'year': year,
                'statuses': {}
            }
        
        # Count bulletin-client pairs by status
        if status not in evolution_data[month]['statuses']:
            evolution_data[month]['statuses'][status] = 0
        evolution_data[month]['statuses'][status] += 1
        
        all_statuses.add(status)
        all_months.add(month)
    
    # Ensure all months have all status entries (fill with 0 if missing)
    for month_data in evolution_data.values():
        for status in all_statuses:
            if status not in month_data['statuses']:
                month_data['statuses'][status] = 0
    
    # Sort months chronologically
    sorted_months = sorted(all_months)
    
    return {
        'months': sorted_months,
        'data': evolution_data,
        'statuses': sorted(list(all_statuses)),
        'total_months': len(sorted_months)
    }
    
def get_available_months(client=None):
    """Get list of available months with data"""
    conn = get_db()
    
    query = '''
        SELECT DISTINCT
            strftime('%Y-%m', v.Date_de_sortie) as month,
            strftime('%Y', v.Date_de_sortie) as year,
            CASE strftime('%m', v.Date_de_sortie)
                WHEN '01' THEN 'January'
                WHEN '02' THEN 'February'
                WHEN '03' THEN 'March'
                WHEN '04' THEN 'April'
                WHEN '05' THEN 'May'
                WHEN '06' THEN 'June'
                WHEN '07' THEN 'July'
                WHEN '08' THEN 'August'
                WHEN '09' THEN 'September'
                WHEN '10' THEN 'October'
                WHEN '11' THEN 'November'
                WHEN '12' THEN 'December'
            END as month_name
        FROM client_vuln_tracking t
        JOIN vulnerabilities v ON t.id_bulletin = v.id_bulletin AND t.cve_id = v.cve_id
        WHERE v.Date_de_sortie IS NOT NULL
    '''
    
    params = []
    if client:
        query += " AND t.client = ?"
        params.append(client)
    
    query += " ORDER BY month DESC"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    return [{'month': row['month'], 'display_name': f"{row['month_name']} {row['year']}"} for row in rows]
    
def get_open_vs_closed(client=None, month=None):
    """Get Open vs Clos distribution - COUNT BY BULLETIN-CLIENT PAIRS"""
    conn = get_db()
    
    # First get bulletin-client pairs with their status (like tracker logic)
    # Include all statuses to properly categorize them
    query = '''
        SELECT 
            t.client,
            t.id_bulletin,
            MIN(t.status) as status
        FROM client_vuln_tracking t
        JOIN vulnerabilities v ON t.id_bulletin = v.id_bulletin AND t.cve_id = v.cve_id
        WHERE 1=1
    '''
    params = []
    
    if client:
        query += " AND t.client = ?"
        params.append(client)
    if month:
        query += " AND strftime('%Y-%m', v.Date_de_sortie) = ?"
        params.append(month)
    
    query += " GROUP BY t.client, t.id_bulletin"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    # Count bulletin-client pairs by aggregated status
    result = {'Open': 0, 'Clos': 0}
    
    # Define closed statuses to aggregate
    closed_statuses = ['Clos (Traité)', 'Clos (Non concerné)', 'Clos', 'Clos (Patch cumulative)']
    
    for row in rows:
        status = row['status']
        if status == 'Open':
            result['Open'] += 1
        elif status in closed_statuses:
            result['Clos'] += 1
        # Skip other statuses (WIP, Pending, NOK) for this specific chart
    
    return result
    
def get_comprehensive_table(client=None, selected_months=None):
    """Get comprehensive vulnerability table data by month - COUNT BY BULLETIN-CLIENT PAIRS"""
    conn = get_db()
    
    # First get bulletin-client pairs with their details
    query = '''
        SELECT 
            strftime('%Y-%m', v.Date_de_sortie) as month,
            CASE strftime('%m', v.Date_de_sortie)
                WHEN '01' THEN 'January'
                WHEN '02' THEN 'February'
                WHEN '03' THEN 'March'
                WHEN '04' THEN 'April'
                WHEN '05' THEN 'May'
                WHEN '06' THEN 'June'
                WHEN '07' THEN 'July'
                WHEN '08' THEN 'August'
                WHEN '09' THEN 'September'
                WHEN '10' THEN 'October'
                WHEN '11' THEN 'November'
                WHEN '12' THEN 'December'
            END as month_name,
            t.client,
            t.id_bulletin,
            MIN(v.risk) as risk,
            MIN(v.Niveau_de_risqué) as niveau_risque,
            MIN(t.status) as status
        FROM client_vuln_tracking t
        JOIN vulnerabilities v ON t.id_bulletin = v.id_bulletin AND t.cve_id = v.cve_id
        WHERE 1=1
    '''
    
    params = []
    
    # Add month filter if specific months are selected
    if selected_months and len(selected_months) > 0:
        month_placeholders = ','.join(['?' for _ in selected_months])
        query += f" AND strftime('%Y-%m', v.Date_de_sortie) IN ({month_placeholders})"
        params.extend(selected_months)
    # If no specific months selected, show ALL data (no date filter)
    # This makes comprehensive table show complete client history
    
    if client:
        query += " AND t.client = ?"
        params.append(client)
    
    query += '''
        GROUP BY strftime('%Y-%m', v.Date_de_sortie), t.client, t.id_bulletin
        ORDER BY strftime('%Y-%m', v.Date_de_sortie)
    '''
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    # Process results by counting bulletin-client pairs
    months_data = {}
    all_months = set()
    
    # Risk level mappings
    risk_mappings = {
        'Critical': 'Critique',
        'Important': 'Moyen', 
        'Moderate': 'Faible',
        'Low': 'Faible',
        'Fort': 'Risque fort',
        'Élevé': 'Risque fort'
    }
    
    # Status mappings and calculations
    closed_statuses = ['Clos', 'Clos (Traité)', 'Clos (Patch cumulative)', 'Clos (Non concerné)']
    ongoing_statuses = ['Open', 'WIP', 'Pending', 'NOK']
    
    for row in rows:
        month = row['month']
        month_name = row['month_name']
        risk = row['risk'] or ''
        niveau_risque = row['niveau_risque'] or ''
        status = row['status']
        
        if month not in months_data:
            months_data[month] = {
                'month_name': month_name,
                'vulnerabilities': {
                    'Critique': 0,
                    'Moyen': 0,
                    'Faible': 0,
                    'Risque fort': 0
                },
                'statut': {
                    'Open': 0,
                    'WIP': 0,
                    'Pending': 0,
                    'Clos (Patch cumulative)': 0,
                    'Clos (Non concerné)': 0,
                    'Clos (Traité)': 0,
                    'NOK': 0,
                    'Alertes cloturées': 0,
                    'Alertes en cours': 0
                },
                'total_vulnerabilities': 0,
                'total_closed': 0,
                'total_ongoing': 0
            }
        
        all_months.add(month)
        
        # Map risk levels - count this bulletin-client pair once per risk
        mapped_risk = risk_mappings.get(risk, risk_mappings.get(niveau_risque, 'Moyen'))
        if mapped_risk in months_data[month]['vulnerabilities']:
            months_data[month]['vulnerabilities'][mapped_risk] += 1
        
        # Add to status counts - count this bulletin-client pair once per status
        if status in months_data[month]['statut']:
            months_data[month]['statut'][status] += 1
        
        # Calculate aggregated counts - count this bulletin-client pair once
        months_data[month]['total_vulnerabilities'] += 1
        
        if status in closed_statuses:
            months_data[month]['statut']['Alertes cloturées'] += 1
            months_data[month]['total_closed'] += 1
        elif status in ongoing_statuses:
            months_data[month]['statut']['Alertes en cours'] += 1
            months_data[month]['total_ongoing'] += 1
    
    # Calculate treatment percentages
    for month_data in months_data.values():
        total = month_data['total_vulnerabilities']
        if total > 0:
            month_data['treatment_percentage'] = round((month_data['total_closed'] / total) * 100)
        else:
            month_data['treatment_percentage'] = 0
    
    # Sort months chronologically
    sorted_months = sorted(all_months)
    
    return {
        'months': sorted_months,
        'data': months_data
    }
    

def get_kpi_summary(client=None, month=None):
    """Get comprehensive KPI summary"""
    return {
        'status_distribution': get_status_distribution(client, month),
        'sla_compliance': get_sla_compliance(client, month),
        'monthly_trend': get_monthly_trend(client, 6),
        'open_vs_closed': get_open_vs_closed(client, month)
    }


