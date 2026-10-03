#!/usr/bin/env python3
"""Test suite for the build toolkit's Python helpers.

Covers the happy path and, deliberately, every failure path that would
otherwise surface as a confusing error forty minutes into a Mesa compile:
missing anchors, refactored anchors, malformed manifests, wrong-architecture
binaries and corrupt archives.

Standard library only -- run it anywhere:

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import contextmanager

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import apply_d32s8_revert  # noqa: E402
import check_upstreams  # noqa: E402
import make_meta  # noqa: E402
import mesa_facts  # noqa: E402
import optional_step  # noqa: E402
import verify_package  # noqa: E402

VULKAN_CORE_MODERN = """
#ifndef VK_HEADER_VERSION
#define VK_HEADER_VERSION 348
#define VK_HEADER_VERSION_COMPLETE VK_MAKE_API_VERSION_VARIANTS(1, 4, 348, 0)
#endif
"""

VULKAN_CORE_LEGACY = """
#define VK_HEADER_VERSION 271
#define VK_API_VERSION_1_3 VK_MAKE_API_VERSION(1, 3, 271)
#define VK_HEADER_VERSION_COMPLETE VK_MAKE_API_VERSION(1, 3, 271)
"""

# No COMPLETE macro and no VK_API_VERSION_x_y: must be an error, never a guess.
VULKAN_CORE_BARE = """
#define VK_HEADER_VERSION 270
"""

D32S8_BLOCK = """\
   if (depth_format == VK_FORMAT_D32_SFLOAT_S8_UINT) {
      zmode = A6XX_LATE_Z;
   }

   /* A630/A650 hangs with this combination of states. */
   if (CHIP == A6XX && zmode == A6XX_EARLY_Z_LATE_Z && depth_format == VK_FORMAT_D32_SFLOAT_S8_UINT &&
       fs_kill_fragments)
      zmode = A6XX_LATE_Z;

   if ((stencil_test_enable && depth_format == VK_FORMAT_S8_UINT) ||
"""

D32S8_ALREADY_GONE = """\
   if (depth_format == VK_FORMAT_D32_SFLOAT_S8_UINT) {
      zmode = A6XX_LATE_Z;
   }

   if ((stencil_test_enable && depth_format == VK_FORMAT_S8_UINT) ||
"""


@contextmanager
def chdir(path: str):
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def make_elf(machine: int = 183, elf_class: int = 2, endian: int = 1,
             etype: int = 3, extra: bytes = b"") -> bytes:
    """Build a minimal but structurally valid ELF64 header."""
    header = bytearray(64)
    header[0:4] = b"\x7fELF"
    header[4] = elf_class
    header[5] = endian
    struct.pack_into("<H", header, 16, etype)
    struct.pack_into("<H", header, 18, machine)
    return bytes(header) + extra


def good_library_bytes() -> bytes:
    # Bigger than verify_package's plausibility floor, and it exports the
    # entrypoint the AdrenoTools loader needs.
    return make_elf(extra=b"vkGetInstanceProcAddr\x00" + b"\x00" * (600 * 1024))


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


class TestMesaFacts(unittest.TestCase):
    def test_vulkan_version_from_complete_modern(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "include", "vulkan"))
            with open(os.path.join(tmp, "include", "vulkan", "vulkan_core.h"), "w") as handle:
                handle.write(VULKAN_CORE_MODERN)
            self.assertEqual(mesa_facts.vulkan_version(tmp), "1.4.348")

    def test_vulkan_version_from_legacy_make_api_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "include", "vulkan"))
            with open(os.path.join(tmp, "include", "vulkan", "vulkan_core.h"), "w") as handle:
                handle.write(VULKAN_CORE_LEGACY)
            self.assertEqual(mesa_facts.vulkan_version(tmp), "1.3.271")

    def test_vulkan_version_falls_back_to_api_version_macros(self):
        source = "#define VK_HEADER_VERSION 348\n#define VK_API_VERSION_1_4 VK_MAKE_API_VERSION(1, 4, 348)\n"
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "include", "vulkan"))
            with open(os.path.join(tmp, "include", "vulkan", "vulkan_core.h"), "w") as handle:
                handle.write(source)
            self.assertEqual(mesa_facts.vulkan_version(tmp), "1.4.348")

    def test_vulkan_version_refuses_to_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "include", "vulkan"))
            with open(os.path.join(tmp, "include", "vulkan", "vulkan_core.h"), "w") as handle:
                handle.write(VULKAN_CORE_BARE)
            with self.assertRaises(mesa_facts.FactsError):
                mesa_facts.vulkan_version(tmp)

    def test_vulkan_version_missing_header_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(mesa_facts.FactsError):
                mesa_facts.vulkan_version(tmp)

    def test_mesa_version_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "VERSION"), "w") as handle:
                handle.write("26.2.0-devel\n")
            self.assertEqual(mesa_facts.mesa_version(tmp), "26.2.0-devel")

    def test_mesa_version_empty_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "VERSION"), "w") as handle:
                handle.write("   \n")
            with self.assertRaises(mesa_facts.FactsError):
                mesa_facts.mesa_version(tmp)

    def test_mesa_version_garbage_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "VERSION"), "w") as handle:
                handle.write("not-a-version\n")
            with self.assertRaises(mesa_facts.FactsError):
                mesa_facts.mesa_version(tmp)

    def test_collect_missing_directory_raises(self):
        with self.assertRaises(mesa_facts.FactsError):
            mesa_facts.collect(os.path.join("does", "not", "exist"))

    @unittest.skipIf(not _git_available(), "git is not available")
    def test_collect_reads_real_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "include", "vulkan"))
            with open(os.path.join(tmp, "VERSION"), "w") as handle:
                handle.write("26.2.0-devel\n")
            with open(os.path.join(tmp, "include", "vulkan", "vulkan_core.h"), "w") as handle:
                handle.write(VULKAN_CORE_MODERN)

            run = lambda *a: subprocess.run(a, cwd=tmp, check=True, capture_output=True)
            run("git", "init", "-q")
            run("git", "config", "user.email", "test@example.invalid")
            run("git", "config", "user.name", "Test")
            run("git", "add", "-A")
            run("git", "commit", "-q", "-m", "init")
            # Mirror how CI consumes Mesa: pinned to a SHA, detached.
            run("git", "checkout", "-q", "--detach", "HEAD")

            facts = mesa_facts.collect(tmp)
            self.assertEqual(facts["mesa_version"], "26.2.0-devel")
            self.assertEqual(facts["mesa_major_minor"], "26.2")
            self.assertEqual(facts["vulkan_version"], "1.4.348")
            self.assertEqual(len(facts["git_sha"]), 40)
            self.assertEqual(facts["git_sha_short"], facts["git_sha"][:12])
            # The CI checkout is detached; "HEAD" would be a useless branch name.
            self.assertEqual(facts["git_branch"], "detached")


class TestMakeMeta(unittest.TestCase):
    def _args(self, out_path: str):
        return make_meta.parse_args([
            "make_meta.py", "--mesa-dir", "unused", "--variant", "a8xx-patchs1",
            "--build-version", "42", "--name", "Turnip A8xx",
            "--description", "desc with — em dash and \"quotes\"",
            "--author", "AdrenoTools community", "--out", out_path,
        ])

    def test_meta_embeds_real_versions(self):
        facts = {"mesa_version": "26.2.0-devel", "vulkan_version": "1.4.348",
                 "git_sha_short": "abcdef012345"}
        meta = make_meta.build_meta(self._args("meta.json"), facts)

        self.assertEqual(meta["schemaVersion"], 1)
        self.assertEqual(meta["packageVersion"], "42")
        self.assertEqual(meta["vendor"], "Mesa")
        self.assertEqual(meta["minApi"], 28)
        self.assertEqual(meta["libraryName"], "libvulkan_freedreno.so")
        self.assertIn("26.2.0-devel", meta["driverVersion"])
        self.assertIn("1.4.348", meta["driverVersion"])
        self.assertIn("abcdef012345", meta["driverVersion"])
        self.assertIn("1.4.348", meta["description"])

    def test_meta_is_json_serialisable_with_awkward_characters(self):
        facts = {"mesa_version": "26.2.0-devel", "vulkan_version": "1.4.348",
                 "git_sha_short": "abcdef012345"}
        meta = make_meta.build_meta(self._args("meta.json"), facts)
        # If this raises, a driver with an em dash in its description would
        # produce a manifest the AdrenoTools loader cannot read.
        reparsed = json.loads(json.dumps(meta, ensure_ascii=False))
        self.assertEqual(reparsed["name"], "Turnip A8xx")


class TestD32S8Revert(unittest.TestCase):
    def _tree(self, body: str) -> str:
        tmp = tempfile.mkdtemp()
        target = os.path.join(tmp, "src", "freedreno", "vulkan")
        os.makedirs(target)
        with open(os.path.join(target, "tu_cmd_buffer.cc"), "w", newline="") as handle:
            handle.write(body)
        return tmp

    def test_removes_the_workaround(self):
        tmp = self._tree(D32S8_BLOCK)
        with chdir(tmp):
            self.assertEqual(apply_d32s8_revert.main(["x"]), 0)
            with open(apply_d32s8_revert.TARGET, "r", newline="") as handle:
                patched = handle.read()
        self.assertNotIn("A6XX_EARLY_Z_LATE_Z", patched)
        self.assertIn("VK_FORMAT_S8_UINT", patched)  # surrounding code intact

    def test_is_idempotent_when_already_absent(self):
        tmp = self._tree(D32S8_ALREADY_GONE)
        with chdir(tmp):
            self.assertEqual(apply_d32s8_revert.main(["x"]), 0)

    def test_check_mode_does_not_write(self):
        tmp = self._tree(D32S8_BLOCK)
        with chdir(tmp):
            self.assertEqual(apply_d32s8_revert.main(["x", "--check"]), 0)
            with open(apply_d32s8_revert.TARGET, "r", newline="") as handle:
                self.assertEqual(handle.read(), D32S8_BLOCK)

    def test_missing_target_is_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            with chdir(tmp):
                self.assertEqual(apply_d32s8_revert.main(["x"]), 1)


class TestOptionalStep(unittest.TestCase):
    def _run(self, args, cwd):
        return subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "scripts", "optional_step.py"), *args],
            cwd=cwd, capture_output=True, text=True,
        )

    def test_runs_when_anchor_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "t.txt"), "w") as handle:
                handle.write("hello anchor world")
            result = self._run(
                ["--label", "ok", "--expect", "t.txt::anchor",
                 "--", sys.executable, "-c", "print('ran')"],
                tmp,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("APPLY", result.stdout)
            self.assertIn("ran", result.stdout)

    def test_skips_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                ["--label", "skipped", "--expect", "nope.txt::anchor",
                 "--", sys.executable, "-c", "raise SystemExit(9)"],
                tmp,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("SKIP", result.stdout)

    def test_skips_when_anchor_vanished(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "t.txt"), "w") as handle:
                handle.write("mesa refactored this away")
            result = self._run(
                ["--label", "refactored", "--expect", "t.txt::cs_shared_mem_size = 32 * 1024",
                 "--", sys.executable, "-c", "raise SystemExit(9)"],
                tmp,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("SKIP", result.stdout)
            self.assertIn("not found", result.stdout)

    def test_require_turns_missing_anchor_into_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(
                ["--label", "critical", "--require",
                 "--expect", "nope.txt::anchor",
                 "--", sys.executable, "-c", "pass"],
                tmp,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("REQUIRED", result.stderr)

    def test_script_error_is_always_fatal(self):
        # Anchor present but the step itself fails: that is a real bug, not a
        # refactor, so it must not be silently skipped.
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "t.txt"), "w") as handle:
                handle.write("anchor")
            result = self._run(
                ["--label", "buggy", "--expect", "t.txt::anchor",
                 "--", sys.executable, "-c", "raise SystemExit(3)"],
                tmp,
            )
            self.assertEqual(result.returncode, 3)

    def test_missing_command_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(["--label", "empty"], tmp)
            self.assertEqual(result.returncode, 2)


class TestCheckUpstreams(unittest.TestCase):
    """Drift detection, with the network stubbed out."""

    MANIFEST = """
schema_version: 1
base:
  id: mesa-upstream
  repo: https://example.invalid/mesa.git
  ref: main
  role: base
  availability: public
sources:
  - id: pinned
    url: https://example.invalid/a.git
    ref: gen8
    role: patches
    availability: public
    observed_head: aaaaaaaabbbb
  - id: binary
    url: https://example.invalid/b.git
    ref: main
    role: validation
    availability: binary-only
    observed_head: ccccccccdddd
"""

    def _load(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "upstreams.yml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.MANIFEST)
        return path

    def _check(self, heads):
        """Run check() with ls-remote replaced by a fixed answer per url."""
        original = check_upstreams.ls_remote_head
        check_upstreams.ls_remote_head = lambda url, ref, timeout: heads.get(url, "error: unmocked")
        try:
            return check_upstreams.check(check_upstreams.load_manifest(self._load()), 5)
        finally:
            check_upstreams.ls_remote_head = original

    def test_ref_matches_short_pattern_against_qualified_ref(self):
        # This is the bug that made every source look unresolvable: ls-remote
        # prints refs/heads/A8xx while the manifest says A8xx.
        self.assertTrue(check_upstreams.ref_matches("refs/heads/A8xx", "A8xx"))
        self.assertTrue(check_upstreams.ref_matches("refs/heads/main", "main"))
        self.assertTrue(check_upstreams.ref_matches("refs/tags/v1.2", "v1.2"))
        self.assertFalse(check_upstreams.ref_matches("refs/heads/gen8-clean", "gen8"))
        self.assertFalse(check_upstreams.ref_matches("refs/heads/main", "A8xx"))

    def test_ref_matches_qualified_and_head(self):
        self.assertTrue(check_upstreams.ref_matches("refs/heads/main", "refs/heads/main"))
        self.assertFalse(check_upstreams.ref_matches("refs/heads/main", "refs/tags/main"))
        self.assertTrue(check_upstreams.ref_matches("refs/remotes/origin/HEAD", "HEAD"))

    def test_bad_schema_version_rejected(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "m.yml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("schema_version: 99\nbase: {}\nsources: []\n")
        with self.assertRaises(check_upstreams.ManifestError):
            check_upstreams.load_manifest(path)

    def test_missing_sections_rejected(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "m.yml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("schema_version: 1\n")
        with self.assertRaises(check_upstreams.ManifestError):
            check_upstreams.load_manifest(path)

    def test_identical_head_is_current(self):
        findings = self._check({
            "https://example.invalid/mesa.git": "aaaa1111",
            "https://example.invalid/a.git": "aaaaaaaabbbb",
        })
        pinned = next(f for f in findings if f["id"] == "pinned")
        self.assertEqual(pinned["status"], "current")

    def test_changed_head_is_moved(self):
        findings = self._check({
            "https://example.invalid/mesa.git": "aaaa1111",
            "https://example.invalid/a.git": "999999999999",
        })
        pinned = next(f for f in findings if f["id"] == "pinned")
        self.assertEqual(pinned["status"], "moved")
        self.assertIn("999999999999", pinned["detail"])

    def test_unrecorded_head_is_unpinned(self):
        findings = self._check({
            "https://example.invalid/mesa.git": "aaaa1111",
            "https://example.invalid/a.git": "zzzz",
        })
        self.assertIn("unpinned", [f["status"] for f in findings])

    def test_binary_only_source_is_not_tracked(self):
        findings = self._check({
            "https://example.invalid/mesa.git": "aaaa1111",
            "https://example.invalid/a.git": "aaaaaaaabbbb",
        })
        binary = next(f for f in findings if f["id"] == "binary")
        self.assertEqual(binary["status"], "not-tracked")
        self.assertIsNone(binary["head"])

    def test_unreachable_source_is_reported(self):
        findings = self._check({"https://example.invalid/a.git": "error: timed out"})
        pinned = next(f for f in findings if f["id"] == "pinned")
        self.assertEqual(pinned["status"], "unreachable")

    def test_markdown_has_a_row_per_source(self):
        findings = self._check({
            "https://example.invalid/mesa.git": "aaaa1111",
            "https://example.invalid/a.git": "aaaaaaaabbbb",
        })
        table = check_upstreams.to_markdown(findings)
        self.assertEqual(table.count("\n"), len(findings) + 1)
        self.assertIn("pinned", table)
        self.assertIn("not-tracked", table)


class TestPackagingRoundTrip(unittest.TestCase):
    """End-to-end: source tree -> meta.json -> ZIP -> verification.

    Exercises the real scripts together the way build_turnip.sh drives them,
    against a synthetic Mesa tree and a synthetic AArch64 driver.
    """

    @unittest.skipIf(not _git_available(), "git is not available")
    def _mesa_tree(self) -> str:
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "include", "vulkan"))
        with open(os.path.join(tmp, "VERSION"), "w") as handle:
            handle.write("26.2.0-devel\n")
        with open(os.path.join(tmp, "include", "vulkan", "vulkan_core.h"), "w") as handle:
            handle.write(VULKAN_CORE_MODERN)
        run = lambda *a: subprocess.run(a, cwd=tmp, check=True, capture_output=True)
        run("git", "init", "-q")
        run("git", "config", "user.email", "test@example.invalid")
        run("git", "config", "user.name", "Test")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "init")
        run("git", "checkout", "-q", "--detach", "HEAD")
        return tmp

    def _build_zip(self, mesa_dir: str, out_dir: str, library: bytes) -> str:
        lib_name = "libvulkan_freedreno.so"
        os.makedirs(out_dir, exist_ok=True)

        rc = make_meta.main([
            "make_meta.py", "--mesa-dir", mesa_dir, "--variant", "a8xx-patchs1",
            "--build-version", "1842", "--name", "Turnip A8xx Patched Patchs1",
            "--description", "integration test", "--author", "AdrenoTools community",
            "--out", os.path.join(out_dir, "meta.json"),
        ])
        self.assertEqual(rc, 0)

        path = os.path.join(out_dir, "Turnip_test.zip")
        with zipfile.ZipFile(path, "w") as archive:
            archive.write(os.path.join(out_dir, "meta.json"), "meta.json")
            archive.writestr(lib_name, library)
        return path

    def test_round_trip_passes_verification(self):
        mesa_dir = self._mesa_tree()
        out_dir = tempfile.mkdtemp()
        path = self._build_zip(mesa_dir, out_dir, good_library_bytes())

        rc = verify_package.main([
            "verify_package.py", path,
            "--library-name", "libvulkan_freedreno.so",
            "--expect-package-version", "1842",
            "--expect-name-prefix", "Turnip A8xx Patched Patchs1",
            "--expect-vulkan-version", "1.4.348",
        ])
        self.assertEqual(rc, 0)

        # The generated manifest must describe the tree it was built from.
        with zipfile.ZipFile(path) as archive:
            meta = json.loads(archive.read("meta.json"))
        self.assertEqual(meta["packageVersion"], "1842")
        self.assertIn("26.2.0-devel", meta["driverVersion"])
        self.assertIn("1.4.348", meta["driverVersion"])

    def test_round_trip_rejects_host_architecture_binary(self):
        mesa_dir = self._mesa_tree()
        out_dir = tempfile.mkdtemp()
        # Exactly the failure this exists to catch: it compiled, it is in the
        # ZIP, it exports the entrypoint -- and it cannot run on the device.
        path = self._build_zip(
            mesa_dir, out_dir,
            make_elf(machine=62, extra=b"vkGetInstanceProcAddr\x00" + b"\x00" * (600 * 1024)),
        )
        rc = verify_package.main(["verify_package.py", path])
        self.assertEqual(rc, 1)


class TestRealManifest(unittest.TestCase):
    """The shipped manifest must stay parseable and self-consistent."""

    @unittest.skipUnless(os.path.exists(os.path.join(REPO_ROOT, "upstreams.yml")), "no manifest")
    def test_repository_manifest_is_valid(self):
        manifest = check_upstreams.load_manifest(os.path.join(REPO_ROOT, "upstreams.yml"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertTrue(manifest["base"]["repo"].startswith("https://"))
        self.assertTrue(manifest["base"]["ref"])

        ids = [s["id"] for s in manifest["sources"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate source ids")
        for source in manifest["sources"]:
            self.assertIn("role", source)
            self.assertIn("availability", source)
            head = source.get("observed_head")
            if head is not None:
                self.assertRegex(str(head), r"^[0-9a-f]{7,40}$",
                                 "observed_head for {} is not a commit SHA".format(source["id"]))
        self.assertTrue(manifest.get("people"), "attribution list is empty")


class TestVerifyPackage(unittest.TestCase):
    LIB = "libvulkan_freedreno.so"

    def _good_meta(self) -> dict:
        return {
            "schemaVersion": 1, "name": "Turnip A8xx",
            "description": "d", "author": "a", "packageVersion": "42",
            "vendor": "Mesa", "driverVersion": "Mesa 26.2.0-devel | Vulkan 1.4.348 | abc",
            "minApi": 28, "libraryName": self.LIB,
        }

    def _zip(self, path: str, library: bytes = None, meta=None,
             library_name: str = None, extra_member: str = None) -> str:
        library_name = library_name or self.LIB
        if library is None:
            library = good_library_bytes()
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(library_name, library)
            archive.writestr("meta.json", json.dumps(meta or self._good_meta()))
            if extra_member:
                archive.writestr(extra_member, "surprise")
        return path

    def _args(self, zip_path: str, **overrides):
        argv = ["verify_package.py", zip_path, "--library-name", self.LIB]
        for key, value in overrides.items():
            argv += ["--{}".format(key.replace("_", "-")), value]
        return verify_package.parse_args(argv)

    def test_accepts_a_good_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(os.path.join(tmp, "d.zip"))
            args = self._args(path, expect_package_version="42",
                              expect_name_prefix="Turnip A8xx",
                              expect_vulkan_version="1.4.348")
            self.assertEqual(verify_package.verify(path, args), 0)

    def test_rejects_non_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "d.zip")
            with open(path, "w") as handle:
                handle.write("not a zip")
            self.assertEqual(verify_package.verify(path, self._args(path)), 1)

    def test_rejects_x86_library(self):
        # 62 == EM_X86_64: builds fine on the CI host, useless on the device.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(os.path.join(tmp, "d.zip"),
                             library=make_elf(machine=62, extra=b"vkGetInstanceProcAddr\x00" + b"\x00" * (600 * 1024)))
            self.assertEqual(verify_package.verify(path, self._args(path)), 1)

    def test_rejects_big_endian_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(os.path.join(tmp, "d.zip"),
                             library=make_elf(endian=2, extra=b"vkGetInstanceProcAddr\x00" + b"\x00" * (600 * 1024)))
            self.assertEqual(verify_package.verify(path, self._args(path)), 1)

    def test_rejects_library_without_vulkan_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(os.path.join(tmp, "d.zip"),
                             library=make_elf(extra=b"\x00" * (600 * 1024)))
            self.assertEqual(verify_package.verify(path, self._args(path)), 1)

    def test_rejects_truncated_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(os.path.join(tmp, "d.zip"),
                             library=make_elf(extra=b"vkGetInstanceProcAddr"))
            self.assertEqual(verify_package.verify(path, self._args(path)), 1)

    def test_rejects_invalid_meta_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "d.zip")
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(self.LIB, good_library_bytes())
                archive.writestr("meta.json", "{not json")
            self.assertEqual(verify_package.verify(path, self._args(path)), 1)

    def test_rejects_meta_missing_required_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta = self._good_meta()
            del meta["libraryName"]
            path = self._zip(os.path.join(tmp, "d.zip"), meta=meta)
            self.assertEqual(verify_package.verify(path, self._args(path)), 1)

    def test_rejects_library_name_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(os.path.join(tmp, "d.zip"))
            args = verify_package.parse_args(
                ["verify_package.py", path, "--library-name", "vulkan.adreno.so"])
            self.assertEqual(verify_package.verify(path, args), 1)

    def test_rejects_extra_archive_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(os.path.join(tmp, "d.zip"), extra_member="notes.txt")
            self.assertEqual(verify_package.verify(path, self._args(path)), 1)

    def test_rejects_wrong_package_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(os.path.join(tmp, "d.zip"))
            args = self._args(path, expect_package_version="99")
            self.assertEqual(verify_package.verify(path, args), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)