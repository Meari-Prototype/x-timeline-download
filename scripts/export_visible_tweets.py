import argparse
import csv
import html
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


CSV_FIELDS = [
    "author_id",
    "author_screen_name",
    "author_name",
    "created_at_iso",
    "display_time",
    "tweet_id",
    "content",
    "conversation_id",
    "reply_to_tweet_id",
    "reply_to_user_id",
    "reply_to_screen_name",
    "reply_time",
    "quote_to_tweet_id",
    "view_count",
    "reply_count",
    "retweet_count",
    "like_count",
    "quote_count",
    "bookmark_count",
    "media_urls",
    "local_image_paths",
    "source",
    "source_url",
    "captured_at",
    "saved_at",
]

MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

FIXED_TIMEZONES = {
    "Asia/Tokyo": timezone(timedelta(hours=9), "Asia/Tokyo"),
}


def build_visible_records(captures_dir, timezone_name=None, sort_order="desc"):
    captures_dir = Path(captures_dir)
    tz = _load_timezone(timezone_name)
    records_by_id = {}
    summary = {
        "raw_lines": 0,
        "raw_parse_errors": 0,
        "raw_tweets": 0,
        "tweet_json_files": 0,
        "skipped_user_json": 0,
        "tweet_json_parse_errors": 0,
        "missing_author": 0,
        "missing_time": 0,
        "missing_content": 0,
        "records": 0,
    }

    for raw_path in sorted((captures_dir / "raw").glob("*.ndjson")):
        with raw_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                summary["raw_lines"] += 1
                try:
                    raw_record = json.loads(line)
                except json.JSONDecodeError:
                    summary["raw_parse_errors"] += 1
                    continue
                for tweet in iter_tweet_objects(raw_record.get("body")):
                    summary["raw_tweets"] += 1
                    record = record_from_raw_tweet(tweet, raw_record, captures_dir, tz)
                    _merge_record(records_by_id, record)

    for tweet_path in sorted((captures_dir / "tweets").glob("*.json")):
        summary["tweet_json_files"] += 1
        try:
            tweet = json.loads(tweet_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary["tweet_json_parse_errors"] += 1
            continue
        if tweet.get("rawTypename") == "User":
            summary["skipped_user_json"] += 1
            continue
        record = record_from_saved_tweet(tweet, captures_dir, tz)
        if record["tweet_id"]:
            _merge_record(records_by_id, record)

    records = list(records_by_id.values())
    for record in records:
        if not record["author_id"] and not record["author_screen_name"] and not record["author_name"]:
            summary["missing_author"] += 1
        if not record["created_at_iso"]:
            summary["missing_time"] += 1
        if not record["content"]:
            summary["missing_content"] += 1

    reverse = sort_order != "asc"
    records.sort(key=_sort_key, reverse=reverse)
    summary["records"] = len(records)
    return records, summary


def iter_tweet_objects(value):
    visited = set()

    def walk(item):
        if item is None:
            return
        if isinstance(item, (dict, list)):
            marker = id(item)
            if marker in visited:
                return
            visited.add(marker)

        if isinstance(item, dict):
            if item.get("__typename") == "Tweet" and isinstance(item.get("rest_id"), str):
                yield item
            for child in item.values():
                yield from walk(child)
        elif isinstance(item, list):
            for child in item:
                yield from walk(child)

    yield from walk(value)


def record_from_raw_tweet(tweet, raw_record, captures_dir, tz):
    legacy = tweet.get("legacy") or {}
    author = _extract_author(tweet.get("core", {}).get("user_results", {}).get("result"))
    created = parse_x_created_at(legacy.get("created_at"), tz)
    tweet_id = str(tweet.get("rest_id") or legacy.get("id_str") or "")
    media_urls = _extract_media_urls(tweet)
    local_image_paths = _find_local_images(captures_dir, tweet_id)

    return _record(
        tweet_id=tweet_id,
        author_id=author["id"],
        author_screen_name=author["screen_name"],
        author_name=author["name"],
        created_at_raw=legacy.get("created_at") or "",
        created=created,
        content=_tweet_text(tweet),
        conversation_id=legacy.get("conversation_id_str") or "",
        reply_to_tweet_id=legacy.get("in_reply_to_status_id_str") or "",
        reply_to_user_id=legacy.get("in_reply_to_user_id_str") or "",
        reply_to_screen_name=legacy.get("in_reply_to_screen_name") or "",
        quote_to_tweet_id=legacy.get("quoted_status_id_str") or "",
        view_count=str((tweet.get("views") or {}).get("count") or ""),
        reply_count=legacy.get("reply_count", ""),
        retweet_count=legacy.get("retweet_count", ""),
        like_count=legacy.get("favorite_count", ""),
        quote_count=legacy.get("quote_count", ""),
        bookmark_count=legacy.get("bookmark_count", ""),
        media_urls=media_urls,
        local_image_paths=local_image_paths,
        source="raw",
        source_url=raw_record.get("url") or "",
        captured_at=raw_record.get("received_at") or "",
        saved_at="",
    )


def record_from_saved_tweet(tweet, captures_dir, tz):
    author = tweet.get("author") or {}
    created = parse_x_created_at(tweet.get("createdAt"), tz)
    tweet_id = str(tweet.get("id") or "")
    media_urls = [
        item.get("url")
        for item in tweet.get("mediaImages", [])
        if isinstance(item, dict) and item.get("url")
    ]
    return _record(
        tweet_id=tweet_id,
        author_id=author.get("id") or "",
        author_screen_name=author.get("screenName") or "",
        author_name=author.get("name") or "",
        created_at_raw=tweet.get("createdAt") or "",
        created=created,
        content=tweet.get("text") or "",
        conversation_id="",
        reply_to_tweet_id="",
        reply_to_user_id="",
        reply_to_screen_name="",
        quote_to_tweet_id="",
        view_count="",
        reply_count="",
        retweet_count="",
        like_count="",
        quote_count="",
        bookmark_count="",
        media_urls=media_urls,
        local_image_paths=_find_local_images(captures_dir, tweet_id),
        source="tweet_json",
        source_url="",
        captured_at="",
        saved_at=tweet.get("saved_at") or "",
    )


def parse_x_created_at(value, tz):
    if not value:
        return None
    parts = str(value).split()
    if len(parts) != 6 or parts[1] not in MONTHS:
        return None
    hour, minute, second = [int(part) for part in parts[3].split(":")]
    offset = _parse_offset(parts[4])
    created = datetime(
        int(parts[5]),
        MONTHS[parts[1]],
        int(parts[2]),
        hour,
        minute,
        second,
        tzinfo=offset,
    )
    return created.astimezone(tz)


def display_time(value):
    if value is None:
        return ""
    label = "上午" if value.hour < 12 else "下午"
    hour = value.hour % 12 or 12
    return f"{label}{hour}:{value.minute:02d} · {value.year}年{value.month}月{value.day}日"


def write_exports(records, summary, out_dir, captures_dir):
    out_dir = Path(out_dir)
    captures_dir = Path(captures_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = out_dir / "visible_tweets.jsonl"
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")

    csv_path = out_dir / "visible_tweets.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(_csv_record(record))

    html_path = out_dir / "visible_tweets.html"
    html_path.write_text(_render_html(records, out_dir, captures_dir), encoding="utf-8")

    pure_path = out_dir / "visible_tweets_pure.txt"
    pure_path.write_text(_render_pure_text(records), encoding="utf-8", newline="\n")

    summary_path = out_dir / "summary.json"
    output_summary = dict(summary)
    output_summary["records"] = len(records)
    summary_path.write_text(
        json.dumps(output_summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return {
        "jsonl": jsonl_path,
        "csv": csv_path,
        "html": html_path,
        "pure": pure_path,
        "summary": summary_path,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export captured X tweets as visible HTML/CSV/JSONL.")
    parser.add_argument("--captures", default=str(_default_captures_dir()))
    parser.add_argument("--out", default="")
    parser.add_argument("--timezone", default="")
    parser.add_argument("--sort", choices=["asc", "desc"], default="desc")
    args = parser.parse_args(argv)

    captures_dir = Path(args.captures)
    if not captures_dir.exists():
        raise SystemExit(f"captures directory not found: {captures_dir}")
    if not (captures_dir / "raw").exists() and not (captures_dir / "tweets").exists():
        raise SystemExit(f"raw/ or tweets/ directory not found under: {captures_dir}")

    records, summary = build_visible_records(captures_dir, args.timezone or None, args.sort)
    out_dir = Path(args.out) if args.out else _default_output_dir(captures_dir)
    written = write_exports(records, summary, out_dir, captures_dir)
    print(f"records: {len(records)}")
    print(f"html: {written['html']}")
    print(f"csv: {written['csv']}")
    print(f"jsonl: {written['jsonl']}")
    print(f"summary: {written['summary']}")


def _record(
    *,
    tweet_id,
    author_id,
    author_screen_name,
    author_name,
    created_at_raw,
    created,
    content,
    conversation_id,
    reply_to_tweet_id,
    reply_to_user_id,
    reply_to_screen_name,
    quote_to_tweet_id,
    view_count,
    reply_count,
    retweet_count,
    like_count,
    quote_count,
    bookmark_count,
    media_urls,
    local_image_paths,
    source,
    source_url,
    captured_at,
    saved_at,
):
    created_iso = created.isoformat() if created else ""
    shown_time = display_time(created)
    is_reply = bool(reply_to_tweet_id or reply_to_user_id or reply_to_screen_name)
    return {
        "author_id": author_id or "",
        "author_screen_name": author_screen_name or "",
        "author_name": author_name or "",
        "created_at_iso": created_iso,
        "created_at_raw": created_at_raw or "",
        "display_time": shown_time,
        "tweet_id": tweet_id or "",
        "content": content or "",
        "conversation_id": conversation_id or "",
        "reply_to_tweet_id": reply_to_tweet_id or "",
        "reply_to_user_id": reply_to_user_id or "",
        "reply_to_screen_name": reply_to_screen_name or "",
        "reply_time": shown_time if is_reply else "",
        "quote_to_tweet_id": quote_to_tweet_id or "",
        "view_count": view_count,
        "reply_count": reply_count,
        "retweet_count": retweet_count,
        "like_count": like_count,
        "quote_count": quote_count,
        "bookmark_count": bookmark_count,
        "media_urls": media_urls,
        "local_image_paths": local_image_paths,
        "source": source,
        "source_url": source_url or "",
        "captured_at": captured_at or "",
        "saved_at": saved_at or "",
    }


def _extract_author(user):
    if not isinstance(user, dict):
        return {"id": "", "screen_name": "", "name": ""}
    legacy = user.get("legacy") or {}
    core = user.get("core") or {}
    return {
        "id": str(user.get("rest_id") or user.get("id_str") or ""),
        "screen_name": legacy.get("screen_name") or core.get("screen_name") or user.get("screen_name") or "",
        "name": legacy.get("name") or core.get("name") or user.get("name") or "",
    }


def _tweet_text(tweet):
    note_text = (
        ((tweet.get("note_tweet") or {}).get("note_tweet_results") or {})
        .get("result", {})
        .get("text")
    )
    if isinstance(note_text, str):
        return note_text
    return (tweet.get("legacy") or {}).get("full_text") or ""


def _extract_media_urls(tweet):
    legacy = tweet.get("legacy") or {}
    media_items = []
    media_items.extend(((legacy.get("extended_entities") or {}).get("media") or []))
    media_items.extend(((legacy.get("entities") or {}).get("media") or []))
    seen = set()
    urls = []
    for item in media_items:
        if not isinstance(item, dict) or item.get("type") != "photo":
            continue
        url = item.get("media_url_https") or item.get("media_url")
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _find_local_images(captures_dir, tweet_id):
    if not tweet_id:
        return []
    image_dir = Path(captures_dir) / "images" / str(tweet_id)
    if not image_dir.exists():
        return []
    paths = []
    for path in sorted(image_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif"}:
            paths.append(path.relative_to(captures_dir).as_posix())
    return paths


def _merge_record(records_by_id, record):
    tweet_id = record.get("tweet_id")
    if not tweet_id:
        return
    current = records_by_id.get(tweet_id)
    if current is None:
        records_by_id[tweet_id] = record
        return
    for key, value in record.items():
        if key in {"media_urls", "local_image_paths"}:
            current[key] = _merge_lists(current.get(key, []), value)
        elif _is_empty(current.get(key)) and not _is_empty(value):
            current[key] = value
        elif current.get("source") == "tweet_json" and record.get("source") == "raw" and not _is_empty(value):
            current[key] = value


def _merge_lists(left, right):
    out = []
    seen = set()
    for item in [*(left or []), *(right or [])]:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _sort_key(record):
    return (
        record.get("created_at_iso") or "",
        _numeric_sort_value(record.get("tweet_id")),
    )


def _numeric_sort_value(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _csv_record(record):
    row = {}
    for field in CSV_FIELDS:
        value = record.get(field, "")
        if isinstance(value, list):
            value = ";".join(str(item) for item in value)
        row[field] = value
    return row


def _render_html(records, out_dir, captures_dir):
    cards = "\n".join(_render_card(record, out_dir, captures_dir) for record in records)
    return f"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>X visible export</title>
  <style>
    body {{ margin: 0; background: #f7f9f9; color: #0f1419; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 720px; margin: 0 auto; background: #fff; min-height: 100vh; border-left: 1px solid #eff3f4; border-right: 1px solid #eff3f4; }}
    header {{ position: sticky; top: 0; background: rgba(255,255,255,.94); backdrop-filter: blur(8px); padding: 14px 18px; border-bottom: 1px solid #eff3f4; font-weight: 800; font-size: 20px; }}
    article {{ padding: 16px 18px; border-bottom: 1px solid #eff3f4; }}
    .byline {{ display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }}
    .name {{ font-weight: 800; }}
    .handle, .meta, .reply {{ color: #536471; }}
    .content {{ white-space: pre-wrap; font-size: 17px; line-height: 1.45; margin: 12px 0; }}
    .counts {{ display: flex; gap: 18px; color: #536471; font-size: 14px; flex-wrap: wrap; }}
    .media {{ display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); margin-top: 12px; }}
    .media a {{ color: #536471; text-decoration: none; font-size: 12px; }}
    .media img {{ width: 100%; max-height: 260px; object-fit: cover; border-radius: 8px; border: 1px solid #cfd9de; display: block; }}
    .idline {{ color: #536471; font-size: 12px; margin-top: 10px; overflow-wrap: anywhere; }}
  </style>
</head>
<body>
<main>
  <header>帖子</header>
  {cards}
</main>
</body>
</html>
"""


def _render_card(record, out_dir, captures_dir):
    display_name = record.get("author_name") or record.get("author_screen_name") or record.get("author_id") or "Unknown author"
    handle = f"@{record.get('author_screen_name')}" if record.get("author_screen_name") else record.get("author_id", "")
    reply = ""
    if record.get("reply_to_tweet_id") or record.get("reply_to_screen_name"):
        target = record.get("reply_to_screen_name") or record.get("reply_to_user_id") or record.get("reply_to_tweet_id")
        reply = f'<div class="reply">回复 {html.escape(str(target))} · {html.escape(record.get("reply_time", ""))}</div>'
    media = _render_media(record, out_dir, captures_dir)
    counts = _render_counts(record)
    return f"""<article>
  <div class="byline"><span class="name">{html.escape(str(display_name))}</span><span class="handle">{html.escape(str(handle))}</span></div>
  <div class="meta">{html.escape(record.get("display_time", ""))}</div>
  {reply}
  <div class="content">{html.escape(record.get("content", ""))}</div>
  {counts}
  {media}
  <div class="idline">tweet_id: {html.escape(record.get("tweet_id", ""))}</div>
</article>"""


def _render_counts(record):
    pairs = [
        ("回复", record.get("reply_count")),
        ("转发", record.get("retweet_count")),
        ("喜欢", record.get("like_count")),
        ("引用", record.get("quote_count")),
        ("查看", record.get("view_count")),
    ]
    items = [
        f"<span>{html.escape(label)} {html.escape(str(value))}</span>"
        for label, value in pairs
        if not _is_empty(value)
    ]
    return f'<div class="counts">{"".join(items)}</div>' if items else ""


def _render_pure_text(records):
    blocks = [_render_pure_record(record) for record in records]
    blocks = [block for block in blocks if block]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _render_pure_record(record):
    speaker = _pure_speaker(record)
    time_value = record.get("created_at_iso") or record.get("display_time") or ""
    relation = _pure_relation(record)
    content = _clean_pure_text(record.get("content", ""))

    lines = [item for item in (speaker, time_value, relation, content) if item]
    return "\n".join(lines)


def _pure_speaker(record):
    name = _clean_pure_text(record.get("author_name", ""))
    screen_name = _clean_pure_text(record.get("author_screen_name", ""))
    author_id = _clean_pure_text(record.get("author_id", ""))
    if name and screen_name:
        return f"{name} @{screen_name}"
    if name:
        return name
    if screen_name:
        return f"@{screen_name}"
    return author_id


def _pure_relation(record):
    quote_to = _clean_pure_text(record.get("quote_to_tweet_id", ""))
    if quote_to:
        return f"引用 {quote_to}"

    reply_to_screen_name = _clean_pure_text(record.get("reply_to_screen_name", ""))
    reply_to_tweet_id = _clean_pure_text(record.get("reply_to_tweet_id", ""))
    reply_to_user_id = _clean_pure_text(record.get("reply_to_user_id", ""))
    if not (reply_to_screen_name or reply_to_tweet_id or reply_to_user_id):
        return ""

    target = f"@{reply_to_screen_name}" if reply_to_screen_name else reply_to_user_id
    if target and reply_to_tweet_id:
        return f"回复 {target} {reply_to_tweet_id}"
    return f"回复 {target or reply_to_tweet_id}"


def _clean_pure_text(value):
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _render_media(record, out_dir, captures_dir):
    links = []
    for local_path in record.get("local_image_paths", []):
        absolute = Path(captures_dir) / local_path
        href = os.path.relpath(absolute, out_dir).replace("\\", "/")
        label = html.escape(local_path)
        escaped_href = html.escape(href, quote=True)
        links.append(
            f'<a href="{escaped_href}" data-local-path="{label}"><img src="{escaped_href}" alt="{label}"><span>{label}</span></a>'
        )
    return f'<div class="media">{"".join(links)}</div>' if links else ""


def _load_timezone(timezone_name):
    if timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            if timezone_name in FIXED_TIMEZONES:
                return FIXED_TIMEZONES[timezone_name]
            raise
    return datetime.now().astimezone().tzinfo


def _parse_offset(value):
    sign = 1 if value[0] == "+" else -1
    hours = int(value[1:3])
    minutes = int(value[3:5])
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def _is_empty(value):
    return value is None or value == "" or value == []


def _default_captures_dir():
    return Path(__file__).resolve().parents[1] / "native_host" / "captures"


def _default_output_dir(captures_dir):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(captures_dir) / "exports" / f"visible-{stamp}"


if __name__ == "__main__":
    main()
