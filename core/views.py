from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView
from django.contrib.staticfiles import finders
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from .forms import PostForm, ThreadForm, first_error
from .models import Post, Thread
from .utils import notify_admin

THREADS_PER_PAGE = 20
POSTS_PER_PAGE = 100

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


def thread_list(request):
    """スレッド一覧。閲覧はログインなしでもできる。"""
    threads = (
        Thread.objects.select_related("created_by")
        .annotate(post_count=Count("posts"))
        .order_by("-created_at", "-id")
    )
    # get_page は ?page=abc や範囲外の番号でもエラーにせず、最初/最後のページを返す
    page_obj = Paginator(threads, THREADS_PER_PAGE).get_page(request.GET.get("page"))
    return render(request, "core/index.html", {"page_obj": page_obj, "threads": page_obj.object_list})


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
        return render(request, "core/post_create.html", {"error": first_error(form), "form": form}, status=400)

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


def _post_paginator(thread):
    posts = thread.posts.select_related("author").order_by("created_at", "id")
    return Paginator(posts, POSTS_PER_PAGE)


def _render_thread(request, thread, page=None, error=None, status=200, form=None):
    paginator = _post_paginator(thread)
    # エラーで再表示するときは、投稿フォームのある最後のページを出す
    page_obj = paginator.get_page(page if page is not None else paginator.num_pages)
    return render(request, "core/thread_detail.html", {
        "thread": thread,
        "page_obj": page_obj,
        "posts": page_obj.object_list,
        "error": error,
        "form": form,
    }, status=status)


def thread_detail(request, thread_id):
    """スレッド詳細。閲覧はログインなしでもできる（投稿はログインが必要）。"""
    thread = get_object_or_404(Thread.objects.select_related("created_by"), id=thread_id)
    return _render_thread(request, thread, page=request.GET.get("page", 1))


@login_required
@require_POST
@ratelimit(key="user", rate="20/m", method="POST", block=False)
def post_reply(request, thread_id):
    thread = get_object_or_404(Thread, id=thread_id)

    if getattr(request, "limited", False):
        return _render_thread(request, thread, error="投稿が多すぎます。1分後に再試行してください。", status=429)

    form = PostForm(request.POST, request.FILES)
    if not form.is_valid():
        return _render_thread(request, thread, error=first_error(form), status=400, form=form)

    post = form.save(commit=False)
    post.thread = thread
    post.author = request.user
    post.save()

    notify_admin(
        "新しいレス投稿",
        f"新しいレスが投稿されました。\n\nスレッド: {thread.title}\n"
        f"投稿者: {request.user.username}\n本文: {post.content or '[画像のみ]'}",
    )
    # 自分の投稿が載っている最後のページの、その投稿の位置へ移動する
    paginator = _post_paginator(thread)
    url = reverse("thread_detail", args=[thread.id])
    return redirect(f"{url}?page={paginator.num_pages}#post-{paginator.count}")


# ログインは IP 単位とユーザー名単位の両方で制限する。
# IP は X-Forwarded-For から取るため偽装され得るが、ユーザー名単位の制限は
# 偽装できないので、特定アカウントへの総当たりは確実に止められる。
@method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=False), name="dispatch")
@method_decorator(ratelimit(key="post:username", rate="5/m", method="POST", block=False), name="dispatch")
class RateLimitedLoginView(LoginView):
    template_name = "core/login.html"
    # 音源ファイル（フリー素材）を置くと、ログイン画面に BGM ボタンが出る
    bgm_path = "core/bgm.mp3"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["bgm_path"] = self.bgm_path
        context["has_bgm"] = finders.find(self.bgm_path) is not None
        return context

    def post(self, request, *args, **kwargs):
        if getattr(request, "limited", False):
            messages.error(request, "ログイン試行が多すぎます。1分後に再試行してください。")
            return self.render_to_response(self.get_context_data(form=self.form_class(request)), status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        notify_admin("ログイン通知", f"ユーザーがログインしました。\n\nユーザー名: {form.get_user().username}")
        return response
