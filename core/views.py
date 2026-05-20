from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings

from django.contrib.auth import get_user

from .models import Thread, Post

try:
    from ratelimit.decorators import ratelimit
except ImportError:
    from django_ratelimit.decorators import ratelimit


def signup_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()

            send_mail(
                subject="【掲示板】新規ユーザー登録",
                message=f"新しいユーザーが登録されました。\n\nユーザー名: {user.username}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.ADMIN_NOTIFY_EMAIL],
                fail_silently=True,
            )

            return redirect('login')
    else:
        form = UserCreationForm()

    return render(request, 'core/signup.html', {'form': form})


@login_required
def thread_list(request):
    threads = Thread.objects.all().order_by('-created_at')
    return render(request, 'core/index.html', {'threads': threads})


@login_required
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def thread_new(request):
    if request.method == 'POST':
        if getattr(request, 'limited', False):
            return render(request, 'core/post_create.html', {
                'error': 'スレ立てが多すぎます。1分後に再試行してください。'
            })

        title = request.POST.get('title')
        content = request.POST.get('content')
        image = request.FILES.get('image')

        if title and content:
            thread = Thread.objects.create(
                title=title,
                created_by=request.user
            )

            try:
                Post.objects.create(
                    thread=thread,
                    author=request.user,
                    content=content,
                    image=image,
                )
            except ValidationError as e:
                thread.delete()
                return render(request, 'core/post_create.html', {
                    'error': e.messages[0]
                })

            send_mail(
                subject="【掲示板】新規スレッド作成",
                message=(
                    f"新しいスレッドが作成されました。\n\n"
                    f"タイトル: {thread.title}\n"
                    f"作成者: {request.user.username}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.ADMIN_NOTIFY_EMAIL],
                fail_silently=True,
            )

            return redirect('thread_detail', thread_id=thread.id)

    return render(request, 'core/post_create.html')


@login_required
def thread_detail(request, thread_id):
    thread = get_object_or_404(Thread, id=thread_id)
    posts = thread.posts.all().order_by('created_at')

    return render(request, 'core/thread_detail.html', {
        'thread': thread,
        'posts': posts
    })


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

        if content or image:
            try:
                Post.objects.create(
                    thread=thread,
                    author=request.user,
                    content=content or "",
                    image=image,
                )
            except ValidationError as e:
                posts = thread.posts.all().order_by('created_at')
                return render(request, 'core/thread_detail.html', {
                    'thread': thread,
                    'posts': posts,
                    'error': e.messages[0]
                })

            send_mail(
                subject="【掲示板】新しいレス投稿",
                message=(
                    f"新しいレスが投稿されました。\n\n"
                    f"スレッド: {thread.title}\n"
                    f"投稿者: {request.user.username}\n"
                    f"本文: {content or '[画像のみ]'}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.ADMIN_NOTIFY_EMAIL],
                fail_silently=True,
            )

        return redirect('thread_detail', thread_id=thread.id)

    return redirect('thread_detail', thread_id=thread.id)


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
            messages.error(
                request,
                "ログイン試行が多すぎます。1分後に再試行してください。"
            )
            return self.get(request, *args, **kwargs)

        response = super().post(request, *args, **kwargs)

        user=get_user(request)

        if user.is_authenticated:
            send_mail(
                subject="【掲示板】ログイン通知",
                message=(
                    f"ユーザーがログインしました。\n\n"
                    f"ユーザー名: {user.username}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.ADMIN_NOTIFY_EMAIL],
                fail_silently=True,
            )

        return response