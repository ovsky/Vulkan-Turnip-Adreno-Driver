# Adreno Mesa Drivers Toolkit

Automated builds of **Turnip**, the open-source Vulkan driver for Qualcomm
Adreno GPUs, packaged for the AdrenoTools ecosystem — Eden, Winlator,
Yuzu/Sudachi/Suyu, Vita3K, Skyline/Strato and anything else using the
`libadrenotools` injection model.

The driver is compiled from **upstream Mesa mainline** and then patched with
fixes from the community driver projects, so it stays current without depending
on a personal Mesa fork that stops being updated.

> Building the driver needs Linux, the Android NDK and about 20–40 minutes per
> variant. If you only want a driver, grab a release asset — you do not need to
> build anything.

---

## Releases

Every nightly build publishes one ZIP per variant plus a `SHA256SUMS.txt`.

Package names carry everything needed to identify a build later:

```
Turnip_A8xx-Patched-Patchs1_mesa26.2.0-devel_vk1.4.348_R1842_1a2b3c4d5e6f.zip
         └─── variant ───────┘ └─ Mesa ─┘ └ VK ┘ └build┘ └── commit ──┘
```

The Mesa version, Vulkan version and commit are read from the tree that was
actually compiled, so a release can never claim a version it does not contain.

### Installing

1. Download a `Turnip_*.zip` from the [releases page](../../releases).
2. **Do not extract it.**
3. In your emulator or driver manager: **Settings → GPU → Install / Add New
   Driver**, select the ZIP.
4. Make sure it is the active driver.
5. Clear the shader cache on first boot if prompted.

Verify a download:

```bash
sha256sum -c SHA256SUMS.txt
```

---

## Variants

Pick by GPU. All four are built from the same Mesa commit in a given run.

| Variant | For | Contains |
|---------|-----|----------|
| `a7xx` | Adreno 6xx / 7xx | Upstream Mesa, D32S8 `EARLY_Z_LATE_Z` workaround reverted, `has_early_preamble` disabled, KGSL correctness tier |
| `a7xx-oneui` | Adreno 6xx / 7xx on OneUI | `a7xx` plus the 8g2 overlay flicker/texture-corruption fix |
| `a8xx-patchs2` | Adreno 8xx (gen8) | KGSL + gen8 correctness tiers, gen8 stack, 64 KiB shared memory, A840v2 |
| `a8xx-patchs1` | Adreno 8xx (gen8) | KGSL tier, Android/Bionic gralloc recipe (AIMapper + UBWC swapchain), `VK_EXT_mesh_shader` emulation, half-warp subgroups, retired-IB caching |

Adreno 8xx is Qualcomm's newest architecture and its driver support is still
maturing upstream. Expect regressions on untested titles and prefer `patchs2`
unless you specifically need what `patchs1` adds.

---

## Building locally

### Prerequisites

Ubuntu 22.04+ or Arch. The cross-compile needs an aarch64 Android target, so a
native Windows or macOS host cannot build the driver — only run the lint and
test steps.

```bash
sudo apt-get update
sudo apt-get install -y \
    git ca-certificates curl unzip zip patch \
    ninja-build meson patchelf flex bison glslang-tools \
    python3 python3-pip ccache build-essential clang lld llvm
pip3 install --break-system-packages mako
```

The NDK (~600 MB) is downloaded automatically into `turnip_workdir/` on first
run and reused afterwards.

### Build

```bash
./build_turnip.sh --list                # what can be built
./build_turnip.sh --variant a8xx-patchs1 # one variant
./build_turnip.sh --all                  # all four, sequentially
./build_turnip.sh --dry-run -v a7xx      # show the plan, change nothing
```

Packages land in `turnip_workdir/`, each with a `.sha256` beside it.

### Useful environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MESA_REPO` / `MESA_REF` | from `upstreams.yml` | Build a different Mesa remote or ref |
| `MESA_COMMIT` | — | Pin an exact Mesa SHA |
| `BUILD_VERSION` | CI run number, else date | Number baked into the package name |
| `TURNIP_LTO` | `1` | Link-time optimisation (smaller, faster binary) |
| `USE_CCACHE` | `0` | Wrap the compiler in ccache |
| `COMMON_PATCHES` | `1` | Skip the cross-cutting KGSL correctness tier |
| `A7XX_REVERT_D32S8` | `1` | Keep the upstream D32S8 workaround on a7xx legs |
| `WORKDIR` | `turnip_workdir` | Scratch directory |

---

## What "patched" actually guarantees

The point of this repository is that a fix is not merely *applied* but
*verified present* before anything is packaged:

- Every KGSL/gen8 correctness patch must apply cleanly **and** its effect must
  be greppable in the source tree. If it is not, the build fails. A driver that
  quietly lost a correctness fix is worse than no driver.
- Optional tuning steps are treated differently on purpose. When Mesa
  refactors an anchor away, the step is skipped with a loud warning instead of
  dying with a traceback forty minutes in.
- `freedreno_devices.py` is syntax-checked after every stage; it generates the
  device table, so a mistake there surfaces much later as something
  incomprehensible.
- Each package is verified before it can be released: archive integrity, a
  complete and parseable `meta.json`, a 64-bit little-endian **AArch64**
  `ET_DYN`, and an exported `vkGetInstanceProcAddr`. That last set is what
  catches a binary that compiled fine on the CI host but cannot load on a
  device.

See [`docs/PATCHES.md`](docs/PATCHES.md) for the per-patch catalogue and
attribution, and [`patches/README.md`](patches/README.md) for the tier layout.

---

## Keeping up with the community

[`upstreams.yml`](upstreams.yml) is the single source of truth for every driver
source we merge from, including which fixes are genuinely available and which
are not.

```bash
python3 -m pip install pyyaml
python3 scripts/check_upstreams.py           # table of recorded vs remote heads
python3 scripts/check_upstreams.py --strict  # non-zero if anything drifted
```

`Sync community sources` runs this twice a week and opens or updates a single
rolling issue when a source moves, so "we ship the community's fixes" stays
true instead of quietly rotting.

---

## CI

| Workflow | Trigger | Does |
|----------|---------|------|
| `build.yml` | nightly, manual, or on changes to build inputs | lint + tests, resolve Mesa once, build every variant in parallel, verify, publish a release |
| `sync-community-sources.yml` | twice weekly | detect upstream source drift |

Every variant in one release is built from the **same** resolved Mesa commit,
so a release can never silently mix two Mesa versions.

---

## Development

```bash
python3 -m pip install pyyaml
python3 -m unittest discover -s tests -v
```

The suite covers the release-naming logic, manifest handling, drift detection
and every package-verification failure mode — including a deliberately
wrong-architecture binary.

Conventions: conventional-commit messages, one logical change per commit,
`feature/…` or `fix/…` branches, and a PR for anything that touches build
logic or patches. CI is the gate.

---

## Acknowledgements

This project exists because of other people's work:

- **StevenMXZ** — the gen8 branches, the Android/Bionic packaging and the patch
  sets under `patches/`
- **K11MCH1** — packaging, and the Quest 3 / Ray-Ban vendor driver extractions
- **MrPurple666** — the unified A6xx/A7xx/A8xx driver, and the QA work behind it
- **Rob Clark** (Qualcomm / Mesa) — the Adreno 8xx gen8 driver
- **DiskDVD**, **Vauzi-17**, **Karmjit Mahil**, **Hugo** and everyone else who
  has shipped a fix and told someone about it

Mesa is MIT-licensed and the driver is built from it. Full credits in
[`docs/PATCHES.md`](docs/PATCHES.md).

## Licence

Build tooling: MIT — see [`LICENSE`](LICENSE). Imported patches retain their
original headers; see [`docs/PATCHES.md`](docs/PATCHES.md) for per-source
licensing. Driver binaries inherit Mesa's MIT/X11 licence; the NDK is under
Google's licence.