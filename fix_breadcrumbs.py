import os
import re

template_dir = r'E:\project-django\myapp\templates'

for filename in os.listdir(template_dir):
    if filename.endswith('.html'):
        filepath = os.path.join(template_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Determine base template
            if "{% extends 'seller-header.html' %}" in content:
                home_url = "{% url 'seller-index' %}"
            else:
                home_url = "{% url 'index' %}"
                
            # Replace breadcrumb Home link
            # Look for <li class="breadcrumb-item"><a href="#">Home</a></li>
            # or variations with different quoting
            pattern = re.compile(r'(<li class=["\']breadcrumb-item["\']>\s*<a href=["\'])#( ["\']>\s*Home\s*</a>\s*</li>)', re.IGNORECASE)
            new_content = pattern.sub(fr'\1{home_url}\2', content)
            
            # Simple fallback for standard formatting
            if new_content == content:
                 new_content = content.replace('<li class="breadcrumb-item"><a href="#">Home</a></li>', 
                                              f'<li class="breadcrumb-item"><a href="{home_url}">Home</a></li>')
            
            # Additional fallback for seller product details which might have different formatting
            if new_content == content:
                 new_content = content.replace('<li class="breadcrumb-item"><a href="#">Home</a></li>', 
                                              f'<li class="breadcrumb-item"><a href="{home_url}">Home</a></li>')

            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Fixed {filename}")
        except Exception as e:
            print(f"Error processing {filename}: {e}")
