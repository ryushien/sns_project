from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import Thread, Post  # ★ ここを変更：Thread も読み込む

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


# -----------------------------
# 2ch 風：スレッド一覧
# -----------------------------
@login_required
def thread_list(request):
    threads = Thread.objects.all().order_by('-created_at')
    return render(request, 'core/index.html', {  # ★ index.html をスレ一覧に使う
        'threads': threads
    })


# -----------------------------
# 新規スレッド作成（スレ立て＋>>1）
# -----------------------------
@login_required
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def thread_new(request):
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            return render(
                request,
                'core/post_create.html',
                {'error': 'スレ立てが多すぎます。1分後に再試行してください。'}
            )

        title = request.POST.get('title')
        content = request.POST.get('content')
        image = request.FILES.get('image')
        video = request.FILES.get('video')

        if title and content:
            # スレッド本体
            thread = Thread.objects.create(
                title=title,
                created_by=request.user
            )
            # >>1 の投稿
            Post.objects.create(
                thread=thread,
                author=request.user,
                content=content,
                image=image,   
                video=video, 
            )
            return redirect('thread_detail', thread_id=thread.id)

    return render(request, 'core/post_create.html')


# -----------------------------
# スレッド詳細（レス一覧）
# -----------------------------
@login_required
def thread_detail(request, thread_id):
    thread = get_object_or_404(Thread, id=thread_id)
    posts = thread.posts.all().order_by('created_at')
    return render(request, 'core/thread_detail.html', {
        'thread': thread,
        'posts': posts
    })


# -----------------------------
# レス投稿
# -----------------------------
@login_required
@ratelimit(key='user', rate='20/m', method='POST', block=True)
def post_reply(request, thread_id):
    thread = get_object_or_404(Thread, id=thread_id)

    if request.method == 'POST':
        if getattr(request, 'limited', False):
            posts = thread.posts.all().order_by('created_at')
            return render(request, 'core/thread_detail.html', {
                'thread': thread,
                'posts': posts,
                'error': '投稿が多すぎます。1分後に再試行してください。'
            })

        content = request.POST.get('content')

        image = request.FILES.get('image')
        video = request.FILES.get('video')

        if content or image or video:
            Post.objects.create(
                thread=thread,
                author=request.user,
                content=content or "",
                image=image,
                video=video,
            )
        return redirect('thread_detail', thread_id=thread.id)

    return redirect('thread_detail', thread_id=thread.id)


# -----------------------------
# ログイン制限付き LoginView（そのまま）
# -----------------------------
from django.contrib.auth.views import LoginView
from django.utils.decorators import method_decorator

@method_decorator(
    ratelimit(key='ip', rate='5/m', method='POST', block=True),
    name='dispatch'
)
class RateLimitedLoginView(LoginView):
    template_name = 'core/login.html'

    def post(self, request, *args, **kwargs):
        if getattr(request, 'limited', False):
            messages.error(request, "ログイン試行が多すぎます。1分後に再試行してください。")
            return self.get(request, *args, **kwargs)
        return super().post(request, *args, **kwargs)
