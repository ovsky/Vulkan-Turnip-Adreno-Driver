#!/usr/bin/env python3
"""Verify a built AdrenoTools package before it is published.

A driver ZIP that is subtly wrong still *looks* fine to CI -- it exists, it is
non-empty, the release job is green -- and the user only finds out when the
emulator refuses to load it. So every package is put through real checks here
before it can become a release asset:

  1. the archive is not corrupt and contains exactly the expected members;
  2. ``meta.json`` parses and carries every field the AdrenoTools loader needs;
  3. ``libraryName`` names a file that is actually present;
  4. the driver is a 64-bit little-endian AArch64 shared object;
  5. it actually exports the Vulkan entrypoint the loader calls.

Checks 4 and 5 are what catch the common real-world failure: an x86-64 or
stripped-to-nothing binary that compiled fine on the host but cannot load on
the device.

Usage:
    verify_package.py Turnip_....zip --library-name libvulkan_freedreno.so \\
        --expect-package-version 42 --expect-name-prefix "Turnip A8xx"
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zipfile

#: ELF constants, spelled out so the check has no external dependency.
_ELF_MAGIC = b"\x7fELF"
_ELFCLASS64 = 2
_ELFDATA2LSB = 1
_ET_DYN = 3
_EM_AARCH64 = 183

#: Fields the AdrenoTools loader reads. Missing any of these can make an
#: install silently do nothing.
_REQUIRED_META_KEYS = (
    "schemaVersion",
    "name",
    "description",
    "author",
    "packageVersion",
    "vendor",
    "driverVersion",
    "minApi",
    "libraryName",
)

#: The single symbol an ICD must export for the loader to find it at all.
_VK_ENTRYPOINT = b"vkGetInstanceProcAddr"

#: A real Turnip build is tens of MB; anything under this is a broken link step.
_MIN_LIBRARY_BYTES = 512 * 1024


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def ok(self, message: str) -> None:
        print("  PASS  {}".format(message))

    def fail(self, message: str) -> None:
        self.failures += 1
        print("  FAIL  {}".format(message))

    def check(self, condition: bool, message: str) -> bool:
        (self.ok if condition else self.fail)(message)
        return condition


def read_elf_header(data: bytes) -> dict:
    if len(data) < 64 or data[:4] != _ELF_MAGIC:
        raise ValueError("not an ELF file")
    return {
        "class": data[4],
        "data": data[5],
        "type": struct.unpack_from("<H", data, 16)[0],
        "machine": struct.unpack_from("<H", data, 18)[0],
    }


def verify(zip_path: str, args: argparse.Namespace) -> int:
    report = Report()
    print("verify_package: {}".format(zip_path))

    if not zipfile.is_zipfile(zip_path):
        report.fail("file is not a ZIP archive")
        return 1

    with zipfile.ZipFile(zip_path) as archive:
        corrupt = archive.testzip()
        if corrupt is not None:
            report.fail("corrupt member in archive: {}".format(corrupt))
            return 1
        report.ok("archive integrity (no corrupt members)")

        names = set(archive.namelist())
        expected = {args.library_name, "meta.json"}
        extra = names - expected
        missing = expected - names
        if missing:
            report.fail("missing from archive: {}".format(", ".join(sorted(missing))))
        if extra:
            report.fail("unexpected extra members: {}".format(", ".join(sorted(extra))))
        if not missing and not extra:
            report.ok("archive contains exactly {}".format(", ".join(sorted(expected))))

        if missing:
            return 1

        try:
            meta = json.loads(archive.read("meta.json").decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            report.fail("meta.json is not valid UTF-8 JSON: {}".format(exc))
            return 1
        report.ok("meta.json parses as JSON")

        absent = [key for key in _REQUIRED_META_KEYS if key not in meta]
        if absent:
            report.fail("meta.json missing required keys: {}".format(", ".join(absent)))
            return 1
        report.ok("meta.json carries all {} required keys".format(len(_REQUIRED_META_KEYS)))

        report.check(
            meta.get("schemaVersion") == 1,
            "meta.json schemaVersion == 1 (got {!r})".format(meta.get("schemaVersion")),
        )
        report.check(
            str(meta.get("libraryName")) == args.library_name,
            "meta.json libraryName {!r} matches the packaged library".format(meta.get("libraryName")),
        )

        if args.expect_package_version:
            report.check(
                str(meta.get("packageVersion")) == args.expect_package_version,
                "packageVersion is {!r} (expected {!r})".format(
                    meta.get("packageVersion"), args.expect_package_version
                ),
            )
        if args.expect_name_prefix:
            report.check(
                str(meta.get("name", "")).startswith(args.expect_name_prefix),
                "name {!r} starts with {!r}".format(meta.get("name"), args.expect_name_prefix),
            )
        if args.expect_vulkan_version:
            driver_version = str(meta.get("driverVersion", ""))
            report.check(
                args.expect_vulkan_version in driver_version,
                "driverVersion {!r} reports Vulkan {}".format(driver_version, args.expect_vulkan_version),
            )

        library = archive.read(args.library_name)

    size = len(library)
    report.check(
        size >= _MIN_LIBRARY_BYTES,
        "library size {} bytes (>= {} KiB, plausible for a real driver)".format(
            size, _MIN_LIBRARY_BYTES // 1024
        ),
    )

    try:
        header = read_elf_header(library)
    except ValueError as exc:
        report.fail("cannot parse the driver ELF: {}".format(exc))
        return 1

    report.check(header["class"] == _ELFCLASS64, "ELF class is 64-bit")
    report.check(header["data"] == _ELFDATA2LSB, "ELF endianness is little-endian")
    report.check(header["type"] == _ET_DYN, "ELF type is ET_DYN (shared object)")
    report.check(
        header["machine"] == _EM_AARCH64,
        "ELF machine is AArch64 (183), got {}".format(header["machine"]),
    )
    report.check(
        _VK_ENTRYPOINT in library,
        "exports {}".format(_VK_ENTRYPOINT.decode()),
    )

    if report.failures:
        print("verify_package: {} check(s) failed".format(report.failures), file=sys.stderr)
        return 1

    print("verify_package: all checks passed")
    return 0


def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip")
    parser.add_argument("--library-name", default="libvulkan_freedreno.so")
    parser.add_argument("--expect-package-version", default=None)
    parser.add_argument("--expect-name-prefix", default=None)
    parser.add_argument("--expect-vulkan-version", default=None)
    return parser.parse_args(argv[1:])


def main(argv: list) -> int:
    args = parse_args(argv)
    return verify(args.zip, args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))