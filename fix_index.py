import re

with open('E:\\project-django\\myapp\\templates\\index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace any occurrence of Apple iPad Mini or SmartPhone dummy data blocks within index.html
content = re.sub(r'<div class="carousel-banner-content text-center p-4">.*?Add To Cart</a>', r'''<div class="col-12 text-center py-5">
    <h3 class="text-white">No promotional products available</h3>
</div>''', content, flags=re.DOTALL)

with open('E:\\project-django\\myapp\\templates\\index.html', 'w', encoding='utf-8') as f:
    f.write(content)
