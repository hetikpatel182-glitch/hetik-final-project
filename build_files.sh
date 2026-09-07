#!/bin/bash

# Install Python dependencies
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput

# Create output directory for Vercel static build
mkdir -p staticfiles_build
