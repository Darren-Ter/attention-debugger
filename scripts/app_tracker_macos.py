#!/usr/bin/env python3
import json
import os
import plistlib
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
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
"""


APPLESCRIPT = """
tell application "System Events"
  set frontProcess to first application process whose frontmost is true
  set frontApp to name of frontProcess
  set frontBundleId to ""
  set frontAppPath to ""
  set frontTitle to ""
  try
    set frontBundleId to bundle identifier of frontProcess
  end try
  try
    set frontAppPath to POSIX path of (application file of frontProcess as alias)
  end try
  try
    tell process frontApp
      set frontTitle to name of front window
    end tell
  end try
end tell
return frontApp & "\n" & frontBundleId & "\n" & frontAppPath & "\n" & frontTitle
"""


def now_iso():
  return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def connect_db():
  DB_PATH.parent.mkdir(parents=True, exist_ok=True)
  connection = sqlite3.connect(DB_PATH)
  connection.executescript(SCHEMA)
  return connection


def display_name_for_app(process_name, app_path):
  if not app_path:
    return process_name

  path = Path(app_path)
  info_plist = path / "Contents" / "Info.plist"
  if info_plist.exists():
    try:
      with info_plist.open("rb") as file:
        info = plistlib.load(file)
      return info.get("CFBundleDisplayName") or info.get("CFBundleName") or path.stem or process_name
    except Exception:
      pass

  return path.stem or process_name


def current_frontmost_app():
  result = subprocess.run(
    ["osascript", "-e", APPLESCRIPT],
    check=True,
    capture_output=True,
    text=True,
  )
  lines = result.stdout.splitlines()
  process_name = lines[0] if lines else ""
  bundle_id = lines[1] if len(lines) > 1 else ""
  app_path = lines[2] if len(lines) > 2 else ""
  window_title = lines[3] if len(lines) > 3 else ""
  app_name = display_name_for_app(process_name, app_path)
  return app_name, window_title, process_name, bundle_id, app_path


def insert_event(connection, app_name, window_title, process_name, bundle_id, app_path):
  event = {
    "occurred_at": now_iso(),
    "source": "macos-app-tracker",
    "event_type": "foreground_app_changed",
    "app_name": app_name,
    "window_title": window_title,
    "process_name": process_name,
    "bundle_id": bundle_id,
    "app_path": app_path,
  }
  connection.execute(
    """
    INSERT INTO events (
      occurred_at, source, event_type, app_name, window_title, payload_json
    ) VALUES (
      :occurred_at, :source, :event_type, :app_name, :window_title, :payload_json
    )
    """,
    {**event, "payload_json": json.dumps(event, sort_keys=True, separators=(",", ":"))},
  )
  connection.commit()


def main():
  connection = connect_db()
  last_seen = None
  print(f"Logging foreground app changes to {DB_PATH}")

  while True:
    try:
      app_name, window_title, process_name, bundle_id, app_path = current_frontmost_app()
      current = (app_name, window_title)
      if current != last_seen:
        insert_event(connection, app_name, window_title, process_name, bundle_id, app_path)
        print(f"{now_iso()} {app_name} - {window_title}")
        last_seen = current
    except KeyboardInterrupt:
      break
    except Exception as error:
      print(f"tracker error: {error}")

    time.sleep(2)


if __name__ == "__main__":
  main()
