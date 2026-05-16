import base64
import hashlib
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse


HOST_NAME = "com.master.x_tweet_fetcher"


def encode_message(message):
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return struct.pack("<I", len(payload)) + payload


def decode_message(stream):
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise ValueError("Incomplete native message length header")
    length = struct.unpack("<I", header)[0]
    payload = stream.read(length)
    if len(payload) != length:
        raise ValueError("Incomplete native message payload")
    return json.loads(payload.decode("utf-8"))


class NativeHostStorage:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.raw_dir = self.base_dir / "raw"
        self.tweets_dir = self.base_dir / "tweets"
        self.images_dir = self.base_dir / "images"
        self.errors_dir = self.base_dir / "errors"
        self.sessions_dir = self.base_dir / "sessions"
        for path in (self.raw_dir, self.tweets_dir, self.images_dir, self.errors_dir, self.sessions_dir):
            path.mkdir(parents=True, exist_ok=True)

    def create_session(self, info, now=None):
        timestamp = _now(now)
        session_id = self._unique_session_id(info.get("tabUrl", ""), timestamp)
        session_dir = self._session_dir(session_id)
        for path in self._session_paths(session_id).values():
            if path.suffix:
                continue
            path.mkdir(parents=True, exist_ok=True)
        manifest = {
            "id": session_id,
            "status": "active",
            "tabUrl": info.get("tabUrl", ""),
            "tabTitle": info.get("tabTitle", ""),
            "started_at": timestamp.isoformat(),
            "updated_at": timestamp.isoformat(),
            "ended_at": None,
            "counters": _empty_counters(),
        }
        self._write_manifest(session_id, manifest)
        return {"ok": True, "session": self._session_summary(manifest, session_dir)}

    def close_session(self, session_id, counters=None, now=None):
        timestamp = _now(now)
        manifest = self._read_manifest(session_id)
        manifest["status"] = "closed"
        manifest["ended_at"] = timestamp.isoformat()
        manifest["updated_at"] = timestamp.isoformat()
        if counters:
            manifest["counters"] = _normalize_counters(counters)
        self._write_manifest(session_id, manifest)
        manifest["export"] = self.ensure_session_export(session_id, now=timestamp)
        self._write_manifest(session_id, manifest)
        return {"ok": True, "session": self._session_summary(manifest, self._session_dir(session_id))}

    def list_sessions(self):
        sessions = []
        for manifest_path in self.sessions_dir.glob("*/manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            sessions.append(self._session_summary(manifest, manifest_path.parent))
        sessions.sort(key=lambda item: item.get("started_at") or "", reverse=True)
        return {"ok": True, "sessions": sessions}

    def delete_session(self, session_id):
        session_dir = self._session_dir(session_id)
        if not session_dir.exists():
            return {"ok": True, "deleted": False, "sessionId": session_id}
        _remove_tree(session_dir)
        return {"ok": True, "deleted": True, "sessionId": session_id}

    def open_session_directory(self, session_id, opener=None):
        session_dir = self._session_dir(session_id)
        if not session_dir.is_dir():
            return {"ok": False, "error": "session directory not found", "sessionId": session_id}
        export = self.ensure_session_export(session_id)
        if not export.get("ok"):
            return {
                "ok": False,
                "error": export.get("error", "export failed"),
                "sessionId": session_id,
                "export": export,
            }
        open_directory = opener or _open_directory
        open_directory(session_dir)
        return {"ok": True, "path": str(session_dir), "sessionId": session_id, "export": export}

    def generate_session_export(self, session_id):
        session_dir = self._session_dir(session_id)
        if not session_dir.is_dir():
            return {"ok": False, "error": "session directory not found", "sessionId": session_id}
        export = self.ensure_session_export(session_id)
        if not export.get("ok"):
            return {
                "ok": False,
                "error": export.get("error", "export failed"),
                "sessionId": session_id,
                "export": export,
            }
        manifest = self._read_manifest(session_id)
        return {
            "ok": True,
            "sessionId": session_id,
            "session": self._session_summary(manifest, session_dir),
            "export": export,
        }

    def generate_pure_export(self, session_id):
        result = self.generate_session_export(session_id)
        if not result.get("ok"):
            return result
        pure_path = result.get("export", {}).get("pure", "")
        return {
            "ok": True,
            "sessionId": session_id,
            "pure": pure_path,
            "export": result.get("export"),
            "session": result.get("session"),
        }

    def ensure_session_export(self, session_id, now=None):
        timestamp = _now(now)
        try:
            export = _export_visible_session(self._session_dir(session_id), now=timestamp)
        except Exception as exc:
            export = {
                "ok": False,
                "error": str(exc),
                "generated_at": timestamp.isoformat(),
            }
        try:
            manifest = self._read_manifest(session_id)
            manifest["export"] = export
            manifest["updated_at"] = timestamp.isoformat()
            self._write_manifest(session_id, manifest)
        except Exception:
            pass
        return export

    def save_raw_json(self, record, session_id=None, now=None):
        timestamp = _now(now)
        output = dict(record)
        output["received_at"] = timestamp.isoformat()
        paths = self._session_paths(session_id) if session_id else None
        path = (paths["raw"] if paths else self.raw_dir) / f"{timestamp.date().isoformat()}.ndjson"
        _append_json_line(path, output)
        if session_id:
            self._increment_counter(session_id, "rawJson", timestamp)
        return {"ok": True, "path": str(path)}

    def save_tweet_json(self, tweet, session_id=None, now=None):
        tweet_id = _safe_name(str(tweet.get("id", "")))
        if not tweet_id:
            raise ValueError("tweet JSON is missing id")
        output = dict(tweet)
        timestamp = _now(now)
        output["saved_at"] = timestamp.isoformat()
        paths = self._session_paths(session_id) if session_id else None
        path = (paths["tweets"] if paths else self.tweets_dir) / f"{tweet_id}.json"
        path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        if session_id:
            self._increment_counter(session_id, "tweets", timestamp)
        return {"ok": True, "path": str(path)}

    def save_image(self, message, session_id=None, now=None):
        body = base64.b64decode(message["bodyBase64"])
        tweet_ids = [str(item) for item in message.get("tweetIds", []) if str(item)]
        tweet_id = _safe_name(tweet_ids[0]) if tweet_ids else "unassigned"
        paths = self._session_paths(session_id) if session_id else None
        image_root = paths["images"] if paths else self.images_dir
        image_dir = image_root / tweet_id
        image_dir.mkdir(parents=True, exist_ok=True)

        ext = _image_extension(message.get("url", ""), message.get("mimeType", ""))
        digest = hashlib.sha256((message.get("url", "") + "\n").encode("utf-8") + body).hexdigest()
        path = image_dir / f"{digest[:24]}{ext}"
        if path.exists():
            return {"ok": True, "path": str(path), "skipped": True}
        path.write_bytes(body)

        sidecar = path.with_suffix(path.suffix + ".json")
        sidecar.write_text(
            json.dumps(
                {
                    "url": message.get("url"),
                    "mimeType": message.get("mimeType"),
                    "tweetIds": tweet_ids,
                    "saved_at": _now(now).isoformat(),
                    "file": path.name,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        if session_id:
            self._increment_counter(session_id, "images", _now(now))
        return {"ok": True, "path": str(path), "skipped": False}

    def save_error(self, record, session_id=None, now=None):
        timestamp = _now(now)
        output = dict(record)
        output["recorded_at"] = timestamp.isoformat()
        paths = self._session_paths(session_id) if session_id else None
        path = (paths["errors"] if paths else self.errors_dir) / f"{timestamp.date().isoformat()}.ndjson"
        _append_json_line(path, output)
        if session_id:
            self._increment_counter(session_id, "errors", timestamp)
        return {"ok": True, "path": str(path)}

    def _unique_session_id(self, tab_url, timestamp):
        parsed = urlparse(tab_url or "")
        slug_source = (parsed.hostname or "x") + parsed.path
        slug = _safe_name(slug_source.replace(".", "-").replace("/", "-")).strip("-") or "x"
        base = f"{timestamp.strftime('%Y%m%d-%H%M%S')}-{slug[:48]}"
        candidate = base
        index = 2
        while self._session_dir(candidate).exists():
            candidate = f"{base}-{index}"
            index += 1
        return candidate

    def _session_dir(self, session_id):
        if not session_id or session_id != _safe_name(str(session_id)):
            raise ValueError("invalid session id")
        root = self.sessions_dir.resolve()
        target = (self.sessions_dir / str(session_id)).resolve()
        if root != target and root not in target.parents:
            raise ValueError("session path escapes sessions directory")
        return target

    def _session_paths(self, session_id):
        session_dir = self._session_dir(session_id)
        paths = {
            "root": session_dir,
            "raw": session_dir / "raw",
            "tweets": session_dir / "tweets",
            "images": session_dir / "images",
            "errors": session_dir / "errors",
            "manifest": session_dir / "manifest.json",
        }
        for key, path in paths.items():
            if key not in {"manifest"}:
                path.mkdir(parents=True, exist_ok=True)
        return paths

    def _read_manifest(self, session_id):
        manifest_path = self._session_paths(session_id)["manifest"]
        if not manifest_path.exists():
            raise ValueError("session manifest not found")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def _write_manifest(self, session_id, manifest):
        manifest_path = self._session_paths(session_id)["manifest"]
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _increment_counter(self, session_id, name, timestamp):
        manifest = self._read_manifest(session_id)
        manifest["counters"] = _normalize_counters(manifest.get("counters", {}))
        manifest["counters"][name] += 1
        manifest["updated_at"] = timestamp.isoformat()
        self._write_manifest(session_id, manifest)

    def _session_summary(self, manifest, session_dir):
        return {
            "id": manifest.get("id"),
            "status": manifest.get("status"),
            "tabUrl": manifest.get("tabUrl", ""),
            "tabTitle": manifest.get("tabTitle", ""),
            "started_at": manifest.get("started_at"),
            "updated_at": manifest.get("updated_at"),
            "ended_at": manifest.get("ended_at"),
            "counters": _normalize_counters(manifest.get("counters", {})),
            "export": manifest.get("export"),
            "path": str(session_dir),
        }


def handle_message(storage, message):
    message_type = message.get("type")
    try:
        if message_type == "ping":
            return {"ok": True, "type": "pong"}
        if message_type == "create_session":
            return storage.create_session(message)
        if message_type == "close_session":
            return storage.close_session(message.get("sessionId"), message.get("counters"))
        if message_type == "list_sessions":
            return storage.list_sessions()
        if message_type == "generate_session_export":
            return storage.generate_session_export(message.get("sessionId"))
        if message_type == "generate_pure_export":
            return storage.generate_pure_export(message.get("sessionId"))
        if message_type == "open_session_directory":
            return storage.open_session_directory(message.get("sessionId"))
        if message_type == "delete_session":
            return storage.delete_session(message.get("sessionId"))
        if message_type == "save_raw_json":
            return storage.save_raw_json(message.get("record", {}), session_id=message.get("sessionId"))
        if message_type == "save_tweet_json":
            return storage.save_tweet_json(message.get("tweet", {}), session_id=message.get("sessionId"))
        if message_type == "save_image":
            return storage.save_image(message, session_id=message.get("sessionId"))
        if message_type == "save_error":
            return storage.save_error(message.get("error", {}), session_id=message.get("sessionId"))
        return {"ok": False, "error": f"Unknown message type: {message_type}"}
    except Exception as exc:
        error_record = {
            "stage": "host",
            "message": str(exc),
            "inputType": message_type,
        }
        try:
            storage.save_error(error_record)
        except Exception:
            pass
        return {"ok": False, "error": str(exc)}


def run(stdin=None, stdout=None, storage=None):
    _set_binary_stdio()
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    storage = storage or NativeHostStorage(Path(__file__).resolve().parent / "captures")

    while True:
        message = decode_message(stdin)
        if message is None:
            break
        stdout.write(encode_message(handle_message(storage, message)))
        stdout.flush()


def _append_json_line(path, value):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")


def _now(value=None):
    if value is not None:
        return value
    return datetime.now(timezone.utc)


def _safe_name(value):
    return "".join(ch for ch in value if ch.isalnum() or ch in ("-", "_"))


def _empty_counters():
    return {"rawJson": 0, "tweets": 0, "images": 0, "errors": 0}


def _normalize_counters(value):
    counters = _empty_counters()
    if isinstance(value, dict):
        for key in counters:
            try:
                counters[key] = int(value.get(key, 0))
            except (TypeError, ValueError):
                counters[key] = 0
    return counters


def _remove_tree(path):
    path = Path(path)
    for root, dirs, files in os.walk(path, topdown=False):
        root_path = Path(root)
        for name in files:
            _remove_path_with_retry(root_path / name, os.unlink)
        for name in dirs:
            _remove_path_with_retry(root_path / name, os.rmdir)
    _remove_path_with_retry(path, os.rmdir)


def _remove_path_with_retry(path, remover):
    last_error = None
    for attempt in range(8):
        try:
            remover(path)
            return
        except FileNotFoundError:
            return
        except PermissionError as exc:
            last_error = exc
            try:
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            except OSError:
                pass
            time.sleep(0.025 * (attempt + 1))
    if last_error:
        raise last_error


def _open_directory(path):
    path = Path(path)
    if os.name == "nt":
        subprocess.Popen(["explorer.exe", str(path)])
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])


def _export_visible_session(session_dir, now=None):
    build_visible_records, write_exports = _load_visible_exporter()
    session_dir = Path(session_dir)
    records, summary = build_visible_records(session_dir, timezone_name="Asia/Tokyo")
    written = write_exports(records, summary, session_dir, session_dir)
    return {
        "ok": True,
        "generated_at": _now(now).isoformat(),
        "records": len(records),
        "html": str(written["html"]),
        "pure": str(written["pure"]),
        "csv": str(written["csv"]),
        "jsonl": str(written["jsonl"]),
        "summary": str(written["summary"]),
    }


def _load_visible_exporter():
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from scripts.export_visible_tweets import build_visible_records, write_exports

    return build_visible_records, write_exports


def _image_extension(url, mime_type):
    mime = (mime_type or "").lower().split(";")[0].strip()
    by_mime = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/avif": ".avif",
        "image/gif": ".gif",
    }
    if mime in by_mime:
        return by_mime[mime]

    parsed = urlparse(url)
    query_format = parse_qs(parsed.query).get("format", [None])[0]
    if query_format:
        return "." + _safe_name(query_format.lower())

    suffix = Path(parsed.path).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif"} else ".bin"


def _set_binary_stdio():
    if os.name != "nt":
        return
    try:
        import msvcrt

        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    except Exception:
        pass


if __name__ == "__main__":
    run()
