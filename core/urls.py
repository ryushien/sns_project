from django.urls import path
from . import views

urlpatterns = [
    # スレッド一覧（トップページ）
    path('', views.thread_list, name='thread_list'),

    # ユーザー登録
    path('signup/', views.signup_view, name='signup'),

    # 新規スレ建て
    path('threads/new/', views.thread_new, name='thread_new'),

    # スレッド詳細（中のレス一覧）
    path('threads/<int:thread_id>/', views.thread_detail, name='thread_detail'),

    # レス投稿
    path('threads/<int:thread_id>/reply/', views.post_reply, name='post_reply'),
]
