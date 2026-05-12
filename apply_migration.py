"""
Direct SQLite migration script.
Adds the product_status column to myapp_product table
and records it in django_migrations table.
Run: python apply_migration.py
"""
import sqlite3
import datetime

DB_PATH = "db.sqlite3"
MIGRATION_APP = "myapp"
MIGRATION_NAME = "0008_product_product_status"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 1. Check if column already exists
cursor.execute("PRAGMA table_info(myapp_product)")
columns = [row[1] for row in cursor.fetchall()]

if "product_status" in columns:
    print("Column 'product_status' already exists. Nothing to do.")
else:
    # 2. Add the column with default=1 (True)
    cursor.execute(
        "ALTER TABLE myapp_product ADD COLUMN product_status integer NOT NULL DEFAULT 1"
    )
    print("Added column 'product_status' to myapp_product table.")

# 3. Check if migration already recorded
cursor.execute(
    "SELECT id FROM django_migrations WHERE app=? AND name=?",
    (MIGRATION_APP, MIGRATION_NAME)
)
already_recorded = cursor.fetchone()

if already_recorded:
    print(f"Migration '{MIGRATION_NAME}' already recorded in django_migrations.")
else:
    # 4. Record migration as applied
    applied_at = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
    cursor.execute(
        "INSERT INTO django_migrations (app, name, applied) VALUES (?, ?, ?)",
        (MIGRATION_APP, MIGRATION_NAME, applied_at)
    )
    print(f"Recorded migration '{MIGRATION_NAME}' in django_migrations.")

conn.commit()
conn.close()
print("\nDone! The product_status column has been applied.")
print("Restart the Django server and the error should be gone.")
