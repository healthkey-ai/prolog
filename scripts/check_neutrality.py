#!/usr/bin/env python3
"""Fail if any customer-specific term appears in the repository.

The deny-list itself must not live in this public repository, so it is read
from the NEUTRALITY_DENYLIST environment variable (comma-separated, case-
insensitive terms), set as a CI secret and optionally in a developer's shell.
With the variable unset the check prints a notice and passes locally; in CI
(``CI`` set) it fails unless ``NEUTRALITY_ALLOW_UNSET`` is ``true`` (fork pull
requests, where the secret is not available).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".woff", ".woff2", ".ico", ".lock")


def main() -> int:
    raw = os.environ.get("NEUTRALITY_DENYLIST", "").strip()
    terms = [t.strip() for t in raw.split(",") if t.strip()]
    if not terms:
        print("check_neutrality: NEUTRALITY_DENYLIST not set; nothing to check")
        if os.environ.get("CI") and os.environ.get("NEUTRALITY_ALLOW_UNSET", "").lower() != "true":
            print("check_neutrality: refusing to pass silently in CI (set the secret)")
            return 1
        return 0
    pattern = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
    files = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.split()
    hits = 0
    for path in files:
        if path.endswith(SKIP_SUFFIXES):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    if pattern.search(line):
                        print(f"{path}:{lineno}: customer-specific term found")
                        hits += 1
        except OSError:
            continue
    if hits:
        print(f"check_neutrality: {hits} hit(s); remove customer-specific content")
        return 1
    print(f"check_neutrality: clean ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
