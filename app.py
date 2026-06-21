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
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time as datetime_time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
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


def load_config():
    load_dotenv()
    config = {
        "YAHOO_CLIENT_ID": required_env("YAHOO_CLIENT_ID"),
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
        "SESSION_SECRET": os.environ.get("SESSION_SECRET") or secrets.token_hex(32),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
        "OPENAI_MODEL": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "VOICEVOX_URL": os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021"),
        "VOICEVOX_SPEAKER": int_env("VOICEVOX_SPEAKER", 24, 0, 999),
    }
    if config["HOST"] not in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
        raise RuntimeError("HOST は 127.0.0.1 / localhost / ::1 / 0.0.0.0 のいずれかにしてください。")
    if config["ALLOW_REMOTE_ACCESS"] and not config["ACCESS_PASSWORD"]:
        raise RuntimeError("公開利用時は ACCESS_PASSWORD を .env に設定してください。")
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
    if source not in {"connpass", "kokuchpro", "doorkeeper", "all"}:
        raise InputError("検索元の指定が不正です。")
    return {
        "keyword": clean_text(data.get("keyword"), "キーワード"),
        "area": clean_optional_text(data.get("area", ""), "エリア"),
        "results": min(clean_int(data.get("results", 20), 1, 100, "件数"), max_results),
        "start": clean_int(data.get("start", 1), 1, 1000, "開始位置"),
        "futureOnly": data.get("futureOnly") is not False,
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


def request_text(url, headers=None):
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
        with urllib.request.urlopen(req, timeout=30) as response:
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


def search_connpass_events(search):
    keyword = search["keyword"]
    if search["area"]:
        keyword = f"{keyword} {search['area']}"
    if search["source"] == "connpass":
        events = scrape_connpass_search(keyword, search["start"], search["results"], search["futureOnly"])
    elif search["source"] == "kokuchpro":
        events = scrape_kokuchpro_search(search["keyword"], search["area"], search["start"], search["results"], search["futureOnly"])
    elif search["source"] == "doorkeeper":
        events = scrape_doorkeeper_search(search["keyword"], search["area"], search["start"], search["results"], search["futureOnly"])
    else:
        events = merge_event_sources(
            scrape_connpass_search(keyword, search["start"], search["results"], search["futureOnly"]),
            scrape_kokuchpro_search(search["keyword"], search["area"], search["start"], search["results"], search["futureOnly"]),
            scrape_doorkeeper_search(search["keyword"], search["area"], search["start"], search["results"], search["futureOnly"]),
        )[: search["results"]]
    return {
        "total": len(events),
        "count": len(events),
        "items": events,
    }


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
    return datetime.now().astimezone().date()


def is_event_today_or_later(started_at, today):
    try:
        value = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    local_timezone = datetime.now().astimezone().tzinfo
    local_midnight = datetime.combine(today, datetime_time.min, local_timezone)
    return value.astimezone(local_timezone) >= local_midnight


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
    local_timezone = datetime.now().astimezone().tzinfo
    value = datetime(
        int(date_match.group(1)),
        int(date_match.group(2)),
        int(date_match.group(3)),
        hour,
        minute,
        tzinfo=local_timezone,
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

    class Handler(BaseHTTPRequestHandler):
        server_version = "LocalSearchSheets/1.0"

        def do_GET(self):
            if not self.security_check(hits, config):
                return
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/login":
                self.send_login_page()
                return
            if parsed.path == "/logout":
                self.handle_logout()
                return
            if parsed.path in {"/login-bg.jpg", "/login-bg.mp4"}:
                self.serve_static(parsed.path)
                return
            if not self.require_login(config):
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
            if not self.require_login(config):
                return
            if self.headers.get("x-csrf-token") != csrf_token:
                self.send_json(403, {"error": "不正なリクエストです。画面を再読み込みしてください。"})
                return
            try:
                data = self.read_json_body()
                if self.path == "/api/events/search-and-append":
                    self.handle_event_search(data)
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
            result = search_connpass_events(search)
            sheet_result = (
                append_events_to_sheet(sheets, config, result["items"])
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

        def read_json_body(self):
            length = int(self.headers.get("content-length", "0"))
            if length > 20 * 1024:
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
            member_id = (params.get("member_id") or [""])[0]
            password = (params.get("password") or [""])[0]
            expected_id = cfg["ACCESS_MEMBER_ID"] or member_id
            if secrets.compare_digest(member_id, expected_id) and secrets.compare_digest(password, cfg["ACCESS_PASSWORD"]):
                cookie = make_session_cookie(member_id or "member", cfg["SESSION_SECRET"])
                self.send_response(303)
                self.send_security_headers()
                self.send_header("Set-Cookie", f"crm_session={cookie}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400")
                self.send_header("Location", "/crm/index.html")
                self.end_headers()
                return
            self.send_login_page("会員IDまたはパスワードが違います。")

        def require_login(self, cfg):
            if not cfg["ALLOW_REMOTE_ACCESS"] and not cfg["ACCESS_PASSWORD"]:
                return True
            if valid_session_cookie(self.headers.get("Cookie", ""), cfg["SESSION_SECRET"]):
                return True
            if self.path.startswith("/api/"):
                self.send_json(401, {"error": "ログインしてください。"})
                return False
            self.send_response(303)
            self.send_security_headers()
            self.send_header("Location", "/login")
            self.end_headers()
            return False

        def send_login_page(self, error=""):
            body = login_page(error).encode("utf-8")
            self.send_response(200)
            self.send_login_security_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

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


def valid_session_cookie(cookie_header, secret):
    cookies = {}
    for part in (cookie_header or "").split(";"):
        if "=" in part:
            key, value = part.strip().split("=", 1)
            cookies[key] = value
    raw = cookies.get("crm_session", "")
    parts = raw.split(":")
    if len(parts) != 3:
        return False
    member_id, issued_at, signature = parts
    try:
        if int(time.time()) - int(issued_at) > 86400:
            return False
    except ValueError:
        return False
    payload = f"{member_id}:{issued_at}"
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def login_page(error=""):
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return """<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>会員ログイン | テレアポCRM</title>
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
      body { margin: 0; min-height: 100vh; overflow: hidden; }
      .bgVideo, .bgFallback, .shade { position: fixed; inset: 0; width: 100%; height: 100%; pointer-events: none; }
      .bgVideo { display: none; object-fit: cover; z-index: -3; }
      .bgFallback { z-index: -4; background: url('/login-bg.jpg') center / cover no-repeat; transform: scale(1.04); animation: loginDrift 16s ease-in-out infinite alternate; }
      .shade { z-index: -2; background: radial-gradient(circle at 50% 45%, rgb(56 189 248 / 12%), transparent 34%), linear-gradient(90deg, rgb(3 7 18 / 72%), rgb(3 7 18 / 38%), rgb(3 7 18 / 72%)); }
      :root[data-theme="light"] .shade { background: radial-gradient(circle at 50% 45%, rgb(56 189 248 / 16%), transparent 34%), linear-gradient(90deg, rgb(246 248 251 / 62%), rgb(246 248 251 / 30%), rgb(246 248 251 / 66%)); }
      @keyframes loginDrift { from { transform: scale(1.04) translate3d(-8px, -6px, 0); } to { transform: scale(1.09) translate3d(10px, 8px, 0); } }
      main { min-height: 100vh; display: grid; place-items: center; padding: 20px; }
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
            <p class="eyebrow">Teleapo Command CRM</p>
            <h1 id="loginTitle">会員ログイン</h1>
          </div>
          <button id="modeToggle" class="modeToggle" type="button">ライト</button>
        </div>
        <p>会員IDとパスワードを入力して、CRMと検索システムに入ります。</p>
        """ + error_html + """
        <form method="post" action="/login">
          <label>会員ID<input name="member_id" autocomplete="username" required autofocus /></label>
          <label>パスワード<input name="password" type="password" autocomplete="current-password" required /></label>
          <button type="submit">ログイン</button>
        </form>
        <div class="hintRow" aria-label="機能">
          <span class="chip">CRM</span>
          <span class="chip">店舗検索</span>
          <span class="chip">架電メモ</span>
        </div>
      </section>
    </main>
  </body>
</html>"""

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
