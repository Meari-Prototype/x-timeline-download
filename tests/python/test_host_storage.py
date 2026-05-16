import base64
import io
import json
import sys
import unittest
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "native_host"))

from x_capture_host import (  # noqa: E402
    NativeHostStorage,
    decode_message,
    encode_message,
    handle_message,
)


FIXED_NOW = datetime(2026, 5, 1, 12, 30, tzinfo=timezone.utc)
TEST_TMP_ROOT = Path(__file__).resolve().parents[2] / ".tmp-tests"
TEST_TMP_ROOT.mkdir(exist_ok=True)


@contextmanager
def temporary_capture_dir():
    path = TEST_TMP_ROOT / f"case-{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


class NativeHostStorageTest(unittest.TestCase):
    def test_native_message_framing_round_trips_json(self):
        encoded = encode_message({"type": "ping", "value": 1})

        decoded = decode_message(io.BytesIO(encoded))

        self.assertEqual(decoded, {"type": "ping", "value": 1})

    def test_creates_capture_subdirectories(self):
        with temporary_capture_dir() as tmp:
            storage = NativeHostStorage(Path(tmp))

            self.assertTrue((Path(tmp) / "raw").is_dir())
            self.assertTrue((Path(tmp) / "tweets").is_dir())
            self.assertTrue((Path(tmp) / "images").is_dir())
            self.assertTrue((Path(tmp) / "errors").is_dir())
            self.assertIs(storage.base_dir, storage.base_dir)

    def test_appends_raw_json_to_daily_ndjson(self):
        with temporary_capture_dir() as tmp:
            storage = NativeHostStorage(Path(tmp))

            result = storage.save_raw_json(
                {
                    "url": "https://x.com/i/api/graphql/HomeTimeline",
                    "body": {"data": {"ok": True}},
                },
                now=FIXED_NOW,
            )

            self.assertTrue(result["ok"])
            raw_path = Path(tmp) / "raw" / "2026-05-01.ndjson"
            line = raw_path.read_text(encoding="utf-8").strip()
            saved = json.loads(line)
            self.assertEqual(saved["received_at"], "2026-05-01T12:30:00+00:00")
            self.assertEqual(saved["body"], {"data": {"ok": True}})

    def test_writes_tweet_json_by_tweet_id(self):
        with temporary_capture_dir() as tmp:
            storage = NativeHostStorage(Path(tmp))

            result = storage.save_tweet_json(
                {"id": "123", "text": "hello", "mediaImages": []},
                now=FIXED_NOW,
            )

            self.assertTrue(result["ok"])
            saved = json.loads((Path(tmp) / "tweets" / "123.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["id"], "123")
            self.assertEqual(saved["saved_at"], "2026-05-01T12:30:00+00:00")

    def test_writes_image_under_first_tweet_id_and_skips_duplicates(self):
        with temporary_capture_dir() as tmp:
            storage = NativeHostStorage(Path(tmp))
            image_body = base64.b64encode(b"image bytes").decode("ascii")
            message = {
                "url": "https://pbs.twimg.com/media/Gabc123?format=jpg&name=large",
                "mimeType": "image/jpeg",
                "bodyBase64": image_body,
                "tweetIds": ["123", "456"],
            }

            first = storage.save_image(message, now=FIXED_NOW)
            second = storage.save_image(message, now=FIXED_NOW)

            self.assertTrue(first["ok"])
            self.assertFalse(first["skipped"])
            self.assertTrue(second["ok"])
            self.assertTrue(second["skipped"])
            image_path = Path(first["path"])
            self.assertEqual(image_path.parent.name, "123")
            self.assertEqual(image_path.suffix, ".jpg")
            self.assertEqual(image_path.read_bytes(), b"image bytes")

    def test_appends_errors_to_daily_ndjson(self):
        with temporary_capture_dir() as tmp:
            storage = NativeHostStorage(Path(tmp))

            result = storage.save_error({"stage": "body", "message": "unavailable"}, now=FIXED_NOW)

            self.assertTrue(result["ok"])
            saved = json.loads((Path(tmp) / "errors" / "2026-05-01.ndjson").read_text(encoding="utf-8"))
            self.assertEqual(saved["stage"], "body")
            self.assertEqual(saved["recorded_at"], "2026-05-01T12:30:00+00:00")

    def test_session_lifecycle_routes_records_and_lists_manifest(self):
        with temporary_capture_dir() as tmp:
            storage = NativeHostStorage(Path(tmp))

            created = storage.create_session(
                {"tabUrl": "https://x.com/home", "tabTitle": "Home"},
                now=FIXED_NOW,
            )
            session_id = created["session"]["id"]
            storage.save_raw_json(
                {"url": "https://x.com/i/api/graphql/HomeTimeline", "body": {"ok": True}},
                session_id=session_id,
                now=FIXED_NOW,
            )
            storage.save_tweet_json(
                {"id": "123", "text": "hello", "mediaImages": []},
                session_id=session_id,
                now=FIXED_NOW,
            )
            closed = storage.close_session(
                session_id,
                counters={"rawJson": 1, "tweets": 1, "images": 0, "errors": 0},
                now=FIXED_NOW,
            )

            self.assertTrue(created["ok"])
            self.assertTrue(closed["ok"])
            session_dir = Path(tmp) / "sessions" / session_id
            self.assertTrue((session_dir / "raw" / "2026-05-01.ndjson").is_file())
            self.assertTrue((session_dir / "tweets" / "123.json").is_file())
            listed = storage.list_sessions()
            self.assertEqual(len(listed["sessions"]), 1)
            self.assertEqual(listed["sessions"][0]["id"], session_id)
            self.assertEqual(listed["sessions"][0]["status"], "closed")
            self.assertEqual(listed["sessions"][0]["counters"]["tweets"], 1)

    def test_close_session_writes_visible_export_files(self):
        with temporary_capture_dir() as tmp:
            storage = NativeHostStorage(Path(tmp))
            session_id = storage.create_session({"tabUrl": "https://x.com/home"}, now=FIXED_NOW)[
                "session"
            ]["id"]
            storage.save_tweet_json(
                {
                    "id": "123",
                    "rawTypename": "Tweet",
                    "author": {"id": "7", "screenName": "YuLin807", "name": "QingYue"},
                    "createdAt": "Fri May 01 12:24:00 +0000 2026",
                    "text": "hello",
                    "mediaImages": [],
                },
                session_id=session_id,
                now=FIXED_NOW,
            )

            closed = storage.close_session(
                session_id,
                counters={"rawJson": 0, "tweets": 1, "images": 0, "errors": 0},
                now=FIXED_NOW,
            )

            session_dir = Path(tmp) / "sessions" / session_id
            self.assertTrue((session_dir / "visible_tweets.html").is_file())
            self.assertTrue((session_dir / "visible_tweets.csv").is_file())
            self.assertTrue((session_dir / "visible_tweets.jsonl").is_file())
            self.assertTrue((session_dir / "visible_tweets_pure.txt").is_file())
            self.assertTrue((session_dir / "summary.json").is_file())
            self.assertTrue(closed["session"]["export"]["ok"])
            self.assertEqual(closed["session"]["export"]["records"], 1)

    def test_delete_session_only_removes_session_directory(self):
        with temporary_capture_dir() as tmp:
            storage = NativeHostStorage(Path(tmp))
            session_id = storage.create_session({"tabUrl": "https://x.com/home"}, now=FIXED_NOW)[
                "session"
            ]["id"]
            legacy_raw = Path(tmp) / "raw" / "2026-05-01.ndjson"
            legacy_raw.write_text('{"keep":true}\n', encoding="utf-8")

            deleted = storage.delete_session(session_id)

            self.assertTrue(deleted["ok"])
            self.assertFalse((Path(tmp) / "sessions" / session_id).exists())
            self.assertTrue(legacy_raw.exists())
            with self.assertRaises(ValueError):
                storage.delete_session("../raw")

    def test_open_session_directory_invokes_opener_after_path_validation(self):
        with temporary_capture_dir() as tmp:
            storage = NativeHostStorage(Path(tmp))
            session_id = storage.create_session({"tabUrl": "https://x.com/home"}, now=FIXED_NOW)[
                "session"
            ]["id"]
            opened = []

            result = storage.open_session_directory(session_id, opener=lambda path: opened.append(path))

            self.assertTrue(result["ok"])
            self.assertEqual(opened, [Path(tmp) / "sessions" / session_id])
            self.assertTrue((Path(tmp) / "sessions" / session_id / "visible_tweets.html").is_file())
            self.assertEqual(result["path"], str(Path(tmp) / "sessions" / session_id))
            with self.assertRaises(ValueError):
                storage.open_session_directory("../raw", opener=lambda path: opened.append(path))

    def test_generate_session_export_message_writes_visible_files(self):
        with temporary_capture_dir() as tmp:
            storage = NativeHostStorage(Path(tmp))
            session_id = storage.create_session({"tabUrl": "https://x.com/home"}, now=FIXED_NOW)[
                "session"
            ]["id"]
            storage.save_tweet_json(
                {
                    "id": "123",
                    "rawTypename": "Tweet",
                    "author": {"id": "7", "screenName": "YuLin807", "name": "QingYue"},
                    "createdAt": "Fri May 01 12:24:00 +0000 2026",
                    "text": "hello",
                    "mediaImages": [],
                },
                session_id=session_id,
                now=FIXED_NOW,
            )

            result = handle_message(
                storage,
                {"type": "generate_session_export", "sessionId": session_id},
            )

            session_dir = Path(tmp) / "sessions" / session_id
            self.assertTrue(result["ok"])
            self.assertEqual(result["export"]["records"], 1)
            self.assertTrue((session_dir / "visible_tweets.html").is_file())
            manifest = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["export"]["records"], 1)

    def test_generate_pure_export_message_returns_pure_text_path(self):
        with temporary_capture_dir() as tmp:
            storage = NativeHostStorage(Path(tmp))
            session_id = storage.create_session({"tabUrl": "https://x.com/home"}, now=FIXED_NOW)[
                "session"
            ]["id"]
            storage.save_tweet_json(
                {
                    "id": "123",
                    "rawTypename": "Tweet",
                    "author": {"id": "7", "screenName": "YuLin807", "name": "QingYue"},
                    "createdAt": "Fri May 01 12:24:00 +0000 2026",
                    "text": "hello",
                    "mediaImages": [],
                },
                session_id=session_id,
                now=FIXED_NOW,
            )

            result = handle_message(storage, {"type": "generate_pure_export", "sessionId": session_id})

            pure_path = Path(tmp) / "sessions" / session_id / "visible_tweets_pure.txt"
            self.assertTrue(result["ok"])
            self.assertEqual(result["pure"], str(pure_path))
            self.assertTrue(pure_path.is_file())

    def test_handle_message_exposes_session_management(self):
        with temporary_capture_dir() as tmp:
            storage = NativeHostStorage(Path(tmp))

            created = handle_message(
                storage,
                {"type": "create_session", "tabUrl": "https://x.com/home", "tabTitle": "Home"},
            )
            session_id = created["session"]["id"]
            listed = handle_message(storage, {"type": "list_sessions"})
            deleted = handle_message(storage, {"type": "delete_session", "sessionId": session_id})

            self.assertTrue(created["ok"])
            self.assertEqual(listed["sessions"][0]["id"], session_id)
            self.assertTrue(deleted["ok"])


if __name__ == "__main__":
    unittest.main()
