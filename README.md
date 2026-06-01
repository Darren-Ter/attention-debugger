# Attention Debugger

Local-first attention analytics for developers and ADHD-friendly workflows.

Attention Debugger records browser tab activity and optional macOS app focus into a local SQLite database, then helps you inspect where your attention went. The first MVP is intentionally small:

- Chrome extension captures active tabs, URL/domain, title, idle state, and current task.
- Native Messaging host writes events to local SQLite.
- macOS app tracker can log foreground app/window changes.
- Local dashboard summarizes app and site usage.
- No cloud service. No account. Your raw data stays on your machine.

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

Click the extension icon and set a current task, such as:

```text
Implement billing webhook retry tests
```

The extension will record active tab changes and idle state. To also log macOS foreground app/window activity:

```bash
python3 scripts/app_tracker_macos.py
```

Start the local dashboard:

```bash
python3 dashboard/server.py
```

Then open:

```text
http://127.0.0.1:8765
```

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
- current task
- idle state

macOS app events may include:

- foreground app name
- window title
- current task

## Privacy Notes

This project is local-first, but browser titles and URLs can still be sensitive. Future work should include:

- domain allow/deny rules
- private browsing redaction
- title hashing
- per-site capture controls
- encrypted database option
- automatic sensitive-domain suppression

## Roadmap

- Drift detection: identify the moment a task turns into unrelated browsing.
- Tab debt analyzer: cluster open tabs by intent.
- Recovery mode: "show last productive tab", "summarize open tabs", "write next 3-minute action".
- Daily attention review with a local summary file ready for Codex analysis.
- Firefox Native Messaging manifest installer.
- Optional OpenAI/Codex summarization layer using redacted local summaries.

## License

MIT
