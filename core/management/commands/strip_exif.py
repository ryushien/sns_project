"""保存済みの投稿画像から EXIF などのメタデータを取り除く。

使い方:
    python manage.py strip_exif --dry-run   # 対象を表示するだけ（変更しない）
    python manage.py strip_exif             # 実際に作り直して保存し直す

新しいファイル名で保存してから古いファイルを削除するので、
途中で失敗しても画像が消えることはない。
"""

import os

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from core.image_sanitize import clean_filename, strip_metadata
from core.models import Post


class Command(BaseCommand):
    help = "保存済みの投稿画像から EXIF（GPS位置情報など）を取り除く"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="変更せず対象だけ表示する")

    def handle(self, *args, dry_run=False, **options):
        posts = Post.objects.exclude(image="").exclude(image__isnull=True).order_by("id")
        done = failed = 0

        for post in posts.iterator():
            old_name = post.image.name
            if dry_run:
                self.stdout.write(f"[dry-run] post {post.id}: {old_name}")
                continue
            try:
                with post.image.open("rb") as f:
                    data, fmt = strip_metadata(f)
                storage = post.image.storage
                post.image.save(clean_filename(os.path.basename(old_name), fmt),
                                ContentFile(data), save=True)
                if post.image.name != old_name:
                    storage.delete(old_name)
                done += 1
                self.stdout.write(f"post {post.id}: {old_name} -> {post.image.name}")
            except Exception as e:
                failed += 1
                self.stderr.write(f"post {post.id}: {old_name} の処理に失敗しました ({e})")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"対象 {posts.count()} 件（dry-run のため変更なし）"))
        else:
            self.stdout.write(self.style.SUCCESS(f"完了: {done} 件 / 失敗: {failed} 件"))
