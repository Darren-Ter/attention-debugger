#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path


HOST_NAME = "com.attentiondebugger.host"
CHROME_NATIVE_HOST_DIR = Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts"


def repo_root():
  return Path(__file__).resolve().parents[1]


def host_path():
  return repo_root() / "native-host" / "host.py"


def manifest(extension_id):
  allowed_origins = []
  if extension_id:
    allowed_origins.append(f"chrome-extension://{extension_id}/")

  return {
    "name": HOST_NAME,
    "description": "Attention Debugger Native Messaging host",
    "path": str(host_path()),
    "type": "stdio",
    "allowed_origins": allowed_origins
  }


def main():
  parser = argparse.ArgumentParser(description="Install the Attention Debugger Chrome Native Messaging host.")
  parser.add_argument("--chrome-extension-id", help="Chrome extension ID to allow.")
  args = parser.parse_args()

  host_path().chmod(0o755)
  CHROME_NATIVE_HOST_DIR.mkdir(parents=True, exist_ok=True)

  destination = CHROME_NATIVE_HOST_DIR / f"{HOST_NAME}.json"
  destination.write_text(json.dumps(manifest(args.chrome_extension_id), indent=2) + "\n", encoding="utf-8")

  print(f"Installed native host manifest: {destination}")
  print(f"Native host executable: {host_path()}")
  if not args.chrome_extension_id:
    print("")
    print("Next: load extension/ in chrome://extensions, copy its extension ID, then run:")
    print(f"  python3 native-host/install.py --chrome-extension-id EXTENSION_ID")


if __name__ == "__main__":
  main()
