from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from .models import Post
try:
    from ratelimit.decorators import ratelimit           # 通常はこちら
except ImportError:
    from django_ratelimit.decorators import ratelimit    # 環境によってはこちら


def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserCreationForm()
    return render(request, 'core/signup.html', {'form': form})

@login_required
def index(request):
    posts = Post.objects.all().order_by('-created_at')
    return render(request, 'core/index.html', {'posts': posts})

@login_required
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def post_create(request):
    if request.method == 'POST':
        if getattr(request,'limited',False):
            return render(request,'core/post_create.html',{'error': '投稿が多すぎます 1分後に再試行してください。'})
        content = request.POST.get('content')
        if content:
            Post.objects.create(user=request.user, content=content)
        return redirect('index')
    return render(request, 'core/post_create.html')

# Create your views here.

from django.contrib.auth.views import LoginView
from django.utils.decorators import method_decorator
from django.contrib import messages

# POSTメソッドの試行をIP単位で 5回/分 に制限。超過時は 429 を返す。
@method_decorator(ratelimit(key='ip', rate='5/m', method='POST', block=True), name='dispatch')
class RateLimitedLoginView(LoginView):
    template_name = 'core/login.html'

    def post(self, request, *args, **kwargs):
        # ratelimit によって request.limited が付与される
        if getattr(request, 'limited', False):
            messages.error(request, "ログイン試行が多すぎます。1分後に再試行してください。")
            return self.get(request, *args, **kwargs)  # フォーム再表示
        return super().post(request, *args, **kwargs)
