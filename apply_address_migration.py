import sqlite3
import datetime

DB_PATH = "db.sqlite3"
MIGRATION_APP = "myapp"
MIGRATION_NAME = "0009_cart_delivery_address_auto"

print("Starting direct database migration for delivery_address...")

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Check if column already exists
    cursor.execute("PRAGMA table_info(myapp_cart)")
    columns = [row[1] for row in cursor.fetchall()]

    if "delivery_address" in columns:
        print("✅ Column 'delivery_address' already exists in myapp_cart. Nothing to do.")
    else:
        # 2. Add the column (text, nullable)
        print("⏳ Adding 'delivery_address' column...")
        cursor.execute(
            "ALTER TABLE myapp_cart ADD COLUMN delivery_address text NULL"
        )
        print("✅ Added column 'delivery_address' to myapp_cart table.")

    # 3. Check if migration already recorded
    cursor.execute(
        "SELECT id FROM django_migrations WHERE app=? AND name=?",
        (MIGRATION_APP, MIGRATION_NAME)
    )
    already_recorded = cursor.fetchone()

    if already_recorded:
        print(f"✅ Migration '{MIGRATION_NAME}' already recorded in django_migrations.")
    else:
        # 4. Record migration as applied
        applied_at = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
        cursor.execute(
            "INSERT INTO django_migrations (app, name, applied) VALUES (?, ?, ?)",
            (MIGRATION_APP, MIGRATION_NAME, applied_at)
        )
        print(f"✅ Recorded migration '{MIGRATION_NAME}' in django_migrations.")

    conn.commit()
    print("\n🎉 Done! The database has been updated successfully.")
    print("Please restart your Django development server and refresh the page.")

except Exception as e:
    print(f"❌ Error applying migration: {e}")
finally:
    if 'conn' in locals():
        conn.close()
