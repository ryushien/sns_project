import os

from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LogoutView
from django.conf import settings
from django.conf.urls.static import static
from core.views import RateLimitedLoginView

# 本番の管理画面URLは環境変数で指定する（公開リポジトリに載せない）
ADMIN_URL = os.environ.get("ADMIN_URL", "admin/")

urlpatterns = [
    path(ADMIN_URL, admin.site.urls),
    path('', include('core.urls')),
    path('login/', RateLimitedLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='/'), name='logout'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)