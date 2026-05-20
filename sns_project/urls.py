from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LogoutView
from django.conf import settings
from django.conf.urls.static import static
from core.views import RateLimitedLoginView

urlpatterns = [
    path('secret-admin-7xk2/', admin.site.urls),
    path('', include('core.urls')),
    path('login/', RateLimitedLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='/'), name='logout'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)