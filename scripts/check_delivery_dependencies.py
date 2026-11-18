"""Fail before starting services if delivery attachment dependencies are missing."""

import importlib
import subprocess
import sys


def main():
    missing = []
    for module, package in (("pypdf", "pypdf==7.0.1"), ("PIL.Image", "Pillow==12.3.0"), ("mammoth", "mammoth==1.12.0")):
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    if missing:
        print("Delivery attachment dependencies are unavailable for: " + sys.executable, file=sys.stderr)
        print("Install with: " + subprocess.list2cmdline([sys.executable, "-m", "pip", "install", *missing]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
