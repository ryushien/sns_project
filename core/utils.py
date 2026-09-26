import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """リバースプロキシ（Render）経由でもクライアントIPを取り出す。

    X-Forwarded-For は「client, proxy1, proxy2」の形式なので先頭を使う。
    ヘッダが無い（ローカル実行など）ときは REMOTE_ADDR を使う。
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        if ip:
            return ip
    return request.META.get("REMOTE_ADDR", "")


def notify_admin(subject, message):
    """管理者に通知メールを送る。ADMIN_NOTIFY_EMAIL が未設定なら何もしない。"""
    if not settings.ADMIN_NOTIFY_EMAIL:
        return
    try:
        send_mail(
            subject=f"【掲示板】{subject}",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.ADMIN_NOTIFY_EMAIL],
        )
    except Exception:
        # 通知の失敗でユーザーの操作は止めない（ログには残す）
        logger.exception("管理者への通知メール送信に失敗しました")
