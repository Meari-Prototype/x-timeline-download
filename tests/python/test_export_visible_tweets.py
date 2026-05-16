import csv
import json
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts.export_visible_tweets as export_visible_tweets  # noqa: E402
from scripts.export_visible_tweets import (  # noqa: E402
    build_visible_records,
    write_exports,
)


TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".tmp-tests"
TEST_TMP_ROOT.mkdir(exist_ok=True)


@contextmanager
def temporary_capture_dir():
    path = TEST_TMP_ROOT / f"case-{uuid.uuid4().hex}"
    (path / "raw").mkdir(parents=True)
    (path / "tweets").mkdir()
    (path / "images").mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def append_raw(path, record):
    raw_path = path / "raw" / "2026-05-01.ndjson"
    with raw_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")


class VisibleTweetExportTest(unittest.TestCase):
    def test_extracts_web_visible_fields_from_raw_tweet_payload(self):
        with temporary_capture_dir() as captures:
            image_dir = captures / "images" / "123"
            image_dir.mkdir()
            (image_dir / "local.jpg").write_bytes(b"image")
            append_raw(
                captures,
                {
                    "url": "https://x.com/i/api/graphql/test/TweetDetail",
                    "received_at": "2026-05-01T12:31:00+00:00",
                    "body": {
                        "data": {
                            "tweet_results": {
                                "result": {
                                    "__typename": "Tweet",
                                    "rest_id": "123",
                                    "core": {
                                        "user_results": {
                                            "result": {
                                                "__typename": "User",
                                                "rest_id": "7",
                                                "core": {
                                                    "name": "QingYue",
                                                    "screen_name": "YuLin807",
                                                },
                                            },
                                        },
                                    },
                                    "legacy": {
                                        "full_text": "超市的西瓜🍉2.99元/斤\n路边摊却4块钱",
                                        "created_at": "Fri May 01 12:24:00 +0000 2026",
                                        "conversation_id_str": "99",
                                        "in_reply_to_status_id_str": "98",
                                        "in_reply_to_user_id_str": "6",
                                        "in_reply_to_screen_name": "PandaCheck38",
                                        "reply_count": 1,
                                        "retweet_count": 2,
                                        "favorite_count": 3,
                                        "quote_count": 4,
                                        "bookmark_count": 5,
                                        "extended_entities": {
                                            "media": [
                                                {
                                                    "type": "photo",
                                                    "media_url_https": "https://pbs.twimg.com/media/abc.jpg",
                                                    "expanded_url": "https://x.com/YuLin807/status/123/photo/1",
                                                }
                                            ]
                                        },
                                    },
                                    "views": {"count": "184", "state": "EnabledWithCount"},
                                }
                            }
                        }
                    },
                },
            )

            records, summary = build_visible_records(captures, timezone_name="Asia/Tokyo")

            self.assertEqual(summary["records"], 1)
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["tweet_id"], "123")
            self.assertEqual(record["author_id"], "7")
            self.assertEqual(record["author_screen_name"], "YuLin807")
            self.assertEqual(record["author_name"], "QingYue")
            self.assertEqual(record["content"], "超市的西瓜🍉2.99元/斤\n路边摊却4块钱")
            self.assertEqual(record["created_at_iso"], "2026-05-01T21:24:00+09:00")
            self.assertEqual(record["display_time"], "下午9:24 · 2026年5月1日")
            self.assertEqual(record["reply_to_tweet_id"], "98")
            self.assertEqual(record["reply_to_screen_name"], "PandaCheck38")
            self.assertEqual(record["reply_time"], "下午9:24 · 2026年5月1日")
            self.assertEqual(record["view_count"], "184")
            self.assertEqual(record["reply_count"], 1)
            self.assertEqual(record["retweet_count"], 2)
            self.assertEqual(record["like_count"], 3)
            self.assertEqual(record["quote_count"], 4)
            self.assertEqual(record["bookmark_count"], 5)
            self.assertEqual(record["media_urls"], ["https://pbs.twimg.com/media/abc.jpg"])
            self.assertEqual(record["local_image_paths"], ["images/123/local.jpg"])

    def test_uses_tweet_json_fallback_and_skips_user_pollution(self):
        with temporary_capture_dir() as captures:
            (captures / "tweets" / "456.json").write_text(
                json.dumps(
                    {
                        "id": "456",
                        "rawTypename": "Tweet",
                        "author": {
                            "id": "8",
                            "screenName": "PandaCheck38",
                            "name": "Panda Check",
                        },
                        "createdAt": "Fri May 01 12:10:00 +0000 2026",
                        "text": "差点看成路边摊却4毛钱😂",
                        "mediaImages": [],
                        "saved_at": "2026-05-01T12:30:00+00:00",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (captures / "tweets" / "8.json").write_text(
                json.dumps(
                    {
                        "id": "8",
                        "rawTypename": "User",
                        "text": "",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            records, summary = build_visible_records(captures, timezone_name="Asia/Tokyo")

            self.assertEqual([record["tweet_id"] for record in records], ["456"])
            self.assertEqual(summary["skipped_user_json"], 1)
            self.assertEqual(records[0]["source"], "tweet_json")
            self.assertEqual(records[0]["display_time"], "下午9:10 · 2026年5月1日")

    def test_writes_html_csv_jsonl_and_summary(self):
        with temporary_capture_dir() as captures:
            records = [
                {
                    "tweet_id": "123",
                    "author_id": "7",
                    "author_screen_name": "YuLin807",
                    "author_name": "Qing<Yue>",
                    "created_at_iso": "2026-05-01T21:24:00+09:00",
                    "created_at_raw": "Fri May 01 12:24:00 +0000 2026",
                    "display_time": "下午9:24 · 2026年5月1日",
                    "content": "A&B\n第二行",
                    "conversation_id": "123",
                    "reply_to_tweet_id": "",
                    "reply_to_user_id": "",
                    "reply_to_screen_name": "",
                    "reply_time": "",
                    "quote_to_tweet_id": "456",
                    "view_count": "184",
                    "reply_count": 1,
                    "retweet_count": 0,
                    "like_count": 1,
                    "quote_count": 0,
                    "bookmark_count": "",
                    "media_urls": [],
                    "local_image_paths": ["images/123/local.jpg"],
                    "source": "raw",
                    "source_url": "https://x.com/i/api/graphql/test/TweetDetail",
                    "captured_at": "2026-05-01T12:31:00+00:00",
                    "saved_at": "",
                }
            ]
            out_dir = captures / "exports" / "visible-test"

            written = write_exports(records, {"records": 1}, out_dir, captures)

            self.assertTrue(written["html"].exists())
            self.assertTrue(written["csv"].exists())
            self.assertTrue(written["jsonl"].exists())
            self.assertTrue(written["pure"].exists())
            self.assertTrue(written["summary"].exists())
            html = written["html"].read_text(encoding="utf-8")
            self.assertIn("Qing&lt;Yue&gt;", html)
            self.assertIn("A&amp;B", html)
            self.assertIn("images/123/local.jpg", html)
            with written["csv"].open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["tweet_id"], "123")
            self.assertEqual(rows[0]["content"], "A&B\n第二行")
            jsonl = written["jsonl"].read_text(encoding="utf-8").strip()
            self.assertEqual(json.loads(jsonl)["tweet_id"], "123")
            pure = written["pure"].read_text(encoding="utf-8")
            self.assertEqual(
                pure,
                "Qing<Yue> @YuLin807\n"
                "2026-05-01T21:24:00+09:00\n"
                "引用 456\n"
                "A&B\n"
                "第二行\n",
            )
            self.assertNotIn("tweet_id", pure)
            self.assertNotIn("184", pure)

    def test_falls_back_to_fixed_tokyo_timezone_when_zoneinfo_data_is_missing(self):
        original_zoneinfo = export_visible_tweets.ZoneInfo

        def missing_zoneinfo(_key):
            raise ZoneInfoNotFoundError("No time zone found")

        export_visible_tweets.ZoneInfo = missing_zoneinfo
        try:
            tz = export_visible_tweets._load_timezone("Asia/Tokyo")
        finally:
            export_visible_tweets.ZoneInfo = original_zoneinfo

        self.assertEqual(tz.utcoffset(None), timedelta(hours=9))


if __name__ == "__main__":
    unittest.main()
