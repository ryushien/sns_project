from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import os

def validate_image_file(value):
    max_size = 5 * 1024 * 1024  # 5MB
    if value.size > max_size:
        raise ValidationError("画像サイズは5MB以下にしてください。")

    ext = os.path.splitext(value.name)[1].lower()
    allowed_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
    if ext not in allowed_extensions:
        raise ValidationError("投稿できる画像は jpg, jpeg, png, gif, webp のみです。")
    
class Thread(models.Model):
    title = models.CharField(max_length=200)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Post(models.Model):
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name='posts')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()

    # ★ ここから追加
    image = models.ImageField(upload_to='post_images/', 
                              blank=True, 
                              null=True,
                              validators=[validate_image_file])
    #video = models.FileField(upload_to='post_videos/', blank=True, null=True)
    # ★ ここまで追加

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.author.username}: {self.content[:20]}"
