"""
Vercel serverless function entry point.
Wraps the Django WSGI application for Vercel's Python runtime.
"""
import os
import sys

# Add the project root to sys.path so Django can find the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')

from django.core.wsgi import get_wsgi_application

app = application = get_wsgi_application()
