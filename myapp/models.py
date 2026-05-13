from django.db import models
from django.utils import timezone

# Create your models here.
class User(models.Model):
    fname=models.CharField(max_length=100)
    lname=models.CharField(max_length=100)
    email=models.EmailField()
    mobile=models.PositiveIntegerField()
    address=models.TextField()
    password=models.CharField(max_length=100)
    profile_picture=models.ImageField(upload_to="profile_picture/")
    usertype=models.CharField(max_length=100,default="buyer")
    
    def __str__(self):
        return self.fname+" "+self.lname
    
class Product(models.Model):
    seller=models.ForeignKey(User,on_delete=models.CASCADE)
    category=(
        ("Mobile","Mobile"),
        ("Electronics","Electronics"),
    )
    product_category=models.CharField(max_length=100,choices=category)
    product_name=models.CharField(max_length=100)
    product_price=models.PositiveIntegerField()
    product_desc=models.TextField()
    product_picture=models.ImageField(upload_to="product_picture/")
    product_status=models.BooleanField(default=True)
    product_stock=models.PositiveIntegerField(default=0)
    returnable=models.BooleanField(default=False)
    return_days=models.PositiveIntegerField(default=0)
    
    def __str__(self):
        return self.seller.fname+" - "+self.product_name
    
class Wishlist(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    product=models.ForeignKey(Product,on_delete=models.CASCADE)
    time=models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return self.user.fname+" - "+self.product.product_name
    
class Cart(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    product=models.ForeignKey(Product,on_delete=models.CASCADE)
    time=models.DateTimeField(default=timezone.now)
    product_price=models.PositiveIntegerField()
    product_qty=models.PositiveIntegerField(default=1)
    total_price=models.PositiveIntegerField()
    payment_status=models.BooleanField(default=False)
    order_id=models.CharField(max_length=100, null=True, blank=True)
    item_order_id=models.CharField(max_length=100, null=True, blank=True)
    payment_method=models.CharField(max_length=100, default="Stripe")
    delivery_address=models.TextField(null=True, blank=True)
    is_cancelled=models.BooleanField(default=False)
    cancel_reason=models.TextField(null=True, blank=True)
    delivery_status=models.CharField(max_length=100, default="placed")
    delivery_date=models.DateTimeField(null=True, blank=True)
    return_status=models.CharField(max_length=100, default="none")
    return_reason=models.TextField(null=True, blank=True)
    is_restocked=models.BooleanField(default=False)
    
    def __str__(self):
        return self.user.fname+" - "+self.product.product_name

    @property
    def gst_amount(self):
        return (self.total_price * 18) / 100

    @property
    def total_amount(self):
        return self.total_price + self.gst_amount

    @property
    def cod_payment_status(self):
        if self.payment_method == 'COD':
            return 'Done' if self.delivery_status == 'delivered' else 'Pending'
        return 'Done'

    @property
    def display_order_id(self):
        if self.order_id:
            return self.order_id
        # Fallback generation for display only
        # Deterministic based on pk and creation timestamp to ensure stability on page refresh
        epoch = int(self.time.timestamp())
        import hashlib
        h = hashlib.md5(f"{self.pk}-{epoch}".encode()).hexdigest().upper()[:5]
        return f"ORDER-{epoch}-{h}"

    @property
    def display_item_order_id(self):
        if self.item_order_id:
            return self.item_order_id
        # Fallback generation for display only
        epoch = int(self.time.timestamp())
        import hashlib
        h = hashlib.md5(f"item-{self.pk}-{epoch}".encode()).hexdigest().upper()[:5]
        return f"ITEM-ORDER-{epoch}-PROD{self.product.pk}-{h}"

class Contact(models.Model):
    seller=models.ForeignKey(User,on_delete=models.CASCADE,related_name='received_messages')
    product=models.ForeignKey(Product,on_delete=models.CASCADE,null=True,blank=True)
    name=models.CharField(max_length=100)
    email=models.EmailField()
    mobile=models.CharField(max_length=100,null=True,blank=True)
    subject=models.CharField(max_length=100)
    message=models.TextField()
    reply=models.TextField(null=True,blank=True)
    is_read=models.BooleanField(default=False)
    time=models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name + " - " + self.subject

class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, null=True, blank=True)
    rating = models.PositiveIntegerField()
    review_text = models.TextField()
    time = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.fname} - {self.product.product_name} ({self.rating} Stars)"

class SellerProfile(models.Model):
    """Stores seller-specific business info, linked 1-to-1 with the User."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='seller_profile')
    business_name = models.CharField(max_length=200)
    gst_number = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.business_name} ({self.user.email})"

# =====================================================================
# AUTO-HEALING MIGRATION: Injects new columns dynamically
# =====================================================================
try:
    import sqlite3
    import os
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(BASE_DIR, 'db.sqlite3')
    
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Ensure myapp_review table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS myapp_review (
                id integer PRIMARY KEY AUTOINCREMENT,
                rating integer NOT NULL,
                review_text text NOT NULL,
                time datetime NOT NULL,
                cart_id integer NULL REFERENCES myapp_cart(id) ON DELETE CASCADE,
                product_id integer NOT NULL REFERENCES myapp_product(id) ON DELETE CASCADE,
                user_id integer NOT NULL REFERENCES myapp_user(id) ON DELETE CASCADE
            )
        """)
        
        # Auto-heal myapp_product columns if missing
        cursor.execute("PRAGMA table_info(myapp_product)")
        prod_columns = [row[1] for row in cursor.fetchall()]
        if "product_status" not in prod_columns:
            cursor.execute("ALTER TABLE myapp_product ADD COLUMN product_status integer NOT NULL DEFAULT 1")
        if "product_stock" not in prod_columns:
            cursor.execute("ALTER TABLE myapp_product ADD COLUMN product_stock integer NOT NULL DEFAULT 0")
        if "returnable" not in prod_columns:
            cursor.execute("ALTER TABLE myapp_product ADD COLUMN returnable integer NOT NULL DEFAULT 0")
        if "return_days" not in prod_columns:
            cursor.execute("ALTER TABLE myapp_product ADD COLUMN return_days integer NOT NULL DEFAULT 0")
        
        # Auto-heal myapp_cart columns if missing
        cursor.execute("PRAGMA table_info(myapp_cart)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "delivery_address" not in columns:
            cursor.execute("ALTER TABLE myapp_cart ADD COLUMN delivery_address text NULL")
        if "is_cancelled" not in columns:
            cursor.execute("ALTER TABLE myapp_cart ADD COLUMN is_cancelled integer NOT NULL DEFAULT 0")
        if "cancel_reason" not in columns:
            cursor.execute("ALTER TABLE myapp_cart ADD COLUMN cancel_reason text NULL")
        if "delivery_status" not in columns:
            cursor.execute("ALTER TABLE myapp_cart ADD COLUMN delivery_status varchar(100) NOT NULL DEFAULT 'placed'")
        if "order_id" not in columns:
            cursor.execute("ALTER TABLE myapp_cart ADD COLUMN order_id varchar(100) NULL")
        if "item_order_id" not in columns:
            cursor.execute("ALTER TABLE myapp_cart ADD COLUMN item_order_id varchar(100) NULL")
        if "delivery_date" not in columns:
            cursor.execute("ALTER TABLE myapp_cart ADD COLUMN delivery_date datetime NULL")
        if "return_status" not in columns:
            cursor.execute("ALTER TABLE myapp_cart ADD COLUMN return_status varchar(100) NOT NULL DEFAULT 'none'")
        if "return_reason" not in columns:
            cursor.execute("ALTER TABLE myapp_cart ADD COLUMN return_reason text NULL")
        if "is_restocked" not in columns:
            cursor.execute("ALTER TABLE myapp_cart ADD COLUMN is_restocked integer NOT NULL DEFAULT 0")
        # Auto-heal myapp_sellerprofile table if missing
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS myapp_sellerprofile (
                id integer PRIMARY KEY AUTOINCREMENT,
                business_name varchar(200) NOT NULL DEFAULT '',
                gst_number varchar(20) NULL,
                created_at datetime NOT NULL,
                user_id integer NOT NULL UNIQUE REFERENCES myapp_user(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        conn.close()
except Exception as e:
    pass
