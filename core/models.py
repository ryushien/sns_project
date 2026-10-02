import os

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp"]


def validate_image_file(value):
    """画像のサイズと拡張子をチェックする。

    注意: モデルの validators は objects.create() では実行されない。
    必ずフォーム（core/forms.py）経由で保存すること。
    """
    if value.size > MAX_IMAGE_SIZE:
        raise ValidationError("画像サイズは5MB以下にしてください。")

    ext = os.path.splitext(value.name)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError("投稿できる画像は jpg, jpeg, png, gif, webp のみです。")


class Thread(models.Model):
    title = models.CharField(max_length=200)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Post(models.Model):
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="posts")
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    image = models.ImageField(
        upload_to="post_images/",
        blank=True,
        null=True,
        validators=[validate_image_file],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.author.username}: {self.content[:20]}"
