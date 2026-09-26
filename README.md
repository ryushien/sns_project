# Mini SNS（Django製 匿名掲示板風SNS）

スレッドを立ててレス（本文＋画像）を投稿できる掲示板です。

## ローカルでの起動

環境変数を設定しなくても、そのまま起動できます（SQLite / 画像はローカル保存 / メールはターミナルに表示）。

```bash
python -m venv venv
venv\Scripts\activate          # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

http://127.0.0.1:8000/ を開きます。

## テスト

```bash
python manage.py test core
```

## 本番（Render）で使う環境変数

| 変数 | 用途 |
|---|---|
| `SECRET_KEY` | 必須。本番ではこれが無いと起動しない |
| `DATABASE_URL` | Postgres の接続URL |
| `AWS_STORAGE_BUCKET_NAME` / `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | 画像を S3 に保存する（未設定ならローカル保存） |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Gmail SMTP（未設定ならコンソール出力） |
| `ADMIN_NOTIFY_EMAIL` | 管理者通知の送信先（未設定なら通知しない） |

`RENDER` と `RENDER_EXTERNAL_HOSTNAME` は Render が自動で設定します。

## セキュリティ対策

- **画像アップロード**: 拡張子・サイズ（5MB）に加え、Pillow で実際に画像として開けるか、実際の形式が JPEG/PNG/GIF/WebP かを検証。拡張子だけ偽装したHTML等を S3 に置かれるのを防ぐ
- **レート制限**: スレ立て・レス・新規登録・ログインに制限。ログインは IP 単位に加えてユーザー名単位でも制限し、IP を偽装した総当たりも防ぐ
- **その他**: CSRF対策、HTTPS強制、HSTS、Secure Cookie、クリックジャッキング対策、管理画面URLの変更
