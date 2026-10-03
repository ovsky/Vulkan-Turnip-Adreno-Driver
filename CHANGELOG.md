# Changelog

All notable changes to this project. Releases themselves are tagged
`Turnip-R<run>-<mesa version>` on the Releases page; this file tracks the
tooling.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Four buildable driver legs (`a7xx`, `a7xx-oneui`, `a8xx-patchs2`,
  `a8xx-patchs1`) selectable with `--variant`, plus `--all`, `--list` and
  `--dry-run`.
- `upstreams.yml` as the machine-readable source manifest, recording each
  community project's role, licence, availability and observed head SHA.
- `scripts/check_upstreams.py` and a twice-weekly `Sync community sources`
  workflow that opens or updates a rolling issue when a tracked source moves.
- `scripts/mesa_facts.py`, which derives the Mesa version, Vulkan version and
  commit from the tree being compiled, and refuses to guess.
- `scripts/verify_package.py`, gating every package on archive integrity,
  `meta.json` completeness, and a 64-bit little-endian AArch64 `ET_DYN` that
  exports `vkGetInstanceProcAddr`.
- `scripts/optional_step.py`, distinguishing correctness patches (must apply,
  or the build fails) from tuning patches (skipped with a warning when Mesa
  has refactored the anchor away).
- `scripts/apply_d32s8_revert.py`, a history-independent, idempotent source
  edit replacing a `git revert` that could not work on a depth-1 checkout.
- Tiered patch application in `apply_common.sh`, with the KGSL correctness tier
  now applied to **every** variant instead of the A8xx Patchs2 leg only.
- LTO (`-Db_lto=true`), `-Dllvm=disabled` for cross-compile determinism, and
  optional ccache support.
- `SHA256SUMS.txt` alongside every published package.
- 55 unit tests covering release naming, manifest validation, drift detection,
  the D32S8 edit, step-skipping semantics, every package failure mode, and the
  build script's own argument handling.
- `--print-config`, which reports the fully resolved Mesa base, NDK, target SDK
  and patch configuration without building anything.
- `docs/PATCHES.md`: per-patch catalogue, provenance and attribution.
- `patches/README.md`: tier layout, the required-versus-optional policy, and why
  each file under `patches/legacy/` is dead.

### Changed

- **The patches are actually applied now.** `build_turnip.sh` never referenced
  the `patches/` directory, so every "fix" in this repository reached no build
  at all.
- Build base moved from the personal `whitebelyash/mesa-tu8` fork (last commit
  2026-04-25) to upstream Mesa mainline, with the fork's still-relevant fixes
  carried in `patches/`.
- Package and `meta.json` versions are now read from the compiled tree. They
  were hardcoded — every build claimed `Vulkan 1.4.348` and author `stevenmx`
  regardless of what it contained.
- Release asset names now include variant, Mesa version, Vulkan version, build
  number and commit, instead of `a8xx-gen8-V<run>.zip`.
- CI resolves one Mesa commit per run and pins every variant to it.
- Dependency check names each missing tool and prints the install command.
- `.gitattributes` pins LF for shell scripts, patches, Python and YAML. A CRLF
  shebang fails on the Linux runner, and a CRLF patch does not apply at all,
  because its context lines stop matching Mesa's LF sources.

### Fixed

- `--help` printed four lines of shell code. `usage()` read the header comment
  with a hardcoded `sed -n '2,40p'` while the block ends at line 35; it now
  walks to the first non-comment line, so editing the header cannot change the
  help output. `--print-config` is documented too.
- `--dry-run` ran `patch` from the repository root for two of the patch stages
  that had no dry-run guard. From the wrong directory that prompts to modify
  *this* repository's files. Every patch stage is now guarded, and a test
  asserts `--dry-run --all` leaves the working tree byte-identical.
- `--dry-run` no longer requires a Linux toolchain, an NDK or a Mesa checkout,
  so the plan can be inspected anywhere — including by a Windows contributor.
- `--dry-run` reports missing dependencies instead of aborting.
- `.github/workflows/build.yml` never ran: the workflow lived at the repository
  root as `build.yml`, where GitHub ignores it. The only live workflow,
  `turnip_build.yml`, omitted `ccache` while the cross-file required it, so the
  build could not have completed.
- The D32S8 workaround is reverted by editing the source instead of
  `git revert`, which failed whenever the commit was absent from a shallow
  fetch — the normal case.
- Patches anchored on `tu_autotune.cc` no longer crash the build when Mesa
  replaced the autotuner.
- Freedreno device tables are syntax-checked after patching rather than
  failing later inside the build.
- NDK clang warning suppressions are restored to the cross-file. Mesa builds
  against its own `android_stub` headers, which do not match Bionic and which
  the NDK diagnoses more strictly than the desktop GCC Mesa normally uses.

### Removed

- `build.yml` (repository root, never executed).
- `.github/workflows/turnip_build.yml` (superseded; missing `ccache`).
- `turnip_workdir/tu_gen8*.patch` — build artifacts committed to the repository.
- `patches/vk_sync_timeline.patch` — despite the name it is a complete
  replacement source file, not a diff, so `patch` could never apply it. Kept
  for reference under `patches/legacy/`.
- Loose `39751.patch`, `tu8_kgsl_26.patch` and `tu_gen8.patch` from the
  repository root — older snapshots of fixes already carried, rebased, by the
  active `patchs1`/`patchs2` sets. Moved to `patches/legacy/`.

### Documentation

- README rewritten. The previous one claimed the project built Zink (it does
  not — `-Dgallium-drivers=` is empty), advertised a "R29" release that does not
  exist, attributed the driver to `stevenmx` for code the project had not
  merged, and asserted a "25% to 40% performance boost" that was never
  measured. Those claims are removed.
- The package-name example uses placeholders rather than concrete versions, so
  it cannot be mistaken for a claim about any particular build.