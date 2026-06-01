#!/usr/bin/env python3
from pathlib import Path


HOST_NAME = "com.attentiondebugger.host"
CHROME_NATIVE_HOST_DIR = Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts"


def main():
  path = CHROME_NATIVE_HOST_DIR / f"{HOST_NAME}.json"
  if path.exists():
    path.unlink()
    print(f"Removed {path}")
  else:
    print(f"No native host manifest found at {path}")


if __name__ == "__main__":
  main()
