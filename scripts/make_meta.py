#!/usr/bin/env python3
"""Generate an AdrenoTools ``meta.json`` from real build facts.

``meta.json`` is the manifest the AdrenoTools loader reads to decide whether a
package is installable and which file to load. Two mistakes here are expensive:
a hand-edited version string that lies about the driver, and an unescaped
character in a description that produces invalid JSON (which some loaders
silently treat as "no manifest", leaving users with an install that does
nothing).

So: versions are read from the compiled tree by :mod:`mesa_facts`, all string
escaping is done by ``json``, and the output is re-parsed before it is written.

Usage:
    make_meta.py --mesa-dir DIR --variant a8xx-patchs1 --build-version 42 \
                 --name "Turnip A8xx Patchs1" --description "..." \
                 --author "..." --vendor Mesa --min-api 28 \
                 --library-name libvulkan_freedreno.so --out meta.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mesa_facts import FactsError, collect  # noqa: E402  (path set above)


def build_meta(args: argparse.Namespace, facts: dict) -> dict:
    driver_version = "Mesa {mesa} | Vulkan {vk} | {sha}".format(
        mesa=facts["mesa_version"],
        vk=facts["vulkan_version"],
        sha=facts["git_sha_short"],
    )
    return {
        "schemaVersion": 1,
        "name": args.name,
        "description": "{desc} [mesa {mesa}, vulkan {vk}, {sha}]".format(
            desc=args.description,
            mesa=facts["mesa_version"],
            vk=facts["vulkan_version"],
            sha=facts["git_sha_short"],
        ),
        "author": args.author,
        "packageVersion": args.build_version,
        "vendor": args.vendor,
        "driverVersion": driver_version,
        "minApi": args.min_api,
        "libraryName": args.library_name,
    }


def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesa-dir", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--build-version", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--author", required=True)
    parser.add_argument("--vendor", default="Mesa")
    parser.add_argument("--min-api", type=int, default=28)
    parser.add_argument("--library-name", default="libvulkan_freedreno.so")
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv[1:])


def main(argv: list) -> int:
    args = parse_args(argv)

    try:
        facts = collect(args.mesa_dir)
    except FactsError as exc:
        print("make_meta: {}".format(exc), file=sys.stderr)
        return 1

    meta = build_meta(args, facts)

    # Round-trip before writing. A manifest that does not parse is worse than
    # no manifest, because the failure surfaces as a silent no-op install.
    try:
        encoded = json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=False)
        json.loads(encoded)
    except (TypeError, ValueError) as exc:
        print("make_meta: generated invalid JSON: {}".format(exc), file=sys.stderr)
        return 1

    tmp_path = args.out + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.write("\n")

    stamped = dict(meta)
    stamped["_generated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print(json.dumps(stamped, indent=2, ensure_ascii=False), file=sys.stderr)
    print(encoded)

    os.replace(tmp_path, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))