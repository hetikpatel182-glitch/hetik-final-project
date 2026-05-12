import sqlite3

def migrate():
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE myapp_contact ADD COLUMN reply TEXT")
        print("Column 'reply' added successfully.")
    except sqlite3.OperationalError:
        print("Column 'reply' already exists.")

    try:
        cursor.execute("ALTER TABLE myapp_contact ADD COLUMN is_read BOOLEAN DEFAULT 0")
        print("Column 'is_read' added successfully.")
    except sqlite3.OperationalError:
        print("Column 'is_read' already exists.")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
