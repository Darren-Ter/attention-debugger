#!/usr/bin/env python3
import html
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


APP_DIR = Path.home() / "Library" / "Application Support" / "AttentionDebugger"
DB_PATH = Path(os.environ.get("ATTENTION_DEBUGGER_DB", APP_DIR / "attention.sqlite3"))
HOST = "127.0.0.1"
PORT = int(os.environ.get("ATTENTION_DEBUGGER_PORT", "8765"))


def connect_db():
  return sqlite3.connect(DB_PATH)


def rows_for_query(query, params=()):
  if not DB_PATH.exists():
    return []
  with connect_db() as connection:
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(query, params)]


def since_iso(hours=24):
  return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def top_domains():
  return rows_for_query(
    """
    SELECT domain, COUNT(*) AS events
    FROM events
    WHERE domain IS NOT NULL AND domain != '' AND occurred_at >= ?
    GROUP BY domain
    ORDER BY events DESC
    LIMIT 20
    """,
    (since_iso(),),
  )


def top_apps():
  return rows_for_query(
    """
    SELECT app_name, COUNT(*) AS events
    FROM events
    WHERE app_name IS NOT NULL AND app_name != '' AND occurred_at >= ?
    GROUP BY app_name
    ORDER BY events DESC
    LIMIT 20
    """,
    (since_iso(),),
  )


def recent_events():
  return rows_for_query(
    """
    SELECT occurred_at, source, event_type, domain, title, app_name, window_title, current_task
    FROM events
    ORDER BY occurred_at DESC
    LIMIT 80
    """
  )


def event_count():
  rows = rows_for_query("SELECT COUNT(*) AS count FROM events")
  return rows[0]["count"] if rows else 0


def render_table(rows, columns):
  if not rows:
    return "<p class='empty'>No data yet.</p>"

  header = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
  body = []
  for row in rows:
    cells = []
    for key, _label in columns:
      value = row.get(key)
      cells.append(f"<td>{html.escape('' if value is None else str(value))}</td>")
    body.append("<tr>" + "".join(cells) + "</tr>")
  return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def render_home():
  domains = render_table(top_domains(), [("domain", "Domain"), ("events", "Events")])
  apps = render_table(top_apps(), [("app_name", "App"), ("events", "Events")])
  events = render_table(
    recent_events(),
    [
      ("occurred_at", "Time"),
      ("source", "Source"),
      ("event_type", "Event"),
      ("domain", "Domain"),
      ("title", "Title"),
      ("app_name", "App"),
      ("window_title", "Window"),
      ("current_task", "Task"),
    ],
  )

  return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Attention Debugger</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: Canvas;
      color: CanvasText;
    }}
    body {{
      margin: 0;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 18px 48px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
      margin-bottom: 24px;
    }}
    h1 {{
      font-size: 28px;
      line-height: 1.1;
      margin: 0 0 6px;
    }}
    h2 {{
      font-size: 16px;
      margin: 0 0 10px;
    }}
    p {{
      margin: 0;
      color: color-mix(in srgb, CanvasText 72%, Canvas);
    }}
    a {{
      color: LinkText;
    }}
    .metric {{
      min-width: 140px;
      text-align: right;
    }}
    .metric strong {{
      display: block;
      font-size: 30px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 20px;
      margin-bottom: 24px;
    }}
    section {{
      min-width: 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid color-mix(in srgb, CanvasText 12%, Canvas);
      padding: 8px 6px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      font-size: 12px;
      color: color-mix(in srgb, CanvasText 68%, Canvas);
    }}
    td {{
      max-width: 320px;
      overflow-wrap: anywhere;
    }}
    .empty {{
      padding: 18px 0;
    }}
    @media (max-width: 760px) {{
      header, .grid {{
        display: block;
      }}
      .metric {{
        margin-top: 16px;
        text-align: left;
      }}
      section {{
        margin-bottom: 24px;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Attention Debugger</h1>
        <p>Local browser and app activity from the last 24 hours. Database: {html.escape(str(DB_PATH))}</p>
      </div>
      <div class="metric">
        <strong>{event_count()}</strong>
        <p>total events</p>
      </div>
    </header>
    <div class="grid">
      <section>
        <h2>Top Domains</h2>
        {domains}
      </section>
      <section>
        <h2>Top Apps</h2>
        {apps}
      </section>
    </div>
    <section>
      <h2>Recent Events</h2>
      {events}
    </section>
  </main>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
  def do_GET(self):
    parsed = urlparse(self.path)
    if parsed.path == "/api/events":
      payload = json.dumps(recent_events()).encode("utf-8")
      self.send_response(200)
      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Content-Length", str(len(payload)))
      self.end_headers()
      self.wfile.write(payload)
      return

    if parsed.path != "/":
      self.send_error(404)
      return

    payload = render_home().encode("utf-8")
    self.send_response(200)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.send_header("Content-Length", str(len(payload)))
    self.end_headers()
    self.wfile.write(payload)

  def log_message(self, format, *args):
    return


def main():
  server = ThreadingHTTPServer((HOST, PORT), Handler)
  print(f"Attention Debugger dashboard: http://{HOST}:{PORT}")
  print(f"Database: {DB_PATH}")
  server.serve_forever()


if __name__ == "__main__":
  main()
