#!/usr/bin/env python3
"""Run a patch step only when its upstream anchor is actually present.

Mesa refactors constantly, and the community patch scripts here anchor on
source text (``cs_shared_mem_size = 32 * 1024``, ``tu_autotune.cc``, ...). When
an anchor disappears the honest outcomes differ:

  * a *correctness* fix that cannot be applied must fail the build, because
    shipping a driver without it is worse than shipping nothing;
  * an *optimisation* whose anchor was refactored away should be reported and
    skipped, because failing the whole build over a tunable nobody needs is
    worse than the missing tunable.

Without this distinction a vanished anchor surfaces as a bare
``FileNotFoundError`` traceback in the middle of a 40 minute compile, which
says nothing about which step broke or whether it mattered.

Semantics:
    precondition missing  -> SKIP (exit 0) unless --require, then fatal
    script itself errors  -> always fatal; the script was expected to run

Usage:
    optional_step.py --label "shared mem" \\
        --expect src/freedreno/common/freedreno_devices.py::cs_shared_mem_size \\
        -- python3 patches/patchs2/a8xx_shared_mem.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys


class Precondition:
    def __init__(self, path: str, needle: str) -> None:
        self.path = path
        self.needle = needle

    def check(self) -> "str | None":
        """Return None when satisfied, else a human-readable reason."""
        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read()
        except OSError as exc:
            return "cannot read {}: {}".format(self.path, exc)

        if self.needle and self.needle not in content:
            return "anchor {!r} not found in {}".format(self.needle, self.path)
        return None


def parse_expect(raw: str) -> Precondition:
    # "path::needle" -- an empty needle means "the file just has to exist".
    path, sep, needle = raw.partition("::")
    if not sep:
        raise argparse.ArgumentTypeError(
            "--expect expects PATH::ANCHOR, got {!r}".format(raw)
        )
    if not path:
        raise argparse.ArgumentTypeError("--expect is missing a path: {!r}".format(raw))
    return Precondition(path, needle)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="patch step")
    parser.add_argument(
        "--require",
        action="store_true",
        help="treat a missing anchor as a build failure (use for correctness fixes)",
    )
    parser.add_argument(
        "--expect",
        action="append",
        default=[],
        type=parse_expect,
        metavar="PATH::ANCHOR",
        help="precondition; may be repeated. All must hold or the step is skipped.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv[1:])

    command = [c for c in args.command if c != "--"]
    if not command:
        print("optional_step: no command given for {!r}".format(args.label), file=sys.stderr)
        return 2

    for precondition in args.expect:
        reason = precondition.check()
        if reason is not None:
            if args.require:
                print(
                    "optional_step: {}: REQUIRED but {}".format(args.label, reason),
                    file=sys.stderr,
                )
                return 1
            print("optional_step: {}: SKIP ({})".format(args.label, reason))
            return 0

    print("optional_step: {}: APPLY".format(args.label))
    result = subprocess.run(command)
    if result.returncode != 0:
        print(
            "optional_step: {}: step ran but failed with exit {}. The anchor was "
            "present, so this is a real patch/environment error, not a refactor.".format(
                args.label, result.returncode
            ),
            file=sys.stderr,
        )
        return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))