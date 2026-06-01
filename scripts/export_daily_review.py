#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


APP_DIR = Path.home() / "Library" / "Application Support" / "AttentionDebugger"
DB_PATH = Path(os.environ.get("ATTENTION_DEBUGGER_DB", APP_DIR / "attention.sqlite3"))


def since_iso(hours):
  return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def query_rows(connection, query, params=()):
  connection.row_factory = sqlite3.Row
  return [dict(row) for row in connection.execute(query, params)]


def render_markdown(hours):
  if not DB_PATH.exists():
    return f"# Attention Review\n\nNo database found at `{DB_PATH}`.\n"

  with sqlite3.connect(DB_PATH) as connection:
    since = since_iso(hours)
    domains = query_rows(
      connection,
      """
      SELECT domain, COUNT(*) AS events
      FROM events
      WHERE domain IS NOT NULL AND domain != '' AND occurred_at >= ?
      GROUP BY domain
      ORDER BY events DESC
      LIMIT 20
      """,
      (since,),
    )
    apps = query_rows(
      connection,
      """
      SELECT app_name, COUNT(*) AS events
      FROM events
      WHERE app_name IS NOT NULL AND app_name != '' AND occurred_at >= ?
      GROUP BY app_name
      ORDER BY events DESC
      LIMIT 20
      """,
      (since,),
    )
    timeline = query_rows(
      connection,
      """
      SELECT occurred_at, source, event_type, domain, title, app_name, window_title
      FROM events
      WHERE occurred_at >= ?
      ORDER BY occurred_at ASC
      LIMIT 300
      """,
      (since,),
    )

  lines = [
    "# Attention Review",
    "",
    f"Window: last {hours} hours",
    f"Database: `{DB_PATH}`",
    "",
    "## Top Domains",
    "",
  ]
  lines.extend(f"- {row['domain']}: {row['events']} events" for row in domains)
  lines.extend(["", "## Top Apps", ""])
  lines.extend(f"- {row['app_name']}: {row['events']} events" for row in apps)
  lines.extend(["", "## Timeline Sample", ""])

  for row in timeline:
    label = row.get("domain") or row.get("app_name") or row.get("source") or "unknown"
    title = row.get("title") or row.get("window_title") or ""
    lines.append(f"- {row['occurred_at']} [{row['event_type']}] {label} {title}")

  lines.extend(
    [
      "",
      "## Codex Prompt",
      "",
      "Analyze this browser and app activity timeline. Identify likely drift points, useful detours, repeated triggers, and one practical experiment for tomorrow. Keep the output concise and non-judgmental.",
      "",
      "## Raw JSON",
      "",
      "```json",
      json.dumps({"domains": domains, "apps": apps, "timeline": timeline}, indent=2),
      "```",
    ]
  )
  return "\n".join(lines) + "\n"


def main():
  parser = argparse.ArgumentParser(description="Export a local attention review markdown file.")
  parser.add_argument("--hours", type=int, default=24)
  parser.add_argument("--output", default="attention-review.md")
  args = parser.parse_args()

  output = Path(args.output)
  output.write_text(render_markdown(args.hours), encoding="utf-8")
  print(f"Wrote {output.resolve()}")


if __name__ == "__main__":
  main()
