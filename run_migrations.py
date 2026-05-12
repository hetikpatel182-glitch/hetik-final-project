import os
import django
from django.core.management import call_command

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')
django.setup()

try:
    print("Running makemigrations...")
    call_command('makemigrations', 'myapp', interactive=False)
    print("Running migrate...")
    call_command('migrate', interactive=False)
    print("Migration completed successfully.")
except Exception as e:
    print(f"Error during migration: {e}")
