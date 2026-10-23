import io
import os
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
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


def make_exif_image(name="photo.jpg", fmt="JPEG", size=(10, 10), orientation=None):
    """機種名と GPS 座標を埋め込んだ画像を作る（スマホ写真の代わり）。"""
    exif = Image.Exif()
    exif[0x010F] = "TestMaker"  # Make
    exif[0x8825] = {1: "N", 2: (35.0, 41.0, 22.0), 3: "E", 4: (140.0, 1.0, 30.0)}  # GPS
    if orientation:
        exif[0x0112] = orientation
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, format=fmt, exif=exif.tobytes())
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


def stored_image(post):
    with post.image.open("rb") as f:
        return Image.open(io.BytesIO(f.read()))


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
    def test_anonymous_can_read_list_and_thread(self):
        """閲覧はログインなしでもできる"""
        Post.objects.create(thread=self.thread, author=self.user, content="読めるレス")
        self.client.logout()
        self.assertContains(self.client.get(reverse("thread_list")), "テストスレ")
        res = self.client.get(reverse("thread_detail", args=[self.thread.id]))
        self.assertContains(res, "読めるレス")
        self.assertContains(res, "レスを書くにはログインが必要です")
        self.assertNotContains(res, 'id="reply"')

    def test_anonymous_cannot_post(self):
        """投稿・スレ立てはログインが必要"""
        self.client.logout()
        res = self.client.post(reverse("post_reply", args=[self.thread.id]), {"content": "x"})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res["Location"].startswith(reverse("login")))
        res = self.client.get(reverse("thread_new"))
        self.assertTrue(res["Location"].startswith(reverse("login")))
        self.assertEqual(Post.objects.count(), 0)

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
        self.assertContains(res, "2 レス")


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


class ExifStripTests(BaseTestCase):
    """アップロード画像から EXIF（GPS位置情報など）が消えていること"""

    def assert_no_metadata(self, img):
        exif = img.getexif()
        self.assertEqual(len(exif), 0, f"EXIF が残っている: {dict(exif)}")
        self.assertNotIn("exif", img.info)

    def test_exif_is_removed_from_reply_images(self):
        for name, fmt in [("a.jpg", "JPEG"), ("a.png", "PNG"), ("a.webp", "WEBP")]:
            with self.subTest(fmt=fmt):
                src = make_exif_image(name, fmt)
                self.assertIn(0x8825, Image.open(io.BytesIO(src.read())).getexif())  # 前提: 元にはGPSがある
                src.seek(0)
                res = self.reply(content="写真", image=src)
                self.assertEqual(res.status_code, 302)
                img = stored_image(Post.objects.latest("id"))
                self.assertEqual(img.format, fmt)
                self.assert_no_metadata(img)

    def test_exif_is_removed_when_creating_thread(self):
        res = self.client.post(reverse("thread_new"), {
            "title": "写真スレ", "content": "見て", "image": make_exif_image(),
        })
        self.assertEqual(res.status_code, 302)
        self.assert_no_metadata(stored_image(Post.objects.latest("id")))

    def test_orientation_is_applied_before_stripping(self):
        """Orientation=6（90度回転）の縦長写真は、画素を回転させてから EXIF を消す"""
        res = self.reply(image=make_exif_image(size=(40, 20), orientation=6))
        self.assertEqual(res.status_code, 302)
        img = stored_image(Post.objects.get())
        self.assertEqual(img.size, (20, 40))
        self.assert_no_metadata(img)

    def test_extension_matches_real_format(self):
        """中身が PNG なのに .jpg で送られても、保存名は .png になる"""
        self.reply(image=make_image("trick.jpg", "PNG"))
        self.assertTrue(Post.objects.get().image.name.endswith(".png"))

    def test_animated_gif_keeps_all_frames(self):
        frames = [Image.new("RGB", (8, 8), c) for c in ("red", "green", "blue")]
        buf = io.BytesIO()
        frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                       duration=100, loop=0, comment=b"secret")
        res = self.reply(image=SimpleUploadedFile("a.gif", buf.getvalue(), content_type="image/gif"))
        self.assertEqual(res.status_code, 302)
        img = stored_image(Post.objects.get())
        self.assertEqual(img.n_frames, 3)
        self.assertNotIn("comment", img.info)

    def test_strip_exif_command_cleans_existing_images(self):
        """修正前に保存された画像も、コマンドで EXIF を消せる"""
        post = Post.objects.create(thread=self.thread, author=self.user, content="",
                                   image=make_exif_image("old.jpg"))
        self.assertIn(0x8825, stored_image(post).getexif())
        old_name = post.image.name

        call_command("strip_exif", stdout=io.StringIO())

        post.refresh_from_db()
        self.assert_no_metadata(stored_image(post))
        self.assertFalse(post.image.storage.exists(old_name) and post.image.name != old_name)


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


class TemplateTests(BaseTestCase):
    def test_reply_keeps_text_on_error(self):
        """エラーのときも入力した本文が消えない"""
        res = self.reply(content="消えないで", image=make_image("a.png", "BMP"))
        self.assertContains(res, "消えないで", status_code=400)

    def test_login_page_hides_bgm_button_without_audio(self):
        self.client.logout()
        res = self.client.get(reverse("login"))
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, "bgm-toggle")


class PaginationTests(BaseTestCase):
    def test_thread_list_is_paginated_by_20(self):
        for i in range(25):
            Thread.objects.create(title=f"スレ{i:02d}", created_by=self.user)
        res = self.client.get(reverse("thread_list"))
        self.assertEqual(len(res.context["threads"]), 20)
        self.assertContains(res, "1 / 2")
        res = self.client.get(reverse("thread_list") + "?page=2")
        self.assertEqual(len(res.context["threads"]), 6)  # 25 + setUp の1件

    def test_invalid_page_number_does_not_error(self):
        for value in ["abc", "999", "-1"]:
            res = self.client.get(reverse("thread_list") + f"?page={value}")
            self.assertEqual(res.status_code, 200)

    def test_post_numbers_continue_across_pages(self):
        Post.objects.bulk_create(
            [Post(thread=self.thread, author=self.user, content=f"レス{i}") for i in range(1, 106)]
        )
        res = self.client.get(reverse("thread_detail", args=[self.thread.id]) + "?page=2")
        self.assertEqual(len(res.context["posts"]), 5)
        self.assertContains(res, 'id="post-101"')
        self.assertContains(res, 'id="post-105"')
        self.assertNotContains(res, 'id="post-1"')

    def test_reply_redirects_to_new_post_on_last_page(self):
        Post.objects.bulk_create(
            [Post(thread=self.thread, author=self.user, content="x") for _ in range(100)]
        )
        res = self.reply(content="101番目")
        url = reverse("thread_detail", args=[self.thread.id])
        self.assertRedirects(res, f"{url}?page=2#post-101", fetch_redirect_response=False)
