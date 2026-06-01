# Attention Debugger

Local-first attention analytics for developers and ADHD-friendly workflows.

Attention Debugger records browser tab activity and optional macOS app focus into a local SQLite database, then helps you inspect where your attention went. The MVP is intentionally small and passive:

- Chrome extension captures active tabs, URL/domain, title, and idle state.
- Native Messaging host writes events to local SQLite.
- macOS app tracker can log foreground app/window changes.
- Local dashboard shows attention metrics, sessions, insights, top domains/apps, context switches, and recent events.
- No cloud service. No account. Your raw data stays on your machine.

The extension does not ask for a current task or manual journaling. It only tracks browser tab activity.

## Architecture

```text
Chrome extension
  -> Native Messaging host
  -> ~/Library/Application Support/AttentionDebugger/attention.sqlite3

macOS app tracker
  -> same SQLite database

dashboard/server.py
  -> local-only dashboard at http://127.0.0.1:8765
```

## Requirements

- macOS
- Python 3
- Google Chrome or Chromium-compatible browser with Native Messaging support

No npm install is required.

## Install

From this repository:

```bash
python3 native-host/install.py
```

Then load the extension:

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select the `extension/` folder in this repo
5. Copy the extension ID shown by Chrome
6. Re-run the installer with that ID:

```bash
python3 native-host/install.py --chrome-extension-id YOUR_EXTENSION_ID
```

Chrome requires the native host manifest to explicitly allow the extension ID.

## Use

The extension records active tab changes and idle state after it is loaded in Chrome.

To also log macOS foreground app/window activity:

```bash
python3 scripts/app_tracker_macos.py
```

macOS may ask for Accessibility permission for the app that launches this script, such as Terminal, Windsurf, or another editor. This is expected because the tracker uses macOS accessibility APIs to read the frontmost app and window title.

Start the local dashboard:

```bash
python3 dashboard/server.py
```

Then open:

```text
http://127.0.0.1:8765
```

If you change extension files, reload the unpacked extension from `chrome://extensions`. If you change Python files, restart the relevant script or dashboard server.

## Dashboard

The dashboard is local-only and dependency-free. It reads directly from SQLite and renders:

- **Now**: latest observed app, browser, or idle signal.
- **Sessions**: inferred work sessions based on gaps in event timestamps.
- **Key Metrics**: context-switch pressure, dominant browser domain, dominant app, and other simple insights.
- **Today's Summary**: hourly activity over the last 24 hours.
- **Top Domains** and **Top Apps**: ranked event counts.
- **Context Switch Matrix**: common transitions between apps/domains.
- **Recent Events**: latest raw events for debugging.

The dashboard uses event counts and timestamp gaps. It does not yet calculate exact time-on-site or exact foreground duration.

## Data Location

Default database:

```text
~/Library/Application Support/AttentionDebugger/attention.sqlite3
```

Override it with:

```bash
export ATTENTION_DEBUGGER_DB=/path/to/attention.sqlite3
```

## What It Records

Browser events may include:

- timestamp
- event type
- URL
- domain
- tab title
- active window/tab IDs
- idle state

macOS app events may include:

- foreground app name
- window title
- bundle ID and app path in the event payload when available

Attention Debugger does not record page contents, keystrokes, screenshots, form values, or passwords.

## Utilities

Send one test event:

```bash
python3 scripts/send_test_event.py
```

Export a local daily review prompt:

```bash
python3 scripts/export_daily_review.py
```

## Privacy Notes

This project is local-first, but browser titles and URLs can still be sensitive. Future work should include:

- domain allow/deny rules
- private browsing redaction
- title hashing
- per-site capture controls
- encrypted database option
- automatic sensitive-domain suppression

## Roadmap

- Duration estimation from tab/app intervals.
- Local filters for domains, extension URLs, and private browsing redaction.
- Drift detection: identify the moment focused work turns into unrelated browsing.
- Tab debt analyzer: cluster open tabs by intent.
- Recovery mode: show last productive tab, summarize open tabs, and suggest the next 3-minute action.
- Daily attention review with a local summary file ready for Codex analysis.
- Firefox Native Messaging manifest installer.
- Optional OpenAI/Codex summarization layer using redacted local summaries.

## License

MIT
