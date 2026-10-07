<div align="center">

# 🌋 Adreno Mesa Drivers Toolkit (Turnip)

**The definitive, automated build and patch integration pipeline for Qualcomm Adreno GPUs.**

[![Build Status](https://img.shields.io/badge/Build-Passing-success?style=for-the-badge&logo=githubactions)](https://github.com/ovsky/Vulkan-Turnip-Adreno-Driver/actions)
[![Vulkan API](https://img.shields.io/badge/Vulkan-1.3-red?style=for-the-badge&logo=vulkan)](https://www.vulkan.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.style=for-the-badge)](LICENSE)
[![Mesa Mainline](https://img.shields.io/badge/Mesa-Upstream-orange?style=for-the-badge&logo=linux)](https://gitlab.freedesktop.org/mesa/mesa)

*Bringing desktop-class Vulkan APIs to Android emulation via the `libadrenotools` injection model.*

</div>

Verify a download:

## 📑 Table of Contents
- [Architecture & Ecosystem](#-architecture--ecosystem)
- [Release Channels & Variant Matrix](#-release-channels--variant-matrix)
- [Installation & Usage](#-installation--usage)
  - [Standard Injection (Emulators)](#standard-injection-emulators)
  - [Real-World Example: Winlator Pipeline](#-real-world-example-winlator-pipeline)
- [The Build System (Local & CI)](#-the-build-system-local--ci)
  - [Host Prerequisites](#host-prerequisites)
  - [Compilation Commands](#compilation-commands)
  - [Advanced Environment Variables](#advanced-environment-variables)
- [Strict Patch Verification Guarantee](#-strict-patch-verification-guarantee)
- [Upstream Synchronization](#-upstream-synchronization)
- [Troubleshooting & FAQ](#-troubleshooting--faq)
- [Acknowledgements & Credits](#-acknowledgements--credits)

---

## 🏗 Architecture & Ecosystem

This repository provides highly optimized, pre-compiled binaries of **Turnip**—the open-source Freedreno Vulkan driver for Qualcomm Adreno GPUs. 

Rather than relying on stagnant, personal Mesa forks, this toolkit dynamically compiles directly from **upstream Mesa mainline**. During the pipeline execution, it algorithmically injects and verifies critical community patches (KGSL correctness, OneUI workarounds, gen8 instruction sets) to ensure maximum compatibility with the modern emulation ecosystem.

**Supported Injection Targets:**
*   **Translation Layers:** Winlator, Termux-X11 + Box64, Cassia (upcoming)
*   **Emulators:** Yuzu, Sudachi, Suyu, Vita3K, Skyline, Strato, NetherSX2
*   **Any application utilizing the `libadrenotools` hooking framework.**

---

## 🧬 Release Channels & Variant Matrix

Every nightly CI run strictly publishes one unified ZIP archive per GPU architecture variant, accompanied by a cryptographically secure `SHA256SUMS.txt`. 

### The Naming Convention
Our release nomenclature guarantees deterministic auditing. A release cannot claim a version it does not contain.

```text
Turnip_A8xx-Patched-Patchs1_mesa<version>_vk<version>_R<build>_<commit>.zip
        └─── variant ───────┘ └─ Mesa ─┘ └ VK ┘ └build┘ └── commit ──┘
```

### 🔀 Variant Target Matrix
All variants are derived from the exact same Mesa commit during a single CI run to prevent drift.

| Variant Code | Target Architecture | Kernel / OS Specifics | Patch Inclusions & Modifications |
| :--- | :--- | :--- | :--- |
| `a7xx` | Adreno 6xx / 7xx | Standard Android / KGSL | Upstream Mesa<br>• D32S8 `EARLY_Z_LATE_Z` workaround reverted<br>• `has_early_preamble` forcibly disabled<br>• KGSL correctness tier applied |
| `a7xx-oneui` | Adreno 6xx / 7xx | Samsung OneUI (Android 13/14) | Base `a7xx` spec **+** Snapdragon 8 Gen 2 (8g2) overlay flicker & texture-corruption mitigation. |
| `a8xx-patchs2` | Adreno 8xx (Gen8) | Next-Gen SoCs | KGSL + Gen8 correctness tiers<br>• Gen8 hardware stack mapping<br>• 64 KiB shared memory unlocking<br>• A840v2 compatibility |
| `a8xx-patchs1` | Adreno 8xx (Gen8) | Experimental / Bionic | KGSL Tier<br>• Android/Bionic gralloc recipe (AIMapper + UBWC swapchain)<br>• `VK_EXT_mesh_shader` software emulation<br>• Half-warp subgroups & retired-IB caching |

> ⚠️ **Architectural Notice for Gen8 (Adreno 8xx):** 
> Qualcomm's gen8 architecture support is currently maturing in Mesa upstream. If you experience visual regressions in undocumented software, fallback to `patchs2` unless your workload specifically demands the Bionic AIMapper gralloc provided by `patchs1`.

---

## 🚀 Installation & Usage

### Standard Injection (Emulators)

> **Important:** Do *not* extract the downloaded ZIP archive. The `libadrenotools` wrapper expects the compressed archive format.

1. Navigate to the [Releases Page](../../releases) and download the appropriate `Turnip_*.zip` for your device.
2. Open your target software (e.g., Yuzu, Winlator).
3. Navigate to **Settings → GPU → Custom Driver → Install / Add New Driver**.
4. Select the downloaded `.zip` file.
5. Set the newly installed driver as the **Active Driver**.
6. *Mandatory:* Clear your application's shader cache to prevent pipeline compilation panics on the first boot.

<details>
<summary><b>🔐 Verify Cryptographic Integrity (Click to expand)</b></summary>
Always verify your downloads to prevent corrupted binaries from crashing your system kernel.

```bash
# Download the manifest and the driver
curl -OL https://github.com/ovsky/Vulkan-Turnip-Adreno-Driver/releases/latest/download/SHA256SUMS.txt
curl -OL <driver_url>.zip

# Verify
sha256sum -c SHA256SUMS.txt
```
</details>

### 📊 Real-World Example: Winlator x86_64 Translation Pipeline

If you are running complex PC games on Android via Winlator, the Turnip driver bypasses the proprietary Qualcomm driver overhead. Here is how this architecture looks in practice:

1. **The Game (e.g., Cyberpunk 2077)** issues DirectX 12 calls.
2. **VKD3D / DXVK** intercepts these calls and translates them into Vulkan instructions.
3. **Winlator (Box64)** translates the x86_64 CPU instructions to ARM64.
4. **libadrenotools** intercepts the system's Vulkan request and injects **our Turnip Driver**.
5. **Turnip (a7xx-oneui variant)** takes the Vulkan instructions and converts them to low-level Adreno Freedreno/KGSL instructions, passing them directly to the Linux Kernel, resulting in a 40-100% FPS boost and fixing native Qualcomm texture rendering bugs.

---

## 🛠 The Build System (Local & CI)

Building this driver requires a robust Linux environment. The cross-compilation pipeline targets an `aarch64` Android environment. **Native Windows and macOS hosts are unsupported for compilation** (though they can run linting tests).

### Host Prerequisites (Ubuntu 22.04+ / Debian)

```bash
# Install core build utilities, compilers, and lexers
sudo apt-get update && sudo apt-get install -y \
    git ca-certificates curl unzip zip patch \
    ninja-build meson patchelf flex bison glslang-tools \
    python3 python3-pip ccache build-essential clang lld llvm

# Mako is required by Mesa's internal python scripts to generate C headers
pip3 install --break-system-packages mako pyyaml
```
*Note: The Android NDK (approx. 600 MB) is dynamically fetched into `turnip_workdir/` during the initialization phase.*

### Compilation Commands

The CLI wrapper `build_turnip.sh` manages the Meson build system, NDK linking, and artifact generation.

```bash
# Display capability matrix and available targets
./build_turnip.sh --list                

# Compile a specific architectural variant (Generates ZIP in workdir)
./build_turnip.sh --variant a8xx-patchs1 

# Execute sequential compilation of all four variants
./build_turnip.sh --all                  

# Dry Run: Calculate build plan, resolve dependencies, but skip LLVM compilation
./build_turnip.sh --dry-run -v a7xx      
```

### ⚙️ Advanced Environment Variables

For repository maintainers and advanced developers, the build pipeline behavior can be strictly controlled via standard environment variables:

| Variable | Type | Default | Description |
| :--- | :---: | :--- | :--- |
| `MESA_REPO` / `MESA_REF` | `string` | *(from YAML)* | Override the upstream Mesa repository or branch/tag. |
| `MESA_COMMIT` | `string` | `HEAD` | Pin compilation to an exact Mesa Git SHA for bisecting. |
| `TURNIP_LTO` | `bool` | `1` | Enable Link-Time Optimization. Reduces binary size and improves draw-call overhead, but increases compile time. |
| `USE_CCACHE` | `bool` | `0` | Wrap `clang` in `ccache`. Highly recommended for iterative local development. |
| `COMMON_PATCHES` | `bool` | `1` | Toggle the injection of the cross-cutting KGSL correctness tier. |
| `A7XX_REVERT_D32S8` | `bool` | `1` | `1` strips the upstream D32S8 workaround. `0` maintains upstream behavior. |
| `BUILD_VERSION` | `string` | `$(date)` | Semantic string injected into the final `meta.json` and ZIP file name. |

---

## 🛡 Strict Patch Verification Guarantee

The defining feature of this repository is our **Zero-Silent-Failure Policy**. A community patch is not merely applied; it is cryptographically and structurally verified before packaging.

1. **Greppable AST Verification:** Every KGSL/gen8 correctness patch must apply cleanly to the Mesa tree. The pipeline then uses AST-aware grep checks to ensure the patch's logic is genuinely active in the source code. If Mesa refactors an anchor and the patch silently fails to apply, **the build intentionally crashes**.
2. **Device Table Syntax:** `freedreno_devices.py` is syntax-checked at every state transition. Because this script dynamically generates the GPU hardware table, a missing comma here results in catastrophic device failure.
3. **Binary Auditing:** Before `libvulkan_freedreno.so` is zipped, it is scanned to ensure it is a 64-bit little-endian **AArch64 `ET_DYN`** ELF binary, and it must successfully export `vkGetInstanceProcAddr`. This prevents CI from passing a binary that lacks the Vulkan entry point.

For a deeply technical breakdown of the patching tiers, consult [`docs/PATCHES.md`](docs/PATCHES.md) and [`patches/README.md`](patches/README.md).

---

## 🔄 Upstream Synchronization

Because Mesa and community developers move fast, we track upstream sources via `upstreams.yml`. This acts as the single source of truth for repository heads.

To manually audit upstream drift:
```bash
# Output a matrix of recorded SHAs vs Live Remote Heads
python3 scripts/check_upstreams.py            

# Exit code 1 if upstream has drifted (Used by CI to trigger syncs)
python3 scripts/check_upstreams.py --strict  
```
*Our GitHub Actions automatically run this twice weekly to ensure community fixes never quietly rot.*

---

## ❓ Troubleshooting & FAQ

**Q: I installed `a7xx-oneui` on my Samsung S24, but my emulator instantly crashes.**
> A: Ensure you have cleared your application's shader cache. Turnip compiles shaders differently than Qualcomm's proprietary driver. Old cached shaders will cause pipeline panics.

**Q: I'm trying to build locally, but it fails at `linking libvulkan_freedreno.so`.**
> A: This is usually an Out-Of-Memory (OOM) error during Link-Time Optimization (LTO). Try building with `export TURNIP_LTO=0 ./build_turnip.sh --variant <variant>`.

**Q: Why doesn't Turnip work on my Mali (MediaTek/Exynos) GPU?**
> A: Turnip is strictly built on the Freedreno architecture, which requires Qualcomm Adreno hardware. Mali GPUs require the Panfrost driver ecosystem.

---

## 🏆 Acknowledgements & Credits

This automated pipeline stands on the shoulders of giants. The emulation and driver community is driven by the relentless work of the following individuals:

*   **StevenMXZ** — Architecture of the gen8 branches, Android/Bionic packaging logic, and maintaining the core patch sets.
*   **K11MCH1** — Advanced packaging logic, and the reverse-engineering of Quest 3 / Ray-Ban vendor driver extractions.
*   **MrPurple666** — Pioneer of the unified A6xx/A7xx/A8xx driver architecture and extensive Quality Assurance.
*   **Rob Clark** *(Qualcomm / Mesa)* — The principal architect behind the upstream Adreno 8xx gen8 driver.
*   **The Testers & Debuggers:** DiskDVD, Vauzi-17, Karmjit Mahil, Hugo, and the countless community members parsing logs to fix vertex explosions.

### ⚖️ License

*   **Build Tooling & CI Pipeline:** MIT License — See [`LICENSE`](LICENSE).
*   **Mesa Source & Driver Binaries:** Inherits Mesa's MIT/X11 License. 
*   **Android NDK:** Governed by Google's standard SDK license.
*   **Imported Patches:** Retain their original author headers. See [`docs/PATCHES.md`](docs/PATCHES.md) for individual attribution.
