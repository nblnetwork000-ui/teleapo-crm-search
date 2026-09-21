#!/usr/bin/env python3
import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as datetime_time, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
JST = timezone(timedelta(hours=9))
PHONEBOOK_CASSETTE_ID = "d8a23e9e64a4c817227ab09858bc1330"
HEADERS = [
    "会社名",
    "電話番号",
    "住所",
    "ステータス",
    "メモ",
]
SHOP_STATUS_OPTIONS = ["架電済み", "留守", "再コール", "見込み", "アポ", "成約"]
SHOP_STATUS_COLORS = {
    "架電済み": {"red": 0.93, "green": 0.95, "blue": 0.98},
    "留守": {"red": 0.94, "green": 0.94, "blue": 0.94},
    "再コール": {"red": 1.0, "green": 0.96, "blue": 0.82},
    "見込み": {"red": 0.88, "green": 0.95, "blue": 1.0},
    "アポ": {"red": 0.86, "green": 0.94, "blue": 0.86},
    "成約": {"red": 0.80, "green": 0.90, "blue": 0.78},
}
SHOP_COLUMN_WIDTHS = [220, 150, 360, 130, 420]
EVENT_SHEET_NAME = "イベントリスト"
JOB_SHEET_NAME = "求人掲載店舗リスト"
USER_SHEET_NAME = "SIGNALユーザー"
CUSTOMER_SHEET_NAME = "SIGNAL顧客リスト"
CUSTOMER_HEADERS = ["所有者メール", "ID", "会社名・店舗名", "電話番号", "住所", "担当者", "ステータス", "次回連絡", "メモ", "記録履歴JSON", "更新日時"]
USER_HEADERS = [
    "メールアドレス",
    "パスワードハッシュ",
    "権限",
    "状態",
    "招待トークンハッシュ",
    "招待期限",
    "作成日時",
    "更新日時",
    "最終ログイン日時",
]
EVENT_HEADERS = [
    "取得日時",
    "イベント名",
    "開催開始",
    "開催終了",
    "会場",
    "住所",
    "URL",
    "定員",
    "参加人数",
    "補欠人数",
    "主催者",
    "ハッシュタグ",
    "イベントID",
    "取得元",
]
JOB_HEADERS = [
    "取得日時",
    "店舗名・会社名",
    "掲載企業",
    "求人タイトル",
    "勤務地",
    "雇用形態",
    "給与",
    "掲載日",
    "求人URL",
    "求人媒体",
    "求人ID",
    "取得元",
]
EVENT_BUSINESS_HIGHLIGHT_COLOR = {"red": 1.0, "green": 0.95, "blue": 0.6}
EVENT_MEETUP_KEYWORDS = (
    "交流会",
    "異業種交流",
    "名刺交換",
    "ネットワーキング",
    "networking",
)
EVENT_BUSINESS_KEYWORDS = (
    "ビジネス",
    "経営",
    "経営者",
    "起業",
    "創業",
    "事業",
    "法人",
    "企業",
    "会社",
    "社長",
    "代表",
    "営業",
    "商談",
    "販路",
    "マーケティング",
    "集客",
    "人脈",
    "士業",
    "投資",
    "不動産",
    "財務",
    "資金調達",
)
EXTERNAL_EVENT_SOURCES = {
    "doomo": ("Doomo", "https://doomo.jp/event"),
    "clip_tokyo": ("CLIP TOKYO", "https://clip-tokyo.jp/event/"),
    "passion_leaders": ("Passion Leaders", "https://members.passion-leaders.com/event_schedule/"),
    "tact": ("TACT", "https://tact-business.jp/"),
    "friendlink": ("フレンドリンク", "https://friendlink.jp/"),
    "lepane": ("レパン", "https://lepane.net/"),
    "hive_lab": ("Hive Lab", "https://www.hive-lab.jp/"),
    "kobushi": ("KOBUSHI BEER", "https://kobushibeer.connpass.com/"),
    "onlystory": ("OnlyStory", "https://onlystory.co.jp/service/seminar_event_c/event/"),
    "first_village": ("First Village", "https://firstvillage.co.jp/event/"),
    "keizaikai": ("経済界倶楽部", "https://club.keizaikai.co.jp/event/"),
    "flos": ("フロース", "https://flos32.com/events/"),
    "osaka_plus": ("OSAKA Plus", "https://osaka-plus.com/"),
    "deal_den": ("Deal Den", "https://dealden.co.jp/"),
    "cxo_meetup": ("CxO交流会カレンダー", "https://cxo-meetup.com/events"),
    "doyu": ("中小企業家同友会", "https://www.doyu.jp/schedule"),
    "eventmado": ("イベマド", "https://evemado.jp/"),
}


class InputError(Exception):
    pass


def load_dotenv():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


def required_env(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"環境変数 {name} を .env に設定してください。")
    return value


def int_env(name, default, minimum, maximum):
    value = int(os.environ.get(name, str(default)))
    if value < minimum or value > maximum:
        raise RuntimeError(f"{name} は {minimum} から {maximum} の整数で設定してください。")
    return value


def parse_access_users(raw_value):
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise RuntimeError("ACCESS_USERS_JSON は正しいJSONで設定してください。") from error

    if isinstance(parsed, dict):
        entries = parsed.items()
    elif isinstance(parsed, list):
        entries = ((item.get("email"), item.get("password")) for item in parsed if isinstance(item, dict))
    else:
        raise RuntimeError("ACCESS_USERS_JSON はメールアドレスとパスワードの一覧で設定してください。")

    users = {}
    for email_address, password in entries:
        normalized_email = str(email_address or "").strip().lower()
        normalized_password = str(password or "")
        if not normalized_email or "@" not in normalized_email or not normalized_password:
            raise RuntimeError("ACCESS_USERS_JSON の各ユーザーには有効なメールアドレスとパスワードが必要です。")
        users[normalized_email] = normalized_password
    if not users:
        raise RuntimeError("ACCESS_USERS_JSON に1件以上のユーザーを設定してください。")
    return users


def verify_password(password, stored_value):
    if not stored_value.startswith("pbkdf2_sha256$"):
        return secrets.compare_digest(password, stored_value)
    try:
        _, iterations_text, salt_text, expected_text = stored_value.split("$", 3)
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_text.encode("ascii"))
    except (ValueError, UnicodeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def hash_password(password, iterations=310000):
    if len(password) < 12:
        raise InputError("パスワードは12文字以上で設定してください。")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(iterations),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def parse_email_list(raw_value):
    return {
        value.strip().lower()
        for value in re.split(r"[,\s]+", raw_value or "")
        if value.strip() and "@" in value
    }


def load_config():
    load_dotenv()
    app_mode = os.environ.get("APP_MODE", "full").strip().lower()
    if app_mode not in {"full", "events", "customers"}:
        raise RuntimeError("APP_MODE は full / events / customers のいずれかを設定してください。")
    access_users = parse_access_users(os.environ.get("ACCESS_USERS_JSON", ""))
    config = {
        "APP_MODE": app_mode,
        "YAHOO_CLIENT_ID": os.environ.get("YAHOO_CLIENT_ID", ""),
        "GOOGLE_SHEET_ID": required_env("GOOGLE_SHEET_ID"),
        "GOOGLE_SHEET_NAME": os.environ.get("GOOGLE_SHEET_NAME", "店舗リスト"),
        "GOOGLE_SERVICE_ACCOUNT_JSON_BASE64": os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64"),
        "GOOGLE_APPLICATION_CREDENTIALS": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        "HOST": os.environ.get("HOST", "127.0.0.1"),
        "PORT": int_env("PORT", 3000, 1024, 65535),
        "MAX_RESULTS_PER_RUN": int_env("MAX_RESULTS_PER_RUN", 100, 1, 1000),
        "REQUESTS_PER_15_MIN": int_env("REQUESTS_PER_15_MIN", 60, 5, 1000),
        "SKIP_DUPLICATES": os.environ.get("SKIP_DUPLICATES", "true") == "true",
        "ALLOW_REMOTE_ACCESS": os.environ.get("ALLOW_REMOTE_ACCESS", "false") == "true",
        "ACCESS_MEMBER_ID": os.environ.get("ACCESS_MEMBER_ID", ""),
        "ACCESS_PASSWORD": os.environ.get("ACCESS_PASSWORD") or os.environ.get("SHARE_PASSWORD", ""),
        "ACCESS_USERS": access_users,
        "ADMIN_EMAILS": parse_email_list(os.environ.get("ADMIN_EMAILS", "nblnetwork.000@gmail.com")),
        "SESSION_SECRET": os.environ.get("SESSION_SECRET") or secrets.token_hex(32),
        "APP_BASE_URL": os.environ.get("APP_BASE_URL", "").rstrip("/"),
        "RESEND_API_KEY": os.environ.get("RESEND_API_KEY", ""),
        "INVITE_FROM_EMAIL": os.environ.get("INVITE_FROM_EMAIL", "SIGNAL <onboarding@resend.dev>"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
        "OPENAI_MODEL": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "BRAVE_SEARCH_API_KEY": os.environ.get("BRAVE_SEARCH_API_KEY", ""),
        "VOICEVOX_URL": os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021"),
        "VOICEVOX_SPEAKER": int_env("VOICEVOX_SPEAKER", 24, 0, 999),
    }
    if config["HOST"] not in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
        raise RuntimeError("HOST は 127.0.0.1 / localhost / ::1 / 0.0.0.0 のいずれかにしてください。")
    if config["APP_MODE"] == "full" and not config["YAHOO_CLIENT_ID"]:
        raise RuntimeError("通常版では環境変数 YAHOO_CLIENT_ID を設定してください。")
    if config["ALLOW_REMOTE_ACCESS"] and not config["ACCESS_USERS"] and not config["ACCESS_PASSWORD"]:
        raise RuntimeError("公開利用時は ACCESS_USERS_JSON または ACCESS_PASSWORD を設定してください。")
    if not config["GOOGLE_SERVICE_ACCOUNT_JSON_BASE64"] and not config["GOOGLE_APPLICATION_CREDENTIALS"]:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 または GOOGLE_APPLICATION_CREDENTIALS を設定してください。")
    return config


def clean_text(value, label):
    if not isinstance(value, str):
        raise InputError(f"{label}を入力してください。")
    value = value.strip()
    if not value or len(value) > 80:
        raise InputError(f"{label}は1文字以上80文字以内で入力してください。")
    return value


def clean_int(value, minimum, maximum, label):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise InputError(f"{label}は整数で入力してください。")
    if number < minimum or number > maximum:
        raise InputError(f"{label}は{minimum}から{maximum}で入力してください。")
    return number


def parse_search_input(data, max_results):
    allowed_sorts = {"rating", "score", "hybrid", "review", "kana", "price", "dist", "geo", "match"}
    sort = data.get("sort", "hybrid")
    if sort not in allowed_sorts:
        raise InputError("並び順の指定が不正です。")
    return {
        "keyword": clean_text(data.get("keyword"), "キーワード"),
        "area": clean_text(data.get("area"), "エリア"),
        "results": min(clean_int(data.get("results", 20), 1, 100, "件数"), max_results),
        "start": clean_int(data.get("start", 1), 1, 3000, "開始位置"),
        "sort": sort,
        "append": data.get("append") is not False,
    }


def parse_event_search_input(data, max_results):
    source = data.get("source", "connpass")
    allowed_sources = {"connpass", "kokuchpro", "doorkeeper", "web", "all", *EXTERNAL_EVENT_SOURCES}
    if source not in allowed_sources:
        raise InputError("検索元の指定が不正です。")
    date_from = clean_optional_date(data.get("dateFrom"), "開催日の開始")
    date_to = clean_optional_date(data.get("dateTo"), "開催日の終了")
    if date_from and date_to and date_from > date_to:
        raise InputError("開催日の終了は開始日以降を指定してください。")
    return {
        "keyword": clean_text(data.get("keyword"), "キーワード"),
        "area": clean_optional_text(data.get("area", ""), "エリア"),
        "results": min(clean_int(data.get("results", 20), 1, 100, "件数"), max_results),
        "start": clean_int(data.get("start", 1), 1, 1000, "開始位置"),
        "futureOnly": data.get("futureOnly") is not False and not (date_from or date_to),
        "dateFrom": date_from,
        "dateTo": date_to,
        "source": source,
        "append": data.get("append") is not False,
    }


def parse_job_search_input(data, max_results):
    source = data.get("source", "kyujinbox")
    if source not in {"kyujinbox"}:
        raise InputError("求人検索元の指定が不正です。")
    return {
        "keyword": clean_text(data.get("keyword"), "キーワード"),
        "area": clean_text(data.get("area"), "エリア"),
        "results": min(clean_int(data.get("results", 20), 1, 100, "件数"), max_results),
        "start": clean_int(data.get("start", 1), 1, 1000, "開始位置"),
        "source": source,
        "append": data.get("append") is not False,
    }


def clean_optional_text(value, label):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InputError(f"{label}の指定が不正です。")
    value = value.strip()
    if len(value) > 80:
        raise InputError(f"{label}は80文字以内で入力してください。")
    return value


def clean_optional_date(value, label):
    if value in (None, ""):
        return ""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise InputError(f"{label}の指定が不正です。")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise InputError(f"{label}の指定が不正です。")
    return value


def request_json(url, method="GET", body=None, headers=None):
    payload = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Accept": "application/json",
            "User-Agent": "yahoo-local-to-sheets-python/1.0",
            **(headers or {}),
        },
    )
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"外部APIでエラーが発生しました: HTTP {error.code} {details[:300]}")


def request_text(url, headers=None, timeout=30):
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"外部ページ取得でエラーが発生しました: HTTP {error.code} {details[:300]}")


def search_yahoo_local(config, search):
    params = urllib.parse.urlencode(
        {
            "appid": config["YAHOO_CLIENT_ID"],
            "output": "json",
            "cid": PHONEBOOK_CASSETTE_ID,
            "query": f"{search['area']} {search['keyword']}",
            "results": str(search["results"]),
            "start": str(search["start"]),
            "sort": search["sort"],
            "detail": "full",
            "group": "gid",
        }
    )
    data = request_json(f"https://map.yahooapis.jp/search/local/V1/localSearch?{params}")
    result_info = data.get("ResultInfo", {})
    status = int(result_info.get("Status", 200))
    if status != 200:
        raise RuntimeError(f"Yahoo!ローカルサーチAPIでエラーが発生しました: status={status}")
    return {
        "total": int(result_info.get("Total", 0)),
        "count": int(result_info.get("Count", 0)),
        "items": normalize_features(data.get("Feature")),
    }


def search_connpass_events(search, brave_search_api_key=""):
    keyword = search["keyword"]
    if search["area"]:
        keyword = f"{keyword} {search['area']}"
    warnings = []
    if search["source"] == "connpass":
        events = scrape_connpass_search(keyword, search["start"], search["results"], search["futureOnly"])
    elif search["source"] == "kokuchpro":
        events = scrape_kokuchpro_search(search["keyword"], search["area"], search["start"], search["results"], search["futureOnly"])
    elif search["source"] == "doorkeeper":
        events = scrape_doorkeeper_search(search["keyword"], search["area"], search["start"], search["results"], search["futureOnly"])
    elif search["source"] == "web":
        if not brave_search_api_key:
            raise InputError("Web検索APIが未設定です。管理者に設定を依頼してください。")
        events = search_web_events(brave_search_api_key, search)
    elif search["source"] in EXTERNAL_EVENT_SOURCES:
        events = scrape_external_event_source(search["source"], search)
    else:
        source_searches = [
            ("connpass", lambda: scrape_connpass_search(keyword, search["start"], search["results"], search["futureOnly"])),
            (
                "こくちーず",
                lambda: scrape_kokuchpro_search(
                    search["keyword"], search["area"], search["start"], search["results"], search["futureOnly"]
                ),
            ),
            (
                "Doorkeeper",
                lambda: scrape_doorkeeper_search(
                    search["keyword"], search["area"], search["start"], search["results"], search["futureOnly"]
                ),
            ),
        ]
        source_searches.extend(
            (
                source_name,
                lambda source_id=source_id: scrape_external_event_source(source_id, search),
            )
            for source_id, (source_name, _source_url) in EXTERNAL_EVENT_SOURCES.items()
        )
        successful_sources = []
        if brave_search_api_key:
            source_searches.append(("Web検索", lambda: search_web_events(brave_search_api_key, search)))
        with ThreadPoolExecutor(max_workers=6) as executor:
            pending = {
                executor.submit(source_search): source_name
                for source_name, source_search in source_searches
            }
            for future in as_completed(pending):
                source_name = pending[future]
                try:
                    successful_sources.append(future.result())
                except Exception as error:
                    warnings.append(f"{source_name}は一時取得できませんでした（{brief_external_error(error)}）")
        if not successful_sources:
            raise RuntimeError("すべてのイベント検索元から取得できませんでした。しばらく待って再試行してください。")
        events = merge_event_sources(*successful_sources)
    events = filter_events_by_area(events, search["area"])
    events = filter_events_by_date_range(events, search["dateFrom"], search["dateTo"])
    events = events[: search["results"]]
    return {
        "total": len(events),
        "count": len(events),
        "items": events,
        "warnings": summarize_warnings(warnings),
    }


def brief_external_error(error):
    message = re.sub(r"<[^>]+>", " ", str(error))
    message = re.sub(r"\s+", " ", message).strip()
    http_status = re.search(r"HTTP\s+(\d{3})", message)
    if http_status:
        return f"HTTP {http_status.group(1)}"
    return message[:120] or "取得エラー"


def summarize_warnings(warnings):
    if len(warnings) <= 3:
        return warnings
    return warnings[:3] + [f"ほか{len(warnings) - 3}件の検索元は一時取得できませんでした。"]


def scrape_external_event_source(source_id, search):
    source_name, source_url = EXTERNAL_EVENT_SOURCES[source_id]
    text = request_text(source_url, timeout=15)
    items = parse_external_event_html(text, source_url, source_name, search["keyword"])
    if search["futureOnly"]:
        today = today_local_date()
        items = [item for item in items if is_event_today_or_later(item["startedAt"], today)]
    items = filter_events_by_area(items, search["area"])
    offset = max(0, search["start"] - 1)
    return items[offset : offset + search["results"]]


def parse_external_event_html(text, page_url, source_name, keyword):
    items = [
        item for item in parse_external_jsonld_events(text, page_url, source_name)
        if external_keyword_matches(keyword, event_searchable_text(item))
    ]
    known_items = parse_known_external_events(text, page_url, source_name, keyword)
    if known_items:
        return merge_event_sources(*([items, known_items] if items else [known_items]))
    seen = {(item["url"], item["startedAt"]) for item in items}
    generic_labels = {
        "イベント", "イベント一覧", "イベントページ一覧", "交流会", "詳細", "詳細を見る",
        "開催予定", "開催日程を見る", "交流会の全日程を確認する", "もっと見る", "more",
        "お申し込み", "お申し込みはこちら", "ビジネスサポート", source_name.lower(),
    }
    patterns = (
        r'<a\b[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        r'<h[2-4]\b[^>]*>(.*?)</h[2-4]>',
    )
    for pattern_index, pattern in enumerate(patterns):
        for match in re.finditer(pattern, text or "", re.I | re.S):
            href = match.group(1) if pattern_index == 0 else ""
            title_html = match.group(2) if pattern_index == 0 else match.group(1)
            title = clean_html(title_html)
            context_raw = text[max(0, match.start() - 220) : min(len(text), match.end() + 760)]
            context = clean_html(context_raw)
            if len(title) < 4 or title.lower() in generic_labels:
                title = derive_external_title(context_raw, source_name)
            if len(title) < 4 or title.lower() in generic_labels:
                continue
            if not looks_like_external_event(title, context):
                continue
            if not external_keyword_matches(keyword, f"{title} {context}"):
                continue
            if not href:
                link_match = re.search(r'<a\b[^>]*?href=["\']([^"\']+)["\']', text[match.end() : match.end() + 1200], re.I)
                href = link_match.group(1) if link_match else page_url
            url = urllib.parse.urljoin(page_url, html.unescape(href))
            if not url.startswith(("http://", "https://")):
                continue
            datetimes = parse_external_datetimes(title)
            if not datetimes:
                datetimes = parse_external_datetimes(context)
            for started_at in datetimes[:8]:
                key = (url, started_at)
                if key in seen:
                    continue
                seen.add(key)
                summary = re.sub(r"\s+", " ", context).strip()
                items.append(
                    make_external_event(
                        title=title[:220],
                        started_at=started_at,
                        place=extract_external_location(f"{title} {context}"),
                        address=summary[:320],
                        url=url,
                        source_name=source_name,
                    )
                )
    items.sort(key=lambda item: item.get("startedAt") or "")
    return items


def parse_known_external_events(text, page_url, source_name, keyword):
    parsers = {
        "Doomo": parse_doomo_events,
        "CLIP TOKYO": parse_clip_tokyo_events,
        "フレンドリンク": parse_friendlink_events,
        "レパン": parse_lepane_events,
        "KOBUSHI BEER": parse_kobushi_events,
        "OnlyStory": parse_onlystory_events,
        "First Village": parse_first_village_events,
        "経済界倶楽部": parse_keizaikai_events,
        "イベマド": parse_eventmado_events,
    }
    parser = parsers.get(source_name)
    if not parser:
        return []
    items = parser(text, page_url, source_name)
    if keyword:
        items = [item for item in items if external_keyword_matches(keyword, event_searchable_text(item))]
    return dedupe_external_events(items)


def event_searchable_text(item):
    return " ".join(
        as_text(item.get(key))
        for key in ("title", "place", "address", "owner")
    )


def dedupe_external_events(items):
    unique = []
    seen = set()
    for item in sorted(items, key=lambda value: value.get("startedAt") or ""):
        key = (item.get("url"), item.get("startedAt"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def event_from_block(block, page_url, source_name, title_pattern, href_pattern=None, place_pattern=None, title_prefix=""):
    title_match = re.search(title_pattern, block, re.I | re.S)
    dates = parse_external_datetimes(clean_html(block))
    if not title_match or not dates:
        return []
    title = clean_html(title_match.group(1))
    if title_prefix and title_prefix.lower() not in title.lower():
        title = f"{title_prefix}{title}"
    href_match = re.search(href_pattern, block, re.I | re.S) if href_pattern else None
    href = html.unescape(href_match.group(1)) if href_match else page_url
    place_match = re.search(place_pattern, block, re.I | re.S) if place_pattern else None
    place = clean_html(place_match.group(1)) if place_match else extract_external_location(clean_html(block))
    summary = clean_html(block)
    return [
        make_external_event(
            title=title[:220],
            started_at=started_at,
            place=place[:120],
            address=summary[:320],
            url=urllib.parse.urljoin(page_url, href),
            source_name=source_name,
        )
        for started_at in dates[:1]
    ]


def parse_doomo_events(text, page_url, source_name):
    items = []
    blocks = re.findall(
        r'(<a\b[^>]*href="https://doomo\.jp/event/[^"]+"[^>]*>.*?</a>)',
        text or "",
        re.I | re.S,
    )
    for block in blocks:
        title_match = re.search(r'<div\b[^>]*class="eventlisttitle"[^>]*>(.*?)</div>', block, re.I | re.S)
        href_match = re.search(r'<a\b[^>]*href="([^"]+)"', block, re.I)
        if not title_match or not href_match:
            continue
        title = clean_html(title_match.group(1))
        for schedule in re.findall(r'<div\b[^>]*class="nittei[^>]*>.*?</div>\s*</div>', block, re.I | re.S):
            schedule_text = clean_html(schedule)
            dates = parse_external_datetimes(schedule_text)
            if not dates:
                continue
            items.append(make_external_event(
                title=title[:220],
                started_at=dates[0],
                place=extract_external_location(schedule_text),
                address=schedule_text[:320],
                url=urllib.parse.urljoin(page_url, html.unescape(href_match.group(1))),
                source_name=source_name,
            ))
    return items


def parse_friendlink_events(text, page_url, source_name):
    items = []
    for block in re.findall(r"<li>\s*<span class=\"date\">20\d{2}年.*?</li>", text or "", re.I | re.S):
        items.extend(event_from_block(
            block, page_url, source_name,
            r'<a\b[^>]*href=["\'][^"\']+["\'][^>]*>(.*?)</a>',
            r'<a\b[^>]*href=["\']([^"\']+)["\']',
        ))
    return items


def parse_lepane_events(text, page_url, source_name):
    items = []
    blocks = re.findall(r'<li class="wp-block-post[^>]*meeting[^>]*>.*?</li>', text or "", re.I | re.S)
    for block in blocks:
        items.extend(event_from_block(
            block, page_url, source_name,
            r'<h2\b[^>]*>\s*<a\b[^>]*>(.*?)</a>\s*</h2>',
            r'<h2\b[^>]*>\s*<a\b[^>]*href=["\']([^"\']+)["\']',
            title_prefix="レパン異業種交流会（",
        ))
        if items:
            items[-1]["title"] = items[-1]["title"].rstrip("）") + "）"
    return items


def parse_eventmado_events(text, page_url, source_name):
    items = []
    for block in re.findall(r'<article class="evemado-mjp-card".*?</article>', text or "", re.I | re.S):
        items.extend(event_from_block(
            block, page_url, source_name,
            r'<h3\b[^>]*>(.*?)</h3>',
            r'<a\b[^>]*class="evemado-mjp-detail-button"[^>]*href="([^"]+)"',
            r'<p\b[^>]*class="evemado-mjp-card-place"[^>]*>(.*?)</p>',
        ))
    return items


def parse_first_village_events(text, page_url, source_name):
    items = []
    blocks = re.findall(r'<div class="txtbox">.*?</div>\s*</div>', text or "", re.I | re.S)
    for block in blocks:
        items.extend(event_from_block(
            block, page_url, source_name,
            r'<dt\b[^>]*class="dsc__ttl"[^>]*>(.*?)</dt>',
            r'<a\b[^>]*class="tmp__btn"[^>]*href="([^"]+)"',
            r'<span\b[^>]*class="tag"[^>]*>会場</span>\s*(.*?)(?:</div>|<)',
        ))
    return items


def parse_keizaikai_events(text, page_url, source_name):
    items = []
    blocks = re.findall(r'<div class="event-list[^>]*>.*?(?=<div class="event-list|</main>|$)', text or "", re.I | re.S)
    for block in blocks:
        items.extend(event_from_block(
            block, page_url, source_name,
            r'<dl\b[^>]*class="event-header"[^>]*>.*?<dd>(.*?)</dd>',
            r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*class="btn-border2"',
            r'<th>会場</th>\s*<td>(.*?)</td>',
        ))
    return items


def parse_kobushi_events(text, page_url, source_name):
    items = []
    for block in re.findall(r'<div class="group_event_inner">.*?(?=<div class="group_event_inner">|$)', text or "", re.I | re.S):
        items.extend(event_from_block(
            block, page_url, source_name,
            r'<p\b[^>]*class="event_title"[^>]*>\s*<a\b[^>]*>(.*?)</a>',
            r'<p\b[^>]*class="event_title"[^>]*>\s*<a\b[^>]*href="([^"]+)"',
            r'<p\b[^>]*class="event_place location"[^>]*>.*?<span\b[^>]*class="icon_place"[^>]*>(.*?)</span>',
        ))
    return items


def parse_onlystory_events(text, page_url, source_name):
    items = []
    for block in re.findall(r'<a\b[^>]*class="p-card-column _post1"[^>]*>.*?</a>', text or "", re.I | re.S):
        items.extend(event_from_block(
            block, page_url, source_name,
            r'<h2\b[^>]*class="__title"[^>]*>(.*?)</h2>',
            r'<a\b[^>]*href="([^"]+)"',
        ))
    return items


def parse_clip_tokyo_events(text, page_url, source_name):
    items = []
    for block in re.findall(r'<div class="Event_List_Box\b[^>]*>.*?</a>\s*</div>', text or "", re.I | re.S):
        items.extend(event_from_block(
            block, page_url, source_name,
            r'<h3\b[^>]*class="Event_List_Box_Name_h3"[^>]*>(.*?)</h3>',
            r'<a\b[^>]*href="([^"]+)"',
            r'<div\b[^>]*class="Event_List_Box_Place"[^>]*>(.*?)</div>',
        ))
    return items


def parse_external_jsonld_events(text, page_url, source_name):
    items = []
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', text or "", re.I | re.S):
        try:
            payload = json.loads(html.unescape(raw).strip())
        except (json.JSONDecodeError, TypeError):
            continue
        for event in iter_jsonld_events(payload):
            location = event.get("location") if isinstance(event.get("location"), dict) else {}
            address_value = location.get("address")
            if isinstance(address_value, dict):
                address_value = " ".join(as_text(value) for value in address_value.values() if value)
            offers = event.get("offers") if isinstance(event.get("offers"), dict) else {}
            url = urllib.parse.urljoin(page_url, as_text(event.get("url") or offers.get("url") or page_url))
            started_at = as_text(event.get("startDate"))
            if not started_at:
                continue
            items.append(
                make_external_event(
                    title=as_text(event.get("name")),
                    started_at=started_at,
                    ended_at=as_text(event.get("endDate")),
                    place=as_text(location.get("name")),
                    address=as_text(address_value),
                    url=url,
                    source_name=source_name,
                    owner=as_text(event.get("organizer")),
                )
            )
    return items


def iter_jsonld_events(value):
    if isinstance(value, list):
        for item in value:
            yield from iter_jsonld_events(item)
        return
    if not isinstance(value, dict):
        return
    event_type = value.get("@type")
    if event_type == "Event" or (isinstance(event_type, list) and "Event" in event_type):
        yield value
    for key in ("@graph", "itemListElement", "item"):
        if key in value:
            yield from iter_jsonld_events(value[key])


def looks_like_external_event(title, context):
    text = f"{title} {context}".lower()
    event_terms = EVENT_MEETUP_KEYWORDS + EVENT_BUSINESS_KEYWORDS + (
        "イベント", "セミナー", "例会", "講演", "勉強会", "サロン", "倶楽部", "部会", "meetup",
    )
    return any(term.lower() in text for term in event_terms) and bool(parse_external_datetimes(title) or parse_external_datetimes(context))


def derive_external_title(context_raw, source_name):
    candidates = []
    for pattern in (r'<h[2-5]\b[^>]*>(.*?)</h[2-5]>', r'<img\b[^>]*?alt=["\']([^"\']+)["\']'):
        candidates.extend(clean_html(value) for value in re.findall(pattern, context_raw or "", re.I | re.S))
    ignored = {"イベント", "イベント一覧", "詳細を見る", "more", source_name.lower()}
    candidates = [value for value in candidates if len(value) >= 6 and value.lower() not in ignored]
    event_terms = EVENT_MEETUP_KEYWORDS + EVENT_BUSINESS_KEYWORDS + ("イベント", "セミナー", "例会", "講演", "倶楽部")
    candidates = [value for value in candidates if any(term.lower() in value.lower() for term in event_terms)]
    if not candidates:
        return ""
    return max(candidates, key=lambda value: (bool(parse_external_datetimes(value)), len(value)))


def external_keyword_matches(keyword, text):
    normalized = text.lower()
    tokens = [token.lower() for token in re.split(r"[\s,、]+", keyword or "") if token]
    for token in tokens:
        if token == "交流会":
            continue
        if token not in normalized:
            return False
    return True


def parse_external_datetimes(text):
    patterns = (
        r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日",
        r"(20\d{2})\s*年?\s*(\d{1,2})\s*/\s*(\d{1,2})",
        r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})",
        r"(?<!\d)(\d{1,2})月\s*(\d{1,2})日",
        r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)",
    )
    values = []
    seen = set()
    for pattern_index, pattern in enumerate(patterns):
        for match in re.finditer(pattern, text or ""):
            groups = [int(value) for value in match.groups()]
            if pattern_index < 3:
                year, month, day = groups
            else:
                year = today_local_date().year
                month, day = groups
            tail = (text or "")[match.end() : match.end() + 200]
            time_match = re.search(r"(\d{1,2}):(?P<minute>\d{2})", tail)
            hour = int(time_match.group(1)) if time_match else 0
            minute = int(time_match.group("minute")) if time_match else 0
            try:
                value = datetime(year, month, day, hour, minute, tzinfo=JST).isoformat()
            except ValueError:
                continue
            if value not in seen:
                seen.add(value)
                values.append(value)
    return values


def extract_external_location(text):
    match = re.search(
        r"(オンライン|東京都|大阪府|北海道|神奈川県|埼玉県|千葉県|愛知県|福岡県|兵庫県|京都府|"
        r"新宿|渋谷|有楽町|銀座|梅田|本町|心斎橋|名古屋|札幌|仙台|横浜|神戸|広島|福岡|東京|大阪)",
        text or "",
    )
    return match.group(1) if match else ""


def make_external_event(title, started_at, place, address, url, source_name, ended_at="", owner=""):
    return {
        "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "title": title,
        "startedAt": started_at,
        "endedAt": ended_at,
        "place": place,
        "address": address,
        "url": url,
        "fee": extract_external_fee(f"{title} {address}"),
        "limit": "",
        "accepted": "",
        "waiting": "",
        "owner": owner,
        "hashTag": "",
        "eventId": f"{source_name}:{url}:{started_at}",
        "source": source_name,
    }


def extract_external_fee(text):
    normalized = clean_html(text or "")
    if re.search(r"(?:参加費|料金|会費|入場料|チケット)\s*[：:]?\s*無料|(?:参加|入場)無料|無料開催", normalized):
        return "無料"
    values = []
    patterns = (
        r"(?:参加費|料金|会費|入場料|チケット|男性|女性)\s*[：:]?\s*([￥¥]?\s*\d[\d,]*\s*円?)",
        r"([￥¥]\s*\d[\d,]*)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized, re.I):
            value = re.sub(r"\s+", "", match.group(1))
            if value and value not in values:
                values.append(value)
            if len(values) == 3:
                break
        if values:
            break
    return " / ".join(values)


def filter_events_by_area(events, area):
    tokens = [token for token in re.split(r"[\s,、]+", area or "") if token]
    if not tokens:
        return events

    # 市区町村まで指定した場合は、掲載側が都道府県名を省略していても
    # 最も細かい地域名が一致すれば候補として残す。
    required_tokens = tokens[-1:] if len(tokens) > 1 else tokens

    def token_matches(token, searchable):
        candidates = {token}
        shorter = re.sub(r"(?:都|道|府|県|市|区|町|村)$", "", token)
        if shorter:
            candidates.add(shorter)
        return any(candidate.lower() in searchable for candidate in candidates)

    filtered = []
    for item in events:
        if item.get("source") == "Web検索":
            filtered.append(item)
            continue
        searchable = " ".join(
            str(item.get(field) or "") for field in ("title", "place", "address", "owner")
        ).lower()
        if all(token_matches(token, searchable) for token in required_tokens):
            filtered.append(item)
    return filtered


def filter_events_by_date_range(events, date_from="", date_to=""):
    if not date_from and not date_to:
        return events
    start_date = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else None
    end_date = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else None
    filtered = []
    for item in events:
        try:
            event_date = datetime.fromisoformat(
                as_text(item.get("startedAt")).replace("Z", "+00:00")
            ).astimezone(JST).date()
        except ValueError:
            continue
        if start_date and event_date < start_date:
            continue
        if end_date and event_date > end_date:
            continue
        filtered.append(item)
    return filtered


def search_web_events(api_key, search):
    query_parts = [search["keyword"], search["area"], "イベント セミナー 交流会"]
    query = " ".join(part for part in query_parts if part)
    params = urllib.parse.urlencode(
        {
            "q": query,
            "count": str(min(search["results"], 20)),
            "offset": str(min(9, max(0, (search["start"] - 1) // 20))),
            "country": "jp",
            "search_lang": "jp",
            "safesearch": "moderate",
        }
    )
    data = request_json(
        f"https://api.search.brave.com/res/v1/web/search?{params}",
        headers={"X-Subscription-Token": api_key},
    )
    items = []
    for result in (data.get("web") or {}).get("results") or []:
        url = as_text(result.get("url"))
        if not url:
            continue
        profile = result.get("profile") if isinstance(result.get("profile"), dict) else {}
        items.append(
            {
                "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "title": as_text(result.get("title")),
                "startedAt": "",
                "endedAt": "",
                "place": as_text(profile.get("long_name") or urllib.parse.urlparse(url).netloc),
                "address": as_text(result.get("description")),
                "url": url,
                "limit": "",
                "accepted": "",
                "waiting": "",
                "owner": "",
                "hashTag": "",
                "eventId": url,
                "source": "Web検索",
            }
        )
    return items


def search_job_listings(search):
    if search["source"] != "kyujinbox":
        raise InputError("求人検索元の指定が不正です。")
    items = scrape_kyujinbox_search(search["keyword"], search["area"], search["start"], search["results"])
    return {
        "total": len(items),
        "count": len(items),
        "items": items,
    }


def scrape_kyujinbox_search(keyword, area, start, results):
    per_page = 25
    first_page = max(1, ((start - 1) // per_page) + 1)
    offset = (start - 1) % per_page
    items = []
    page = first_page
    while len(items) < results and page < first_page + 10:
        url = kyujinbox_search_url(keyword, area, page)
        text = request_text(url)
        page_items = parse_kyujinbox_search_html(text)
        if page == first_page and offset:
            page_items = page_items[offset:]
        if not page_items:
            break
        items.extend(page_items)
        page += 1
    return items[:results]


def kyujinbox_search_url(keyword, area, page):
    path = f"/{keyword}の仕事-{area}"
    url = f"https://xn--pckua2a7gp15o89zb.com{urllib.parse.quote(path)}"
    if page > 1:
        url = f"{url}?page={page}"
    return url


def parse_kyujinbox_search_html(text):
    items = []
    seen = set()
    for raw in re.findall(r"data-func-show-arg='([^']+)'", text or ""):
        try:
            outer = json.loads(html.unescape(raw))
            payload = json.loads(outer.get("json") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        job_id = as_text(payload.get("uniqueId") or outer.get("uid"))
        title = clean_html(as_text(payload.get("title") or payload.get("formatTitle") or payload.get("originalTitle")))
        business_name = clean_html(as_text(payload.get("company")))
        listing_company = clean_html(as_text(payload.get("siteName")))
        work_area = clean_html(as_text(payload.get("workArea")))
        employ_type = clean_html(as_text(payload.get("employType")))
        payment = clean_html(as_text(payload.get("payment")))
        updated_at = clean_html(as_text(payload.get("updatedAt")))
        source_url = as_text(payload.get("url"))
        rd_url = as_text(payload.get("rdUrl"))
        if not title or not business_name:
            continue
        url = source_url or (f"https://xn--pckua2a7gp15o89zb.com{rd_url}" if rd_url.startswith("/") else rd_url)
        key = normalize_key_part(job_id or url or f"{business_name}:{title}:{work_area}")
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "businessName": business_name,
                "listingCompany": listing_company,
                "title": title,
                "workArea": work_area,
                "employType": employ_type,
                "payment": payment,
                "updatedAt": updated_at,
                "url": url,
                "media": "求人ボックス",
                "jobId": job_id,
                "source": "求人ボックス",
            }
        )
    return items


def merge_event_sources(*sources):
    merged = []
    seen = set()
    for source in sources:
        for item in source:
            key = event_key(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    merged.sort(key=lambda item: item.get("startedAt") or "")
    return merged


def scrape_connpass_search(keyword, start, results, future_only):
    per_page = 20
    first_page = max(1, ((start - 1) // per_page) + 1)
    offset = (start - 1) % per_page
    items = []
    page = first_page
    today = today_local_date()
    while len(items) < results and page < first_page + 10:
        params = {
            "q": keyword,
            "page": str(page),
        }
        if future_only:
            params["start_from"] = today.isoformat()
        text = request_text(f"https://connpass.com/search/?{urllib.parse.urlencode(params)}")
        page_items = parse_connpass_search_html(text)
        if page == first_page and offset:
            page_items = page_items[offset:]
        if future_only:
            page_items = [item for item in page_items if is_event_today_or_later(item["startedAt"], today)]
        if not page_items:
            break
        items.extend(page_items)
        page += 1
    return items[:results]


def today_local_date():
    return datetime.now(JST).date()


def is_event_today_or_later(started_at, today):
    try:
        value = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    local_midnight = datetime.combine(today, datetime_time.min, JST)
    return value.astimezone(JST) >= local_midnight


def parse_connpass_search_html(text):
    blocks = re.findall(r'<div class="event_list vevent">(.*?)</div>\s*</div>\s*</div>', text, re.S)
    items = []
    for block in blocks:
        url_match = re.search(r'<a class="url summary" href="([^"]+)">(.*?)</a>', block, re.S)
        if not url_match:
            continue
        url = html.unescape(url_match.group(1))
        title = clean_html(url_match.group(2))
        started_at = attr_match(block, r'class="dtstart".*?title="([^"]+)"')
        ended_at = attr_match(block, r'class="dtend".*?title="([^"]+)"')
        place = clean_html(inner_match(block, r'<p class="event_place location">(.*?)</p>'))
        owner = clean_html(inner_match(block, r'<p class="event_owner">(.*?)</p>'))
        accepted, limit = parse_participants(clean_html(inner_match(block, r'<p class="event_participants[^"]*">(.*?)</p>')))
        event_id = attr_match(url, r'/event/(\d+)/')
        items.append(
            {
                "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "title": title,
                "startedAt": started_at,
                "endedAt": ended_at,
                "place": place,
                "address": place,
                "url": url,
                "limit": limit,
                "accepted": accepted,
                "waiting": "",
                "owner": owner,
                "hashTag": "",
                "eventId": event_id,
                "source": "connpass",
            }
        )
    return items


def scrape_kokuchpro_search(keyword, area, start, results, future_only):
    per_page = 20
    first_page = max(1, ((start - 1) // per_page) + 1)
    offset = (start - 1) % per_page
    today = today_local_date()
    items = []
    page = first_page
    while len(items) < results and page < first_page + 10:
        params = {
            "q": keyword,
            "page": str(page),
            "sort": "date",
        }
        if area:
            params["area"] = normalize_kokuchpro_area(area)
        if future_only:
            params["start_date"] = today.isoformat()
        text = request_text(f"https://www.kokuchpro.com/s/?{urllib.parse.urlencode(params)}")
        page_items = parse_kokuchpro_search_html(text)
        if page == first_page and offset:
            page_items = page_items[offset:]
        if future_only:
            page_items = [item for item in page_items if is_event_today_or_later(item["startedAt"], today)]
        if not page_items:
            break
        items.extend(page_items)
        page += 1
    return items[:results]


def parse_kokuchpro_search_html(text):
    items = []
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
        try:
            data = json.loads(html.unescape(raw))
        except json.JSONDecodeError:
            continue
        if data.get("@type") != "Event":
            continue
        location = data.get("location") if isinstance(data.get("location"), dict) else {}
        offers = data.get("offers") if isinstance(data.get("offers"), dict) else {}
        url = as_text(data.get("url") or offers.get("url"))
        if not url:
            continue
        items.append(
            {
                "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "title": as_text(data.get("name")),
                "startedAt": as_text(data.get("startDate")),
                "endedAt": as_text(data.get("endDate")),
                "place": as_text(location.get("name")),
                "address": as_text(location.get("address")),
                "url": url,
                "limit": "",
                "accepted": "",
                "waiting": "",
                "owner": as_text(data.get("organizer")),
                "hashTag": "",
                "eventId": kokuchpro_event_id(url),
                "source": "こくちーずプロ",
            }
        )
    return items


def scrape_doorkeeper_search(keyword, area, start, results, future_only):
    per_page = 20
    first_page = max(1, ((start - 1) // per_page) + 1)
    offset = (start - 1) % per_page
    today = today_local_date()
    items = []
    page = first_page
    while len(items) < results and page < first_page + 10:
        params = {
            "q": keyword,
            "page": str(page),
        }
        prefecture_id = normalize_doorkeeper_area(area)
        if prefecture_id:
            params["prefecture_id"] = prefecture_id
        text = request_text(f"https://www.doorkeeper.jp/events?{urllib.parse.urlencode(params)}")
        page_items = parse_doorkeeper_search_html(text)
        if page == first_page and offset:
            page_items = page_items[offset:]
        if future_only:
            page_items = [item for item in page_items if is_event_today_or_later(item["startedAt"], today)]
        if not page_items:
            break
        items.extend(page_items)
        page += 1
    return items[:results]


def parse_doorkeeper_search_html(text):
    starts = [match.start() for match in re.finditer(r"<div class='global-event events-list'>", text or "")]
    items = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        block = text[start:end]
        url_match = re.search(r"<div class='events-list-item-title'>.*?<a href=\"([^\"]+)\"><span>(.*?)</span>", block, re.S)
        if not url_match:
            continue
        url = html.unescape(url_match.group(1))
        title = clean_html(url_match.group(2))
        date_text = clean_html(inner_match(block, r"<span class='events-list-item-time-date'>(.*?)</span>"))
        time_text = clean_html(inner_match(block, r"<time>(.*?)</time>"))
        started_at = parse_japanese_datetime(date_text, time_text)
        if not started_at:
            continue
        venue = clean_html(inner_match(block, r"<div class='events-list-item-venue'>(.*?)</div>"))
        owner = clean_html(inner_match(block, r"<div class='events-list-item-group'>(.*?)</div>"))
        items.append(
            {
                "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "title": title,
                "startedAt": started_at,
                "endedAt": "",
                "place": venue,
                "address": venue,
                "url": url,
                "limit": "",
                "accepted": "",
                "waiting": "",
                "owner": owner,
                "hashTag": "",
                "eventId": doorkeeper_event_id(url),
                "source": "Doorkeeper",
            }
        )
    return items


def parse_japanese_datetime(date_text, time_text):
    date_match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", date_text or "")
    time_match = re.search(r"(\d{1,2}):(\d{2})", time_text or "")
    if not date_match:
        return ""
    hour = int(time_match.group(1)) if time_match else 0
    minute = int(time_match.group(2)) if time_match else 0
    value = datetime(
        int(date_match.group(1)),
        int(date_match.group(2)),
        int(date_match.group(3)),
        hour,
        minute,
        tzinfo=JST,
    )
    return value.isoformat()


def doorkeeper_event_id(url):
    match = re.search(r"/events/(\d+)", url or "")
    return match.group(1) if match else url


def kokuchpro_event_id(url):
    match = re.search(r"/event/([^/]+)(?:/([^/]+))?/", url)
    if not match:
        return url
    return ":".join(part for part in match.groups() if part)


def normalize_kokuchpro_area(area):
    area = (area or "").split()[0] if area else ""
    aliases = {
        "東京": "東京都",
        "大阪": "大阪府",
        "京都": "京都府",
        "兵庫": "兵庫県",
        "神奈川": "神奈川県",
        "埼玉": "埼玉県",
        "千葉": "千葉県",
        "福岡": "福岡県",
        "北海道": "北海道",
        "オンライン": "",
    }
    return aliases.get(area, area)


def normalize_doorkeeper_area(area):
    area = (area or "").split()[0] if area else ""
    aliases = {
        "北海道": "hokkaido",
        "青森": "aomori",
        "青森県": "aomori",
        "岩手": "iwate",
        "岩手県": "iwate",
        "宮城": "miyagi",
        "宮城県": "miyagi",
        "秋田": "akita",
        "秋田県": "akita",
        "山形": "yamagata",
        "山形県": "yamagata",
        "福島": "fukushima",
        "福島県": "fukushima",
        "茨城": "ibaraki",
        "茨城県": "ibaraki",
        "栃木": "tochigi",
        "栃木県": "tochigi",
        "群馬": "gunma",
        "群馬県": "gunma",
        "埼玉": "saitama",
        "埼玉県": "saitama",
        "千葉": "chiba",
        "千葉県": "chiba",
        "東京": "tokyo",
        "東京都": "tokyo",
        "神奈川": "kanagawa",
        "神奈川県": "kanagawa",
        "新潟": "niigata",
        "新潟県": "niigata",
        "富山": "toyama",
        "富山県": "toyama",
        "石川": "ishikawa",
        "石川県": "ishikawa",
        "福井": "fukui",
        "福井県": "fukui",
        "山梨": "yamanashi",
        "山梨県": "yamanashi",
        "長野": "nagano",
        "長野県": "nagano",
        "岐阜": "gifu",
        "岐阜県": "gifu",
        "静岡": "shizuoka",
        "静岡県": "shizuoka",
        "愛知": "aichi",
        "愛知県": "aichi",
        "三重": "mie",
        "三重県": "mie",
        "滋賀": "shiga",
        "滋賀県": "shiga",
        "京都": "kyoto",
        "京都府": "kyoto",
        "大阪": "osaka",
        "大阪府": "osaka",
        "兵庫": "hyogo",
        "兵庫県": "hyogo",
        "奈良": "nara",
        "奈良県": "nara",
        "和歌山": "wakayama",
        "和歌山県": "wakayama",
        "鳥取": "tottori",
        "鳥取県": "tottori",
        "島根": "shimane",
        "島根県": "shimane",
        "岡山": "okayama",
        "岡山県": "okayama",
        "広島": "hiroshima",
        "広島県": "hiroshima",
        "山口": "yamaguchi",
        "山口県": "yamaguchi",
        "徳島": "tokushima",
        "徳島県": "tokushima",
        "香川": "kagawa",
        "香川県": "kagawa",
        "愛媛": "ehime",
        "愛媛県": "ehime",
        "高知": "kochi",
        "高知県": "kochi",
        "福岡": "fukuoka",
        "福岡県": "fukuoka",
        "佐賀": "saga",
        "佐賀県": "saga",
        "長崎": "nagasaki",
        "長崎県": "nagasaki",
        "熊本": "kumamoto",
        "熊本県": "kumamoto",
        "大分": "oita",
        "大分県": "oita",
        "宮崎": "miyazaki",
        "宮崎県": "miyazaki",
        "鹿児島": "kagoshima",
        "鹿児島県": "kagoshima",
        "沖縄": "okinawa",
        "沖縄県": "okinawa",
        "オンライン": "",
    }
    return aliases.get(area, "")


def clean_html(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(value).split())


def inner_match(text, pattern):
    match = re.search(pattern, text or "", re.S)
    return match.group(1) if match else ""


def attr_match(text, pattern):
    match = re.search(pattern, text or "", re.S)
    return html.unescape(match.group(1)) if match else ""


def parse_participants(value):
    match = re.search(r"(\d+)\s*/\s*(\d+)", value or "")
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def normalize_features(features):
    if not features:
        features = []
    if isinstance(features, dict):
        features = [features]
    items = []
    for feature in features:
        prop = feature.get("Property", {})
        station = first_item(prop.get("Station")) or {}
        genre = first_item(prop.get("Genre")) or {}
        lon, lat = parse_coordinates(feature.get("Geometry", {}).get("Coordinates"))
        items.append(
            {
                "uid": as_text(prop.get("Uid") or feature.get("Id")),
                "gid": as_text(feature.get("Gid")),
                "name": as_text(feature.get("Name")),
                "yomi": as_text(prop.get("Yomi")),
                "address": as_text(prop.get("Address")),
                "tel": as_text(prop.get("Tel1")),
                "nearestStation": as_text(station.get("Name")),
                "railway": as_text(station.get("Railway")),
                "stationExit": as_text(station.get("Exit")),
                "genre": as_text(genre.get("Name")),
                "genreCode": as_text(genre.get("Code")),
                "access": as_text(prop.get("Access1")),
                "url": as_text(prop.get("PcUrl1")),
                "latitude": lat,
                "longitude": lon,
                "source": "Yahoo!ローカルサーチAPI",
                "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
    return items


def normalize_events(events):
    items = []
    for event in events:
        items.append(
            {
                "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "title": as_text(event.get("title")),
                "startedAt": as_text(event.get("started_at")),
                "endedAt": as_text(event.get("ended_at")),
                "place": as_text(event.get("place")),
                "address": as_text(event.get("address")),
                "url": as_text(event.get("event_url")),
                "limit": as_text(event.get("limit")),
                "accepted": as_text(event.get("accepted")),
                "waiting": as_text(event.get("waiting")),
                "owner": as_text(event.get("owner_display_name")),
                "hashTag": as_text(event.get("hash_tag")),
                "eventId": as_text(event.get("event_id")),
                "source": "connpass API",
            }
        )
    return items


def first_item(value):
    return value[0] if isinstance(value, list) and value else value


def parse_coordinates(value):
    if not isinstance(value, str) or "," not in value:
        return "", ""
    lon, lat = [part.strip() for part in value.split(",", 1)]
    return lon, lat


def as_text(value):
    return "" if value is None else str(value)


class SheetsClient:
    def __init__(self, config):
        self.credentials = load_service_account_credentials(config)
        self.access_token = None
        self.expires_at = 0

    def get_values(self, spreadsheet_id, range_name):
        return self.request(
            "GET",
            f"https://sheets.googleapis.com/v4/spreadsheets/{urllib.parse.quote(spreadsheet_id)}/values/{urllib.parse.quote(range_name, safe='')}",
        )

    def get_spreadsheet(self, spreadsheet_id):
        return self.request(
            "GET",
            f"https://sheets.googleapis.com/v4/spreadsheets/{urllib.parse.quote(spreadsheet_id)}?fields=sheets(properties(title,sheetId),conditionalFormats(booleanRule(condition(values(userEnteredValue)))))",
        )

    def batch_update(self, spreadsheet_id, requests):
        return self.request(
            "POST",
            f"https://sheets.googleapis.com/v4/spreadsheets/{urllib.parse.quote(spreadsheet_id)}:batchUpdate",
            {"requests": requests},
        )

    def update_values(self, spreadsheet_id, range_name, values):
        query = urllib.parse.urlencode({"valueInputOption": "RAW"})
        return self.request(
            "PUT",
            f"https://sheets.googleapis.com/v4/spreadsheets/{urllib.parse.quote(spreadsheet_id)}/values/{urllib.parse.quote(range_name, safe='')}?{query}",
            {"values": values},
        )

    def append_values(self, spreadsheet_id, range_name, values):
        query = urllib.parse.urlencode({"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"})
        return self.request(
            "POST",
            f"https://sheets.googleapis.com/v4/spreadsheets/{urllib.parse.quote(spreadsheet_id)}/values/{urllib.parse.quote(range_name, safe='')}:append?{query}",
            {"values": values},
        )

    def request(self, method, url, body=None):
        return request_json(url, method, body, {"Authorization": f"Bearer {self.get_access_token()}"})

    def get_access_token(self):
        now = int(time.time())
        if self.access_token and now < self.expires_at - 60:
            return self.access_token
        assertion = create_jwt_assertion(self.credentials, now)
        body = urllib.parse.urlencode(
            {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        self.access_token = data["access_token"]
        self.expires_at = now + int(data.get("expires_in", 3600))
        return self.access_token


class UserStore:
    def __init__(self, sheets, config):
        self.sheets = sheets
        self.config = config
        self.lock = threading.RLock()
        self.initialized = False

    def ensure_initialized(self):
        with self.lock:
            if self.initialized:
                return
            ensure_sheet_exists(self.sheets, self.config, USER_SHEET_NAME)
            header_range = f"{quote_sheet_name(USER_SHEET_NAME)}!A1:I1"
            values = self.sheets.get_values(self.config["GOOGLE_SHEET_ID"], header_range).get("values", [])
            if not values or values[0] != USER_HEADERS:
                self.sheets.update_values(self.config["GOOGLE_SHEET_ID"], header_range, [USER_HEADERS])
            existing_users = self.list_users(skip_ensure=True)
            known_emails = {user["email"] for user in existing_users}
            if self.config["ACCESS_USERS"]:
                now = utc_timestamp()
                rows = []
                for email_address, password_hash in self.config["ACCESS_USERS"].items():
                    if email_address in known_emails:
                        continue
                    rows.append(
                        [
                            email_address,
                            password_hash,
                            "admin" if email_address in self.config["ADMIN_EMAILS"] else "member",
                            "active",
                            "",
                            "",
                            now,
                            now,
                            "",
                        ]
                    )
                if rows:
                    self.sheets.append_values(
                        self.config["GOOGLE_SHEET_ID"],
                        f"{quote_sheet_name(USER_SHEET_NAME)}!A:I",
                        rows,
                    )
            elif not existing_users and self.config.get("ACCESS_PASSWORD"):
                now = utc_timestamp()
                legacy_email = (self.config.get("ACCESS_MEMBER_ID") or "member").strip().lower()
                self.sheets.append_values(
                    self.config["GOOGLE_SHEET_ID"],
                    f"{quote_sheet_name(USER_SHEET_NAME)}!A:I",
                    [[legacy_email, self.config["ACCESS_PASSWORD"], "admin", "active", "", "", now, now, ""]],
                )
            self.initialized = True

    def list_users(self, skip_ensure=False):
        with self.lock:
            if not skip_ensure:
                self.ensure_initialized()
            rows = self.sheets.get_values(
                self.config["GOOGLE_SHEET_ID"], f"{quote_sheet_name(USER_SHEET_NAME)}!A2:I"
            ).get("values", [])
            users = []
            for row_number, row in enumerate(rows, start=2):
                padded = row + [""] * (9 - len(row))
                email_address = padded[0].strip().lower()
                if not email_address:
                    continue
                users.append(
                    {
                        "row": row_number,
                        "email": email_address,
                        "passwordHash": padded[1],
                        "role": padded[2] or "member",
                        "status": padded[3] or "disabled",
                        "inviteTokenHash": padded[4],
                        "inviteExpiresAt": padded[5],
                        "createdAt": padded[6],
                        "updatedAt": padded[7],
                        "lastLoginAt": padded[8],
                    }
                )
            return users

    def find(self, email_address):
        normalized = (email_address or "").strip().lower()
        return next((user for user in self.list_users() if user["email"] == normalized), None)

    def authenticate(self, email_address, password):
        with self.lock:
            user = self.find(email_address)
            if not user or user["status"] != "active" or not user["passwordHash"]:
                return None
            if not verify_password(password, user["passwordHash"]):
                return None
            user["lastLoginAt"] = utc_timestamp()
            user["updatedAt"] = user["lastLoginAt"]
            self.write_user(user)
            return user

    def invite(self, email_address, base_url):
        normalized = (email_address or "").strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise InputError("有効なメールアドレスを入力してください。")
        with self.lock:
            existing = self.find(normalized)
            if existing and existing["status"] == "active":
                raise InputError("このメールアドレスはすでに利用中です。")
            raw_token = secrets.token_urlsafe(32)
            now = utc_timestamp()
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(timespec="seconds")
            user = existing or {
                "row": None,
                "email": normalized,
                "createdAt": now,
                "lastLoginAt": "",
            }
            user.update(
                {
                    "passwordHash": "",
                    "role": user.get("role") or ("admin" if normalized in self.config["ADMIN_EMAILS"] else "member"),
                    "status": "invited",
                    "inviteTokenHash": token_hash(raw_token),
                    "inviteExpiresAt": expires_at,
                    "updatedAt": now,
                }
            )
            self.write_user(user)
            return f"{base_url}/invite?token={urllib.parse.quote(raw_token)}"

    def accept_invite(self, raw_token, password):
        if len(password) < 12:
            raise InputError("パスワードは12文字以上で設定してください。")
        candidate_hash = token_hash(raw_token)
        with self.lock:
            user = next(
                (
                    item
                    for item in self.list_users()
                    if item["status"] == "invited"
                    and item["inviteTokenHash"]
                    and hmac.compare_digest(item["inviteTokenHash"], candidate_hash)
                ),
                None,
            )
            if not user or invite_expired(user["inviteExpiresAt"]):
                raise InputError("招待リンクが無効か、期限が切れています。管理者に再招待を依頼してください。")
            now = utc_timestamp()
            user.update(
                {
                    "passwordHash": hash_password(password),
                    "status": "active",
                    "inviteTokenHash": "",
                    "inviteExpiresAt": "",
                    "updatedAt": now,
                }
            )
            self.write_user(user)
            return user

    def set_status(self, email_address, status, acting_email):
        if status not in {"active", "disabled"}:
            raise InputError("状態の指定が不正です。")
        normalized = (email_address or "").strip().lower()
        if normalized == (acting_email or "").strip().lower() and status == "disabled":
            raise InputError("自分自身の利用を停止することはできません。")
        with self.lock:
            user = self.find(normalized)
            if not user:
                raise InputError("利用者が見つかりません。")
            user["status"] = status
            user["updatedAt"] = utc_timestamp()
            self.write_user(user)

    def write_user(self, user):
        row = [
            user.get("email", ""),
            user.get("passwordHash", ""),
            user.get("role", "member"),
            user.get("status", "disabled"),
            user.get("inviteTokenHash", ""),
            user.get("inviteExpiresAt", ""),
            user.get("createdAt", ""),
            user.get("updatedAt", ""),
            user.get("lastLoginAt", ""),
        ]
        if user.get("row"):
            range_name = f"{quote_sheet_name(USER_SHEET_NAME)}!A{user['row']}:I{user['row']}"
            self.sheets.update_values(self.config["GOOGLE_SHEET_ID"], range_name, [row])
        else:
            response = self.sheets.append_values(
                self.config["GOOGLE_SHEET_ID"], f"{quote_sheet_name(USER_SHEET_NAME)}!A:I", [row]
            )
            updated_range = response.get("updates", {}).get("updatedRange", "")
            match = re.search(r"![A-Z]+(\d+):", updated_range)
            if match:
                user["row"] = int(match.group(1))


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def token_hash(raw_token):
    return hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()


def invite_expired(value):
    try:
        expires_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return True


def send_invite_email(config, email_address, invite_url):
    if not config["RESEND_API_KEY"]:
        return False
    request_json(
        "https://api.resend.com/emails",
        "POST",
        {
            "from": config["INVITE_FROM_EMAIL"],
            "to": [email_address],
            "subject": "SIGNALへの招待",
            "html": (
                "<p>SIGNALへ招待されました。</p>"
                f'<p><a href="{html.escape(invite_url, quote=True)}">パスワードを設定して利用を開始する</a></p>'
                "<p>このリンクの有効期限は24時間で、1回だけ使用できます。</p>"
            ),
        },
        {"Authorization": f"Bearer {config['RESEND_API_KEY']}"},
    )
    return True


def load_service_account_credentials(config):
    if config["GOOGLE_SERVICE_ACCOUNT_JSON_BASE64"]:
        raw = base64.b64decode(config["GOOGLE_SERVICE_ACCOUNT_JSON_BASE64"]).decode("utf-8")
        return json.loads(raw)
    path = ROOT / config["GOOGLE_APPLICATION_CREDENTIALS"]
    return json.loads(path.read_text(encoding="utf-8"))


def create_jwt_assertion(credentials, now):
    header = {"alg": "RS256", "typ": "JWT"}
    claim = {
        "iss": credentials["client_email"],
        "scope": "https://www.googleapis.com/auth/spreadsheets",
        "aud": "https://oauth2.googleapis.com/token",
        "exp": now + 3600,
        "iat": now,
    }
    unsigned = f"{base64_url_json(header)}.{base64_url_json(claim)}"
    signature = rsa_sha256_sign(unsigned.encode("utf-8"), credentials["private_key"])
    return f"{unsigned}.{base64_url(signature)}"


def rsa_sha256_sign(data, private_key):
    with tempfile.NamedTemporaryFile("w", delete=False) as key_file:
        key_file.write(private_key)
        key_path = key_file.name
    os.chmod(key_path, 0o600)
    try:
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return result.stdout
    finally:
        try:
            os.unlink(key_path)
        except FileNotFoundError:
            pass


def base64_url_json(value):
    return base64_url(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def base64_url(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def quote_sheet_name(sheet_name):
    return "'" + sheet_name.replace("'", "''") + "'"


def ensure_header_row(sheets, config):
    ensure_sheet_exists(sheets, config, config["GOOGLE_SHEET_NAME"])
    range_name = f"{quote_sheet_name(config['GOOGLE_SHEET_NAME'])}!A1:E1"
    values = sheets.get_values(config["GOOGLE_SHEET_ID"], range_name).get("values", [])
    if not values or values[0] != HEADERS:
        sheets.update_values(config["GOOGLE_SHEET_ID"], range_name, [HEADERS])
    format_shop_sheet(sheets, config)


def ensure_sheet_exists(sheets, config, sheet_name):
    spreadsheet = sheets.get_spreadsheet(config["GOOGLE_SHEET_ID"])
    titles = {
        sheet.get("properties", {}).get("title")
        for sheet in spreadsheet.get("sheets", [])
    }
    if sheet_name in titles:
        return
    sheets.batch_update(
        config["GOOGLE_SHEET_ID"],
        [{"addSheet": {"properties": {"title": sheet_name}}}],
    )


class CustomerStore:
    """Keep every customer's owner on the server, never accept it from a request."""

    def __init__(self, sheets, config):
        self.sheets = sheets
        self.config = config
        self.lock = threading.RLock()

    def _rows(self):
        ensure_sheet_exists(self.sheets, self.config, CUSTOMER_SHEET_NAME)
        sheet = quote_sheet_name(CUSTOMER_SHEET_NAME)
        header = self.sheets.get_values(self.config["GOOGLE_SHEET_ID"], f"{sheet}!A1:K1").get("values", [])
        if not header:
            self.sheets.update_values(self.config["GOOGLE_SHEET_ID"], f"{sheet}!A1:K1", [CUSTOMER_HEADERS])
        elif header[0] != CUSTOMER_HEADERS:
            raise RuntimeError("顧客リストの列構成が一致しません。管理者に確認してください。")
        return self.sheets.get_values(self.config["GOOGLE_SHEET_ID"], f"{sheet}!A2:K").get("values", [])

    def list_for(self, email):
        with self.lock:
            return [self._decode(row) for row in self._rows() if row and row[0].lower() == email.lower()]

    @staticmethod
    def _decode(row):
        cells = (row + [""] * 11)[:11]
        try:
            notes = json.loads(cells[9]) if cells[9] else []
        except (TypeError, ValueError):
            notes = []
        return dict(zip(("owner", "id", "name", "phone", "address", "person", "status", "nextCall", "memo", "notes", "updatedAt"), cells[:9] + [notes, cells[10]]))

    def save(self, email, items):
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise InputError("顧客は1回につき1〜100件で保存してください。")
        with self.lock:
            rows = self._rows()
            existing = {(row[0].lower(), row[1]): index + 2 for index, row in enumerate(rows) if len(row) > 1 and row[1]}
            saved = []
            seen = set()
            appended = 0
            for item in items:
                if not isinstance(item, dict):
                    raise InputError("顧客情報が不正です。")
                name = clean_customer_field(item.get("name"), "会社名・店舗名", 160)
                if not name:
                    raise InputError("会社名・店舗名を入力してください。")
                identifier = item.get("id") or secrets.token_hex(16)
                if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
                    raise InputError("顧客IDが不正です。")
                if identifier in seen:
                    raise InputError("同じ顧客IDが重複しています。")
                seen.add(identifier)
                notes = item.get("notes", [])
                if not isinstance(notes, list) or len(json.dumps(notes, ensure_ascii=False)) > 12000:
                    raise InputError("記録履歴が大きすぎます。")
                row = [email.lower(), identifier, name]
                for field, label, limit in (("phone", "電話番号", 80), ("address", "住所", 300), ("person", "担当者", 120), ("status", "ステータス", 80), ("nextCall", "次回連絡", 80), ("memo", "メモ", 2000)):
                    row.append(clean_customer_field(item.get(field), label, limit))
                row.extend([json.dumps(notes, ensure_ascii=False), utc_timestamp()])
                sheet = quote_sheet_name(CUSTOMER_SHEET_NAME)
                key = (email.lower(), identifier)
                if key in existing:
                    number = existing[key]
                    self.sheets.update_values(self.config["GOOGLE_SHEET_ID"], f"{sheet}!A{number}:K{number}", [row])
                else:
                    self.sheets.append_values(self.config["GOOGLE_SHEET_ID"], f"{sheet}!A:K", [row])
                    appended += 1
                    existing[key] = len(rows) + appended + 1
                saved.append(self._decode(row))
            return saved


def clean_customer_field(value, label, limit):
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise InputError(f"{label}は{limit}文字以内で入力してください。")
    return value.strip()


def get_sheet_id(sheets, config, sheet_name):
    spreadsheet = sheets.get_spreadsheet(config["GOOGLE_SHEET_ID"])
    for sheet in spreadsheet.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("title") == sheet_name:
            return properties.get("sheetId")
    return None


def get_sheet_metadata(sheets, config, sheet_name):
    spreadsheet = sheets.get_spreadsheet(config["GOOGLE_SHEET_ID"])
    for sheet in spreadsheet.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("title") == sheet_name:
            return sheet
    return {}


def format_shop_sheet(sheets, config):
    sheet = get_sheet_metadata(sheets, config, config["GOOGLE_SHEET_NAME"])
    sheet_id = sheet.get("properties", {}).get("sheetId")
    if sheet_id is None:
        return
    requests = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(HEADERS),
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.91, "green": 0.94, "blue": 0.97},
                        "horizontalAlignment": "CENTER",
                        "textFormat": {"bold": True},
                    }
                },
                "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.horizontalAlignment,userEnteredFormat.textFormat",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 1000,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(HEADERS),
                },
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP",
                        "verticalAlignment": "MIDDLE",
                    }
                },
                "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment",
            }
        },
        {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 1000,
                    "startColumnIndex": 3,
                    "endColumnIndex": 4,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": status} for status in SHOP_STATUS_OPTIONS],
                    },
                    "inputMessage": "ステータスを選択",
                    "strict": False,
                    "showCustomUi": True,
                },
            }
        },
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
    ]
    for index, width in enumerate(SHOP_COLUMN_WIDTHS):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": index,
                        "endIndex": index + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            }
        )
    existing_status_rules = existing_conditional_status_values(sheet)
    for status in SHOP_STATUS_OPTIONS:
        if status in existing_status_rules:
            continue
        requests.append(
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [
                            {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": 1000,
                                "startColumnIndex": 0,
                                "endColumnIndex": len(HEADERS),
                            }
                        ],
                        "booleanRule": {
                            "condition": {
                                "type": "CUSTOM_FORMULA",
                                "values": [{"userEnteredValue": f'=$D2="{status}"'}],
                            },
                            "format": {"backgroundColor": SHOP_STATUS_COLORS[status]},
                        },
                    },
                    "index": 0,
                }
            }
        )
    sheets.batch_update(config["GOOGLE_SHEET_ID"], requests)


def existing_conditional_status_values(sheet):
    values = set()
    for rule in sheet.get("conditionalFormats", []) or []:
        condition = rule.get("booleanRule", {}).get("condition", {})
        if condition.get("type") != "CUSTOM_FORMULA":
            continue
        for value in condition.get("values", []) or []:
            formula = value.get("userEnteredValue", "")
            for status in SHOP_STATUS_OPTIONS:
                if f'"{status}"' in formula:
                    values.add(status)
    return values


def ensure_event_header_row(sheets, config):
    ensure_sheet_exists(sheets, config, EVENT_SHEET_NAME)
    range_name = f"{quote_sheet_name(EVENT_SHEET_NAME)}!A1:N1"
    values = sheets.get_values(config["GOOGLE_SHEET_ID"], range_name).get("values", [])
    if not values:
        sheets.update_values(config["GOOGLE_SHEET_ID"], range_name, [EVENT_HEADERS])


def ensure_job_header_row(sheets, config):
    ensure_sheet_exists(sheets, config, JOB_SHEET_NAME)
    range_name = f"{quote_sheet_name(JOB_SHEET_NAME)}!A1:L1"
    values = sheets.get_values(config["GOOGLE_SHEET_ID"], range_name).get("values", [])
    if not values:
        sheets.update_values(config["GOOGLE_SHEET_ID"], range_name, [JOB_HEADERS])


def append_items_to_sheet(sheets, config, items):
    ensure_header_row(sheets, config)
    existing = read_existing_keys(sheets, config) if config["SKIP_DUPLICATES"] else set()
    filtered = []
    seen = set(existing)
    for item in items:
        keys = item_keys(item)
        if config["SKIP_DUPLICATES"] and any(key in seen for key in keys):
            continue
        filtered.append(item)
        seen.update(keys)
    if not filtered:
        return {"appended": 0, "skipped": len(items)}
    rows = [
        [
            item["name"],
            item["tel"],
            item["address"],
            "",
            "",
        ]
        for item in filtered
    ]
    sheets.append_values(config["GOOGLE_SHEET_ID"], f"{quote_sheet_name(config['GOOGLE_SHEET_NAME'])}!A:E", rows)
    return {"appended": len(filtered), "skipped": len(items) - len(filtered)}


def append_events_to_sheet(sheets, config, items):
    ensure_event_header_row(sheets, config)
    existing = read_existing_event_keys(sheets, config) if config["SKIP_DUPLICATES"] else set()
    filtered = []
    seen = set(existing)
    for item in items:
        key = event_key(item)
        if config["SKIP_DUPLICATES"] and key in seen:
            continue
        filtered.append(item)
        seen.add(key)
    if not filtered:
        return {"appended": 0, "skipped": len(items)}
    rows = [
        [
            item["fetchedAt"],
            item["title"],
            item["startedAt"],
            item["endedAt"],
            item["place"],
            item["address"],
            item["url"],
            item["limit"],
            item["accepted"],
            item["waiting"],
            item["owner"],
            item["hashTag"],
            item["eventId"],
            item["source"],
        ]
        for item in filtered
    ]
    append_response = sheets.append_values(config["GOOGLE_SHEET_ID"], f"{quote_sheet_name(EVENT_SHEET_NAME)}!A:N", rows)
    highlight_business_event_rows(sheets, config, filtered, append_response)
    return {"appended": len(filtered), "skipped": len(items) - len(filtered)}


def append_jobs_to_sheet(sheets, config, items):
    ensure_job_header_row(sheets, config)
    existing = read_existing_job_keys(sheets, config) if config["SKIP_DUPLICATES"] else set()
    filtered = []
    seen = set(existing)
    for item in items:
        key = job_key(item)
        if config["SKIP_DUPLICATES"] and key in seen:
            continue
        filtered.append(item)
        seen.add(key)
    if not filtered:
        return {"appended": 0, "skipped": len(items)}
    rows = [
        [
            item["fetchedAt"],
            item["businessName"],
            item["listingCompany"],
            item["title"],
            item["workArea"],
            item["employType"],
            item["payment"],
            item["updatedAt"],
            item["url"],
            item["media"],
            item["jobId"],
            item["source"],
        ]
        for item in filtered
    ]
    sheets.append_values(config["GOOGLE_SHEET_ID"], f"{quote_sheet_name(JOB_SHEET_NAME)}!A:L", rows)
    return {"appended": len(filtered), "skipped": len(items) - len(filtered)}


def highlight_business_event_rows(sheets, config, items, append_response):
    start_row = appended_start_row(append_response)
    if not start_row:
        return
    sheet_id = get_sheet_id(sheets, config, EVENT_SHEET_NAME)
    if sheet_id is None:
        return
    requests = []
    for index, item in enumerate(items):
        if not is_business_meetup_event(item):
            continue
        row_index = start_row + index - 1
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": row_index,
                        "endRowIndex": row_index + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(EVENT_HEADERS),
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": EVENT_BUSINESS_HIGHLIGHT_COLOR,
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor",
                }
            }
        )
    if requests:
        sheets.batch_update(config["GOOGLE_SHEET_ID"], requests)


def appended_start_row(append_response):
    updated_range = (
        append_response.get("updates", {}).get("updatedRange", "")
        if isinstance(append_response, dict)
        else ""
    )
    match = re.search(r"![A-Z]+(\d+):", updated_range)
    if not match:
        return None
    return int(match.group(1))


def is_business_meetup_event(item):
    searchable = " ".join(
        [
            item.get("title", ""),
            item.get("place", ""),
            item.get("address", ""),
            item.get("owner", ""),
            item.get("hashTag", ""),
        ]
    ).lower()
    has_meetup_word = any(keyword.lower() in searchable for keyword in EVENT_MEETUP_KEYWORDS)
    has_business_word = any(keyword.lower() in searchable for keyword in EVENT_BUSINESS_KEYWORDS)
    return has_meetup_word and has_business_word


def read_existing_keys(sheets, config):
    range_name = f"{quote_sheet_name(config['GOOGLE_SHEET_NAME'])}!A2:E"
    rows = sheets.get_values(config["GOOGLE_SHEET_ID"], range_name).get("values", [])
    keys = set()
    for row in rows:
        padded = row + [""] * (5 - len(row))
        if looks_like_timestamp(padded[0]):
            name = padded[1]
            address = padded[3]
            tel = padded[4]
        else:
            name = padded[0]
            tel = padded[1]
            address = padded[2]
        keys.update(row_keys("", "", name, address, tel))
    return keys


def read_existing_event_keys(sheets, config):
    range_name = f"{quote_sheet_name(EVENT_SHEET_NAME)}!G2:M"
    rows = sheets.get_values(config["GOOGLE_SHEET_ID"], range_name).get("values", [])
    keys = set()
    for row in rows:
        padded = row + [""] * (7 - len(row))
        url = padded[0]
        event_id = padded[6]
        keys.add(event_key({"url": url, "eventId": event_id}))
    return keys


def read_existing_job_keys(sheets, config):
    range_name = f"{quote_sheet_name(JOB_SHEET_NAME)}!B2:K"
    rows = sheets.get_values(config["GOOGLE_SHEET_ID"], range_name).get("values", [])
    keys = set()
    for row in rows:
        padded = row + [""] * (10 - len(row))
        business_name = padded[0]
        title = padded[2]
        work_area = padded[3]
        url = padded[7]
        job_id = padded[9]
        keys.add(
            job_key(
                {
                    "businessName": business_name,
                    "title": title,
                    "workArea": work_area,
                    "url": url,
                    "jobId": job_id,
                }
            )
        )
    return keys


def event_key(item):
    event_id = normalize_key_part(item.get("eventId"))
    url = normalize_key_part(item.get("url"))
    return f"event::{event_id or url}"


def job_key(item):
    job_id = normalize_key_part(item.get("jobId"))
    url = normalize_key_part(item.get("url"))
    business_name = normalize_key_part(item.get("businessName"))
    title = normalize_key_part(item.get("title"))
    work_area = normalize_key_part(item.get("workArea"))
    return f"job::{job_id or url or f'{business_name}:{title}:{work_area}'}"


def item_keys(item):
    return row_keys(item["uid"], item["gid"], item["name"], item["address"], item["tel"])


def row_keys(uid, gid, name, address, tel):
    keys = set()
    uid = normalize_key_part(uid)
    gid = normalize_key_part(gid)
    name = normalize_key_part(name)
    address = normalize_key_part(address)
    tel = normalize_key_part(tel)
    if uid or gid:
        keys.add(f"yahoo::{uid}::{gid}")
    if name and (address or tel):
        keys.add(f"shop::{name}::{address}::{tel}")
    return keys


def normalize_key_part(value):
    return "".join(str(value or "").split()).lower()


def looks_like_timestamp(value):
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}", str(value or "")))


def make_handler(config, sheets, csrf_token):
    hits = {}
    users = UserStore(sheets, config)
    customers = CustomerStore(sheets, config)

    class Handler(BaseHTTPRequestHandler):
        server_version = "LocalSearchSheets/1.0"

        def do_GET(self):
            if not self.security_check(hits, config):
                return
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/login":
                self.send_login_page()
                return
            if parsed.path == "/invite":
                token = urllib.parse.parse_qs(parsed.query).get("token", [""])[0]
                self.send_invite_page(token)
                return
            if parsed.path == "/logout":
                self.handle_logout()
                return
            if parsed.path in {"/login-bg.jpg", "/business-login-bg.jpg", "/login-bg.mp4", "/assets/signal-icon.png", "/assets/signal-logo.png"}:
                self.serve_static(parsed.path)
                return
            if not self.require_login(config):
                return
            member = self.current_member(config)
            if parsed.path == "/admin/users":
                if not self.require_admin(member):
                    return
                self.send_admin_users_page(member)
                return
            if parsed.path == "/api/customers":
                if config["APP_MODE"] not in {"full", "customers"}:
                    self.send_json(404, {"error": "イベント検索専用版では利用できない機能です。"})
                    return
                if not member:
                    self.send_json(401, {"error": "ログインしてください。"})
                    return
                try:
                    self.send_json(200, {"items": customers.list_for(member)})
                except Exception as error:
                    self.send_json(500, {"error": str(error)})
                return
            if config["APP_MODE"] == "events":
                if parsed.path == "/":
                    self.redirect("/events.html")
                    return
                if parsed.path in {"/local-search.html", "/customers.html"} or parsed.path.startswith("/crm/"):
                    self.redirect("/events.html")
                    return
            if config["APP_MODE"] == "customers":
                if parsed.path == "/":
                    self.redirect("/customers.html")
                    return
                if parsed.path in {"/events.html", "/local-search.html"} or parsed.path.startswith("/crm/"):
                    self.redirect("/customers.html")
                    return
            if parsed.path == "/api/config":
                self.send_json(
                    200,
                    {
                        "csrfToken": csrf_token,
                        "maxResultsPerRun": min(config["MAX_RESULTS_PER_RUN"], 100),
                        "skipDuplicates": config["SKIP_DUPLICATES"],
                        "sheetName": config["GOOGLE_SHEET_NAME"],
                        "eventSheetName": EVENT_SHEET_NAME,
                        "jobSheetName": JOB_SHEET_NAME,
                        "appMode": config["APP_MODE"],
                        "webSearchAvailable": bool(config["BRAVE_SEARCH_API_KEY"]),
                        "memberEmail": member,
                        "isAdmin": self.is_admin(member),
                    },
                )
                return
            self.serve_static(parsed.path)

        def do_POST(self):
            if not self.security_check(hits, config):
                return
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/login":
                self.handle_login(config)
                return
            if parsed.path == "/invite/accept":
                self.handle_invite_accept(config)
                return
            if not self.require_login(config):
                return
            member = self.current_member(config)
            if parsed.path == "/admin/invite":
                if not self.require_admin(member):
                    return
                self.handle_admin_invite(member)
                return
            if parsed.path == "/admin/users/status":
                if not self.require_admin(member):
                    return
                self.handle_admin_status(member)
                return
            if self.headers.get("x-csrf-token") != csrf_token:
                self.send_json(403, {"error": "不正なリクエストです。画面を再読み込みしてください。"})
                return
            try:
                data = self.read_json_body(1024 * 1024 if parsed.path == "/api/customers" else 20 * 1024)
                if parsed.path == "/api/customers":
                    if config["APP_MODE"] not in {"full", "customers"}:
                        self.send_json(404, {"error": "イベント検索専用版では利用できない機能です。"})
                        return
                    if not member:
                        self.send_json(401, {"error": "ログインしてください。"})
                        return
                    if not isinstance(data, dict):
                        raise InputError("顧客情報が不正です。")
                    self.send_json(200, {"items": customers.save(member, data.get("items"))})
                    return
                if self.path == "/api/events/search-and-append":
                    if config["APP_MODE"] == "customers":
                        self.send_json(404, {"error": "顧客管理専用版では利用できない機能です。"})
                        return
                    self.handle_event_search(data)
                    return
                if config["APP_MODE"] in {"events", "customers"}:
                    message = "イベント検索専用版" if config["APP_MODE"] == "events" else "顧客管理専用版"
                    self.send_json(404, {"error": f"{message}では利用できない機能です。"})
                    return
                if self.path == "/api/jobs/search-and-append":
                    self.handle_job_search(data)
                    return
                if self.path == "/api/rem-chat":
                    self.handle_rem_chat(data)
                    return
                if self.path == "/api/voicevox":
                    self.handle_voicevox(data)
                    return
                if self.path != "/api/search-and-append":
                    self.send_json(404, {"error": "見つかりません。"})
                    return
                search = parse_search_input(data, min(config["MAX_RESULTS_PER_RUN"], 100))
                result = search_yahoo_local(config, search)
                sheet_result = (
                    append_items_to_sheet(sheets, config, result["items"])
                    if search["append"]
                    else {"appended": 0, "skipped": 0}
                )
                self.send_json(
                    200,
                    {
                        "query": {"keyword": search["keyword"], "area": search["area"]},
                        "total": result["total"],
                        "count": result["count"],
                        "appended": sheet_result["appended"],
                        "skipped": sheet_result["skipped"],
                        "items": result["items"],
                        "warnings": result.get("warnings", []),
                    },
                )
            except InputError as error:
                self.send_json(400, {"error": str(error)})
            except Exception as error:
                self.send_json(500, {"error": str(error)})

        def handle_rem_chat(self, data):
            message = clean_optional_text(data.get("message", ""), "メッセージ")
            if not message:
                raise InputError("メッセージを入力してください。")
            reply = generate_rem_reply(config, message, data.get("customer"))
            self.send_json(200, {"reply": reply})

        def handle_voicevox(self, data):
            message = clean_voice_text(data.get("text", ""))
            audio = generate_voicevox_audio(config, message)
            self.send_audio(audio)

        def handle_event_search(self, data):
            search = parse_event_search_input(data, min(config["MAX_RESULTS_PER_RUN"], 100))
            result = search_connpass_events(search, config["BRAVE_SEARCH_API_KEY"])
            warnings = list(result.get("warnings", []))
            sheet_result = {"appended": 0, "skipped": 0}
            if search["append"]:
                try:
                    sheet_result = append_events_to_sheet(sheets, config, result["items"])
                except Exception as error:
                    warnings.append(
                        f"検索結果は取得できましたが、Googleシートへ追記できませんでした（{brief_external_error(error)}）"
                    )
            self.send_json(
                200,
                {
                    "query": {"keyword": search["keyword"], "area": search["area"]},
                    "total": result["total"],
                    "count": result["count"],
                    "appended": sheet_result["appended"],
                    "skipped": sheet_result["skipped"],
                    "items": result["items"],
                    "warnings": warnings,
                },
            )

        def handle_job_search(self, data):
            search = parse_job_search_input(data, min(config["MAX_RESULTS_PER_RUN"], 100))
            result = search_job_listings(search)
            sheet_result = (
                append_jobs_to_sheet(sheets, config, result["items"])
                if search["append"]
                else {"appended": 0, "skipped": 0}
            )
            self.send_json(
                200,
                {
                    "query": {"keyword": search["keyword"], "area": search["area"]},
                    "total": result["total"],
                    "count": result["count"],
                    "appended": sheet_result["appended"],
                    "skipped": sheet_result["skipped"],
                    "items": result["items"],
                },
            )

        def read_json_body(self, max_length=20 * 1024):
            length = int(self.headers.get("content-length", "0"))
            if length > max_length:
                raise InputError("リクエストが大きすぎます。")
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

        def handle_logout(self):
            self.send_response(303)
            self.send_security_headers()
            self.send_header("Set-Cookie", "crm_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0")
            self.send_header("Location", "/login")
            self.end_headers()

        def handle_login(self, cfg):
            length = min(int(self.headers.get("content-length", "0")), 4096)
            params = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
            member_id = ((params.get("email") or params.get("member_id")) or [""])[0].strip().lower()
            password = (params.get("password") or [""])[0]
            try:
                authenticated_user = users.authenticate(member_id, password)
            except Exception as error:
                detail = re.sub(r"\s+", " ", str(error))[:400]
                print(
                    f"LOGIN_AUTH_ERROR {type(error).__name__} "
                    f"detail={detail}",
                    flush=True,
                )
                authenticated_user = None
            if authenticated_user:
                cookie = make_session_cookie(member_id or "member", cfg["SESSION_SECRET"])
                self.send_response(303)
                self.send_security_headers()
                secure = "" if is_local_host(self.headers.get("Host", "")) else "; Secure"
                self.send_header("Set-Cookie", f"crm_session={cookie}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400{secure}")
                destination = app_landing_path(cfg["APP_MODE"])
                self.send_header("Location", destination)
                self.end_headers()
                return
            self.send_login_page("メールアドレスまたはパスワードが違います。")

        def handle_invite_accept(self, cfg):
            params = self.read_form_body()
            raw_token = params.get("token", "")
            password = params.get("password", "")
            password_confirm = params.get("password_confirm", "")
            if password != password_confirm:
                self.send_invite_page(raw_token, "確認用パスワードが一致しません。")
                return
            try:
                user = users.accept_invite(raw_token, password)
            except InputError as error:
                self.send_invite_page(raw_token, str(error))
                return
            cookie = make_session_cookie(user["email"], cfg["SESSION_SECRET"])
            self.send_response(303)
            self.send_security_headers()
            secure = "" if is_local_host(self.headers.get("Host", "")) else "; Secure"
            self.send_header("Set-Cookie", f"crm_session={cookie}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400{secure}")
            self.send_header("Location", app_landing_path(cfg["APP_MODE"]))
            self.end_headers()

        def handle_admin_invite(self, member):
            params = self.read_form_body()
            if params.get("csrf_token") != csrf_token:
                self.send_admin_users_page(member, "不正なリクエストです。画面を再読み込みしてください。", True)
                return
            try:
                email_address = params.get("email", "").strip().lower()
                base_url = config["APP_BASE_URL"] or request_base_url(self)
                invite_url = users.invite(email_address, base_url)
                sent = send_invite_email(config, email_address, invite_url)
                message = "招待メールを送信しました。" if sent else "招待を作成しました。下のリンクを本人へ共有してください。"
                self.send_admin_users_page(member, message, False, invite_url)
            except (InputError, RuntimeError) as error:
                self.send_admin_users_page(member, str(error), True)

        def handle_admin_status(self, member):
            params = self.read_form_body()
            if params.get("csrf_token") != csrf_token:
                self.send_admin_users_page(member, "不正なリクエストです。画面を再読み込みしてください。", True)
                return
            try:
                users.set_status(params.get("email", ""), params.get("status", ""), member)
                self.redirect("/admin/users")
            except InputError as error:
                self.send_admin_users_page(member, str(error), True)

        def require_login(self, cfg):
            if not cfg["ALLOW_REMOTE_ACCESS"] and not cfg["ACCESS_PASSWORD"]:
                return True
            member_id = session_member_from_cookie(self.headers.get("Cookie", ""), cfg["SESSION_SECRET"])
            if member_id:
                try:
                    user = users.find(member_id)
                    if user and user["status"] == "active":
                        return True
                except Exception:
                    pass
            if self.path.startswith("/api/"):
                self.send_json(401, {"error": "ログインしてください。"})
                return False
            self.send_response(303)
            self.send_security_headers()
            self.send_header("Location", "/login")
            self.end_headers()
            return False

        def current_member(self, cfg):
            return session_member_from_cookie(self.headers.get("Cookie", ""), cfg["SESSION_SECRET"]) or ""

        def is_admin(self, member):
            try:
                user = users.find(member)
                if user:
                    return user["status"] == "active" and user["role"] == "admin"
            except Exception:
                pass
            return member in config["ADMIN_EMAILS"]

        def require_admin(self, member):
            if self.is_admin(member):
                return True
            self.send_json(403, {"error": "管理者のみ利用できます。"})
            return False

        def read_form_body(self):
            length = min(int(self.headers.get("content-length", "0")), 16 * 1024)
            parsed = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
            return {key: values[0] if values else "" for key, values in parsed.items()}

        def send_invite_page(self, token, error=""):
            body = invite_page(token, error, config["APP_MODE"]).encode("utf-8")
            self.send_response(200)
            self.send_login_security_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_admin_users_page(self, member, message="", is_error=False, invite_url=""):
            try:
                user_list = users.list_users()
                body = admin_users_page(
                    user_list,
                    member,
                    csrf_token,
                    message,
                    is_error,
                    invite_url,
                    config["APP_MODE"],
                    bool(config["RESEND_API_KEY"]),
                ).encode("utf-8")
            except Exception as error:
                body = admin_users_page(
                    [],
                    member,
                    csrf_token,
                    f"利用者一覧を取得できませんでした: {error}",
                    True,
                    "",
                    config["APP_MODE"],
                    bool(config["RESEND_API_KEY"]),
                ).encode("utf-8")
            self.send_response(200)
            self.send_login_security_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_login_page(self, error=""):
            body = login_page(error, config["APP_MODE"]).encode("utf-8")
            self.send_response(200)
            self.send_login_security_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def redirect(self, location):
            self.send_response(303)
            self.send_security_headers()
            self.send_header("Location", location)
            self.end_headers()

        def serve_static(self, request_path):
            safe_path = "index.html" if request_path == "/" else request_path.lstrip("/")
            target = (PUBLIC_DIR / safe_path).resolve()
            if not str(target).startswith(str(PUBLIC_DIR.resolve())) or not target.exists():
                self.send_json(404, {"error": "見つかりません。"})
                return
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
            }.get(target.suffix, "application/octet-stream")
            self.send_response(200)
            self.send_security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(target.read_bytes())

        def security_check(self, hits_map, cfg):
            if not cfg["ALLOW_REMOTE_ACCESS"] and not is_local_host(self.headers.get("host", "")):
                self.send_json(403, {"error": "ローカルホストからのみ利用できます。"})
                return False
            key = self.client_address[0]
            now = time.time()
            count, reset_at = hits_map.get(key, (0, now + 15 * 60))
            if now > reset_at:
                count, reset_at = 0, now + 15 * 60
            count += 1
            hits_map[key] = (count, reset_at)
            if count > cfg["REQUESTS_PER_15_MIN"]:
                self.send_json(429, {"error": "リクエスト数が多すぎます。少し待ってから再実行してください。"})
                return False
            return True

        def send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_security_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_audio(self, body):
            self.send_response(200)
            self.send_security_headers()
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_login_security_headers(self):
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob: data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")

        def send_security_headers(self):
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob: data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")

        def log_message(self, fmt, *args):
            print("%s - %s" % (self.address_string(), fmt % args))

    return Handler




def clean_voice_text(value):
    if not isinstance(value, str):
        raise InputError("読み上げテキストが不正です。")
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        raise InputError("読み上げテキストを入力してください。")
    return value[:160]


def generate_voicevox_audio(config, text):
    base_url = str(config.get("VOICEVOX_URL") or "http://127.0.0.1:50021").rstrip("/")
    speaker = int(config.get("VOICEVOX_SPEAKER") or 24)
    query_url = f"{base_url}/audio_query?" + urllib.parse.urlencode({"text": text, "speaker": speaker})
    query_req = urllib.request.Request(query_url, method="POST", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(query_req, timeout=10) as response:
            audio_query = json.loads(response.read().decode("utf-8") or "{}")
    except Exception as error:
        raise RuntimeError(f"VOICEVOXに接続できません。VOICEVOXを起動してください。{error}")

    audio_query["speedScale"] = 1.06
    audio_query["pitchScale"] = 0.02
    audio_query["intonationScale"] = 1.12
    synthesis_url = f"{base_url}/synthesis?" + urllib.parse.urlencode({"speaker": speaker})
    body = json.dumps(audio_query).encode("utf-8")
    synthesis_req = urllib.request.Request(
        synthesis_url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "audio/wav"},
    )
    try:
        with urllib.request.urlopen(synthesis_req, timeout=20) as response:
            return response.read()
    except Exception as error:
        raise RuntimeError(f"VOICEVOX音声の生成に失敗しました。{error}")


def generate_rem_reply(config, message, customer=None):
    if config.get("OPENAI_API_KEY"):
        try:
            return generate_openai_reply(config, message, customer)
        except Exception as error:
            return fallback_rem_reply(message, customer, str(error))
    return fallback_rem_reply(message, customer)


def generate_openai_reply(config, message, customer=None):
    customer_text = ""
    if isinstance(customer, dict) and customer.get("name"):
        customer_text = f"\n現在選択中の顧客: {customer.get('name')} / 状態: {customer.get('status', '')} / メモ: {customer.get('memo', '')}"
    payload = {
        "model": config["OPENAI_MODEL"],
        "input": [
            {
                "role": "system",
                "content": "あなたはテレアポCRM内の案内役『レム』です。著作物の台詞や人物設定は真似せず、やさしく短く実務的に返答します。営業トーク、優先順位、メモ整理、軽い雑談に対応します。返答は日本語で80文字以内を基本にしてください。"
            },
            {"role": "user", "content": message + customer_text},
        ],
        "max_output_tokens": 180,
    }
    data = request_json(
        "https://api.openai.com/v1/responses",
        "POST",
        payload,
        {"Authorization": f"Bearer {config['OPENAI_API_KEY']}"},
    )
    parts = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                parts.append(content.get("text", ""))
    return "".join(parts).strip() or fallback_rem_reply(message, customer)


def fallback_rem_reply(message, customer=None, error=""):
    text = str(message or "").lower()
    name = customer.get("name") if isinstance(customer, dict) else ""
    status = customer.get("status") if isinstance(customer, dict) else ""
    memo = customer.get("memo") if isinstance(customer, dict) else ""
    notes = customer.get("notes") if isinstance(customer, dict) else []
    prefix = f"{name}の件ですね。" if name else "はい。"

    if "insufficient_quota" in str(error) or "quota" in str(error).lower():
        return "OpenAIの利用枠が止まっているため、今は簡易AIで返します。課金枠が復活したら会話の精度が上がります。"
    if re.search(r"疲|しんど|無理|つら|不安|怖|焦", text):
        return "大丈夫です。今日は全部やろうとせず、まず一件だけ選びましょう。短く記録して、次の一手を決めれば十分です。"
    if re.search(r"何から|優先|どれ|順番|どう進め", text):
        if status:
            return f"{prefix}今の状態は{status}です。再コール、見込み、未架電の順で確認して、温度が高い相手から進めるのが良いです。"
        return "優先順位は、再コール、見込み、未架電の順がおすすめです。迷ったら次回連絡日が近いものから見ましょう。"
    if re.search(r"トーク|話し方|断ら|営業|切り返", text):
        return "最初は『30秒だけ要件をお伝えしてもよろしいでしょうか』で短く入り、反応が薄ければ資料送付か再コールに分けるのが使いやすいです。"
    if re.search(r"メモ|要約|まとめ|整理", text):
        if memo:
            return f"{prefix}今のメモは『{memo[:45]}』です。結論、温度感、次回アクションの3つに分けると後で見返しやすいです。"
        if notes:
            return f"{prefix}履歴が{len(notes)}件あります。最新の会話から、次に聞くことと次回連絡日を残しましょう。"
        return "メモは『相手の反応』『課題』『次回やること』の3行で残すと、次の電話がかなり楽になります。"
    if re.search(r"アポ|日程|予定|商談", text):
        return "アポ化するなら、候補日を2つ出して選んでもらう形が強いです。『火曜午前か木曜午後ならどちらが近いですか』で進めましょう。"
    if re.search(r"留守|出ない|不在", text):
        return "留守なら時間帯を変えて再コールにしましょう。午前に出なければ夕方、夕方に出なければ翌営業日の午前が試しやすいです。"
    if re.search(r"禁止|ng|断り|不要", text):
        return "禁止や強い断りは無理に追わず、理由だけ短く残しましょう。次の見込み客に時間を回す方が効率的です。"
    if re.search(r"ありがとう|助か|いいね|最高|笑|ｗ|ww", text):
        return "えへへ、ありがとうございます。次は見込みか再コールを一件だけ片付けましょう。流れができれば一気に進みます。"
    return f"{prefix}今は簡易AIで対応中です。状況、相手の反応、次にしたいことを一言くれたら、トーク案か次回アクションに整理します。"

def make_session_cookie(member_id, secret):
    issued_at = str(int(time.time()))
    payload = f"{member_id}:{issued_at}"
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def session_member_from_cookie(cookie_header, secret):
    cookies = {}
    for part in (cookie_header or "").split(";"):
        if "=" in part:
            key, value = part.strip().split("=", 1)
            cookies[key] = value
    raw = cookies.get("crm_session", "")
    parts = raw.split(":")
    if len(parts) != 3:
        return None
    member_id, issued_at, signature = parts
    try:
        if int(time.time()) - int(issued_at) > 86400:
            return None
    except ValueError:
        return None
    payload = f"{member_id}:{issued_at}"
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return member_id if hmac.compare_digest(signature, expected) else None


def app_landing_path(app_mode):
    return {"events": "/events.html", "customers": "/customers.html"}.get(app_mode, "/crm/index.html")


def login_page(error="", app_mode="full"):
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    product_name = "SIGNAL" if app_mode == "events" else ("SIGNAL CUSTOMER" if app_mode == "customers" else "テレアポCRM")
    eyebrow = "SIGNAL" if app_mode in {"events", "customers"} else "Teleapo Command CRM"
    description = {
        "events": "メールアドレスとパスワードを入力して、イベント検索に入ります。",
        "customers": "メールアドレスとパスワードを入力して、本人専用の顧客リストに入ります。",
    }.get(app_mode, "メールアドレスとパスワードを入力して、CRMと検索システムに入ります。")
    return """<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ログイン | """ + product_name + """</title>
    """ + ('<link rel="icon" type="image/png" href="/assets/signal-icon.png" />' if app_mode in {"events", "customers"} else '') + """
    <style>
      :root {
        color-scheme: dark;
        --accent: #38bdf8;
        --text: #e5eefb;
        --muted: #b7c6dc;
        --card: rgb(8 13 24 / 72%);
        --line: rgb(255 255 255 / 15%);
        --field: rgb(8 13 24 / 78%);
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #050814;
        color: var(--text);
      }
      :root[data-theme="light"] {
        color-scheme: light;
        --text: #17202a;
        --muted: #516173;
        --card: rgb(255 255 255 / 78%);
        --line: rgb(23 32 42 / 16%);
        --field: rgb(255 255 255 / 86%);
      }
      * { box-sizing: border-box; }
      body { margin: 0; min-height: 100vh; overflow: hidden; isolation: isolate; }
      .bgVideo, .bgFallback, .shade { position: fixed; inset: 0; width: 100%; height: 100%; pointer-events: none; }
      .bgVideo { display: none; object-fit: cover; z-index: 0; }
      .bgFallback { z-index: 0; background: url('/business-login-bg.jpg') center / cover no-repeat; transform: scale(1.025); animation: loginDrift 20s ease-in-out infinite alternate; }
      .shade { z-index: 1; background: radial-gradient(circle at 50% 44%, rgb(15 23 42 / 22%), transparent 33%), linear-gradient(90deg, rgb(2 6 23 / 70%), rgb(2 6 23 / 46%), rgb(2 6 23 / 72%)); }
      :root[data-theme="light"] .shade { background: radial-gradient(circle at 50% 45%, rgb(255 255 255 / 18%), transparent 34%), linear-gradient(90deg, rgb(238 244 250 / 62%), rgb(238 244 250 / 34%), rgb(238 244 250 / 66%)); }
      @keyframes loginDrift { from { transform: scale(1.04) translate3d(-8px, -6px, 0); } to { transform: scale(1.09) translate3d(10px, 8px, 0); } }
      main { position: relative; z-index: 2; min-height: 100vh; display: grid; place-items: center; padding: 20px; }
      .loginCard {
        width: min(420px, calc(100vw - 32px));
        background: var(--card);
        border: 1px solid var(--line);
        border-radius: 8px;
        box-shadow: 0 28px 90px rgb(0 0 0 / 42%);
        backdrop-filter: blur(18px) saturate(130%);
        padding: 24px;
        display: grid;
        gap: 18px;
      }
      .brandRow { display: flex; align-items: start; justify-content: space-between; gap: 14px; }
      .signalBrand { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
      .signalBrand img { width: 48px; height: 48px; object-fit: contain; filter: drop-shadow(0 0 10px rgb(56 189 248 / 20%)); }
      .signalBrand span { color: var(--text); font-size: 31px; font-weight: 950; letter-spacing: .035em; line-height: 1; }
      .eyebrow { margin: 0 0 7px; color: var(--accent); font-size: 11px; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; }
      h1 { margin: 0; font-size: 30px; line-height: 1.12; }
      p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.65; }
      form { display: grid; gap: 14px; }
      label { display: grid; gap: 7px; color: var(--text); font-size: 12px; font-weight: 850; }
      input { width: 100%; border: 1px solid var(--line); border-radius: 7px; background: var(--field); color: var(--text); padding: 12px 13px; font: inherit; }
      input:focus { outline: 3px solid rgb(56 189 248 / 30%); border-color: var(--accent); }
      button { border: 0; border-radius: 7px; background: var(--accent); color: #06101d; padding: 12px 14px; font: inherit; font-weight: 900; cursor: pointer; }
      .modeToggle { width: auto; min-width: 82px; padding: 8px 12px; border-radius: 999px; background: rgb(22 34 56 / 78%); color: #d8e6f7; border: 1px solid var(--line); font-size: 12px; }
      :root[data-theme="light"] .modeToggle { background: rgb(238 246 255 / 78%); color: #1769aa; }
      .error { color: #fecaca; background: rgb(69 26 26 / 78%); border: 1px solid rgb(127 29 29 / 72%); border-radius: 7px; padding: 10px 12px; font-weight: 800; }
      :root[data-theme="light"] .error { color: #a12a2a; background: rgb(255 241 241 / 82%); border-color: #f3c2c2; }
      .hintRow { display: flex; gap: 8px; flex-wrap: wrap; }
      .chip { border: 1px solid var(--line); background: rgb(16 24 39 / 52%); color: #dce8f7; border-radius: 999px; padding: 7px 10px; font-size: 12px; font-weight: 800; }
      :root[data-theme="light"] .chip { background: rgb(238 246 255 / 72%); color: #1769aa; }
      @media (max-width: 640px) {
        body { overflow: auto; }
        main { align-items: center; padding: 14px; }
        .loginCard { padding: 18px; }
        h1 { font-size: 26px; }
      }
    </style>
    <script>
      const key = 'teleapo-ui-mode';
      function applyMode(mode) {
        const next = mode === 'light' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        localStorage.setItem(key, next);
        const button = document.querySelector('#modeToggle');
        if (button) button.textContent = next === 'dark' ? 'ライト' : 'ダーク';
      }
      document.addEventListener('DOMContentLoaded', () => {
        applyMode(localStorage.getItem(key) || 'dark');
        document.querySelector('#modeToggle')?.addEventListener('click', () => applyMode(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
      });
    </script>
  </head>
  <body>
    <div class="bgFallback" aria-hidden="true"></div>
    <div class="shade" aria-hidden="true"></div>
    <main>
      <section class="loginCard" aria-labelledby="loginTitle">
        <div class="brandRow">
          <div>
            """ + ('<div class="signalBrand" aria-label="' + product_name + '"><img src="/assets/signal-icon.png" alt="" /><span>' + product_name + '</span></div>' if app_mode in {"events", "customers"} else '<p class="eyebrow">' + eyebrow + '</p>') + """
            <h1 id="loginTitle">ログイン</h1>
          </div>
          <button id="modeToggle" class="modeToggle" type="button">ライト</button>
        </div>
        <p>""" + description + """</p>
        """ + error_html + """
        <form method="post" action="/login">
          <label>メールアドレス<input name="email" type="email" autocomplete="username" required autofocus /></label>
          <label>パスワード<input name="password" type="password" autocomplete="current-password" required /></label>
          <button type="submit">ログイン</button>
        </form>
      </section>
    </main>
  </body>
</html>"""


def invite_page(token, error="", app_mode="events"):
    product_name = "SIGNAL" if app_mode == "events" else ("SIGNAL CUSTOMER" if app_mode == "customers" else "テレアポCRM")
    message = f'<p class="message error">{html.escape(error)}</p>' if error else ""
    safe_token = html.escape(token or "", quote=True)
    disabled = " disabled" if not token else ""
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>パスワード設定 | {html.escape(product_name)}</title>
  <link rel="icon" type="image/png" href="/assets/signal-icon.png" />
  <style>
    :root {{ color-scheme: dark; font-family: system-ui, sans-serif; background:#050814; color:#e5eefb; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; min-height:100vh; display:grid; place-items:center; padding:20px; background:radial-gradient(circle at 50% 15%,#12355a,#050814 48%); }}
    main {{ width:min(440px,100%); padding:26px; background:rgb(8 13 24 / 88%); border:1px solid rgb(255 255 255 / 14%); border-radius:12px; box-shadow:0 24px 80px #0008; }}
    .brand {{ color:#38bdf8; font-weight:950; letter-spacing:.08em; }} h1 {{ margin:8px 0; }} p {{ color:#b7c6dc; line-height:1.7; }}
    form,label {{ display:grid; gap:8px; }} form {{ gap:15px; margin-top:20px; }} label {{ font-size:13px; font-weight:800; }}
    input {{ width:100%; padding:12px; border:1px solid #ffffff25; border-radius:8px; background:#081120; color:#fff; font:inherit; }}
    button {{ padding:13px; border:0; border-radius:8px; background:#38bdf8; color:#06101d; font-weight:900; cursor:pointer; }}
    .error {{ color:#fecaca; background:#451a1acc; padding:10px 12px; border-radius:8px; }} a {{ color:#7dd3fc; }}
  </style>
</head>
<body><main>
  <div class="brand">{html.escape(product_name)}</div>
  <h1>パスワード設定</h1>
  <p>12文字以上のパスワードを設定してください。設定後、そのまま{html.escape(product_name)}へログインします。</p>
  {message}
  <form method="post" action="/invite/accept">
    <input type="hidden" name="token" value="{safe_token}" />
    <label>パスワード<input name="password" type="password" minlength="12" autocomplete="new-password" required{disabled} /></label>
    <label>パスワード（確認）<input name="password_confirm" type="password" minlength="12" autocomplete="new-password" required{disabled} /></label>
    <button type="submit"{disabled}>設定して利用を開始</button>
  </form>
  <p><a href="/login">ログイン画面へ戻る</a></p>
</main></body></html>"""


def admin_users_page(user_list, member, csrf_token, message="", is_error=False, invite_url="", app_mode="events", mail_delivery_enabled=False):
    status_labels = {"active": "利用中", "invited": "招待中", "disabled": "停止中"}
    rows = []
    for user in user_list:
        if user["status"] == "invited":
            action = f"""
          <form method="post" action="/admin/invite">
            <input type="hidden" name="csrf_token" value="{html.escape(csrf_token, quote=True)}" />
            <input type="hidden" name="email" value="{html.escape(user['email'], quote=True)}" />
            <button class="secondary" type="submit">再招待</button>
          </form>"""
        else:
            next_status = "disabled" if user["status"] == "active" else "active"
            action_label = "利用停止" if next_status == "disabled" else "利用再開"
            action = "—" if user["email"] == member else f"""
          <form method="post" action="/admin/users/status">
            <input type="hidden" name="csrf_token" value="{html.escape(csrf_token, quote=True)}" />
            <input type="hidden" name="email" value="{html.escape(user['email'], quote=True)}" />
            <input type="hidden" name="status" value="{next_status}" />
            <button class="secondary" type="submit">{action_label}</button>
          </form>"""
        rows.append(
            "<tr>"
            f"<td>{html.escape(user['email'])}</td>"
            f"<td>{'管理者' if user['role'] == 'admin' else '利用者'}</td>"
            f"<td><span class=\"status {html.escape(user['status'])}\">{status_labels.get(user['status'], user['status'])}</span></td>"
            f"<td>{html.escape(format_admin_date(user['updatedAt']))}</td>"
            f"<td>{action}</td>"
            "</tr>"
        )
    notice = ""
    if message:
        notice = f'<p class="notice{" error" if is_error else ""}">{html.escape(message)}</p>'
    link_panel = ""
    if invite_url:
        safe_url = html.escape(invite_url, quote=True)
        link_panel = f'''<div class="inviteLink">
          <strong>招待リンク</strong>
          <div class="copyRow"><input value="{safe_url}" readonly id="inviteUrl" onclick="this.select()" /><button class="secondary" type="button" onclick="copyInviteUrl(this)">コピー</button></div>
          <small>{"招待メールを送信済みです。届かない場合は、このリンクを本人へ共有してください。" if mail_delivery_enabled else "このリンクを本人へ共有してください。24時間・1回限り有効です。"}</small>
        </div>'''
    delivery_status = "メール自動送信：有効" if mail_delivery_enabled else "メール自動送信：未設定（招待リンクを共有）"
    return f"""<!doctype html>
<html lang="ja"><head>
  <meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>利用者管理 | SIGNAL</title><link rel="icon" type="image/png" href="/assets/signal-icon.png" />
  <style>
    :root {{ color-scheme:dark; font-family:Inter,"Noto Sans JP",system-ui,sans-serif; background:#07101f; color:#eaf1f8; }} * {{ box-sizing:border-box; }} body {{ margin:0; min-height:100vh; background:linear-gradient(160deg,#07101f 0%,#0b1729 55%,#101c2d 100%); }}
    main {{ width:min(1100px,calc(100% - 28px)); margin:30px auto 56px; }} header {{ display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:22px; }}
    h1 {{ margin:4px 0; }} h2 {{ margin-top:0; }} .brand {{ color:#7dd3fc; font-weight:950; letter-spacing:.12em; }} a {{ color:#8fdcff; }}
    section {{ background:rgb(10 22 39 / 92%); border:1px solid #ffffff16; border-radius:14px; padding:22px; margin-bottom:20px; box-shadow:0 20px 55px #02061745; }}
    form {{ display:flex; gap:10px; align-items:end; flex-wrap:wrap; }} label {{ display:grid; gap:7px; min-width:min(360px,100%); font-size:13px; font-weight:800; }}
    input {{ padding:11px 12px; border:1px solid #ffffff25; border-radius:8px; background:#081120; color:#fff; font:inherit; }}
    button {{ padding:11px 15px; border:0; border-radius:8px; background:#38bdf8; color:#06101d; font-weight:900; cursor:pointer; }} button.secondary {{ background:#24344d; color:#e5eefb; padding:8px 10px; }}
    table {{ width:100%; border-collapse:collapse; }} th,td {{ text-align:left; padding:12px 10px; border-bottom:1px solid #ffffff14; }} th {{ color:#91a7c4; font-size:12px; }}
    .status {{ display:inline-block; padding:5px 8px; border-radius:999px; font-size:12px; font-weight:850; background:#334155; }} .status.active {{ background:#14532d; }} .status.invited {{ background:#854d0e; }}
    .notice {{ padding:11px 13px; border-radius:8px; background:#0c4a6e; }} .notice.error {{ background:#611c1c; }} .inviteLink {{ display:grid; gap:8px; margin-top:16px; padding:16px; border:1px solid #38bdf845; border-radius:10px; background:#071525; }} .copyRow {{ display:grid; grid-template-columns:1fr auto; gap:8px; }} small {{ color:#9fb0c7; }}
    .flow {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:16px 0 20px; }} .step {{ padding:14px; border:1px solid #ffffff14; border-radius:10px; background:#0a182a; }} .step b {{ display:block; color:#7dd3fc; margin-bottom:5px; }} .delivery {{ display:inline-flex; margin:0 0 16px; padding:7px 10px; border-radius:999px; background:#17283e; color:#b9c9dc; font-size:12px; font-weight:800; }}
    @media(max-width:720px) {{ .tableWrap {{ overflow:auto; }} table {{ min-width:720px; }} header {{ align-items:flex-start; flex-direction:column; }} .flow {{ grid-template-columns:1fr 1fr; }} .copyRow {{ grid-template-columns:1fr; }} }}
  </style>
</head><body><main>
  <header><div><div class="brand">SIGNAL</div><h1>利用者管理</h1><div>{html.escape(member)}</div></div><a href="{app_landing_path(app_mode)}">サービスへ戻る</a></header>
  <section><h2>招待から利用開始まで</h2>
    <div class="flow"><div class="step"><b>1. メール登録</b>管理者が利用者のメールアドレスを登録</div><div class="step"><b>2. 招待共有</b>メールまたは招待リンクを本人へ共有</div><div class="step"><b>3. 本人認証</b>本人が12文字以上のパスワードを設定</div><div class="step"><b>4. 利用開始</b>設定完了後、そのままSIGNALへログイン</div></div>
    <span class="delivery">{delivery_status}</span>
    <h2>利用者を招待</h2><p>招待リンクは24時間・1回限り有効です。</p>{notice}
    <form method="post" action="/admin/invite">
      <input type="hidden" name="csrf_token" value="{html.escape(csrf_token, quote=True)}" />
      <label>メールアドレス<input name="email" type="email" required placeholder="user@example.com" /></label>
      <button type="submit">招待を発行</button>
    </form>{link_panel}
  </section>
  <section><h2>登録済み利用者</h2><div class="tableWrap"><table><thead><tr><th>メールアドレス</th><th>権限</th><th>状態</th><th>更新</th><th>操作</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
  <script>async function copyInviteUrl(button) {{ const input=document.getElementById('inviteUrl'); if(!input)return; await navigator.clipboard.writeText(input.value); button.textContent='コピー済み'; setTimeout(()=>button.textContent='コピー',1600); }}</script>
</main></body></html>"""


def format_admin_date(value):
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(JST)
        return parsed.strftime("%Y/%m/%d %H:%M")
    except ValueError:
        return value


def request_base_url(handler):
    forwarded_proto = handler.headers.get("X-Forwarded-Proto", "")
    scheme = forwarded_proto.split(",", 1)[0].strip() or ("http" if is_local_host(handler.headers.get("Host", "")) else "https")
    host = handler.headers.get("Host", "localhost")
    return f"{scheme}://{host}"

def is_local_host(host_header):
    host = host_header.split(":", 1)[0]
    return host in {"127.0.0.1", "localhost", "::1"}


def main():
    config = load_config()
    sheets = SheetsClient(config)
    csrf_token = secrets.token_hex(32)
    server = ThreadingHTTPServer((config["HOST"], config["PORT"]), make_handler(config, sheets, csrf_token))
    print(f"Local server listening at http://{config['HOST']}:{config['PORT']}")
    server.serve_forever()


if __name__ == "__main__":
    main()
