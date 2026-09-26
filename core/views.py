from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from .forms import PostForm, ThreadForm, first_error
from .models import Post, Thread
from .utils import notify_admin

# block=False にして、制限に掛かったら request.limited を見て
# エラーメッセージ付きで画面を返す（block=True だと即403になりメッセージが出ない）


@ratelimit(key="ip", rate="5/h", method="POST", block=False)
def signup_view(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if getattr(request, "limited", False):
            form.add_error(None, "登録の試行が多すぎます。しばらくしてから再試行してください。")
        elif form.is_valid():
            user = form.save()
            notify_admin("新規ユーザー登録", f"新しいユーザーが登録されました。\n\nユーザー名: {user.username}")
            messages.success(request, "登録しました。ログインしてください。")
            return redirect("login")
    else:
        form = UserCreationForm()

    return render(request, "core/signup.html", {"form": form})


@login_required
def thread_list(request):
    threads = (
        Thread.objects.select_related("created_by")
        .annotate(post_count=Count("posts"))
        .order_by("-created_at")
    )
    return render(request, "core/index.html", {"threads": threads})


@login_required
@ratelimit(key="user", rate="10/m", method="POST", block=False)
def thread_new(request):
    if request.method != "POST":
        return render(request, "core/post_create.html")

    if getattr(request, "limited", False):
        return render(request, "core/post_create.html", {
            "error": "スレ立てが多すぎます。1分後に再試行してください。",
        }, status=429)

    form = ThreadForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "core/post_create.html", {"error": first_error(form)}, status=400)

    # スレッドと >>1 はセットで作る（途中で失敗したら両方なかったことにする）
    with transaction.atomic():
        thread = Thread.objects.create(title=form.cleaned_data["title"], created_by=request.user)
        Post.objects.create(
            thread=thread,
            author=request.user,
            content=form.cleaned_data["content"],
            image=form.cleaned_data.get("image"),
        )

    notify_admin(
        "新規スレッド作成",
        f"新しいスレッドが作成されました。\n\nタイトル: {thread.title}\n作成者: {request.user.username}",
    )
    return redirect("thread_detail", thread_id=thread.id)


def _render_thread(request, thread, error=None, status=200):
    posts = thread.posts.select_related("author").order_by("created_at")
    return render(request, "core/thread_detail.html", {
        "thread": thread,
        "posts": posts,
        "error": error,
    }, status=status)


@login_required
def thread_detail(request, thread_id):
    thread = get_object_or_404(Thread.objects.select_related("created_by"), id=thread_id)
    return _render_thread(request, thread)


@login_required
@require_POST
@ratelimit(key="user", rate="20/m", method="POST", block=False)
def post_reply(request, thread_id):
    thread = get_object_or_404(Thread, id=thread_id)

    if getattr(request, "limited", False):
        return _render_thread(request, thread, "投稿が多すぎます。1分後に再試行してください。", status=429)

    form = PostForm(request.POST, request.FILES)
    if not form.is_valid():
        return _render_thread(request, thread, first_error(form), status=400)

    post = form.save(commit=False)
    post.thread = thread
    post.author = request.user
    post.save()

    notify_admin(
        "新しいレス投稿",
        f"新しいレスが投稿されました。\n\nスレッド: {thread.title}\n"
        f"投稿者: {request.user.username}\n本文: {post.content or '[画像のみ]'}",
    )
    return redirect("thread_detail", thread_id=thread.id)


# ログインは IP 単位とユーザー名単位の両方で制限する。
# IP は X-Forwarded-For から取るため偽装され得るが、ユーザー名単位の制限は
# 偽装できないので、特定アカウントへの総当たりは確実に止められる。
@method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=False), name="dispatch")
@method_decorator(ratelimit(key="post:username", rate="5/m", method="POST", block=False), name="dispatch")
class RateLimitedLoginView(LoginView):
    template_name = "core/login.html"

    def post(self, request, *args, **kwargs):
        if getattr(request, "limited", False):
            messages.error(request, "ログイン試行が多すぎます。1分後に再試行してください。")
            return self.render_to_response(self.get_context_data(form=self.form_class(request)), status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        notify_admin("ログイン通知", f"ユーザーがログインしました。\n\nユーザー名: {form.get_user().username}")
        return response
