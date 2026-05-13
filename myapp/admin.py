from django.contrib import admin
from .models import User,Product,Wishlist,Cart,SellerProfile

# Register your models here.
admin.site.register(User)
admin.site.register(Product)
admin.site.register(Wishlist)
admin.site.register(Cart)
admin.site.register(SellerProfile)