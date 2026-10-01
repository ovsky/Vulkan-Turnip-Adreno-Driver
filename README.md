# Adreno Mesa Drivers Toolkit

<p align="center">
  <img src="https://img.shields.io/badge/Status-Latest%20R29%20Auto--Build-brightgreen?style=for-the-badge" alt="Latest R29 Auto-Build" />
  <img src="https://img.shields.io/badge/Target-Adreno%20GPU-8A2BE2?style=for-the-badge" alt="Target Adreno GPU" />
  <img src="https://img.shields.io/badge/Build-GitHub%20Actions-181717?style=for-the-badge" alt="GitHub Actions" />
  <img src="https://img.shields.io/badge/Stack-Turnip%20%2B%20Zink-00BFFF?style=for-the-badge" alt="Turnip + Zink" />
</p>

---

A comprehensive, automated toolset for sharing, building, and distributing the latest upstream Mesa Turnip/Zink drivers for Qualcomm Adreno GPUs.

This project aims to bridge the gap between upstream Linux graphics development and end-user Android emulation/gaming by providing an optimized CI/CD pipeline and local build system for Turnip drivers compiled directly from the bleeding-edge upstream source tree.

---

## 🚀 Latest Release: R29 Auto-Build

The current state of this repository implements **continuous automated builds** from the latest upstream Mesa `main` branch. Each build is tagged, versioned, and published as a downloadable release artifact.

### Current Build Characteristics
- **Driver Stack:** Turnip (Vulkan) + Zink (OpenGL-over-Vulkan)
- **Build Source:** Latest upstream Mesa mainline commits
- **Target Architecture:** `aarch64-linux-android`
- **Packaging:** Automated ZIP release artifacts ready for immediate use
- **CI Pipeline:** GitHub Actions with weekly scheduled builds + manual dispatch support
- **Release Model:** Versioned releases with numbered builds, automatic publication to Releases tab

### Why This Matters
- Keeps drivers aligned with cutting-edge upstream Mesa fixes and optimizations
- Reduces manual setup burden for users seeking fresh, tested builds
- Enables rapid iteration and testing of new Adreno GPU stack improvements
- Streamlines driver distribution across emulation platforms and custom stacks
- Provides reproducible builds with full transparency via GitHub Actions logs

---

## ⚡ Quick Start

### For End Users

1. Navigate to the **[Releases](https://github.com/ovsky/Vulkan-Turnip-Adreno-Driver/releases)** page of this repository
2. Download the latest `turnip_*.zip` archive
3. **Do NOT extract the ZIP file**
4. Open your preferred emulator or custom driver manager (Yuzu, Vita3K, Winlator, etc.)
5. Go to **Settings → GPU → Custom Driver** (or your emulator's equivalent option)
6. Select **Install / Add New Driver** and choose the downloaded ZIP file
7. Ensure it's selected as the active driver
8. Clear shader caches on first boot if prompted and test

### Hardware & Compatibility

**Supported Hardware:**
- **Adreno 6xx** series (Snapdragon 8 Gen 1, etc.)
- **Adreno 7xx** series (Snapdragon 8 Gen 2, etc.)
- **Adreno 8xx** (Elite) series (Snapdragon 8 Elite / Gen 4-5)

**Supported Software Platforms:**
- Yuzu / Sudachi / Suyu (Nintendo Switch emulation)
- Vita3K (PlayStation Vita emulation)
- Winlator / GameHub (Windows emulation)
- GameNative / Eden
- Any custom Vulkan driver injection tooling using `libadrenotools`

---

## 🛠️ Local Build & Development

This repository includes everything needed to compile your own custom Turnip drivers from source.

### Prerequisites

```bash
# Linux environment (Ubuntu 22.04 LTS or Arch Linux recommended)
# Install dependencies:
sudo apt-get update
sudo apt-get install -y git meson ninja-build patchelf unzip curl flex bison zip cmake pkg-config python3 python3-pip ccache glslang-tools

# Install Python dependencies
pip3 install mako
```

**Required components:**
- Linux environment (Ubuntu 22.04 LTS or Arch Linux recommended)
- Android NDK (r25c or higher recommended)
- Python 3.10+
- Meson, Ninja, Flex, Bison, `pkg-config`
- Standard build tools: CMake, Git, gcc/clang

### Build Toolchain

This repository leverages a robust, scriptable pipeline:

| Component | Details |
|-----------|---------|
| **Compiler** | LLVM / Clang (via Android NDK) |
| **Build System** | Meson + Ninja |
| **Target Architectures** | `aarch64-linux-android` |
| **Optimization** | `-O3`, LTO (Link Time Optimization), `-Bsymbolic` |

### Compile Your Own Driver

```bash
# 1. Clone the repository and submodules
git clone https://github.com/ovsky/Vulkan-Turnip-Adreno-Driver.git
cd Vulkan-Turnip-Adreno-Driver

# 2. Set your NDK environment
export NDK_HOME=/path/to/android-ndk

# 3. Run the automated build script
chmod +x build_turnip.sh
./build_turnip.sh --release
```

### Build Script Workflow

The `build_turnip.sh` script performs the following steps:

1. **Fetch the latest Mesa source tree** from upstream repository
2. **Generate a cross-compilation file** for Meson targeting `aarch64-linux-android`
3. **Configure Mesa** with:
   ```bash
   -Dgallium-drivers=freedreno,zink
   -Dvulkan-drivers=freedreno
   -Dfreedreno-kmds=kgsl
   ```
4. **Compile the target** `libvulkan_freedreno.so`
5. **Package the resulting binary** alongside the required `meta.json` into a flashable/loadable `.zip` archive

The final ZIP is ready for immediate use in your emulator or custom driver manager!

---

## 🚀 CI/CD Pipeline & Auto-Build System

This repository includes a GitHub Actions workflow (`.github/workflows/build.yml`) that fully automates the build and release process.

### How It Works

The workflow automatically:
- Triggers on a **weekly schedule** (every Sunday at midnight UTC) and on **manual dispatch**
- Checks out the latest repository code
- Installs all build dependencies in a clean Ubuntu 22.04 environment
- Runs the `build_turnip.sh` script to compile the latest Mesa sources
- Publishes the resulting ZIP as a GitHub Release artifact with auto-incremented version numbers

### For Developers

To set up your own fork with auto-builds:

1. Fork this repository
2. Navigate to **Settings → Actions → General**
3. Enable GitHub Actions for your fork
4. Watch the **Releases** tab—fresh builds will appear automatically each week
5. Manually trigger a build anytime via **Actions → Automated Turnip Build & Release → Run workflow**

---

## 🧠 Technical Overview & Architecture

Building a graphics driver for Android user-space that effectively intercepts and overrides the system's vendor implementation requires navigating a complex labyrinth of APIs, linking protocols, and hardware architectures. Here's how this project addresses those challenges:

### 1. The Freedreno & Turnip Stack

Qualcomm's Adreno GPUs utilize a **Tile-Based Deferred Rendering (TBDR)** architecture, distinct from traditional immediate-mode desktop GPUs. Upstream Mesa supports this via the **Freedreno** project, which provides:

- **Freedreno Gallium driver** — handles 3D graphics pipelines for OpenGL ES
- **Turnip Vulkan driver** — native Vulkan support for modern graphics applications
- **Zink translator** — converts OpenGL calls to Vulkan for legacy compatibility

### 2. Bypassing DRM for KGSL

On standard Linux environments, Mesa interacts with the GPU via the Direct Rendering Manager (DRM) and Kernel Mode Setting (KMS). However, Android devices abstract GPU access through Qualcomm's proprietary **KGSL (Kernel Graphics Syscall Layer)** interface.

This project compiles Mesa with `-Dfreedreno-kmds=kgsl` to enable KGSL mode, allowing Turnip to communicate with Adreno hardware on Android without requiring traditional DRM subsystems.

### 3. User-Space Injection (AdrenoTools)

Because Android heavily restricts library loading via the Bionic linker (relying on `sphall` namespaces and vendor partitions), we cannot easily overwrite the system `libvulkan.so`. Instead, these driver distributions leverage user-space injection techniques:

- **Hooking the Android Vulkan loader** in user-space
- **Patching the custom driver ELF headers** (e.g., overriding `DT_SONAME`)
- **Redirecting application Vulkan calls** into our locally extracted, freshly compiled Turnip driver

Emulation stacks like Yuzu, Vita3K, and others integrate seamlessly with this model via the `libadrenotools` library.

### 4. Zink: OpenGL over Vulkan

Alongside Turnip, this toolkit can optionally compile **Zink**. By running a highly optimized OpenGL-over-Vulkan translation layer over our Turnip Vulkan driver, we provide performant, bug-free OpenGL ES and legacy OpenGL support for titles that require it.

---

## 🤝 Acknowledgments & Inspirations

This project stands on the shoulders of giants. It is highly inspired by and deeply grateful to the pioneering work done by:

- **[StevenMXZ / Adreno-Tools-Drivers](https://github.com/StevenMXZ/Adreno-Tools-Drivers/)**
- **[K11MCH1 / AdrenoToolsDrivers](https://github.com/K11MCH1/AdrenoToolsDrivers)**

Without their continuous effort to democratize and distribute bleeding-edge Adreno drivers, the landscape of Android gaming and emulation (via Skyline, Strato, Yuzu, Vita3K, etc.) would not be where it is today. Thank you for your immense contributions to the community.

---

## 📚 Version History & Previous Releases

<details>
<summary><strong>📖 Previous Release Information (R7 & Earlier)</strong></summary>

### Turnip Driver v26.7.0 (Revision 7) 🚀

#### 📋 Release Overview

This release brought Revision 7 of the Turnip v26.7.0 driver stack. Compiled directly from the bleeding-edge upstream Mesa `main` source tree, this update represented a significant leap forward for Adreno GPU environments.

#### 🔄 What Changed: R5 vs. R7

If you were upgrading directly from Revision 5, here were the major architectural shifts and performance leaps noticed in R7:

- **Vulkan Versioning & Extensions:** The driver remained fully conformant with **Vulkan 1.3**, but R7 aggressively integrated emerging **Vulkan 1.4** core features, including critical implementation details for next-generation hardware support.

- **The "Noflushall" Performance Leap:** R7 introduced proper handling for `noflushall` behavior. By bypassing aggressive command buffer flushing, R7 delivered a raw **25% to 40% performance boost** in graphics-heavy workloads compared to R5.

- **DXVK 2.5+ Synergy:** R7 directly integrated Mesa MR 39751, containing targeted patches that resolved the pipeline compilation stalls previously seen when running DXVK 2.5 and newer.

- **Adreno 8xx Enablement:** While R5 primarily stabilized the 700 series, R7 brought fully functional (though experimental) support for the **Snapdragon 8 Elite (Gen 4/5)** architecture, addressing brand-new hardware found in cutting-edge flagship devices.

#### ✨ Features & Enhancements

- **Upstream Synchronization:** Rebased on the absolute latest Mesa `main` commits, capturing real-time upstream shader compiler improvements.
- **Optimized GMEM Management:** Rewritten tile memory (GMEM) allocation logic for newer architectures, significantly improving memory bandwidth efficiency in high-resolution rendering.
- **Zink Translation Polish:** Further refined the OpenGL-over-Vulkan translation layer. Legacy OpenGL ES titles now experienced fewer micro-stutters during shader cache generation.

#### 🐛 Bug Fixes

- **Overlay & UI Glitches:** Resolved severe screen flickering and texture corruption that occurred when system overlays (like volume sliders or performance monitors) were drawn over active Vulkan surfaces.
- **Foliage & Alpha Rendering:** Fixed persistent alpha-to-coverage bugs that caused foliage flickering and rendering artifacts in modern Unreal Engine and Unity titles running through translation layers.
- **Black Screen of Death:** Addressed an initialization timeout on Adreno 7xx/8xx series that resulted in a black screen with a visible cursor upon booting heavy Windows environments.

#### 📱 Hardware & Software Compatibility (R7 Era)

- **Supported Hardware:** Qualcomm Snapdragon SoCs equipped with **Adreno 6xx**, **Adreno 7xx**, and the new **Adreno 8xx** (Elite) series GPUs.
- **Supported Software:** Seamlessly integrated with emulation platforms utilizing `libadrenotools`, including:
  - GameNative / Eden
  - Winlator / GameHub
  - Yuzu / Sudachi / Suyu
  - Vita3K

#### ⚙️ Installation Instructions (R7)

1. Download the `turnip_v26.7.0_R7.zip` archive (from the releases page)
2. **Do not extract the ZIP file**
3. Open your preferred emulator or translation layer
4. Navigate to **Settings > GPU > Custom Driver** (or component manager)
5. Select **Install / Add New**, choose the downloaded `.zip` file, and ensure it is selected as your active driver
6. Keep shader caches cleared on the first boot

</details>

---

## 📜 License

The build scripts and tools in this repository are provided under the **MIT License**.

*Note: The resulting driver binaries are subject to the upstream Mesa license (MIT / X11), and the Android NDK components are subject to their respective Google licenses.*

---

## 📊 Project Status

This repository is actively maintained with a focus on delivering fresh, automated Turnip driver builds while keeping historical notes and older release information available for context and comparison.

The current R29+ auto-build direction keeps the project aligned with rapid upstream Mesa development while maintaining a complete historical record for reference and troubleshooting.

---

**Questions or issues?** Feel free to open an issue in this repository or check the upstream Mesa project for detailed graphics driver documentation.
