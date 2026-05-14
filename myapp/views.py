from django.shortcuts import render,redirect
from .models import User,Product,Wishlist,Cart,Contact,Review,SellerProfile
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, F, Q, Sum
import random
import time
import string
import requests
from django.http import JsonResponse,HttpResponse
from django.views.decorators.csrf import csrf_exempt
import json
import stripe

stripe.api_key = settings.STRIPE_PRIVATE_KEY
YOUR_DOMAIN = 'http://localhost:8000'


CATEGORIES = ["Mobile", "Laptops", "Electronics", "Accessories", "Appliances", "Smart Watches", "Tablets", "Earbuds", "Headphones", "Chargers", "Power Banks", "Cameras", "Gaming", "Computer Accessories", "Speakers", "Smart Gadgets"]
GST_PERCENT = 18

CATEGORY_ICONS = {
    "Mobile": "fas fa-mobile-alt",
    "Laptops": "fas fa-laptop",
    "Electronics": "fas fa-microchip",
    "Accessories": "fas fa-plug",
    "Appliances": "fas fa-blender",
    "Smart Watches": "fas fa-stopwatch",
    "Tablets": "fas fa-tablet-alt",
    "Earbuds": "fas fa-headset",
    "Headphones": "fas fa-headphones",
    "Chargers": "fas fa-bolt",
    "Power Banks": "fas fa-battery-full",
    "Cameras": "fas fa-camera",
    "Gaming": "fas fa-gamepad",
    "Computer Accessories": "fas fa-keyboard",
    "Speakers": "fas fa-volume-up",
    "Smart Gadgets": "fas fa-lightbulb"
}

def get_unique_order_id():
    """Generates a globally unique, non-repeating Order ID using timestamp and randomness."""
    while True:
        timestamp = int(time.time())
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        order_id = f"ORDER-{timestamp}-{random_str}"
        if not Cart.objects.filter(order_id=order_id).exists():
            return order_id

def generate_item_order_id(main_order_id, product_id):
    """Generates a unique item-level Order ID using ITEM-{MAIN_ORDER_ID}-{PRODUCT_ID}-{RANDOM} format."""
    while True:
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        item_order_id = f"ITEM-{main_order_id}-PROD{product_id}-{random_str}"
        if not Cart.objects.filter(item_order_id=item_order_id).exists():
            return item_order_id

def send_order_placed_notification(user, carts, order_id):
    """Sends a single consolidated 'Order Placed' notification to the buyer."""
    carts_list = list(carts)
    if not carts_list:
        return
    
    first_item = carts_list[0]
    product_names = [item.product.product_name for item in carts_list if item.product]
    product_list_str = ", ".join(product_names)
    
    subject = f"Order Placed Successfully: {order_id}"
    message_text = f"Order confirmation notification (system generated) | CartID:{first_item.pk}"
    reply_text = (
        f"Your order has been placed successfully.\n\n"
        f"Thank you for your purchase! Your order for '{product_list_str}' "
        f"(Order ID: {order_id}) has been placed successfully and is awaiting confirmation from the seller."
    )
    
    Contact.objects.create(
        seller=first_item.product.seller,
        product=first_item.product,
        name=f"{user.fname} {user.lname}",
        email=user.email,
        subject=subject,
        message=message_text,
        reply=reply_text,
        is_read=False,
    )

# Create your views here.
def attach_product_review_stats(products):
    """Attaches avg rating & star counts to a product list — only fetches reviews for those products."""
    # Materialise once so we can extract PKs and iterate twice without extra queries
    products = list(products)
    if not products:
        return products
    product_ids = [p.pk for p in products]
    reviews = Review.objects.filter(product_id__in=product_ids).only('product_id', 'rating')
    review_stats = {}
    for r in reviews:
        if r.product_id not in review_stats:
            review_stats[r.product_id] = {'sum': 0, 'count': 0}
        review_stats[r.product_id]['sum'] += r.rating
        review_stats[r.product_id]['count'] += 1

    for p in products:
        stats = review_stats.get(p.pk, {'sum': 0, 'count': 0})
        p.total_reviews = stats['count']
        p.avg_rating = round(stats['sum'] / stats['count'], 1) if stats['count'] > 0 else 0
        p.avg_rating_int = int(round(p.avg_rating))
        p.stars_solid = range(p.avg_rating_int)
        p.stars_empty = range(5 - p.avg_rating_int)
    return products

def index(request):
    # Only show active products — use select_related to avoid N+1 on seller/seller_profile
    products = Product.objects.filter(product_status=True).select_related('seller', 'seller__seller_profile').order_by('-id')[:12]
    products = attach_product_review_stats(products)
    wishlist_pks = []
    if 'email' in request.session:
        try:
            user = User.objects.get(email=request.session['email'])
            wishlist_pks = list(Wishlist.objects.filter(user=user).values_list('product_id', flat=True))
            if user.usertype == "buyer":
                return render(request, 'index.html', {'products': products, 'wishlist_pks': wishlist_pks})
            else:
                return redirect('seller-index')
        except Exception:
            return render(request, 'index.html', {'products': products, 'wishlist_pks': wishlist_pks})
    else:
        wishlist_pks = [int(pk) for pk in request.session.get('guest_wishlist', [])]
        return render(request, 'index.html', {'products': products, 'wishlist_pks': wishlist_pks})
    
def seller_index(request):
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype == "seller":
            products = Product.objects.filter(seller=user).order_by('-id')
            total_products = products.count()
            # Use DB aggregation instead of loading all cart rows into memory
            seller_orders_qs = Cart.objects.filter(product__seller=user, payment_status=True, is_cancelled=False)
            total_orders = Cart.objects.filter(product__seller=user, payment_status=True).count()
            revenue_agg = seller_orders_qs.aggregate(total=Sum('total_price'))
            total_revenue = revenue_agg['total'] or 0

            return render(request, 'seller-index.html', {
                'products': products,
                'total_products': total_products,
                'total_orders': total_orders,
                'total_revenue': round(total_revenue, 2)
            })
        else:
            return redirect('index')
    except (User.DoesNotExist, KeyError):
        return redirect('seller-login')

def shop(request, cat):
    if 'email' in request.session:
        try:
            user = User.objects.get(email=request.session['email'])
            if user.usertype == 'seller':
                return redirect('seller-index')
        except User.DoesNotExist:
            pass

    all_products_count = Product.objects.filter(product_status=True).count()
    categories = (Product.objects.filter(product_status=True)
                  .values('product_category')
                  .annotate(count=Count('id'))
                  .filter(count__gt=0)
                  .order_by('product_category'))

    query = request.GET.get('q')
    base_qs = Product.objects.filter(product_status=True).select_related('seller', 'seller__seller_profile')
    if cat == 'all':
        products = base_qs
    else:
        products = base_qs.filter(product_category=cat)

    if query:
        products = products.filter(Q(product_name__icontains=query) | Q(product_desc__icontains=query))

    products = products.order_by('-id')
    products = attach_product_review_stats(products)

    for category in categories:
        category['icon'] = CATEGORY_ICONS.get(category['product_category'], 'fas fa-list')

    wishlist_pks = []
    if 'email' in request.session:
        try:
            user = User.objects.get(email=request.session['email'])
            wishlist_pks = list(Wishlist.objects.filter(user=user).values_list('product_id', flat=True))
        except User.DoesNotExist:
            pass
    else:
        wishlist_pks = [int(pk) for pk in request.session.get('guest_wishlist', [])]

    return render(request, 'shop.html', {
        'products': products,
        'all_products': all_products_count,
        'categories': categories,
        'current_cat': cat,
        'search_query': query,
        'wishlist_pks': wishlist_pks
    })

def contact(request):
    user = None
    if 'email' in request.session:
        try:
            user = User.objects.get(email=request.session['email'])
            if user.usertype == 'seller':
                return redirect('seller-contact')
        except User.DoesNotExist:
            pass

    product = None
    if request.method == "POST":
        p_id = request.POST.get('product_id') or request.POST.get('p_id')
        if p_id:
            try:
                product = Product.objects.get(pk=p_id)
                if not product.product_status:
                    return redirect('index')
                seller = product.seller
            except Product.DoesNotExist:
                product = None
                # Support Routing Fallback: Route to Admin or first registered Seller
                seller = User.objects.filter(email='admin@gmail.com').first() or User.objects.filter(usertype='admin').first() or User.objects.filter(usertype='seller').first() or User.objects.first()
        else:
            # General Inquiries Routing: Securely Route to Support admin or first seller
            seller = User.objects.filter(email='admin@gmail.com').first() or User.objects.filter(usertype='admin').first() or User.objects.filter(usertype='seller').first() or User.objects.first()
            
        name = request.POST.get('name', 'Buyer')
        email = request.POST.get('email', '')
        mobile = request.POST.get('phone', '') or request.POST.get('mobile', '')
        subject = request.POST.get('subject', 'General Inquiry')
        message = request.POST.get('message', '')
        
        # Debounce check to prevent duplicate chatbot messages within 15 seconds
        from django.utils import timezone
        time_threshold = timezone.now() - timezone.timedelta(seconds=15)
        duplicate_exists = Contact.objects.filter(
            email__iexact=email,
            subject=subject,
            message=message,
            time__gte=time_threshold
        ).exists()
        
        if not duplicate_exists and seller:
            Contact.objects.create(
                seller=seller,
                product=product,
                name=name,
                email=email,
                mobile=mobile,
                subject=subject,
                message=message
            )
            
        msg = "Message Sent Successfully"
        
        recent_inquiries = []
        if 'email' in request.session:
            recent_inquiries = Contact.objects.filter(email__iexact=request.session['email']).order_by('-time')[:20]
            
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'msg': msg})
            
        return render(request, 'contact.html', {'msg': msg, 'product': product, 'recent_inquiries': recent_inquiries, 'user': user})
    else:
        p_id = request.GET.get('product_id')
        if p_id:
            try:
                product = Product.objects.get(pk=p_id)
            except Product.DoesNotExist:
                product = None
            
        recent_inquiries = []
        if 'email' in request.session:
            recent_inquiries = Contact.objects.filter(email__iexact=request.session['email']).order_by('-time')[:20]
            
        return render(request, 'contact.html', {'product': product, 'recent_inquiries': recent_inquiries, 'user': user})

def seller_contact(request):
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype == "seller":
            # Mark unread contacts as read upon entering the inbox
            Contact.objects.filter(seller=user, is_read=False).update(is_read=True)
            contacts = Contact.objects.filter(seller=user).order_by('-time')
            return render(request, 'seller-contact.html', {'contacts': contacts})
        else:
            return redirect('index')
    except (User.DoesNotExist, KeyError):
        return redirect('seller-login')

def login(request):
    if 'email' in request.session:
        try:
            user = User.objects.get(email=request.session['email'])
            return redirect('seller-index' if user.usertype == 'seller' else 'index')
        except User.DoesNotExist:
            pass

    if request.method=="POST":
        try:
            user=User.objects.get(email=request.POST['email'])
            if user.password==request.POST['password']:
                request.session['email']=user.email
                request.session['fname']=user.fname
                request.session['profile_picture']=user.profile_picture.url
                
                if user.usertype=="buyer":
                    guest_cart = request.session.get('guest_cart', {})
                    if guest_cart:
                        for pk_str, item in guest_cart.items():
                            try:
                                product = Product.objects.get(pk=int(pk_str))
                                cart, created = Cart.objects.get_or_create(
                                    user=user, 
                                    product=product, 
                                    payment_status=False,
                                    defaults={
                                        'product_price': product.product_price,
                                        'product_qty': item['qty'],
                                        'total_price': item['qty'] * product.product_price
                                    }
                                )
                                if not created:
                                    cart.product_qty += item['qty']
                                    cart.total_price = cart.product_qty * product.product_price
                                    cart.save()
                            except Product.DoesNotExist:
                                pass
                        del request.session['guest_cart']

                    guest_wishlist = request.session.get('guest_wishlist', [])
                    if guest_wishlist:
                        for pk_str in guest_wishlist:
                            try:
                                product = Product.objects.get(pk=int(pk_str))
                                Wishlist.objects.get_or_create(user=user, product=product)
                            except Product.DoesNotExist:
                                pass
                        del request.session['guest_wishlist']
                        
                    wishlists=Wishlist.objects.filter(user=user)
                    carts=Cart.objects.filter(user=user,payment_status=False)
                    request.session['wishlist_count']=len(wishlists)
                    request.session['cart_count']=len(carts)
                    next_url = request.GET.get('next')
                    if next_url:
                        return redirect(next_url)
                    return redirect('index')
                else:
                    return redirect('seller-index')
            else:
                msg="Incorrect Password"
                return render(request,'login.html',{'msg':msg})
        except:
            msg="Email Not Registered"
            return render(request,'login.html',{'msg':msg})
    else:
        return render(request,'login.html')

def seller_login(request):
    if 'email' in request.session:
        try:
            user = User.objects.get(email=request.session['email'])
            if user.usertype == 'seller':
                return redirect('seller-index')
        except User.DoesNotExist:
            pass

    if request.method=="POST":
        try:
            user=User.objects.get(email=request.POST['email'])
            if user.password==request.POST['password']:
                if user.usertype == 'seller':
                    request.session['email']=user.email
                    request.session['fname']=user.fname
                    request.session['profile_picture']=user.profile_picture.url
                    return redirect('seller-index')
                else:
                    msg="This account is not registered as a seller."
                    return render(request,'seller-login.html',{'msg':msg})
            else:
                msg="Incorrect Password"
                return render(request,'seller-login.html',{'msg':msg})
        except:
            msg="Email Not Registered"
            return render(request,'seller-login.html',{'msg':msg})
    else:
        return render(request,'seller-login.html')

def signup(request):
    if request.method=="POST":
        try:
            User.objects.get(email=request.POST['email'])
            msg="Email Already Registered"
            return render(request,'login.html',{'msg':msg})
        except:
            if request.POST['password']==request.POST['cpassword']:
                User.objects.create(
                    fname=request.POST['fname'],
                    lname=request.POST['lname'],
                    email=request.POST['email'],
                    mobile=request.POST['mobile'],
                    address=request.POST['address'],
                    password=request.POST['password'],
                    profile_picture=request.FILES['profile_picture'],
                    usertype=request.POST['usertype']
                )
                msg="User Sign Up Successfully"
                return render(request,'login.html',{'msg':msg})
            else:
                msg="PAssword & Confirm Password Does Not Matched"
                return render(request,'signup.html',{'msg':msg})
    else:
        return render(request,'signup.html')
    
def logout(request):
    try:
        del request.session['fname']
        del request.session['email']
        del request.session['profile_picture']
        del request.session['wishlist_count']
        del request.session['cart_count']
    except:
        pass
    return redirect('login')

def become_seller(request):
    """Secure buyer-to-seller upgrade form. GET shows pre-filled form; POST validates and upgrades."""
    email = request.session.get('email')
    if not email:
        return redirect('login')

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return redirect('login')

    # Only buyers can upgrade — prevent tampering / double-upgrade
    if user.usertype != "buyer":
        return redirect('profile')

    if request.method == "GET":
        return render(request, 'become-seller.html', {'user': user})

    # ── POST: validate and process ──────────────────────────────────────
    business_name = request.POST.get('business_name', '').strip()
    gst_number = request.POST.get('gst_number', '').strip()

    errors = {}
    if not business_name:
        errors['business_name'] = 'Business Name is required.'
    elif len(business_name) > 200:
        errors['business_name'] = 'Business Name must be under 200 characters.'

    if gst_number and len(gst_number) > 20:
        errors['gst_number'] = 'GST Number must be under 20 characters.'

    if errors:
        return render(request, 'become-seller.html', {
            'user': user,
            'errors': errors,
            'form_data': request.POST,
        })

    # Save SellerProfile (create or update, in case of edge case retry)
    seller_profile, _ = SellerProfile.objects.get_or_create(user=user)
    seller_profile.business_name = business_name
    seller_profile.gst_number = gst_number or None
    seller_profile.save()

    # Upgrade role — backend-enforced, cannot be bypassed from frontend
    user.usertype = "seller"
    user.save()

    # Update session so header reflects new role immediately
    request.session['usertype'] = "seller"

    return redirect('seller-index')


def google_callback(request):

    """Serves the OAuth callback page that reads access_token from URL fragment."""
    return render(request, 'google_callback.html')


@csrf_exempt
def google_login(request):
    if request.method == "POST":
        try:
            # Detect mode: redirect mode sends form POST 'credential', popup sends JSON 'id_token'
            content_type = request.content_type or ''
            is_redirect_mode = 'application/x-www-form-urlencoded' in content_type

            if is_redirect_mode:
                id_token_str = request.POST.get('credential')
                email = None
                fname = lname = picture_url = ''
            else:
                data = json.loads(request.body)
                id_token_str = data.get('id_token') or data.get('credential')
                # Custom OAuth button sends access_token + user info directly
                email = data.get('email')
                fname = data.get('fname', 'Google')
                lname = data.get('lname', 'User')
                picture_url = data.get('picture', '')
                access_token = data.get('access_token')

            # If we received an access_token with user info (custom button flow)
            if not is_redirect_mode and access_token and email:
                # Verify access_token is valid by calling Google's userinfo endpoint
                verify_resp = requests.get(
                    'https://www.googleapis.com/oauth2/v3/userinfo',
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=10
                )
                if verify_resp.status_code != 200 or verify_resp.json().get('email') != email:
                    return JsonResponse({'status': 'error', 'message': 'Invalid access token'}, status=400)
                # Token verified — skip id_token flow below and go directly to user creation
                id_token_str = None

            if not id_token_str and not (not is_redirect_mode and access_token and email):
                if is_redirect_mode:
                    return redirect('login')
                return JsonResponse({'status': 'error', 'message': 'Token is missing'}, status=400)
            
            # If using id_token flow (GIS or redirect mode), verify the token
            if id_token_str:
                google_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token_str}"
                response = requests.get(google_url, timeout=10)
                
                if response.status_code != 200:
                    if is_redirect_mode:
                        return redirect('login')
                    return JsonResponse({'status': 'error', 'message': 'Invalid token signature or expired'}, status=400)
                
                token_info = response.json()
                
                if token_info.get('aud') != settings.GOOGLE_CLIENT_ID:
                    if is_redirect_mode:
                        return redirect('login')
                    return JsonResponse({'status': 'error', 'message': 'Audience mismatch'}, status=400)
                    
                email = token_info.get('email')
                if not email:
                    if is_redirect_mode:
                        return redirect('login')
                    return JsonResponse({'status': 'error', 'message': 'Email not provided by Google'}, status=400)
                fname = token_info.get('given_name', 'Google')
                lname = token_info.get('family_name', 'User')
                picture_url = token_info.get('picture', '')
                
            # Retrieve or create User
            created = False
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:

                
                # Create a secure user instance
                # User models require mobile, address, password, profile_picture
                import random
                import string
                from django.core.files.base import ContentFile
                
                password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
                user = User(
                    fname=fname,
                    lname=lname,
                    email=email,
                    mobile=0,
                    address="Registered with Google",
                    password=password,
                    usertype="buyer"
                )
                
                if picture_url:
                    try:
                        img_response = requests.get(picture_url, timeout=5)
                        if img_response.status_code == 200:
                            user.profile_picture.save(f"google_{email}.jpg", ContentFile(img_response.content), save=False)
                    except Exception as img_err:
                        # If profile image fails to download, continue anyway
                        pass
                
                user.save()
                created = True
                
            # Log the user in manually via session
            request.session['email'] = user.email
            request.session['fname'] = user.fname
            request.session['profile_picture'] = user.profile_picture.url if user.profile_picture else ""
            
            # Retrieve wishlist & cart counts
            wishlists = Wishlist.objects.filter(user=user)
            carts = Cart.objects.filter(user=user, payment_status=False)
            request.session['wishlist_count'] = len(wishlists)
            request.session['cart_count'] = len(carts)
            
            # Safe guest cart / wishlist merging (similar to standard login)
            if user.usertype == "buyer":
                guest_cart = request.session.get('guest_cart', {})
                if guest_cart:
                    for pk_str, item in guest_cart.items():
                        try:
                            product = Product.objects.get(pk=int(pk_str))
                            cart, cart_created = Cart.objects.get_or_create(
                                user=user, 
                                product=product, 
                                payment_status=False,
                                defaults={
                                    'product_price': product.product_price,
                                    'product_qty': item['qty'],
                                    'total_price': item['qty'] * product.product_price
                                }
                            )
                            if not cart_created:
                                cart.product_qty += item['qty']
                                cart.total_price = cart.product_qty * product.product_price
                                cart.save()
                        except Product.DoesNotExist:
                            pass
                    del request.session['guest_cart']

                guest_wishlist = request.session.get('guest_wishlist', [])
                if guest_wishlist:
                    for pk_str in guest_wishlist:
                        try:
                            product = Product.objects.get(pk=int(pk_str))
                            Wishlist.objects.get_or_create(user=user, product=product)
                        except Product.DoesNotExist:
                            pass
                    del request.session['guest_wishlist']
            
            # Return response based on mode
            if is_redirect_mode:
                return redirect('index' if user.usertype == 'buyer' else 'seller-index')
            else:
                redirect_target = '/' if user.usertype == 'buyer' else '/seller-index/'
                return JsonResponse({'status': 'success', 'redirect_url': redirect_target, 'created': created})
            
        except Exception as e:
            if is_redirect_mode:
                return redirect('login')
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            
    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)


def profile(request):
    try:
        user=User.objects.get(email=request.session['email'])
    except (User.DoesNotExist, KeyError):
        return redirect('login')
        
    if request.method=="POST":
        user.fname=request.POST['fname']
        user.lname=request.POST['lname']
        user.mobile=request.POST['mobile']
        user.address=request.POST['address']
        try:
            user.profile_picture=request.FILES['profile_picture']
        except:
            pass
        user.save()
        
        # Update Seller-Specific Information if applicable
        if user.usertype == 'seller':
            if not hasattr(user, 'seller_profile'):
                SellerProfile.objects.create(user=user, business_name=user.fname + " " + user.lname)
                
            seller_prof = user.seller_profile
            if 'business_name' in request.POST:
                seller_prof.business_name = request.POST.get('business_name')
            if 'gst_number' in request.POST:
                seller_prof.gst_number = request.POST.get('gst_number')
            seller_prof.save()
        msg="Profile Updated Successfully"
        request.session['profile_picture']=user.profile_picture.url
        
        if user.usertype=="buyer":
            return render(request,'profile.html',{'user':user,'msg':msg})
        else:
            return render(request,'seller-profile.html',{'user':user,'msg':msg})
    else:    
        if user.usertype=="buyer":
            return render(request,'profile.html',{'user':user})
        else:
            return render(request,'seller-profile.html',{'user':user})

def forgot_password(request):
    if request.method=="POST":
        try:
            user=User.objects.get(email=request.POST['email'])
            otp=random.randint(1000,9999)
            subject = 'Your Otp For Forgot Password'
            message = 'Your Otp For Forgot Password  Is '+str(otp)
            from_email = settings.EMAIL_HOST_USER  
            recipient_list = [user.email,]
            send_mail(subject, message, from_email, recipient_list)
            request.session['to_email']=user.email
            request.session['otp']=otp
            return render(request,'otp.html')
        except:
            msg="Email Address Not Registered"
            return render(request,'forgot-password.html',{'msg':msg})
    else:
        return render(request,'forgot-password.html')
    
def verify_otp(request):
    otp1=int(request.session['otp'])
    otp2=int(request.POST['otp'])
    
    if otp1==otp2:
        del request.session['otp']
        msg="Set Your New Password"
        return render(request,'new-password.html',{'msg':msg})
    else:
        msg="Invalid Otp"
        return render(request,'otp.html',{'msg':msg})
    
def new_password(request):
    if request.POST['new_password']==request.POST['cnew_password']:
        user=User.objects.get(email=request.session['to_email'])
        del request.session['to_email']
        user.password=request.POST['new_password']
        user.save()
        msg="Password Updated Successfully"
        return render(request,'login.html',{'msg':msg})
    else:
        msg="New Password & Confirm New Password Does Not Matched"
        return render(request,'new-password.html',{'msg':msg})
    
def change_password(request):
    try:
        user=User.objects.get(email=request.session['email'])
    except:
        return redirect('login')
        
    if request.method=="POST":
        if user.password==request.POST['old_password']:
            if request.POST['new_password']==request.POST['cnew_password']:
                if user.password!=request.POST['new_password']:
                    user.password=request.POST['new_password']
                    user.save()
                    msg="Password Changed Successfully"
                    del request.session['email']
                    del request.session['fname']
                    del request.session['profile_picture']
                    return render(request,'login.html',{'msg':msg})
                else:
                    msg="Old Password & New Password Can't Be Same"
                    if user.usertype=="buyer":
                        return render(request,'change-password.html',{'msg':msg})
                    else:
                        return render(request,'seller-change-password.html',{'msg':msg})
            else:
                msg="New Password & Confirm New Password Does Not Matched"
                if user.usertype=="buyer":
                    return render(request,'change-password.html',{'msg':msg})
                else:
                    return render(request,'seller-change-password.html',{'msg':msg})
        else:
            msg="Old Password Is Incorrect"
            if user.usertype=="buyer":
                return render(request,'change-password.html',{'msg':msg})
            else:
                return render(request,'seller-change-password.html',{'msg':msg})
    else:
        if user.usertype=="buyer":
            return render(request,'change-password.html')
        else:
            return render(request,'seller-change-password.html')
        
def seller_add_product(request):
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype != "seller":
            return redirect('index')
    except (User.DoesNotExist, KeyError):
        return redirect('seller-login')
    
    seller = user
        
    if request.method=="POST":
        product_price = request.POST['product_price'].replace(',', '')
        
        returnable = request.POST.get('returnable') == 'true'
        try:
            return_days = int(request.POST.get('return_days', 0))
        except ValueError:
            return_days = 0
            
        if not returnable:
            return_days = 0
            
        Product.objects.create(
            seller=seller,
            product_category=request.POST['product_category'],
            product_name=request.POST['product_name'],
            product_price=product_price,
            product_desc=request.POST['product_desc'],
            product_picture=request.FILES['product_picture'],
            product_stock=request.POST['product_stock'],
            returnable=returnable,
            return_days=return_days
        )
        msg="Product Added Successfully"
        return render(request,'seller-add-product.html',{'msg':msg, 'categories': CATEGORIES})
    else:
        return render(request,'seller-add-product.html', {'categories': CATEGORIES})
    
def seller_view_product(request):
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype == "seller":
            products = Product.objects.filter(seller=user)
            return render(request, 'seller-view-product.html', {'products': products})
        else:
            return redirect('index')
    except (User.DoesNotExist, KeyError):
        return redirect('seller-login')

def seller_toggle_product_status(request, pk):
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype != "seller":
            return redirect('index')
            
        product = Product.objects.get(pk=pk, seller=user)
        product.product_status = not product.product_status
        product.save()
        # Redirect back to product detail page if 'next' param provided, else listing
        next_url = request.GET.get('next', 'seller-view-product')
        if next_url == 'detail':
            return redirect('seller-product-details', pk=pk)
        return redirect('seller-view-product')
    except (User.DoesNotExist, KeyError, Product.DoesNotExist):
        return redirect('seller-login')

def seller_product_details(request,pk):
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype != "seller":
            return redirect('index')
            
        product = Product.objects.get(pk=pk, seller=user)
        return render(request, 'seller-product-details.html', {'product': product})
    except:
        return redirect('seller-view-product')

def product_details(request,pk):
    if 'email' in request.session:
        try:
            user = User.objects.get(email=request.session['email'])
            if user.usertype == 'seller':
                # If seller owns this product, show them the seller view
                try:
                    product = Product.objects.get(pk=pk, seller=user)
                    return redirect('seller-product-details', pk=pk)
                except Product.DoesNotExist:
                    return redirect('seller-index')
        except User.DoesNotExist:
            pass

    try:
        product=Product.objects.get(pk=pk)
        if not product.product_status:
            return redirect('index')
    except Product.DoesNotExist:
        return redirect('index')
    wishlist_flag=False
    cart_flag=False
    try:
        user=User.objects.get(email=request.session.get('email'))
        try:
            Wishlist.objects.get(user=user,product=product)
            wishlist_flag=True
        except:
            pass
        try:
            Cart.objects.get(user=user,product=product,payment_status=False)
            cart_flag=True
        except:
            pass
    except:
        guest_cart = request.session.get('guest_cart', {})
        if str(pk) in guest_cart:
            cart_flag=True
        guest_wishlist = request.session.get('guest_wishlist', [])
        if str(pk) in guest_wishlist:
            wishlist_flag=True
    product_reviews = Review.objects.filter(product=product).order_by('-time')
    total_reviews = product_reviews.count()
    if total_reviews > 0:
        avg_rating = round(sum(r.rating for r in product_reviews) / total_reviews, 1)
        avg_rating_int = int(round(avg_rating))
        stars_solid = range(avg_rating_int)
        stars_empty = range(5 - avg_rating_int)
    else:
        avg_rating = 0
        avg_rating_int = 0
        stars_solid = range(0)
        stars_empty = range(5)

    for r in product_reviews:
        r.stars_solid = range(r.rating)
        r.stars_empty = range(5 - r.rating)

    return render(request,'product-details.html',{
        'product':product,
        'wishlist_flag':wishlist_flag,
        'cart_flag':cart_flag,
        'reviews': product_reviews,
        'total_reviews': total_reviews,
        'avg_rating': avg_rating,
        'stars_solid': stars_solid,
        'stars_empty': stars_empty
    })

def seller_edit_product(request,pk):
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype != "seller":
            return redirect('index')
        product = Product.objects.get(pk=pk, seller=user)
    except:
        return redirect('seller-view-product')

    if request.method=="POST":
        product.product_category=request.POST['product_category']
        product.product_name=request.POST['product_name']
        product.product_price=request.POST['product_price'].replace(',', '')
        product.product_desc=request.POST['product_desc']
        product.product_stock=request.POST['product_stock']
        
        returnable = request.POST.get('returnable') == 'true'
        try:
            return_days = int(request.POST.get('return_days', 0))
        except ValueError:
            return_days = 0
            
        if not returnable:
            return_days = 0
            
        product.returnable = returnable
        product.return_days = return_days
        
        try:
            product.product_picture=request.FILES['product_picture']
        except:
            pass
        product.save()
        msg="Product Updated Successfully"
        return render(request,'seller-edit-product.html',{'product':product,'msg':msg, 'categories': CATEGORIES})
    else:
        return render(request,'seller-edit-product.html',{'product':product, 'categories': CATEGORIES})

def seller_delete_product(request,pk):
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype != "seller":
            return redirect('index')
        product = Product.objects.get(pk=pk, seller=user)
        product.delete()
        msg = "Product Deleted Successfully"
    except:
        msg = "Product Not Found or Access Denied"
    
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype == "seller":
            products = Product.objects.filter(seller=user)
            return render(request, 'seller-view-product.html', {'products': products, 'msg': msg})
        else:
            return redirect('index')
    except (User.DoesNotExist, KeyError):
        return redirect('seller-login')

def add_to_wishlist(request,pk):
    if 'email' in request.session:
        try:
            user = User.objects.get(email=request.session['email'])
            if user.usertype == 'seller':
                return redirect('seller-index')
        except User.DoesNotExist:
            pass

    try:
        product=Product.objects.get(pk=pk)
        # Allow wishlisting inactive products (Out of Stock items can be saved)
    except Product.DoesNotExist:
        return redirect('index')
    if 'email' in request.session:
        user=User.objects.get(email=request.session['email'])
        wishlist_item, created = Wishlist.objects.get_or_create(user=user,product=product)
        if not created:
            wishlist_item.delete()
            action = 'removed'
        else:
            action = 'added'
        wishlists=Wishlist.objects.filter(user=user, product__product_status=True)
        request.session['wishlist_count'] = len(wishlists)
    else:
        guest_wishlist = request.session.get('guest_wishlist', [])
        if str(pk) in guest_wishlist:
            guest_wishlist.remove(str(pk))
            action = 'removed'
        else:
            guest_wishlist.append(str(pk))
            action = 'added'
        request.session['guest_wishlist'] = guest_wishlist
        request.session['wishlist_count'] = len(guest_wishlist)
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('accept') == 'application/json':
        return JsonResponse({
            'status': 'success', 
            'action': action, 
            'wishlist_count': request.session['wishlist_count'],
            'message': f'Product {action} wishlist'
        })

    return redirect(request.META.get('HTTP_REFERER', 'index'))

def wishlist(request):
    wishlist_pks = []
    if 'email' in request.session:
        try:
            user=User.objects.get(email=request.session['email'])
            if user.usertype == 'seller':
                return redirect('seller-index')
            wishlists=Wishlist.objects.filter(user=user, product__product_status=True)
            wishlist_pks = list(Wishlist.objects.filter(user=user).values_list('product_id', flat=True))
            request.session['wishlist_count']=len(wishlists)
        except:
            return redirect('login')
    else:
        wishlists = []
        guest_wishlist = request.session.get('guest_wishlist', [])
        for pk_str in guest_wishlist:
            try:
                product = Product.objects.get(pk=int(pk_str))
                if product.product_status:
                    wishlists.append({'product': product})
            except Product.DoesNotExist:
                pass
        wishlist_pks = [int(pk) for pk in guest_wishlist]
        request.session['wishlist_count'] = len(wishlists)
    return render(request,'wishlist.html',{'wishlists':wishlists, 'wishlist_pks': wishlist_pks})

def remove_from_wishlist(request,pk):
    if 'email' in request.session:
        try:
            user = User.objects.get(email=request.session['email'])
            if user.usertype == 'seller':
                return redirect('seller-index')
        except User.DoesNotExist:
            pass
        product=Product.objects.get(pk=pk)
        user=User.objects.get(email=request.session['email'])
        try:
            Wishlist.objects.filter(user=user,product=product).delete()
        except: pass
        wishlists=Wishlist.objects.filter(user=user)
        request.session['wishlist_count'] = len(wishlists)
    else:
        guest_wishlist = request.session.get('guest_wishlist', [])
        if str(pk) in guest_wishlist:
            guest_wishlist.remove(str(pk))
            request.session['guest_wishlist'] = guest_wishlist
        request.session['wishlist_count'] = len(guest_wishlist)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('accept') == 'application/json':
        return JsonResponse({'status': 'success', 'wishlist_count': request.session['wishlist_count']})

    return redirect('wishlist')

def add_to_cart(request,pk):
    if 'email' in request.session:
        try:
            user = User.objects.get(email=request.session['email'])
            if user.usertype == 'seller':
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('accept') == 'application/json':
                    return JsonResponse({'status': 'error', 'message': 'Sellers cannot add products to cart.'}, status=403)
                return redirect('seller-index')
        except User.DoesNotExist:
            pass

    try:
        product=Product.objects.get(pk=pk)
        if not product.product_status or product.product_stock == 0:
            # Block purchase of Out of Stock products
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('accept') == 'application/json':
                return JsonResponse({'status': 'error', 'message': 'This product is currently out of stock.'}, status=400)
            return redirect(request.META.get('HTTP_REFERER', 'index'))
    except Product.DoesNotExist:
        return redirect('index')
    if 'email' in request.session:
        user=User.objects.get(email=request.session['email'])
        Cart.objects.get_or_create(
            user=user,
            product=product,
            payment_status=False,
            defaults={
                'product_price': product.product_price,
                'product_qty': 1,
                'total_price': product.product_price
            }
        )
        carts=Cart.objects.filter(user=user,payment_status=False)
        request.session['cart_count']=len(carts)
    else:
        guest_cart = request.session.get('guest_cart', {})
        if str(pk) not in guest_cart:
            guest_cart[str(pk)] = {'qty': 1}
        request.session['guest_cart'] = guest_cart
        request.session['cart_count']=len(guest_cart)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('accept') == 'application/json':
        return JsonResponse({'status': 'success', 'cart_count': request.session['cart_count']})

    return redirect(request.META.get('HTTP_REFERER', 'index'))

def cart(request):
    if 'email' not in request.session:
        return redirect('%s?next=%s' % ('login', 'cart'))
    
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype == 'seller':
            return redirect('seller-index')
            
        carts=Cart.objects.filter(user=user,payment_status=False)
        # Calculate net price only for active products
        active_carts = [i for i in carts if i.product.product_status]
        net_price = sum([i.total_price for i in active_carts])
        
        # GST Calculations
        gst_amount = (net_price * GST_PERCENT) / 100
        total_price = net_price + gst_amount
        
        request.session['cart_count']=len(carts)
        return render(request,'cart.html',{
            'carts':carts,
            'net_price':net_price, 
            'gst_percent': GST_PERCENT,
            'gst_amount': round(gst_amount, 2),
            'total_price': round(total_price, 2),
            'is_authenticated': True
        })
    except:
        return redirect('login')

def remove_from_cart(request,pk):
    if 'email' in request.session:
        try:
            user=User.objects.get(email=request.session['email'])
            if user.usertype == 'seller':
                return redirect('seller-index')
            Cart.objects.filter(user=user, product_id=pk, payment_status=False).delete()
            carts=Cart.objects.filter(user=user,payment_status=False)
            request.session['cart_count']=len(carts)
            active_carts = [c for c in carts if c.product.product_status]
            net_price = sum([c.total_price for c in active_carts])
        except:
            return redirect('login')
    else:
        guest_cart = request.session.get('guest_cart', {})
        if str(pk) in guest_cart:
            del guest_cart[str(pk)]
            request.session['guest_cart'] = guest_cart
        request.session['cart_count']=len(guest_cart)
        net_price = sum([Product.objects.get(pk=int(k)).product_price * v['qty'] for k,v in guest_cart.items()])

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('accept') == 'application/json':
        return JsonResponse({'status': 'success', 'cart_count': request.session['cart_count'], 'net_price': net_price})

    return redirect('cart')

def change_qty(request):
    MAX_QTY = 5
    pk = request.POST['cid']
    product_qty = int(request.POST['product_qty'])
    # Enforce 1-5 limit at the backend (prevents API bypass)
    product_qty = max(1, min(product_qty, MAX_QTY))
    if 'email' in request.session:
        try:
            user = User.objects.get(email=request.session['email'])
            if user.usertype == 'seller':
                return redirect('seller-index')
            cart = Cart.objects.get(pk=int(pk))
            cart.total_price = cart.product_price * product_qty
            cart.product_qty = product_qty
            cart.save()
        except: pass
    else:
        product_pk = str(pk).replace('guest_', '')
        guest_cart = request.session.get('guest_cart', {})
        if product_pk in guest_cart:
            guest_cart[product_pk]['qty'] = product_qty
            request.session['guest_cart'] = guest_cart
    return redirect('cart')

@csrf_exempt
def create_checkout_session(request):
	if 'email' not in request.session:
		return JsonResponse({'error': {'message': 'Please login to checkout.'}}, status=401)
	try:
		try:
			data = json.loads(request.body)
			amount = float(data.get('post_data', 0))
		except (json.JSONDecodeError, ValueError):
			return JsonResponse({'error': {'message': 'Invalid request data.'}}, status=400)
		final_amount=int(amount*100)
		user=User.objects.get(email=request.session['email'])
		if user.usertype == 'seller':
			return JsonResponse({'error': {'message': 'Sellers cannot perform checkout.'}}, status=403)
		
		# Validate stock before creating checkout session
		active_carts = Cart.objects.filter(user=user, payment_status=False, product__product_status=True)
		for item in active_carts:
			if item.product.product_stock < item.product_qty:
				return JsonResponse({'error': {'message': f'Not enough stock for {item.product.product_name}. Available: {item.product.product_stock}'}}, status=400)

		user_name=f"{user.fname} {user.lname}"
		user_address=f"{user.address}"
		user_mobile=f"{user.mobile}"
		session = stripe.checkout.Session.create(
			payment_method_types=['card'],
			line_items=[{
				'price_data': {
					'currency': 'inr',
					'unit_amount': final_amount,
					'product_data': {
						'name': 'Checkout Session Data',
						'description':f'''Customer:{user_name},\n\n
						Address:{user_address},\n
						Mobile:{user_mobile}''',
					},
				},
				'quantity': 1,
				}],
			mode='payment',
			success_url=YOUR_DOMAIN + '/success.html',
			cancel_url=YOUR_DOMAIN + '/cancel.html',
			customer_email=user.email,
			shipping_address_collection={
				'allowed_countries':['IN'],
			}
			)
		
		# Store address in session for the success view
		request.session['temp_delivery_address'] = data.get('delivery_address')
		
		return JsonResponse({'id': session.id})
	except Exception as e:
		return JsonResponse({'error': {'message': str(e)}}, status=500)

def success(request):
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype == 'seller':
            return redirect('seller-index')
        
        active_carts = Cart.objects.filter(user=user, payment_status=False, product__product_status=True)
        
        # Fallback for page refresh / double redirect if cart is already empty
        if not active_carts.exists():
            last_order = Cart.objects.filter(user=user, payment_status=True).order_by('-time').first()
            if last_order:
                order_id = last_order.order_id
                purchased_items = Cart.objects.filter(order_id=order_id)
                total_subtotal = sum(item.total_price for item in purchased_items)
                gst_percent = 18
                gst_val = (total_subtotal * gst_percent) / 100
                grand_total = round(total_subtotal + gst_val, 2)
                payment_method_display = "Online (Stripe)" if last_order.payment_method == 'Stripe' else "Cash on Delivery"
                gst_numbers = set()
                for item in purchased_items:
                    try:
                        if hasattr(item.product.seller, 'seller_profile') and item.product.seller.seller_profile.gst_number:
                            gst_numbers.add(item.product.seller.seller_profile.gst_number)
                    except Exception:
                        pass
                seller_gst_numbers_str = ", ".join(gst_numbers) if gst_numbers else "N/A"
                
                return render(request, 'success.html', {
                    'order_id': order_id,
                    'payment_method': payment_method_display,
                    'subtotal_amount': round(total_subtotal, 2),
                    'gst_amount': round(gst_val, 2),
                    'total_amount': grand_total,
                    'purchased_items': purchased_items,
                    'order_date': last_order.time.strftime('%b %d, %Y %H:%M'),
                    'seller_gst_numbers': seller_gst_numbers_str
                })
            return redirect('index')

        delivery_address = request.session.get('temp_delivery_address')
        order_id = get_unique_order_id()
        
        total_subtotal = 0
        item_list = []
        
        # Deduct stock and generate unique item order ID for each item
        for item in active_carts:
            # Clamp quantity
            if item.product_qty > 5:
                item.product_qty = 5
                item.total_price = item.product_price * 5
                
            total_subtotal += item.total_price
            item_list.append(item)
            
            # Atomic update with stock check
            Product.objects.filter(pk=item.product.pk, product_stock__gte=item.product_qty).update(
                product_stock=F('product_stock') - item.product_qty
            )
            item.item_order_id = generate_item_order_id(order_id, item.product.pk)
            item.save(update_fields=['item_order_id', 'total_price', 'product_qty'])
            
        gst_percent = 18
        gst_val = (total_subtotal * gst_percent) / 100
        grand_total = round(total_subtotal + gst_val, 2)
        
        request.session['last_order_total'] = grand_total
        request.session['last_order_id'] = order_id

        send_order_placed_notification(user, active_carts, order_id)
        active_carts.update(payment_status=True, delivery_address=delivery_address, order_id=order_id)
            
        # Clean up session
        if 'temp_delivery_address' in request.session:
            del request.session['temp_delivery_address']
            
        request.session['cart_count'] = 0
        
        gst_numbers = set()
        for item in item_list:
            try:
                if hasattr(item.product.seller, 'seller_profile') and item.product.seller.seller_profile.gst_number:
                    gst_numbers.add(item.product.seller.seller_profile.gst_number)
            except Exception:
                pass
        seller_gst_numbers_str = ", ".join(gst_numbers) if gst_numbers else "N/A"
        
        return render(request, 'success.html', {
            'order_id': order_id,
            'payment_method': 'Online (Stripe)',
            'subtotal_amount': round(total_subtotal, 2),
            'gst_amount': round(gst_val, 2),
            'total_amount': grand_total,
            'purchased_items': item_list,
            'order_date': timezone.now().strftime('%b %d, %Y %H:%M'),
            'seller_gst_numbers': seller_gst_numbers_str
        })
    except:
        return redirect('login')

def cancel(request):
    if 'email' in request.session:
        try:
            user = User.objects.get(email=request.session['email'])
            if user.usertype == 'seller':
                return redirect('seller-index')
        except User.DoesNotExist:
            pass
    return render(request,'cancel.html')

def myorder(request):
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype == 'seller':
            return redirect('seller-myorder')
        carts = Cart.objects.filter(user=user, payment_status=True).order_by('-time')
        
        # Load and attach reviews
        reviews = Review.objects.filter(user=user)
        review_map = {r.cart_id: r for r in reviews if r.cart_id}
        for cart in carts:
            cart.review = review_map.get(cart.pk)
            
            # Return policy calculations
            is_returnable = cart.product.returnable
            is_return_eligible = False
            return_expiry_date = None
            
            if is_returnable and cart.delivery_status == 'delivered':
                if not cart.delivery_date:
                    cart.delivery_date = timezone.now()
                    cart.save(update_fields=['delivery_date'])
                delivery_dt = cart.delivery_date
                return_expiry_date = delivery_dt + timezone.timedelta(days=cart.product.return_days)
                is_return_eligible = timezone.now() <= return_expiry_date
                
            cart.is_return_allowed = is_returnable
            cart.is_return_eligible = is_return_eligible
            cart.return_expiry_date = return_expiry_date
            
        return render(request, 'myorder.html', {'carts': carts})
    except Exception as e:
        return redirect('login')

def cod_checkout(request):
    if request.method == "POST":
        if 'email' not in request.session:
            return redirect('%s?next=%s' % ('login', 'cart'))
        try:
            user = User.objects.get(email=request.session['email'])
            if user.usertype == 'seller':
                return redirect('seller-index')
            
            active_carts = Cart.objects.filter(user=user, payment_status=False, product__product_status=True)
            
            # Fallback for double submission or page refresh if cart is already empty
            if not active_carts.exists():
                last_order = Cart.objects.filter(user=user, payment_status=True).order_by('-time').first()
                if last_order:
                    order_id = last_order.order_id
                    purchased_items = Cart.objects.filter(order_id=order_id)
                    total_subtotal = sum(item.total_price for item in purchased_items)
                    gst_percent = 18
                    gst_val = (total_subtotal * gst_percent) / 100
                    grand_total = round(total_subtotal + gst_val, 2)
                    payment_method_display = "Cash on Delivery" if last_order.payment_method == 'COD' else "Online (Stripe)"
                    
                    return render(request, 'success.html', {
                        'order_id': order_id,
                        'payment_method': payment_method_display,
                        'subtotal_amount': round(total_subtotal, 2),
                        'gst_amount': round(gst_val, 2),
                        'total_amount': grand_total,
                        'purchased_items': purchased_items,
                        'order_date': last_order.time.strftime('%b %d, %Y %H:%M')
                    })
                return redirect('cart')

            delivery_address = request.POST.get('delivery_address')
            order_id = get_unique_order_id()

            total_subtotal = 0
            item_list = []
            # Validate stock before finalizing
            for item in active_carts:
                if item.product.product_stock < item.product_qty:
                    msg = f"Not enough stock for {item.product.product_name}. Available: {item.product.product_stock}"
                    return render(request, 'cart.html', {'msg': msg, 'carts': active_carts, 'is_authenticated': True})

                # Clamp quantity
                if item.product_qty > 5:
                    item.product_qty = 5
                    item.total_price = item.product_price * 5
                
                total_subtotal += item.total_price
                item_list.append(item)

                # Atomic stock deduction
                Product.objects.filter(pk=item.product.pk, product_stock__gte=item.product_qty).update(
                    product_stock=F('product_stock') - item.product_qty
                )
                
                # Generate unique item order ID
                item.item_order_id = generate_item_order_id(order_id, item.product.pk)
                item.save()

            gst_percent = 18
            gst_val = (total_subtotal * gst_percent) / 100
            grand_total = round(total_subtotal + gst_val, 2)
            
            # Save to session for persistence
            request.session['last_order_total'] = grand_total
            request.session['last_order_id'] = order_id

            send_order_placed_notification(user, active_carts, order_id)

            active_carts.update(payment_status=True, payment_method='COD', delivery_address=delivery_address, order_id=order_id)
            request.session['cart_count'] = 0
            return render(request, 'success.html', {
                'order_id': order_id,
                'payment_method': 'Cash on Delivery',
                'subtotal_amount': round(total_subtotal, 2),
                'gst_amount': round(gst_val, 2),
                'total_amount': grand_total,
                'purchased_items': item_list,
                'order_date': timezone.now().strftime('%b %d, %Y %H:%M')
            })
        except:
            return redirect('login')
    return redirect('cart')

@csrf_exempt
def buyer_cancel_order(request):
    """Buyer cancels an order ONLY if status is 'placed' or 'confirmed' (pre-shipment).
    Notifies the seller via the existing Contact/notification system and restores stock."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if 'email' not in request.session:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    CANCELLABLE_STATUSES = ['placed', 'confirmed']

    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')

        buyer = User.objects.get(email=request.session['email'])
        if buyer.usertype != 'buyer':
            return JsonResponse({'error': 'Forbidden'}, status=403)

        # Verify the order belongs to this buyer and is paid
        order = Cart.objects.get(pk=order_id, user=buyer, payment_status=True)

        if order.is_cancelled:
            return JsonResponse({'error': 'This order is already cancelled.'}, status=400)

        if order.delivery_status not in CANCELLABLE_STATUSES:
            return JsonResponse({'error': 'Order cannot be cancelled after shipment has begun.'}, status=400)

        # Mark as cancelled
        order.is_cancelled = True
        order.cancel_reason = 'Cancelled by buyer'
        order.save()

        # Restore stock safely
        if order.product:
            from django.db.models import F
            Product.objects.filter(pk=order.product.pk).update(
                product_stock=F('product_stock') + order.product_qty
            )

        # Notify the seller via the Contact/notification system
        seller = order.product.seller
        Contact.objects.create(
            seller=seller,
            product=order.product,
            name=f"{buyer.fname} {buyer.lname}",
            email=buyer.email,
            subject=f"Order Cancelled by Buyer: {order.product.product_name}",
            message="Order cancellation notification (buyer initiated, system generated)",
            reply=(
                f"The buyer '{buyer.fname} {buyer.lname}' has cancelled their order for "
                f"'{order.product.product_name}' (Qty: {order.product_qty}). "
                f"The order was in '{order.delivery_status}' status at the time of cancellation."
            ),
            is_read=False,
        )

        return JsonResponse({'success': True, 'message': 'Order cancelled successfully.'})

    except Cart.DoesNotExist:
        return JsonResponse({'error': 'Order not found or unauthorized.'}, status=404)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def buyer_return_order(request):
    """Buyer initiates a return for a delivered order item, provided the item's product is returnable
    and current time is within the return window (days) from delivery."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if 'email' not in request.session:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        return_reason = data.get('return_reason', '').strip()

        buyer = User.objects.get(email=request.session['email'])
        if buyer.usertype != 'buyer':
            return JsonResponse({'error': 'Forbidden'}, status=403)

        # Verify the order belongs to this buyer and is paid
        order = Cart.objects.get(pk=order_id, user=buyer, payment_status=True)

        if order.is_cancelled:
            return JsonResponse({'error': 'Cannot return a cancelled order.'}, status=400)

        if order.delivery_status != 'delivered':
            return JsonResponse({'error': 'Only delivered orders can be returned.'}, status=400)

        if not order.product.returnable:
            return JsonResponse({'error': 'This product is not eligible for returns.'}, status=400)

        if order.return_status not in ['none', 'None', '', None]:
            return JsonResponse({'error': 'Return has already been requested or processed for this order.'}, status=400)

        # Check return window eligibility (delivery_date + return_days)
        if not order.delivery_date:
            order.delivery_date = timezone.now()
            order.save(update_fields=['delivery_date'])
        delivery_dt = order.delivery_date
        return_expiry_date = delivery_dt + timezone.timedelta(days=order.product.return_days)
        
        if timezone.now() > return_expiry_date:
            return JsonResponse({'error': 'The return window for this order has expired.'}, status=400)

        # Update return status to REQUESTED (Return Request Processing) and save reason
        order.return_status = 'REQUESTED'
        order.return_reason = return_reason
        order.save()

        # (Restocking deferred until seller approves/receives return)

        # Notify the seller via the Contact/notification system
        seller = order.product.seller
        Contact.objects.create(
            seller=seller,
            product=order.product,
            name=f"{buyer.fname} {buyer.lname}",
            email=buyer.email,
            subject=f"Product Return: {order.product.product_name}",
            message="Return request notification (buyer initiated, system generated)",
            reply=(
                f"The buyer '{buyer.fname} {buyer.lname}' has initiated a return for "
                f"'{order.product.product_name}' (Qty: {order.product_qty}) under the return window policy of {order.product.return_days} days.\n\n"
                f"Reason for Return: {return_reason if return_reason else 'No reason provided'}"
            ),
            is_read=False,
        )

        return JsonResponse({'success': True, 'message': 'Return process initiated successfully.'})

    except Cart.DoesNotExist:
        return JsonResponse({'error': 'Order not found or unauthorized.'}, status=404)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def seller_receive_return(request):
    """Seller marks order as successfully received/returned, transitioning status to COMPLETED."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if 'email' not in request.session:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')

        seller = User.objects.get(email=request.session['email'])
        if seller.usertype != 'seller':
            return JsonResponse({'error': 'Forbidden'}, status=403)

        # Fetch order and verify it belongs to this seller's product
        order = Cart.objects.get(pk=order_id, product__seller=seller, payment_status=True)

        if order.return_status != 'REQUESTED' and order.return_status != 'returned':
            return JsonResponse({'error': 'Return is not requested or pending for this order.'}, status=400)

        # Update return status to COMPLETED (Returned Successful)
        order.return_status = 'COMPLETED'
        order.save()

        # --- Safely Auto-Restock Product Stock (Atomic, Idempotent) ---
        if not order.is_restocked:
            if order.product:
                from django.db.models import F
                Product.objects.filter(pk=order.product.pk).update(
                    product_stock=F('product_stock') + order.product_qty
                )
                order.is_restocked = True
                order.save(update_fields=['is_restocked'])
                print(f"[Inventory Log] Auto-restocked product '{order.product.product_name}' (ID: {order.product.pk}), added quantity: {order.product_qty} back to stock.")

        # --- Notify buyer via existing Contact/notification system ---
        notification_subject = f"Return Successful: {order.product.product_name}"
        notification_reply = (
            f"Your returned product '{order.product.product_name}' (Qty: {order.product_qty}) "
            f"has been successfully received and processed by the seller. Return Completed!"
        )
        Contact.objects.create(
            seller=seller,
            product=order.product,
            name=f"{order.user.fname} {order.user.lname}",
            email=order.user.email,
            subject=notification_subject,
            message=f"Return completion notification (system generated) | CartID:{order.pk}",
            reply=notification_reply,
            is_read=False,
        )

        return JsonResponse({'success': True, 'message': 'Return marked as completed successfully.'})

    except Cart.DoesNotExist:
        return JsonResponse({'error': 'Order not found or unauthorized.'}, status=404)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def seller_myorder(request):
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype == "seller":
            orders = (Cart.objects.filter(product__seller=user, payment_status=True)
                      .select_related('user', 'product', 'product__seller')
                      .order_by('-time'))
            reviews = Review.objects.filter(product__seller=user).only('cart_id', 'rating', 'review_text', 'time')
            review_map = {r.cart_id: r for r in reviews if r.cart_id}
            for order in orders:
                order.review = review_map.get(order.pk)
            return render(request, 'seller-myorder.html', {'orders': orders})
        else:
            return redirect('index')
    except (User.DoesNotExist, KeyError):
        return redirect('seller-login')

@csrf_exempt
def seller_cancel_order(request):
    """Seller cancels a specific order item with a mandatory reason.
    Notifies the buyer via the existing Contact/notification system."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if 'email' not in request.session:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        cancel_reason = (data.get('cancel_reason') or '').strip()

        # Validate mandatory reason
        if not cancel_reason:
            return JsonResponse({'error': 'Cancellation reason is required.'}, status=400)

        seller = User.objects.get(email=request.session['email'])
        if seller.usertype != 'seller':
            return JsonResponse({'error': 'Forbidden'}, status=403)

        # Fetch order and verify it belongs to this seller's product
        order = Cart.objects.get(pk=order_id, product__seller=seller, payment_status=True)

        if order.is_cancelled:
            return JsonResponse({'error': 'This order is already cancelled.'}, status=400)

        # Mark as cancelled
        order.is_cancelled = True
        order.cancel_reason = cancel_reason
        order.save()

        # --- Restore Stock Safely ---
        if order.product:
            from django.db.models import F
            Product.objects.filter(pk=order.product.pk).update(
                product_stock=F('product_stock') + order.product_qty
            )

        # --- Notify buyer via existing Contact/notification system ---
        notification_subject = f"Order Cancelled: {order.product.product_name}"
        notification_message = (
            f"Your order for '{order.product.product_name}' (Qty: {order.product_qty}) "
            f"has been cancelled by the seller.\n\n"
            f"Reason: {cancel_reason}\n\n"
            f"If you have any questions, please contact the seller."
        )
        Contact.objects.create(
            seller=seller,
            product=order.product,
            name=f"{order.user.fname} {order.user.lname}",
            email=order.user.email,
            subject=notification_subject,
            message=f"Order cancellation notification (system generated) | CartID:{order.pk}",
            reply=notification_message,
            is_read=False,
        )

        return JsonResponse({'success': True, 'message': 'Order cancelled successfully.'})

    except Cart.DoesNotExist:
        return JsonResponse({'error': 'Order not found or unauthorized.'}, status=404)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def seller_confirm_order(request):
    """Seller confirms an order, moving its tracking status from placed to confirmed."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if 'email' not in request.session:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')

        seller = User.objects.get(email=request.session['email'])
        if seller.usertype != 'seller':
            return JsonResponse({'error': 'Forbidden'}, status=403)

        # Fetch order and verify it belongs to this seller's product
        order = Cart.objects.get(pk=order_id, product__seller=seller, payment_status=True)

        if order.is_cancelled:
            return JsonResponse({'error': 'Cannot confirm a cancelled order.'}, status=400)
            
        if order.delivery_status != 'placed':
            return JsonResponse({'error': 'Order is already confirmed or further in the tracking timeline.'}, status=400)

        # Update tracking status
        order.delivery_status = 'confirmed'
        order.save()

        # --- Notify buyer via existing Contact/notification system ---
        notification_subject = f"Order Confirmed: {order.product.product_name}"
        notification_message = (
            f"Great news! Your order for '{order.product.product_name}' (Qty: {order.product_qty}) "
            f"has been confirmed by the seller and is being prepared for shipping."
        )
        Contact.objects.create(
            seller=seller,
            product=order.product,
            name=f"{order.user.fname} {order.user.lname}",
            email=order.user.email,
            subject=notification_subject,
            message=f"Order confirmation notification (system generated) | CartID:{order.pk}",
            reply=notification_message,
            is_read=False,
        )

        return JsonResponse({'success': True, 'message': 'Order confirmed successfully.'})

    except Cart.DoesNotExist:
        return JsonResponse({'error': 'Order not found or unauthorized.'}, status=404)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def seller_ship_order(request):
    """Seller ships an order, moving its tracking status from confirmed to shipped."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if 'email' not in request.session:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')

        seller = User.objects.get(email=request.session['email'])
        if seller.usertype != 'seller':
            return JsonResponse({'error': 'Forbidden'}, status=403)

        # Fetch order and verify it belongs to this seller's product
        order = Cart.objects.get(pk=order_id, product__seller=seller, payment_status=True)

        if order.is_cancelled:
            return JsonResponse({'error': 'Cannot ship a cancelled order.'}, status=400)
            
        if order.delivery_status != 'confirmed':
            return JsonResponse({'error': 'Order must be confirmed before shipping.'}, status=400)

        # Update tracking status
        order.delivery_status = 'shipped'
        order.save()

        # --- Notify buyer via existing Contact/notification system ---
        notification_subject = f"Order Shipped: {order.product.product_name}"
        notification_message = (
            f"Your order for '{order.product.product_name}' (Qty: {order.product_qty}) has been shipped by the seller."
        )
        Contact.objects.create(
            seller=seller,
            product=order.product,
            name=f"{order.user.fname} {order.user.lname}",
            email=order.user.email,
            subject=notification_subject,
            message=f"Order shipment notification (system generated) | CartID:{order.pk}",
            reply=notification_message,
            is_read=False,
        )

        return JsonResponse({'success': True, 'message': 'Order shipped successfully.'})

    except Cart.DoesNotExist:
        return JsonResponse({'error': 'Order not found or unauthorized.'}, status=404)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def seller_out_for_delivery_order(request):
    """Seller marks order out for delivery, moving status from shipped to out_for_delivery."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if 'email' not in request.session:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')

        seller = User.objects.get(email=request.session['email'])
        if seller.usertype != 'seller':
            return JsonResponse({'error': 'Forbidden'}, status=403)

        # Fetch order and verify it belongs to this seller's product
        order = Cart.objects.get(pk=order_id, product__seller=seller, payment_status=True)

        if order.is_cancelled:
            return JsonResponse({'error': 'Cannot mark cancelled order.'}, status=400)
            
        if order.delivery_status != 'shipped':
            return JsonResponse({'error': 'Order must be shipped before marking out for delivery.'}, status=400)

        # Update tracking status
        order.delivery_status = 'out_for_delivery'
        order.save()

        # --- Notify buyer via existing Contact/notification system ---
        notification_subject = f"Out for Delivery: {order.product.product_name}"
        notification_message = (
            f"Your order for '{order.product.product_name}' (Qty: {order.product_qty}) is out for delivery."
        )
        Contact.objects.create(
            seller=seller,
            product=order.product,
            name=f"{order.user.fname} {order.user.lname}",
            email=order.user.email,
            subject=notification_subject,
            message=f"Order out for delivery notification (system generated) | CartID:{order.pk}",
            reply=notification_message,
            is_read=False,
        )

        return JsonResponse({'success': True, 'message': 'Order marked out for delivery successfully.'})

    except Cart.DoesNotExist:
        return JsonResponse({'error': 'Order not found or unauthorized.'}, status=404)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def seller_deliver_order(request):
    """Seller marks order as delivered, moving status from out_for_delivery to delivered."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if 'email' not in request.session:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')

        seller = User.objects.get(email=request.session['email'])
        if seller.usertype != 'seller':
            return JsonResponse({'error': 'Forbidden'}, status=403)

        # Fetch order and verify it belongs to this seller's product
        order = Cart.objects.get(pk=order_id, product__seller=seller, payment_status=True)

        if order.is_cancelled:
            return JsonResponse({'error': 'Cannot deliver a cancelled order.'}, status=400)
            
        if order.delivery_status != 'out_for_delivery':
            return JsonResponse({'error': 'Order must be out for delivery before marking delivered.'}, status=400)

        # Update tracking status
        order.delivery_status = 'delivered'
        order.delivery_date = timezone.now()
        order.save()

        # --- Notify buyer via existing Contact/notification system ---
        notification_subject = f"Order Delivered: {order.product.product_name}"
        notification_message = (
            f"Your order for '{order.product.product_name}' (Qty: {order.product_qty}) has been delivered successfully. Thank you for shopping with us!"
        )
        Contact.objects.create(
            seller=seller,
            product=order.product,
            name=f"{order.user.fname} {order.user.lname}",
            email=order.user.email,
            subject=notification_subject,
            message=f"Order delivery notification (system generated) | CartID:{order.pk}",
            reply=notification_message,
            is_read=False,
        )

        return JsonResponse({'success': True, 'message': 'Order marked delivered successfully.'})

    except Cart.DoesNotExist:
        return JsonResponse({'error': 'Order not found or unauthorized.'}, status=404)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def seller_category_counts(request):
    if 'email' not in request.session:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        seller = User.objects.get(email=request.session['email'])
        cache_key = f'seller_cat_counts_{seller.pk}'
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse({'categories': cached})
        counts = list(Product.objects.filter(seller=seller)
                      .values('product_category')
                      .annotate(count=Count('id'))
                      .filter(count__gt=0)
                      .order_by('product_category'))
        cache.set(cache_key, counts, 30)
        return JsonResponse({'categories': counts})
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

def global_category_counts(request):
    cached = cache.get('global_cat_counts')
    if cached is not None:
        return JsonResponse({'categories': cached})
    counts = list(Product.objects.filter(product_status=True)
                  .values('product_category')
                  .annotate(count=Count('id'))
                  .filter(count__gt=0)
                  .order_by('product_category'))
    cache.set('global_cat_counts', counts, 60)
    return JsonResponse({'categories': counts})
def seller_reply(request):
    if request.method == "POST":
        contact_id = request.POST.get('contact_id')
        reply_text = request.POST.get('reply')
        
        try:
            contact = Contact.objects.get(pk=contact_id)
            contact.reply = reply_text
            contact.is_read = False # Reset read status so buyer gets notified
            contact.save()
            return redirect('seller-contact')
        except Contact.DoesNotExist:
            return redirect('seller-contact')
    return redirect('seller-index')

def get_notifications(request):
    if 'email' not in request.session:
        return JsonResponse({'count': 0, 'notifications': []})
    
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype == 'seller':
            return JsonResponse({'count': 0, 'notifications': []})
        
        # Base queryset (NOT sliced yet) so we can compute count correctly
        base_qs = Contact.objects.filter(email=user.email, reply__isnull=False)
        
        # Unread count MUST be computed before slicing — sliced QS cannot be re-filtered
        unread_count = base_qs.filter(is_read=False).count()
        
        # Now slice for display (last 20 most recent)
        recent = base_qs.order_by('-time')[:20]
        
        notif_list = []
        for n in recent:
            # Parse Cart ID from message if present
            cart_id = None
            if n.message and "CartID:" in n.message:
                try:
                    cart_id = int(n.message.split("CartID:")[1].strip())
                except:
                    pass

            notif_list.append({
                'id': n.id,
                'subject': n.subject,
                'reply': n.reply[:120] + '...' if len(n.reply) > 120 else n.reply,
                'time': n.time.strftime("%b %d, %H:%M"),
                'is_read': n.is_read,
                'product_id': n.product.pk if n.product else None,
                'cart_id': cart_id
            })
            
        return JsonResponse({'count': unread_count, 'notifications': notif_list})
    except User.DoesNotExist:
        return JsonResponse({'count': 0, 'notifications': []})

def get_buyer_recent_orders(request):
    if 'email' not in request.session:
        return JsonResponse({'orders': []})
    try:
        user = User.objects.get(email=request.session['email'])
        orders = Cart.objects.filter(user=user, is_cancelled=False).order_by('-time')[:15]
        order_list = []
        for o in orders:
            order_list.append({
                'id': o.pk,
                'display_id': o.display_item_order_id,
                'product_id': o.product.pk,
                'product_name': o.product.product_name,
                'product_price': o.product_price,
                'product_qty': o.product_qty,
                'seller_id': o.product.seller.pk,
                'seller_name': f"{o.product.seller.fname} {o.product.seller.lname}",
                'status': o.delivery_status,
                'time': o.time.strftime('%Y-%m-%d %H:%M')
            })
        return JsonResponse({'orders': order_list})
    except Exception as e:
        return JsonResponse({'orders': [], 'error': str(e)})

def get_buyer_chats(request):
    if 'email' not in request.session:
        return JsonResponse({'chats': []})
    try:
        user = User.objects.get(email=request.session['email'])
        inquiries = Contact.objects.filter(email__iexact=user.email).order_by('-time')[:20]
        chats_data = []
        for i in inquiries:
            chats_data.append({
                'id': i.pk,
                'time_date': i.time.strftime("%b %d, %Y"),
                'time_clock': i.time.strftime("%H:%M"),
                'subject': i.subject,
                'message': i.message,
                'reply': i.reply if i.reply else "",
                'product_name': i.product.product_name if i.product else None,
            })
        return JsonResponse({'chats': chats_data})
    except Exception as e:
        return JsonResponse({'chats': [], 'error': str(e)})


def mark_single_read(request, pk):
    if 'email' not in request.session:
        return JsonResponse({'status': 'error'})
    try:
        Contact.objects.filter(pk=pk).update(is_read=True)
        return JsonResponse({'status': 'success'})
    except:
        return JsonResponse({'status': 'error'})

def mark_as_read(request):
    if 'email' not in request.session:
        return JsonResponse({'status': 'error'})
    
    try:
        user = User.objects.get(email=request.session['email'])
        Contact.objects.filter(email=user.email, reply__isnull=False, is_read=False).update(is_read=True)
        return JsonResponse({'status': 'success'})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error'})

def get_seller_notifications(request):
    """Returns system-generated notifications for the logged-in seller.
    These are Contact records where the seller is the recipient (e.g. buyer-cancelled orders)."""
    if 'email' not in request.session:
        return JsonResponse({'count': 0, 'notifications': []})

    try:
        seller = User.objects.get(email=request.session['email'])
        if seller.usertype != 'seller':
            return JsonResponse({'count': 0, 'notifications': []})

        # Surface all messages, buyer inquiries, system-generated, or chatbot alerts
        base_qs = Contact.objects.filter(seller=seller)

        unread_count = base_qs.filter(is_read=False).count()
        recent = base_qs.order_by('-time')[:20]

        notif_list = []
        for n in recent:
            cart_id = None
            if n.message and "CartID:" in n.message:
                try:
                    cart_id = int(n.message.split("CartID:")[1].strip())
                except:
                    pass
            
            # Safe text fallback for chatbot messages where n.reply is None
            preview = n.reply if n.reply else (n.message if n.message else "")
            preview_truncated = preview[:120] + '...' if len(preview) > 120 else preview
            
            notif_list.append({
                'id': n.id,
                'subject': n.subject,
                'reply': preview_truncated,
                'time': n.time.strftime("%b %d, %H:%M"),
                'is_read': n.is_read,
                'product_id': n.product.pk if n.product else None,
                'cart_id': cart_id
            })

        return JsonResponse({'count': unread_count, 'notifications': notif_list})
    except User.DoesNotExist:
        return JsonResponse({'count': 0, 'notifications': []})

def mark_seller_notifications_read(request):
    """Marks all seller system notifications as read."""
    if 'email' not in request.session:
        return JsonResponse({'status': 'error'})
    try:
        seller = User.objects.get(email=request.session['email'])
        if seller.usertype != 'seller':
            return JsonResponse({'status': 'error'})
        Contact.objects.filter(seller=seller, is_read=False).update(is_read=True)
        return JsonResponse({'status': 'success'})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error'})

@csrf_exempt
def submit_review(request):
    """Submits or edits a buyer review for a delivered product."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if 'email' not in request.session:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        cart_id = data.get('cart_id')
        rating = data.get('rating')
        review_text = data.get('review_text', '').strip()

        if not cart_id or not rating:
            return JsonResponse({'error': 'Order ID and rating are required.'}, status=400)

        # Validate rating
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                return JsonResponse({'error': 'Rating must be between 1 and 5.'}, status=400)
        except ValueError:
            return JsonResponse({'error': 'Invalid rating format.'}, status=400)

        user = User.objects.get(email=request.session['email'])
        if user.usertype != 'buyer':
            return JsonResponse({'error': 'Only buyers can submit reviews.'}, status=403)

        # Fetch corresponding cart item order and verify ownership and delivery status
        cart_item = Cart.objects.get(pk=cart_id, user=user, payment_status=True)

        if cart_item.delivery_status != 'delivered':
            return JsonResponse({'error': 'Reviews are only allowed after the product is delivered.'}, status=400)

        # Check if review already exists to update it (Edit Review support) or create new
        review, created = Review.objects.update_or_create(
            user=user,
            product=cart_item.product,
            cart=cart_item,
            defaults={
                'rating': rating,
                'review_text': review_text,
                'time': timezone.now()
            }
        )

        if created:
            # Create a real-time notification (Contact record) for the seller
            notification_subject = f"New Product Review: {cart_item.product.product_name}"
            notification_reply = (
                f"New review received on your product '{cart_item.product.product_name}' "
                f"from buyer {user.fname} {user.lname}.\n\n"
                f"Rating: {'★' * rating}{'☆' * (5 - rating)} ({rating}/5)\n"
                f"Review: \"{review_text if review_text else 'No comment provided'}\""
            )
            Contact.objects.create(
                seller=cart_item.product.seller,
                product=cart_item.product,
                name=f"{user.fname} {user.lname}",
                email=user.email,
                subject=notification_subject,
                message=f"New review received (system generated) | CartID:{cart_item.pk}",
                reply=notification_reply,
                is_read=False
            )

        message = 'Review submitted successfully.' if created else 'Review updated successfully.'
        return JsonResponse({
            'success': True,
            'message': message,
            'rating': review.rating,
            'review_text': review.review_text
        })

    except Cart.DoesNotExist:
        return JsonResponse({'error': 'Order details not found.'}, status=404)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def search_suggestions(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'results': []})
    
    from django.db.models import Q
    products = Product.objects.filter(
        Q(product_name__icontains=query) |
        Q(product_category__icontains=query),
        product_status=True
    ).order_by('-id')[:6]
    
    results = []
    for p in products:
        results.append({
            'id': p.pk,
            'name': p.product_name,
            'category': p.product_category,
            'price': p.product_price,
            'image_url': p.product_picture.url if p.product_picture else ''
        })
    return JsonResponse({'results': results})


