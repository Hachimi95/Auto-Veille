import sqlite3
import os
from database import db

# Remove existing database to recreate with new schema
if os.path.exists('vuln_tracker.db'):
    os.remove('vuln_tracker.db')
    print("🗑️ Removed existing database")

conn = sqlite3.connect('vuln_tracker.db')
c = conn.cursor()

# Table for general vulnerabilities (shared across clients)
c.execute('''
CREATE TABLE IF NOT EXISTS vulnerabilities (
    id_bulletin TEXT,
    cve_id TEXT,
    produit_name TEXT,
    Date_de_sortie TEXT,
    description TEXT,
    Niveau_de_risqué TEXT DEFAULT 'Fort',
    severity TEXT,
    risk TEXT,
    processing_time INTEGER,
    mitigation TEXT,
    Référence TEXT,
    Date_de_notification TEXT,
    PRIMARY KEY (id_bulletin, cve_id)
)
''')

# Table for client-specific tracking of each vulnerability
c.execute('''
CREATE TABLE IF NOT EXISTS client_vuln_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_bulletin TEXT,
    cve_id TEXT,
    client TEXT,
    status TEXT DEFAULT 'Open',
    Responsable_resolution TEXT,
    Date_de_traitement TEXT,
    comment TEXT,
    FOREIGN KEY (id_bulletin, cve_id) REFERENCES vulnerabilities(id_bulletin, cve_id)
)
''')

# Create clients and products tables with responsible_resolution
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

conn.commit()
conn.close()
print("✅ Database initialized with new schema including responsible_resolution field")

def main():
    db.create_clients_products_tables()

if __name__ == '__main__':
    main()

