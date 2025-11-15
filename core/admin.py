from django.contrib import admin
from .models import Thread, Post

@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'created_by', 'created_at')
    search_fields = ('title', 'created_by__username')


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('id', 'thread', 'author', 'created_at')
    search_fields = ('thread__title', 'author__username', 'content')
