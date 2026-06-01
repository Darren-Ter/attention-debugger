#!/usr/bin/env python3
import json
import os
import sqlite3
import struct
import sys
from pathlib import Path


APP_DIR = Path.home() / "Library" / "Application Support" / "AttentionDebugger"
DB_PATH = Path(os.environ.get("ATTENTION_DEBUGGER_DB", APP_DIR / "attention.sqlite3"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  source TEXT NOT NULL,
  event_type TEXT NOT NULL,
  app_name TEXT,
  window_title TEXT,
  url TEXT,
  domain TEXT,
  title TEXT,
  tab_id INTEGER,
  window_id INTEGER,
  idle_state TEXT,
  current_task TEXT,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
CREATE INDEX IF NOT EXISTS idx_events_domain ON events(domain);
CREATE INDEX IF NOT EXISTS idx_events_app_name ON events(app_name);
CREATE INDEX IF NOT EXISTS idx_events_current_task ON events(current_task);
"""


def connect_db():
  DB_PATH.parent.mkdir(parents=True, exist_ok=True)
  connection = sqlite3.connect(DB_PATH)
  connection.executescript(SCHEMA)
  return connection


def read_message():
  raw_length = sys.stdin.buffer.read(4)
  if len(raw_length) == 0:
    return None
  if len(raw_length) != 4:
    raise ValueError("Invalid Native Messaging frame length")

  message_length = struct.unpack("<I", raw_length)[0]
  raw_message = sys.stdin.buffer.read(message_length)
  if len(raw_message) != message_length:
    raise ValueError("Incomplete Native Messaging frame")

  return json.loads(raw_message.decode("utf-8"))


def write_message(message):
  encoded = json.dumps(message, separators=(",", ":")).encode("utf-8")
  sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
  sys.stdout.buffer.write(encoded)
  sys.stdout.buffer.flush()


def normalize_event(message):
  event = message.get("event") if isinstance(message, dict) else None
  if not isinstance(event, dict):
    raise ValueError("Expected message.event object")

  return {
    "occurred_at": event.get("occurred_at") or "",
    "source": event.get("source") or "unknown",
    "event_type": event.get("event_type") or "unknown",
    "app_name": event.get("app_name"),
    "window_title": event.get("window_title"),
    "url": event.get("url"),
    "domain": event.get("domain"),
    "title": event.get("title"),
    "tab_id": event.get("tab_id"),
    "window_id": event.get("window_id"),
    "idle_state": event.get("idle_state"),
    "current_task": event.get("current_task"),
    "payload_json": json.dumps(event, sort_keys=True, separators=(",", ":"))
  }


def insert_event(connection, event):
  connection.execute(
    """
    INSERT INTO events (
      occurred_at, source, event_type, app_name, window_title, url, domain,
      title, tab_id, window_id, idle_state, current_task, payload_json
    ) VALUES (
      :occurred_at, :source, :event_type, :app_name, :window_title, :url, :domain,
      :title, :tab_id, :window_id, :idle_state, :current_task, :payload_json
    )
    """,
    event,
  )
  connection.commit()


def main():
  connection = connect_db()

  while True:
    message = read_message()
    if message is None:
      break

    try:
      if message.get("type") != "event":
        write_message({"ok": False, "error": "Unsupported message type"})
        continue

      event = normalize_event(message)
      insert_event(connection, event)
      write_message({"ok": True, "db_path": str(DB_PATH)})
    except Exception as error:
      write_message({"ok": False, "error": str(error)})


if __name__ == "__main__":
  main()
