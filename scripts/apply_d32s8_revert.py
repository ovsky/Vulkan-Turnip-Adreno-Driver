#!/usr/bin/env python3
"""Remove the upstream D32S8 EARLY_Z_LATE_Z workaround (a7xx legs only).

Upstream Mesa commit ``a70d2af5`` ("tu/a6xx: Work around D32S8 EARLY_Z_LATE_Z
hang") downgrades ``A6XX_EARLY_Z_LATE_Z`` to ``A6XX_LATE_Z`` for
``VK_FORMAT_D32_SFLOAT_S8_UINT`` when fragment killing is in play, because
A630/A650 hang in that state.

The AdrenoTools a7xx recipe reverts it, because on the GPUs emulators actually
present that workaround costs correctness on a large class of titles -- and a
depth+stencil hang in one title is a worse failure mode than a rare A6xx hang
on hardware nobody emulates.

This is a *source edit* rather than ``git revert`` on purpose. The build uses a
depth-1 fetch, so the commit is usually not in the available history and
``git revert`` would fail. Editing the source works regardless of how shallow
the clone is, and it is idempotent: if upstream removes the block on its own,
this reports ALREADY-ABSENT and exits 0.

Usage:
    apply_d32s8_revert.py            # edit in place, verify
    apply_d32s8_revert.py --check    # report only, never write
"""

from __future__ import annotations

import argparse
import re
import sys

TARGET = "src/freedreno/vulkan/tu_cmd_buffer.cc"

# The upstream hunk, plus the comment that introduces it and the blank line
# that follows. Whitespace inside the condition is allowed to vary because Mesa
# reformats it over time; the anchors stay literal.
_BLOCK = re.compile(
    r"(?:[ \t]*/\*[^*\n]*\*/[ \t]*\n)?"                       # leading comment
    r"[ \t]*if[ \t]*\([ \t]*CHIP[ \t]*==[ \t]*A6XX[ \t]*&&[ \t]*"
    r"zmode[ \t]*==[ \t]*A6XX_EARLY_Z_LATE_Z[^\n]*\n"         # condition, line 1
    r"(?:[ \t]*[^\n]*\n)*?"                                   # condition, rest
    r"[ \t]*zmode[ \t]*=[ \t]*A6XX_LATE_Z;[ \t]*\n"           # body
    r"(?:[ \t]*\r?\n)?",                                      # trailing blank
)

# Used to prove the fix is gone rather than assume the regex matched. Re-using
# the same matcher is deliberate: a looser "does this symbol still appear"
# check would false-positive on the unrelated A6XX_LATE_Z assignments that
# legitimately surround the hunk.


class TargetError(RuntimeError):
    """Raised when the Mesa file this step edits cannot be read."""


def read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except OSError as exc:
        raise TargetError("cannot read {}: {}".format(path, exc)) from exc


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only, do not write")
    args = parser.parse_args(argv[1:])

    try:
        source = read(TARGET)
    except TargetError as exc:
        print("apply_d32s8_revert: {}".format(exc), file=sys.stderr)
        return 1

    matches = _BLOCK.findall(source)

    if not matches:
        print("apply_d32s8_revert: ALREADY-ABSENT (upstream no longer carries it)")
        return 0

    print("apply_d32s8_revert: found {} occurrence(s) of the D32S8 workaround".format(len(matches)))

    if args.check:
        return 0

    patched, count = _BLOCK.subn("", source)
    if count != len(matches):  # pragma: no cover - defensive
        print("apply_d32s8_revert: removed {} of {} matches".format(count, len(matches)), file=sys.stderr)
        return 1

    if _BLOCK.search(patched):
        print("apply_d32s8_revert: workaround still present after edit, refusing to write", file=sys.stderr)
        return 1

    try:
        with open(TARGET, "w", encoding="utf-8", newline="") as handle:
            handle.write(patched)
    except OSError as exc:
        print("apply_d32s8_revert: cannot write {}: {}".format(TARGET, exc), file=sys.stderr)
        return 1

    print("apply_d32s8_revert: APPLIED (removed {} hunk)".format(count))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))