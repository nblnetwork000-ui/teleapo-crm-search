#!/usr/bin/env python3
import base64
import getpass
import hashlib
import secrets


def main():
    password = getpass.getpass("初期パスワード: ")
    confirmation = getpass.getpass("確認: ")
    if password != confirmation:
        raise SystemExit("パスワードが一致しません。")
    if len(password) < 12:
        raise SystemExit("パスワードは12文字以上にしてください。")

    iterations = 210_000
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii")
    print(f"pbkdf2_sha256${iterations}${salt_text}${digest_text}")


if __name__ == "__main__":
    main()
