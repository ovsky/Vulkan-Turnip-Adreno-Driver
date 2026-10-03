#!/usr/bin/env python3
"""Derive authoritative build facts from a Mesa source tree.

The release naming and ``meta.json`` used to be hard-coded strings that drifted
out of date the moment Mesa moved. This module reads the truth out of the tree
that is actually about to be compiled, so a release can never claim a Mesa or
Vulkan version it does not contain.

Emits a single JSON object on stdout. Exits non-zero, with the reason on
stderr, when a required fact cannot be established -- callers must never fall
back to a guessed version.

Usage:
    mesa_facts.py <mesa-dir>
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

#: ``VK_MAKE_API_VERSION_VARIANTS`` is the modern spelling; the older
#: ``VK_MAKE_API_VERSION`` still appears in some vendored headers.
_API_VERSION_CALLS = (
    r"VK_MAKE_API_VERSION_VARIANTS\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)",
    r"VK_MAKE_API_VERSION\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)",
)

_HEADER_VERSION_COMPLETE = re.compile(
    r"^\s*#\s*define\s+VK_HEADER_VERSION_COMPLETE\s+(?P<body>.+?)\s*$", re.MULTILINE
)
_HEADER_VERSION = re.compile(r"^\s*#\s*define\s+VK_HEADER_VERSION\s+(\d+)\s*$", re.MULTILINE)
_API_VERSION_MAJOR = re.compile(
    r"^\s*#\s*define\s+VK_API_VERSION_(?P<major>\d+)_(?P<minor>\d+)\s+VK_MAKE_API_VERSION\(\s*\d+\s*,\s*(?P=minor)\s*,\s*\d+\s*\)",
    re.MULTILINE,
)


class FactsError(RuntimeError):
    """Raised when a required build fact cannot be determined."""


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError as exc:
        raise FactsError("cannot read {}: {}".format(path, exc)) from exc


def mesa_version(mesa_dir: str) -> str:
    """Return the Mesa version string from the ``VERSION`` file.

    Tracked as ``Mesa 26.2.0-devel``; the trailing ``-devel`` matters to
    anyone reading a release, so it is preserved verbatim.
    """
    raw = _read(os.path.join(mesa_dir, "VERSION")).strip()
    if not raw:
        raise FactsError("VERSION file is empty")
    if not re.match(r"^\d+\.\d+", raw):
        raise FactsError("VERSION file does not look like a Mesa version: {!r}".format(raw))
    return raw


def _git(mesa_dir: str, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", mesa_dir, *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        raise FactsError("git {} failed: {}".format(" ".join(args), exc)) from exc
    return out.stdout.strip()


def vulkan_version(mesa_dir: str) -> str:
    """Return the Vulkan API version the driver will report, as ``1.4.348``.

    Read from ``VK_HEADER_VERSION_COMPLETE``, which is what Mesa compiles
    against, so it cannot drift from the built binary. Falls back to the
    individual ``VK_API_VERSION_major_minor`` defines plus
    ``VK_HEADER_VERSION`` when the complete macro is absent.
    """
    header = _read(os.path.join(mesa_dir, "include", "vulkan", "vulkan_core.h"))

    complete = _HEADER_VERSION_COMPLETE.search(header)
    if complete:
        for pattern in _API_VERSION_CALLS:
            match = re.search(pattern, complete.group("body"))
            if match:
                parts = [int(p) for p in match.groups()[:3]]
                return "{}.{}.{}".format(*parts)

    major = _API_VERSION_MAJOR.search(header)
    patch = _HEADER_VERSION.search(header)
    if major and patch:
        return "{}.{}.{}".format(
            major.group("major"), major.group("minor"), patch.group(1)
        )

    raise FactsError(
        "could not determine the Vulkan header version from vulkan_core.h; "
        "refusing to guess a version for the release name"
    )


def collect(mesa_dir: str) -> dict:
    if not os.path.isdir(mesa_dir):
        raise FactsError("mesa directory does not exist: {}".format(mesa_dir))

    sha = _git(mesa_dir, "rev-parse", "HEAD")

    try:
        branch = _git(mesa_dir, "rev-parse", "--abbrev-ref", "HEAD")
    except FactsError:
        branch = "unknown"

    version = mesa_version(mesa_dir)
    # A detached checkout is normal here (we pin a SHA), and "HEAD" is a
    # useless branch name; report it as detached instead.
    if branch == "HEAD":
        branch = "detached"

    return {
        "mesa_version": version,
        "mesa_major_minor": ".".join(version.split(".")[:2]),
        "vulkan_version": vulkan_version(mesa_dir),
        "git_sha": sha,
        "git_sha_short": sha[:12],
        "git_branch": branch,
        "git_commit_date": _git(mesa_dir, "log", "-1", "--format=%cI"),
    }


def main(argv: list) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        facts = collect(argv[1])
    except FactsError as exc:
        print("mesa_facts: {}".format(exc), file=sys.stderr)
        return 1
    print(json.dumps(facts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))