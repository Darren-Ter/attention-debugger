#!/usr/bin/env python3
import html
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


APP_DIR = Path.home() / "Library" / "Application Support" / "AttentionDebugger"
DB_PATH = Path(os.environ.get("ATTENTION_DEBUGGER_DB", APP_DIR / "attention.sqlite3"))
HOST = "127.0.0.1"
PORT = int(os.environ.get("ATTENTION_DEBUGGER_PORT", "8765"))
WINDOW_HOURS = 24


def connect_db():
  return sqlite3.connect(DB_PATH)


def rows_for_query(query, params=()):
  if not DB_PATH.exists():
    return []
  with connect_db() as connection:
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(query, params)]


def since_iso(hours=WINDOW_HOURS):
  return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def parse_time(value):
  if not value:
    return None
  try:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
  except ValueError:
    return None


def local_time(value, style="time"):
  parsed = parse_time(value)
  if not parsed:
    return ""
  local = parsed.astimezone()
  if style == "date":
    return local.strftime("%b %-d")
  if style == "full":
    return local.strftime("%b %-d, %-I:%M %p")
  return local.strftime("%-I:%M %p")


def trim(value, limit=64):
  text = "" if value is None else str(value)
  return text if len(text) <= limit else text[: limit - 1] + "..."


def escape(value):
  return html.escape("" if value is None else str(value))


def event_label(event):
  domain = event.get("domain")
  app_name = event.get("app_name")
  if domain and domain not in {"127.0.0.1", "localhost"}:
    return domain
  if app_name:
    return app_name
  if domain:
    return domain
  return event.get("source") or "unknown"


def event_kind(event):
  source = event.get("source") or ""
  if event.get("idle_state"):
    return "idle"
  if "chrome" in source or event.get("domain"):
    return "browser"
  return "app"


def all_events(hours=WINDOW_HOURS, limit=2000):
  return rows_for_query(
    """
    SELECT occurred_at, source, event_type, domain, title, app_name, window_title, idle_state
    FROM events
    WHERE occurred_at >= ?
    ORDER BY occurred_at ASC
    LIMIT ?
    """,
    (since_iso(hours), limit),
  )


def top_domains(limit=8):
  return rows_for_query(
    """
    SELECT domain, COUNT(*) AS events
    FROM events
    WHERE domain IS NOT NULL AND domain != '' AND occurred_at >= ?
    GROUP BY domain
    ORDER BY events DESC
    LIMIT ?
    """,
    (since_iso(), limit),
  )


def top_apps(limit=8):
  return rows_for_query(
    """
    SELECT app_name, COUNT(*) AS events
    FROM events
    WHERE app_name IS NOT NULL AND app_name != '' AND occurred_at >= ?
    GROUP BY app_name
    ORDER BY events DESC
    LIMIT ?
    """,
    (since_iso(), limit),
  )


def recent_events(limit=36):
  rows = rows_for_query(
    """
    SELECT occurred_at, source, event_type, domain, title, app_name, window_title, idle_state
    FROM events
    ORDER BY occurred_at DESC
    LIMIT ?
    """,
    (limit,),
  )
  for row in rows:
    row["local_time"] = local_time(row.get("occurred_at"), "full")
    row["label"] = event_label(row)
  return rows


def event_count(hours=None):
  if hours is None:
    rows = rows_for_query("SELECT COUNT(*) AS count FROM events")
  else:
    rows = rows_for_query("SELECT COUNT(*) AS count FROM events WHERE occurred_at >= ?", (since_iso(hours),))
  return rows[0]["count"] if rows else 0


def sessionize(events, gap_minutes=20):
  sessions = []
  current = None
  last_time = None
  for event in events:
    event_time = parse_time(event.get("occurred_at"))
    if not event_time:
      continue
    if current is None or (last_time and event_time - last_time > timedelta(minutes=gap_minutes)):
      if current:
        sessions.append(current)
      current = {
        "start": event_time,
        "end": event_time,
        "events": [],
        "labels": Counter(),
        "apps": Counter(),
      }
    current["end"] = event_time
    current["events"].append(event)
    current["labels"][event_label(event)] += 1
    if event.get("app_name"):
      current["apps"][event["app_name"]] += 1
    last_time = event_time
  if current:
    sessions.append(current)
  return sessions


def format_duration(delta):
  seconds = max(0, int(delta.total_seconds()))
  minutes = seconds // 60
  if minutes < 1:
    return "<1m"
  if minutes < 60:
    return f"{minutes}m"
  hours, remainder = divmod(minutes, 60)
  return f"{hours}h {remainder}m" if remainder else f"{hours}h"


def session_rows(sessions):
  rows = []
  for session in reversed(sessions[-6:]):
    focus = session["labels"].most_common(1)[0][0] if session["labels"] else "unknown"
    app = session["apps"].most_common(1)[0][0] if session["apps"] else "browser"
    rows.append(
      {
        "time": f"{session['start'].astimezone().strftime('%-I:%M')} - {session['end'].astimezone().strftime('%-I:%M %p')}",
        "duration": format_duration(session["end"] - session["start"]),
        "focus": focus,
        "app": app,
        "events": len(session["events"]),
      }
    )
  return rows


def switch_stats(events):
  switches = []
  previous = None
  labels = []
  for event in events:
    label = event_label(event)
    labels.append(label)
    if previous and label != previous:
      switches.append((previous, label))
    previous = label
  return switches, labels


def context_matrix(events):
  switches, labels = switch_stats(events)
  ranked = [label for label, _count in Counter(labels).most_common(5)]
  counts = Counter(switches)
  matrix = []
  for source in ranked:
    row = []
    for target in ranked:
      row.append(counts[(source, target)])
    matrix.append({"source": source, "values": row})
  return ranked, matrix


def hourly_activity(events):
  buckets = defaultdict(int)
  for event in events:
    event_time = parse_time(event.get("occurred_at"))
    if not event_time:
      continue
    buckets[event_time.astimezone().hour] += 1
  now_hour = datetime.now().astimezone().hour
  hours = [((now_hour - offset) % 24) for offset in reversed(range(24))]
  peak = max(buckets.values(), default=1)
  return [{"hour": hour, "count": buckets[hour], "height": max(4, round((buckets[hour] / peak) * 72))} for hour in hours]


def insight_items(events, domains, apps, sessions):
  insights = []
  switches, labels = switch_stats(events)
  total = max(1, len(events))
  top_domain = domains[0] if domains else None
  top_app = apps[0] if apps else None

  if switches:
    rate = round(len(switches) / max(1, total) * 100)
    tone = "high" if rate >= 45 else "steady"
    insights.append(
      {
        "label": "Switch pressure",
        "value": f"{len(switches)} switches",
        "body": f"{rate}% of captured events changed context. Treat this as a cue to batch tabs or apps when the number climbs.",
        "tone": tone,
      }
    )

  if top_domain:
    share = round((top_domain["events"] / total) * 100)
    insights.append(
      {
        "label": "Browser pull",
        "value": top_domain["domain"],
        "body": f"{share}% of today's event trail points at this domain.",
        "tone": "neutral",
      }
    )

  if top_app:
    share = round((top_app["events"] / total) * 100)
    insights.append(
      {
        "label": "App anchor",
        "value": top_app["app_name"],
        "body": f"{share}% of app events came from this app in the last {WINDOW_HOURS} hours.",
        "tone": "neutral",
      }
    )

  localhost_events = sum(row["events"] for row in domains if row["domain"] in {"127.0.0.1", "localhost"})
  if localhost_events >= 3:
    insights.append(
      {
        "label": "Dashboard checking",
        "value": f"{localhost_events} local events",
        "body": "You checked local tools repeatedly. Useful while tuning, but worth filtering once tracking is stable.",
        "tone": "watch",
      }
    )

  if sessions:
    latest = sessions[-1]
    insights.append(
      {
        "label": "Current stretch",
        "value": format_duration(latest["end"] - latest["start"]),
        "body": f"Latest session is centered on {latest['labels'].most_common(1)[0][0] if latest['labels'] else 'unknown'}.",
        "tone": "steady",
      }
    )

  if not insights:
    insights.append(
      {
        "label": "Waiting for signal",
        "value": "No events yet",
        "body": "Reload the browser extension or run the macOS tracker to start building the trail.",
        "tone": "neutral",
      }
    )
  return insights[:5]


def dashboard_data():
  events = all_events()
  domains = top_domains()
  apps = top_apps()
  sessions = sessionize(events)
  labels, matrix = context_matrix(events)
  latest = events[-1] if events else {}
  first_time = parse_time(events[0]["occurred_at"]) if events else None
  last_time = parse_time(events[-1]["occurred_at"]) if events else None
  active_span = format_duration(last_time - first_time) if first_time and last_time else "0m"
  switches, _labels = switch_stats(events)
  browser_events = sum(1 for event in events if event_kind(event) == "browser")
  app_events = sum(1 for event in events if event_kind(event) == "app")
  idle_events = sum(1 for event in events if event_kind(event) == "idle")

  return {
    "events": events,
    "recent": recent_events(),
    "domains": domains,
    "apps": apps,
    "sessions": sessions,
    "session_rows": session_rows(sessions),
    "matrix_labels": labels,
    "matrix": matrix,
    "hourly": hourly_activity(events),
    "insights": insight_items(events, domains, apps, sessions),
    "latest": latest,
    "metrics": {
      "total_events": event_count(),
      "window_events": len(events),
      "switches": len(switches),
      "active_span": active_span,
      "browser_events": browser_events,
      "app_events": app_events,
      "idle_events": idle_events,
      "sessions": len(sessions),
    },
  }


def render_bar_rows(rows, key):
  if not rows:
    return "<p class='empty'>No data yet.</p>"
  peak = max(row["events"] for row in rows) or 1
  items = []
  for row in rows:
    label = row[key]
    width = max(3, round((row["events"] / peak) * 100))
    items.append(
      f"""
      <li class="rank-row">
        <div>
          <strong>{escape(trim(label, 34))}</strong>
          <span>{row["events"]} events</span>
        </div>
        <div class="bar"><i style="width:{width}%"></i></div>
      </li>
      """
    )
  return f"<ol class='rank-list'>{''.join(items)}</ol>"


def render_sessions(rows):
  if not rows:
    return "<p class='empty'>No sessions yet.</p>"
  return "".join(
    f"""
    <div class="session-row">
      <div>
        <strong>{escape(row["focus"])}</strong>
        <span>{escape(row["app"])} / {row["events"]} events</span>
      </div>
      <div>
        <b>{escape(row["duration"])}</b>
        <span>{escape(row["time"])}</span>
      </div>
    </div>
    """
    for row in rows
  )


def render_timeline(hourly):
  bars = []
  for bucket in hourly:
    label = f"{bucket['hour']:02d}:00"
    bars.append(
      f"""
      <div class="hour" title="{label} / {bucket['count']} events">
        <i style="height:{bucket['height']}px"></i>
        <span>{bucket['hour']}</span>
      </div>
      """
    )
  return "".join(bars)


def render_insights(insights):
  return "".join(
    f"""
    <article class="insight {escape(item["tone"])}">
      <div>
        <span>{escape(item["label"])}</span>
        <strong>{escape(item["value"])}</strong>
      </div>
      <p>{escape(item["body"])}</p>
    </article>
    """
    for item in insights
  )


def render_matrix(labels, matrix):
  if not labels:
    return "<p class='empty'>No switches yet.</p>"
  header = "".join(f"<th>{escape(trim(label, 12))}</th>" for label in labels)
  peak = max((max(row["values"]) for row in matrix), default=1) or 1
  body = []
  for row in matrix:
    cells = [f"<th>{escape(trim(row['source'], 14))}</th>"]
    for value in row["values"]:
      strength = round((value / peak) * 45)
      cells.append(f"<td style='--heat:{strength}%'>{value if value else ''}</td>")
    body.append(f"<tr>{''.join(cells)}</tr>")
  return f"<table class='matrix'><thead><tr><th>from / to</th>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def render_recent(rows):
  if not rows:
    return "<p class='empty'>No data yet.</p>"
  body = []
  for row in rows:
    detail = row.get("title") or row.get("window_title") or ""
    context = row.get("domain") or row.get("app_name") or row.get("source") or ""
    body.append(
      f"""
      <tr>
        <td>{escape(row["local_time"])}</td>
        <td><span class="source-pill">{escape(row.get("source"))}</span></td>
        <td>{escape(row.get("event_type"))}</td>
        <td><strong>{escape(trim(context, 36))}</strong><span>{escape(trim(detail, 64))}</span></td>
        <td>{escape(trim(row.get("app_name"), 28))}</td>
      </tr>
      """
    )
  return f"<table class='events-table'><thead><tr><th>Time</th><th>Source</th><th>Event</th><th>Context</th><th>App</th></tr></thead><tbody>{''.join(body)}</tbody></table>"


def render_home():
  data = dashboard_data()
  metrics = data["metrics"]
  latest = data["latest"]
  latest_context = event_label(latest) if latest else "No active signal"
  latest_detail = latest.get("title") or latest.get("window_title") or latest.get("event_type") or "Waiting for events"

  return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Attention Debugger</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0e1116;
      --panel: #151a22;
      --panel-2: #10151d;
      --line: #262d38;
      --line-soft: #1c222d;
      --text: #edf2f7;
      --muted: #8c98a8;
      --faint: #5e6a78;
      --accent: #7dd3fc;
      --accent-2: #a7f3d0;
      --warn: #fbbf24;
      --danger: #fb7185;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      min-width: 320px;
      background:
        linear-gradient(180deg, rgba(125, 211, 252, 0.08), transparent 320px),
        var(--bg);
    }}
    main {{
      width: min(1480px, calc(100vw - 40px));
      margin: 0 auto;
      padding: 28px 0 44px;
    }}
    header {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 22px;
    }}
    h1, h2, h3, p {{
      margin: 0;
    }}
    h1 {{
      font-size: clamp(28px, 3vw, 44px);
      line-height: 1;
      letter-spacing: 0;
    }}
    h2 {{
      font-size: 13px;
      font-weight: 700;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 14px;
    }}
    h3 {{
      font-size: 14px;
      margin-bottom: 8px;
    }}
    p {{
      color: var(--muted);
      line-height: 1.45;
    }}
    .meta {{
      margin-top: 9px;
      max-width: 780px;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .status {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      height: 32px;
      padding: 0 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(16, 21, 29, .82);
      color: var(--accent-2);
      font-size: 13px;
      white-space: nowrap;
    }}
    .status i {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: currentColor;
      box-shadow: 0 0 18px currentColor;
    }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(260px, 330px) minmax(0, 1fr) minmax(280px, 380px);
      gap: 18px;
      align-items: start;
    }}
    .stack {{
      display: grid;
      gap: 18px;
    }}
    .panel {{
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: color-mix(in srgb, var(--panel) 92%, black);
      box-shadow: 0 18px 54px rgba(0, 0, 0, .28);
    }}
    .panel-pad {{
      padding: 18px;
    }}
    .now strong {{
      display: block;
      font-size: 26px;
      line-height: 1.08;
      margin-bottom: 10px;
      overflow-wrap: anywhere;
    }}
    .now .detail {{
      min-height: 42px;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .now-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 18px;
    }}
    .mini {{
      border-top: 1px solid var(--line-soft);
      padding-top: 12px;
    }}
    .mini b {{
      display: block;
      font-size: 22px;
      margin-bottom: 3px;
    }}
    .mini span, .rank-row span, .session-row span, .events-table span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.25;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 1px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--line);
      margin-bottom: 18px;
    }}
    .summary-grid div {{
      background: var(--panel);
      padding: 16px;
      min-height: 92px;
    }}
    .summary-grid b {{
      display: block;
      font-size: clamp(22px, 3vw, 34px);
      line-height: 1;
      margin-bottom: 8px;
    }}
    .summary-grid span {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .timeline {{
      display: grid;
      grid-template-columns: repeat(24, 1fr);
      gap: 5px;
      height: 108px;
      align-items: end;
      padding: 10px 0 0;
      border-top: 1px solid var(--line-soft);
    }}
    .hour {{
      display: grid;
      justify-items: center;
      gap: 6px;
      min-width: 0;
    }}
    .hour i {{
      width: 100%;
      max-width: 14px;
      min-height: 4px;
      border-radius: 4px 4px 1px 1px;
      background: linear-gradient(180deg, var(--accent), #2563eb);
      opacity: .9;
    }}
    .hour span {{
      color: var(--faint);
      font-size: 10px;
    }}
    .session-row {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      padding: 13px 0;
      border-top: 1px solid var(--line-soft);
    }}
    .session-row:first-of-type {{
      border-top: 0;
      padding-top: 0;
    }}
    .session-row > div:last-child {{
      text-align: right;
      flex: 0 0 auto;
    }}
    .rank-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 13px;
    }}
    .rank-row > div:first-child {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 7px;
    }}
    .rank-row strong {{
      min-width: 0;
      overflow-wrap: anywhere;
    }}
    .bar {{
      height: 6px;
      overflow: hidden;
      border-radius: 999px;
      background: #222936;
    }}
    .bar i {{
      display: block;
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
    }}
    .insights {{
      display: grid;
      gap: 10px;
    }}
    .insight {{
      border: 1px solid var(--line-soft);
      border-left: 3px solid var(--accent);
      border-radius: 8px;
      padding: 13px;
      background: var(--panel-2);
    }}
    .insight.high {{
      border-left-color: var(--danger);
    }}
    .insight.watch {{
      border-left-color: var(--warn);
    }}
    .insight > div {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 7px;
    }}
    .insight span {{
      color: var(--muted);
      font-size: 12px;
    }}
    .insight strong {{
      text-align: right;
      overflow-wrap: anywhere;
    }}
    .insight p {{
      font-size: 13px;
    }}
    .wide {{
      grid-column: 1 / -1;
    }}
    .split {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 18px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 13px;
    }}
    th, td {{
      border-top: 1px solid var(--line-soft);
      padding: 10px 9px;
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }}
    th {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .06em;
      font-weight: 700;
    }}
    .matrix th:first-child {{
      width: 110px;
    }}
    .matrix td {{
      text-align: center;
      color: var(--text);
      background: color-mix(in srgb, var(--accent) var(--heat), transparent);
    }}
    .events-table th:nth-child(1) {{
      width: 150px;
    }}
    .events-table th:nth-child(2) {{
      width: 118px;
    }}
    .events-table th:nth-child(3) {{
      width: 132px;
    }}
    .events-table th:nth-child(5) {{
      width: 132px;
    }}
    .source-pill {{
      display: inline-block;
      max-width: 100%;
      padding: 3px 7px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel-2);
      color: var(--muted);
      font-size: 11px;
    }}
    .empty {{
      padding: 16px 0;
      color: var(--muted);
    }}
    @media (max-width: 1120px) {{
      .layout, .split {{
        grid-template-columns: 1fr;
      }}
      .wide {{
        grid-column: auto;
      }}
    }}
    @media (max-width: 720px) {{
      main {{
        width: min(100vw - 24px, 1480px);
        padding-top: 18px;
      }}
      header {{
        display: block;
      }}
      .status {{
        margin-top: 14px;
      }}
      .summary-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .timeline {{
        grid-template-columns: repeat(12, 1fr);
        height: auto;
      }}
      .hour:nth-child(odd) span {{
        display: none;
      }}
      .panel-pad {{
        padding: 15px;
      }}
      table {{
        min-width: 760px;
      }}
      .table-scroll {{
        overflow-x: auto;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Attention Debugger</h1>
        <p class="meta">Local browser and app activity from the last {WINDOW_HOURS} hours. Database: {escape(str(DB_PATH))}</p>
      </div>
      <div class="status"><i></i>Local monitor</div>
    </header>

    <section class="summary-grid" aria-label="Key metrics">
      <div><b>{metrics["window_events"]}</b><span>events today</span></div>
      <div><b>{metrics["switches"]}</b><span>context switches</span></div>
      <div><b>{metrics["sessions"]}</b><span>sessions</span></div>
      <div><b>{escape(metrics["active_span"])}</b><span>active span</span></div>
    </section>

    <div class="layout">
      <aside class="stack">
        <section class="panel panel-pad now">
          <h2>Now</h2>
          <strong>{escape(trim(latest_context, 42))}</strong>
          <p class="detail">{escape(trim(latest_detail, 120))}</p>
          <div class="now-grid">
            <div class="mini"><b>{metrics["browser_events"]}</b><span>browser events</span></div>
            <div class="mini"><b>{metrics["app_events"]}</b><span>app events</span></div>
            <div class="mini"><b>{metrics["idle_events"]}</b><span>idle events</span></div>
            <div class="mini"><b>{metrics["total_events"]}</b><span>all-time events</span></div>
          </div>
        </section>

        <section class="panel panel-pad">
          <h2>Sessions</h2>
          {render_sessions(data["session_rows"])}
        </section>
      </aside>

      <section class="stack">
        <section class="panel panel-pad">
          <h2>Today's Summary</h2>
          <div class="timeline">{render_timeline(data["hourly"])}</div>
        </section>

        <section class="split">
          <div class="panel panel-pad">
            <h2>Top Domains</h2>
            {render_bar_rows(data["domains"], "domain")}
          </div>
          <div class="panel panel-pad">
            <h2>Top Apps</h2>
            {render_bar_rows(data["apps"], "app_name")}
          </div>
        </section>

        <section class="panel panel-pad">
          <h2>Context Switch Matrix</h2>
          <div class="table-scroll">{render_matrix(data["matrix_labels"], data["matrix"])}</div>
        </section>

        <section class="panel panel-pad wide">
          <h2>Recent Events</h2>
          <div class="table-scroll">{render_recent(data["recent"])}</div>
        </section>
      </section>

      <aside class="stack">
        <section class="panel panel-pad">
          <h2>Key Metrics</h2>
          <div class="insights">{render_insights(data["insights"])}</div>
        </section>
      </aside>
    </div>
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
