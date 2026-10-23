"""アップロード画像からメタデータ（EXIF・GPS・コメント等）を取り除く。

元のファイルをそのまま保存すると、スマホ写真に埋め込まれた撮影位置（GPS）や
機種名が誰でも読めてしまう。そこで Pillow で画素データだけを取り出して
画像を作り直し、メタデータを一切引き継がずに保存し直す。

再エンコードには副次効果もある：画像の後ろに別のデータを連結した
polyglot ファイルなど、画素以外のバイト列もすべて落ちる。
"""

import io
import os

from PIL import Image, ImageOps, ImageSequence

# 保存時に使う拡張子（実際の形式に合わせて付け直す）
FORMAT_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp"}

JPEG_QUALITY = 90
WEBP_QUALITY = 90


def _strip_frame(frame):
    """1フレーム分の画素だけをコピーした新しい画像を返す（info/EXIFは空になる）。"""
    clean = Image.new(frame.mode, frame.size)
    clean.paste(frame)
    if frame.mode == "P":
        clean.putpalette(frame.getpalette())
    return clean


def strip_metadata(fileobj):
    """画像を読み込み、メタデータを取り除いたバイト列と形式を返す。

    戻り値: (bytes, format)  format は "JPEG" / "PNG" / "GIF" / "WEBP"
    画像として開けない場合は PIL の例外がそのまま送出される。
    """
    fileobj.seek(0)
    img = Image.open(fileobj)
    fmt = img.format
    if fmt not in FORMAT_EXTENSIONS:
        raise ValueError(f"unsupported format: {fmt}")

    animated = getattr(img, "is_animated", False)
    out = io.BytesIO()

    if animated:
        # アニメーション GIF / WebP はフレームごとに作り直す
        frames, durations = [], []
        for frame in ImageSequence.Iterator(img):
            durations.append(frame.info.get("duration", 100))
            frames.append(_strip_frame(frame.convert("RGBA") if fmt == "WEBP" else frame.copy()))
        params = {"save_all": True, "append_images": frames[1:], "duration": durations,
                  "loop": img.info.get("loop", 0)}
        if fmt == "GIF":
            params["disposal"] = 2
        else:
            params["quality"] = WEBP_QUALITY
        frames[0].save(out, format=fmt, **params)
    else:
        # EXIF の Orientation（回転情報）を画素に反映してから捨てる。
        # これをしないとスマホ写真が横倒しで表示される。
        img = ImageOps.exif_transpose(img)
        transparency = img.info.get("transparency")
        clean = _strip_frame(img)

        params = {}
        if fmt == "JPEG":
            if clean.mode not in ("RGB", "L"):
                clean = clean.convert("RGB")
            params = {"quality": JPEG_QUALITY, "optimize": True}
        elif fmt == "PNG":
            params = {"optimize": True}
            if transparency is not None:
                params["transparency"] = transparency
        elif fmt == "GIF":
            if transparency is not None:
                params["transparency"] = transparency
        elif fmt == "WEBP":
            params = {"quality": WEBP_QUALITY}
        clean.save(out, format=fmt, **params)

    return out.getvalue(), fmt


def clean_filename(original_name, fmt):
    """拡張子を実際の画像形式に合わせたファイル名を返す。"""
    stem = os.path.splitext(os.path.basename(original_name))[0] or "image"
    return stem + FORMAT_EXTENSIONS[fmt]
