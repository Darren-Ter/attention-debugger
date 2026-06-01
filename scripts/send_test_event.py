#!/usr/bin/env python3
import json
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "native-host" / "host.py"


def encode(message):
  payload = json.dumps(message).encode("utf-8")
  return struct.pack("<I", len(payload)) + payload


def decode(data):
  if len(data) < 4:
    return None
  length = struct.unpack("<I", data[:4])[0]
  return json.loads(data[4:4 + length].decode("utf-8"))


def main():
  event = {
    "type": "event",
    "event": {
      "source": "test",
      "event_type": "manual_test",
      "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
      "domain": "example.com",
      "title": "Attention Debugger test event",
      "url": "https://example.com/",
      "current_task": "Verify native host writes SQLite"
    }
  }
  result = subprocess.run([str(HOST)], input=encode(event), capture_output=True)
  if result.returncode != 0:
    raise SystemExit(result.stderr.decode("utf-8", errors="replace"))
  print(decode(result.stdout))


if __name__ == "__main__":
  main()
