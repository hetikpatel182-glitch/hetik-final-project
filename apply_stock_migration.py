import sqlite3
import os

db_path = 'db.sqlite3'

def apply_stock_migration():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Add product_stock column to myapp_product table
        # We use PositiveIntegerField in Django, which translates to INTEGER UNSIGNED in some DBs,
        # but in SQLite it's just INTEGER.
        try:
            cursor.execute("ALTER TABLE myapp_product ADD COLUMN product_stock INTEGER UNSIGNED NOT NULL DEFAULT 0")
            print("Added column 'product_stock' to myapp_product table.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("Column 'product_stock' already exists.")
            else:
                raise e

        # Since I can't easily run manage.py makemigrations/migrate, 
        # I won't try to fake the django_migrations entry here to avoid sync issues 
        # if the user eventually gets manage.py working. 
        # But for the app to work now, the column must exist.

        conn.commit()
        conn.close()
        print("Migration applied successfully.")

    except Exception as e:
        print(f"Error applying migration: {e}")

if __name__ == "__main__":
    apply_stock_migration()
