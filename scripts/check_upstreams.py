#!/usr/bin/env python3
"""Check whether the community sources in ``upstreams.yml`` have moved.

This is the automation behind "keep merging the community's fixes". Mesa and
the driver forks move constantly; the failure mode is not noticing, which
silently turns "built from the latest" into "built from whatever was current
eight months ago".

For every source with a resolvable git ref we ask the remote for its head SHA
and compare it with the ``observed_head`` recorded in the manifest. Anything
that moved is reported so CI can raise it.

Availability is respected on purpose: a source marked ``binary-only`` publishes
no code to compare against, so reporting it as stale would be noise.

Usage:
    check_upstreams.py [--manifest upstreams.yml] [--timeout 30] [--json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    print(
        "check_upstreams: PyYAML is required (pip install pyyaml)",
        file=sys.stderr,
    )
    raise SystemExit(3)

#: Availability values that mean "there is no git ref to compare".
_NO_GIT_REF = {"binary-only", "public-partial"}

_MANIFEST_VERSION = 1


class ManifestError(RuntimeError):
    """Raised when the manifest cannot be trusted."""


def load_manifest(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ManifestError("{} is not a YAML mapping".format(path))

    version = data.get("schema_version")
    if version != _MANIFEST_VERSION:
        raise ManifestError(
            "unsupported schema_version {!r} (this tool understands {})".format(
                version, _MANIFEST_VERSION
            )
        )
    if not isinstance(data.get("base"), dict):
        raise ManifestError("manifest has no 'base' section")
    if not isinstance(data.get("sources"), list):
        raise ManifestError("manifest has no 'sources' list")
    return data


def ref_matches(remote_ref: str, pattern: str) -> bool:
    """True when a remote ref name satisfies an ``ls-remote`` pattern.

    ``git ls-remote <url> A8xx`` returns ``refs/heads/A8xx``, so the short
    pattern in the manifest must be matched against the tail of the qualified
    name, not compared to it verbatim.
    """
    if pattern in ("HEAD", "head"):
        return remote_ref.endswith("/HEAD") or remote_ref == "HEAD"
    if remote_ref == pattern:
        return True
    if pattern.startswith("refs/"):
        return remote_ref == pattern
    return remote_ref.split("/")[-1] == pattern


def ls_remote_head(url: str, ref: str, timeout: int) -> Optional[str]:
    """Return the SHA the remote has for ``ref``, or None if unresolvable."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", url, ref],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return "error: {}".format(exc)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and ref_matches(parts[1], ref):
            return parts[0]
    return None


def check(manifest: dict, timeout: int) -> List[dict]:
    findings: List[dict] = []

    base = manifest["base"]
    findings.append(_check_one(base, "base", timeout, required=True))

    for source in manifest["sources"]:
        findings.append(_check_one(source, "community", timeout, required=False))

    return findings


def _check_one(entry: dict, kind: str, timeout: int, required: bool) -> dict:
    identifier = entry.get("id", "<unnamed>")
    url = entry.get("url") or entry.get("repo") or ""
    ref = entry.get("ref", "")
    availability = entry.get("availability", "public")
    recorded = entry.get("observed_head")
    role = entry.get("role", "reference")

    result = {
        "id": identifier,
        "kind": kind,
        "role": role,
        "url": url,
        "ref": ref,
        "availability": availability,
        "recorded": recorded,
        "head": None,
        "status": "unknown",
        "detail": "",
    }

    if availability in _NO_GIT_REF:
        result["status"] = "not-tracked"
        result["detail"] = "no portable source published; nothing to compare"
        return result

    if not url or not ref:
        result["status"] = "incomplete"
        result["detail"] = "manifest entry has no url/ref"
        return result

    head = ls_remote_head(url, ref, timeout)
    if head is None:
        result["status"] = "unresolvable"
        result["detail"] = "git ls-remote found no ref {!r}".format(ref)
        return result
    if head.startswith("error:"):
        result["status"] = "unreachable"
        result["detail"] = head
        return result

    result["head"] = head
    if recorded is None:
        result["status"] = "unpinned"
        result["detail"] = "no observed_head recorded yet; set it to pin this source"
    elif str(recorded).startswith(head) or head.startswith(str(recorded)):
        result["status"] = "current"
    elif entry.get("drift_expected"):
        # The Mesa base always moves, and that is the intent: we want newest.
        result["status"] = "moved-expected"
        result["detail"] = "{} -> {} (latest is what we want)".format(str(recorded)[:12], head[:12])
    else:
        result["status"] = "moved"
        result["detail"] = "{} -> {}".format(str(recorded)[:12], head[:12])
    return result


def to_markdown(findings: List[dict]) -> str:
    lines = [
        "| Source | Role | Ref | Recorded | Head | State |",
        "|--------|------|-----|----------|------|-------|",
    ]
    for item in findings:
        lines.append(
            "| [{id}]({url}) | {role} | `{ref}` | {recorded} | {head} | {status} |".format(
                id=item["id"],
                url=item["url"] or "-",
                role=item["role"],
                ref=item["ref"] or "-",
                recorded=(item["recorded"] or "-")[:12],
                head=(item["head"] or "-")[:12],
                status=item["status"],
            )
        )
    return "\n".join(lines)


def summarise(findings: List[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in findings:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return counts


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="upstreams.yml")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if the Mesa base or any tracked source has moved",
    )
    args = parser.parse_args(argv[1:])

    try:
        manifest = load_manifest(args.manifest)
    except (ManifestError, OSError) as exc:
        print("check_upstreams: {}".format(exc), file=sys.stderr)
        return 2

    findings = check(manifest, args.timeout)

    if args.json:
        print(json.dumps({"findings": findings, "summary": summarise(findings)}, indent=2))
    else:
        print(to_markdown(findings))

    drifted = [f for f in findings if f["status"] in ("moved", "unpinned")]
    broke = [f for f in findings if f["status"] in ("unreachable", "incomplete")]

    if args.strict and (drifted or broke):
        for item in drifted:
            print("drifted: {} ({})".format(item["id"], item["detail"]), file=sys.stderr)
        for item in broke:
            print("broken:  {} ({})".format(item["id"], item["detail"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))