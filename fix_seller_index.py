import re

with open('E:\\project-django\\myapp\\templates\\seller-index.html', 'r', encoding='utf-8') as f:
    content = f.read()

replacement = '''
                        <div class="row g-4">
                            {% for i in products %}
                            <div class="col-md-6 col-lg-4 col-xl-3">
                                <div class="product-item rounded wow fadeInUp" data-wow-delay="0.1s">
                                    <div class="product-item-inner border rounded">
                                        <div class="product-item-inner-item">
                                            <img src="{{ i.product_picture.url }}" class="img-fluid w-100 rounded-top" alt="{{ i.product_name }}" style="height: 250px; object-fit: contain; padding: 1rem;">
                                            <div class="product-new">Active</div>
                                            <div class="product-details">
                                                <a href="{% url 'seller-product-details' pk=i.pk %}"><i class="fa fa-eye fa-1x"></i></a>
                                            </div>
                                        </div>
                                        <div class="text-center rounded-bottom p-4">
                                            <a href="{% url 'seller-product-details' pk=i.pk %}" class="d-block mb-2">{{ i.product_category }}</a>
                                            <a href="{% url 'seller-product-details' pk=i.pk %}" class="d-block h4 text-truncate">{{ i.product_name }}</a>
                                            <span class="text-primary fs-5">Rs. {{ i.product_price }}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            {% empty %}
                            <div class="col-12 text-center py-5">
                                <h3>No products found</h3>
                                <p class="text-muted">You haven't listed any products yet.</p>
                            </div>
                            {% endfor %}
                        </div>
'''

content = re.sub(r'<div class="row g-4">\s*<div class="col-md-6 col-lg-4 col-xl-3">.*?</div>\s*</div>', replacement.strip(), content, flags=re.DOTALL)

with open('E:\\project-django\\myapp\\templates\\seller-index.html', 'w', encoding='utf-8') as f:
    f.write(content)
