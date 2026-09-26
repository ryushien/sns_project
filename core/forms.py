from django import forms
from PIL import Image

from .models import Post, Thread, validate_image_file

MAX_CONTENT_LENGTH = 2000
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "GIF", "WEBP"}


class PostImageMixin:
    """画像の中身まで検証する。

    - forms.ImageField が Pillow で「本当に画像として開けるか」を確認する
    - モデルの validate_image_file で拡張子とサイズを確認する
    - さらに実際の画像形式が許可リストにあるかを確認する
      （拡張子だけ .png にしたHTMLや、BMP/TIFFなどを弾く）
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Django標準の拡張子チェック（Pillowが読める全形式を許可してしまう）を外し、
        # 自前のチェック（jpg/png/gif/webp・5MB）だけにする
        self.fields["image"].validators = [validate_image_file]

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image
        fmt = getattr(getattr(image, "image", None), "format", None)
        if fmt is None:
            try:
                image.seek(0)
                fmt = Image.open(image).format
            except Exception:
                fmt = None
            finally:
                image.seek(0)
        if fmt not in ALLOWED_IMAGE_FORMATS:
            raise forms.ValidationError("投稿できる画像は jpg, jpeg, png, gif, webp のみです。")
        return image


class PostForm(PostImageMixin, forms.ModelForm):
    """レス投稿。本文か画像のどちらかがあればよい。"""

    class Meta:
        model = Post
        fields = ["content", "image"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["content"].required = False
        self.fields["content"].max_length = MAX_CONTENT_LENGTH

    def clean_content(self):
        content = (self.cleaned_data.get("content") or "").strip()
        if len(content) > MAX_CONTENT_LENGTH:
            raise forms.ValidationError(f"本文は{MAX_CONTENT_LENGTH}文字以内にしてください。")
        return content

    def clean(self):
        cleaned = super().clean()
        if not self.errors and not cleaned.get("content") and not cleaned.get("image"):
            raise forms.ValidationError("本文か画像のどちらかを入力してください。")
        return cleaned


class ThreadForm(PostImageMixin, forms.Form):
    """スレ立て（タイトル + >>1 の本文 + 任意の画像）。"""

    title = forms.CharField(max_length=Thread._meta.get_field("title").max_length)
    content = forms.CharField(max_length=MAX_CONTENT_LENGTH)
    image = forms.ImageField(required=False)

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("タイトルを入力してください。")
        return title

    def clean_content(self):
        content = self.cleaned_data["content"].strip()
        if not content:
            raise forms.ValidationError("本文を入力してください。")
        return content


def first_error(form):
    """テンプレートに出す最初のエラーメッセージ。"""
    for errors in form.errors.values():
        if errors:
            return errors[0]
    return "入力内容を確認してください。"
