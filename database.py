import sqlite3
import os

DB_PATH = "gridpilot.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            carbon REAL NOT NULL,
            capacity REAL NOT NULL,
            security REAL NOT NULL,
            cost REAL NOT NULL
        )
    ''')
    
    # Check if we need to seed
    cursor.execute("SELECT COUNT(*) FROM nodes")
    if cursor.fetchone()[0] == 0:
        initial_regions = [
            ('FRA', 'Frankfurt', 50.11, 8.68, 0.45, 40, 0.98, 140),
            ('MAD', 'Madrid', 40.41, -3.70, 0.25, 35, 0.92, 95),
            ('HEL', 'Helsinki', 60.16, 24.93, 0.05, 45, 0.99, 70),
            ('SIN', 'Singapore', 1.35, 103.81, 0.42, 40, 0.96, 115),
            ('SAU', 'Riyadh', 24.71, 46.67, 0.55, 45, 0.88, 60),
            ('IAD', 'US-East', 39.04, -77.48, 0.48, 50, 0.97, 105),
            ('SAO', 'São Paulo', -23.55, -46.63, 0.12, 30, 0.90, 130),
            ('BOM', 'Mumbai', 19.07, 72.87, 0.65, 40, 0.85, 55),
            ('SYD', 'Sydney', -33.86, 151.20, 0.35, 35, 0.95, 160),
            ('CPT', 'Cape Town', -33.92, 18.42, 0.38, 30, 0.82, 85)
        ]
        cursor.executemany('''
            INSERT INTO nodes (id, name, lat, lng, carbon, capacity, security, cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', initial_regions)
    
    conn.commit()
    conn.close()

def get_nodes():
    conn = get_db_connection()
    nodes = conn.execute('SELECT * FROM nodes').fetchall()
    conn.close()
    return [dict(node) for node in nodes]

def add_node(node_data):
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO nodes (id, name, lat, lng, carbon, capacity, security, cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            node_data['id'],
            node_data['name'],
            node_data['lat'],
            node_data['lng'],
            node_data['carbon'],
            node_data['capacity'],
            node_data['security'],
            node_data['cost']
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
