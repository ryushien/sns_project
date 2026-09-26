import io
import os
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import Post, Thread

TEMP_MEDIA = tempfile.mkdtemp()


def make_image(name="test.png", fmt="PNG", size=(10, 10)):
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, format=fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


@override_settings(
    MEDIA_ROOT=TEMP_MEDIA,
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    ADMIN_NOTIFY_EMAIL="",
)
class BaseTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        cache.clear()  # レート制限のカウントをテストごとにリセット
        self.user = User.objects.create_user("alice", password="S3cure-pass-123")
        self.client.login(username="alice", password="S3cure-pass-123")
        self.thread = Thread.objects.create(title="テストスレ", created_by=self.user)

    def reply(self, **data):
        return self.client.post(reverse("post_reply", args=[self.thread.id]), data)


class AccessControlTests(BaseTestCase):
    def test_anonymous_is_redirected_to_login(self):
        self.client.logout()
        res = self.client.get(reverse("thread_list"))
        self.assertRedirects(res, f"{reverse('login')}?next=/")

    def test_reply_requires_post(self):
        res = self.client.get(reverse("post_reply", args=[self.thread.id]))
        self.assertEqual(res.status_code, 405)


class ThreadTests(BaseTestCase):
    def test_create_thread_with_first_post(self):
        res = self.client.post(reverse("thread_new"), {"title": "新スレ", "content": ">>1です"})
        thread = Thread.objects.get(title="新スレ")
        self.assertRedirects(res, reverse("thread_detail", args=[thread.id]))
        self.assertEqual(thread.posts.get().content, ">>1です")

    def test_invalid_image_creates_nothing(self):
        """画像が不正ならスレッドも作られない（トランザクション）"""
        fake = SimpleUploadedFile("evil.png", b"<script>alert(1)</script>", content_type="image/png")
        res = self.client.post(reverse("thread_new"), {"title": "x", "content": "y", "image": fake})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(Thread.objects.filter(title="x").exists())

    def test_blank_title_rejected(self):
        res = self.client.post(reverse("thread_new"), {"title": "   ", "content": "y"})
        self.assertEqual(res.status_code, 400)

    def test_list_shows_post_count(self):
        Post.objects.create(thread=self.thread, author=self.user, content="a")
        Post.objects.create(thread=self.thread, author=self.user, content="b")
        res = self.client.get(reverse("thread_list"))
        self.assertContains(res, "レス 2")


class ImageUploadTests(BaseTestCase):
    def test_valid_png_is_accepted(self):
        res = self.reply(content="画像", image=make_image())
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Post.objects.get().image.name.startswith("post_images/"))

    def test_image_only_reply_is_accepted(self):
        res = self.reply(image=make_image("a.jpg", "JPEG"))
        self.assertEqual(res.status_code, 302)

    def test_html_disguised_as_png_is_rejected(self):
        """拡張子だけ .png にしたHTMLは弾く（S3上でのXSS対策）"""
        fake = SimpleUploadedFile("evil.png", b"<html><script>alert(1)</script></html>")
        res = self.reply(content="x", image=fake)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Post.objects.count(), 0)

    def test_disallowed_extension_is_rejected(self):
        res = self.reply(content="x", image=make_image("a.html"))
        self.assertEqual(res.status_code, 400)
        self.assertContains(res, "jpg, jpeg, png, gif, webp", status_code=400)

    def test_disallowed_real_format_is_rejected(self):
        """中身が BMP なら拡張子が .png でも弾く"""
        res = self.reply(content="x", image=make_image("a.png", "BMP"))
        self.assertEqual(res.status_code, 400)

    def test_oversized_image_is_rejected(self):
        # 5MBを超える実画像（ノイズ入りPNGは圧縮が効かないので大きくなる）
        buf = io.BytesIO()
        Image.frombytes("RGB", (1400, 1400), os.urandom(1400 * 1400 * 3)).save(buf, format="PNG")
        self.assertGreater(len(buf.getvalue()), 5 * 1024 * 1024)
        big = SimpleUploadedFile("big.png", buf.getvalue(), content_type="image/png")
        res = self.reply(content="x", image=big)
        self.assertEqual(res.status_code, 400)
        self.assertContains(res, "5MB", status_code=400)

    def test_empty_reply_is_rejected(self):
        res = self.reply(content="   ")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Post.objects.count(), 0)


class RateLimitTests(BaseTestCase):
    def test_reply_rate_limit_shows_message(self):
        for _ in range(20):
            self.assertEqual(self.reply(content="連投").status_code, 302)
        res = self.reply(content="21回目")
        self.assertEqual(res.status_code, 429)
        self.assertContains(res, "投稿が多すぎます", status_code=429)
        self.assertEqual(Post.objects.count(), 20)

    def test_login_is_limited_per_username_even_if_ip_changes(self):
        """X-Forwarded-For を毎回変えても、同じユーザー名への総当たりは止まる"""
        self.client.logout()
        url = reverse("login")
        for i in range(5):
            self.client.post(url, {"username": "alice", "password": "wrong"},
                             HTTP_X_FORWARDED_FOR=f"10.0.0.{i}")
        res = self.client.post(url, {"username": "alice", "password": "S3cure-pass-123"},
                               HTTP_X_FORWARDED_FOR="10.0.0.99")
        self.assertEqual(res.status_code, 429)
        self.assertContains(res, "ログイン試行が多すぎます", status_code=429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_succeeds_normally(self):
        self.client.logout()
        res = self.client.post(reverse("login"), {"username": "alice", "password": "S3cure-pass-123"})
        self.assertRedirects(res, "/")
