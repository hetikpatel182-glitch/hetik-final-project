import sqlite3
import os
db_path = 'db.sqlite3'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, fname, lname, email, usertype FROM myapp_user")
    rows = cursor.fetchall()
    for r in rows:
        print(r)
    conn.close()
else:
    print("Database file not found at " + os.path.abspath(db_path))
