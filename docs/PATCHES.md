# Patch catalogue and attribution

Every fix in a release traces back to a row here. Sources and their current
state are machine-tracked in [`upstreams.yml`](../upstreams.yml); the
`sync-community-sources` workflow raises an issue when one of them moves.

## Sources

| Project | Role | What we take | License |
|---------|------|--------------|---------|
| [Mesa upstream](https://gitlab.freedesktop.org/mesa/mesa) | base | The driver itself, including Rob Clark's gen8/Adreno 8xx work | MIT |
| [StevenMXZ / Adreno-Tools-Drivers](https://github.com/StevenMXZ/Adreno-Tools-Drivers) (`A8xx`) | patches | The patch sets under `patches/patchs1`, `patches/patchs2`, `patches/a7xx` | GPL-3.0 |
| [whitebelyash / mesa-tu8](https://github.com/whitebelyash/mesa-tu8) | reference | Historical gen8 fixes; see "already merged" below | MIT |
| [MrPurple666 / purple-turnip](https://github.com/MrPurple666/purple-turnip) | validation | QA signal and triage; **no portable patches published** | unspecified |
| [K11MCH1 / AdrenoToolsDrivers](https://github.com/K11MCH1/AdrenoToolsDrivers) | validation | Quest 3 / Ray-Ban vendor-driver notes; **binary-only** | unspecified |

### Why Mesa mainline is the base, not a fork

`mesa-tu8` was StevenMXZ's fork and its `gen8` branch carried the A8xx work
before it reached upstream. Its last commit is 2026-04-25. Building from it
means going stale every time upstream lands something new. Everything still
wanted from it is either upstream now or captured in `patches/`, so it is kept
as a reference for archaeology rather than as a build input.

### Reported fixes we cannot merge, and why

Stated plainly rather than implied:

- **PurpleVK** (MrPurple) — an A6xx Vulkan 1.4 exposure patch shipped only
  inside their binaries. No source is published, so there is nothing to merge.
  Track their releases for manual testing instead.
- **MrPurple's public CI** (`MrPurple666/freedreno-CI`) predates the current
  Mesa layout: it downloads `mesa-main.zip` from gitlab, uses NDK r25c and API
  31, and applies no community patches at all. Their shipped drivers credit
  whitebelyash's Mesa source, which is the route by which their fixes actually
  reach the community — that is the path we follow.
- **K11MCH1's Quest 3 / Ray-Ban vendor drivers** are closed Qualcomm binaries
  unpacked from hardware. Useful as a compatibility reference for real A7xx/A8xx
  behaviour; not redistributable and not mergeable.

## Fixes, by category

### KGSL correctness — every variant

These are KGSL bugs rather than platform bugs, so they ship on all legs.

| Fix | Patch | What it prevents |
|-----|-------|------------------|
| syncobj timestamp→fd merge | `kgsl-syncobj-merge-ts-fd.patch` | A second, racing timestamp→fd conversion; duplicated submit paths leaking fds |
| Zero-timeout poll | `kgsl-zero-timeout-poll.patch` | `kgsl_timestamp_retired` returning success immediately, so the driver busy-waits instead of reporting `VK_TIMEOUT` |

### Adreno 8xx (gen8) — Patchs2 leg

| Fix | Patch | What it prevents |
|-----|-------|------------------|
| Cube-map direction sanitisation | `a8xx-cube-coord-sanitize.patch` | The `cube_coord_hang_quirk` GPU hang on crafted/invalid cube coordinates |
| Bindless descriptor invalidation | `a8xx-bindless-invalidate.patch` | Stale bindless descriptors surviving across passes (`SP_GFX_BINDLESS_INVALIDATE` never issued) |
| Index-buffer/VBO aliasing | `a8xx-kgsl-ib-vbo-alias.patch` | `KGSL_MEMFLAGS_VBO` missing, so aliased index reads fault or return garbage |
| gen8 stack | `patchs2/a8xx_gen8.patch` | Base gen8 bring-up on A8xx |
| Shared memory 32→64 KiB | `patchs2/a8xx_shared_mem.py` | Occupancy clipping on gen8 hardware |
| A840v2 entry | `patchs2/a840v2.py` | A840v2 falling back to a default config |

### Adreno 8xx (gen8) — Patchs1 leg

Carries the same A8xx fixes as its own `0003`/`0004`/`0005`, plus:

| Fix | Patch | What it prevents |
|-----|-------|------------------|
| `VK_EXT_mesh_shader` emulated with compute | `patchs1/0001` | Titles requiring mesh shaders failing outright on gen8 |
| Half-warp required subgroup size | `patchs1/0002` | Correctness/perf mismatch when a shader demands a half-warp subgroup |
| A8xx command streams via virtual file | `patchs1/0005` | KGSL command-stream fetch failing on gen8 |
| Retired A8xx IB storage caching | `patchs1/0006` | Re-reading retired index buffers every draw |
| AIMapper gralloc backend | `patchs1/android/add_aimapper_gralloc.py` | Gralloc on emulators that do not expose the AHardwareBuffer path the driver expects |
| UBWC swapchain usage bit | `patchs1/android/add_ubwc_swapchain_usage.py` | Compressed swapchains being rejected |
| Gralloc flushall fix | `patchs1/android/fix_gralloc_flushall.py` | The legacy `gmsm` magic check misreading A8xx/A840 buffers |
| A8xx device-info fix | `patchs1/android/fix_a8xx_dev_info.py` | Wrong render-mode reasons reported for no-gmem paths |

### Adreno 6xx / 7xx — a7xx legs

| Fix | Source | What it prevents |
|-----|--------|------------------|
| D32S8 `EARLY_Z_LATE_Z` revert | `scripts/apply_d32s8_revert.py` | Reverts upstream `a70d2af5`; the A630/A650 hang it guarded is rare, while the correctness cost on emulated titles is not. Disable with `A7XX_REVERT_D32S8=0`. |
| `has_early_preamble = False` on a7xx gen1 | `build_turnip.sh` | A7xx gen1 mis-executing early-preamble command streams |
| OneUI 8g2 overlay glitch | `patches/a7xx/8g2_ui_glitch.patch` | Flicker and texture corruption when system overlays draw over a Vulkan surface |

### Already merged into upstream Mesa

Carried by Mesa mainline now, so deliberately **not** re-implemented here:

| Fix | Origin |
|-----|--------|
| Adreno 8xx (gen8) driver base, KGSL UBWC_5 / UBWC_6 | Rob Clark, Qualcomm / Mesa |
| `TU_DECK_EMU` (Steam Deck advertisement, MR 38808) | Karmjit Mahil, Collabora |
| Removal of unconditional `TU_DEBUG_FLUSHALL` on a8xx | Zan Dobersek |
| Adreno 710/720 support | Vauzi-17, via whitebelyash/mesa-tu8 |
| A8xx family config refresh, A810 feature gating | DiskDVD, via whitebelyash/mesa-tu8 |

## People

| Who | Contribution |
|-----|--------------|
| Rob Clark (Qualcomm / Mesa) | Adreno 8xx gen8 driver base, KGSL UBWC_5/UBWC_6 |
| StevenMXZ (`whitebelyash`) | gen8 branches, Android/Bionic packaging, the A7xx/A8xx patch sets |
| K11MCH1 | packaging, Quest 3 and Ray-Ban vendor driver extraction |
| MrPurple666 | unified A6xx/A7xx/A8xx driver, QA and issue triage |
| DiskDVD | A8xx family config refresh, A810 feature gating |
| Vauzi-17 | Adreno 710/720 support |
| Karmjit Mahil (Collabora) | `TU_DECK_EMU` |
| Hugo | Quest 3 vendor driver extraction (via K11MCH1) |

## Licensing

Build tooling in this repository is MIT (see [`LICENSE`](../LICENSE)).
Imported patches come from StevenMXZ/Adreno-Tools-Drivers, whose repository is
GPL-3.0, and derive from Mesa code under MIT. Each patch keeps its original
header. Redistributing driver binaries built here is subject to Mesa's MIT/X11
licence; the NDK is covered by Google's licence.