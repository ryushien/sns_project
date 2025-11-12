"""
URL configuration for sns_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# sns_project/urls.py
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LoginView, LogoutView
from ratelimit.decorators import ratelimit

# ここで LoginView をデコレータで包む（core.views を import しない）
login_view = ratelimit(key='ip', rate='5/m', method='POST', block=True)(
    LoginView.as_view(template_name='core/login.html')
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('login/', login_view, name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
