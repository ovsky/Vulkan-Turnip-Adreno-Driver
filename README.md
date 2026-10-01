# Adreno Mesa Drivers Toolkit

<p align="center">
  <img src="https://img.shields.io/badge/Status-Latest%20R29%20Auto--Build-brightgreen?style=for-the-badge" alt="Latest R29 Auto-Build" />
  <img src="https://img.shields.io/badge/Target-Adreno%20GPU-8A2BE2?style=for-the-badge" alt="Target Adreno GPU" />
  <img src="https://img.shields.io/badge/Build-GitHub%20Actions-181717?style=for-the-badge" alt="GitHub Actions" />
  <img src="https://img.shields.io/badge/Stack-Turnip%20%2B%20Zink-00BFFF?style=for-the-badge" alt="Turnip + Zink" />
</p>

A comprehensive, automated toolkit for sharing, building, and distributing the latest upstream Mesa Turnip/Zink drivers for Qualcomm Adreno GPUs.

This project bridges the gap between upstream Linux graphics development and Android emulation by packaging fresh Mesa builds into a usable, installable driver archive for end users and developers.

## Latest update: R29 Auto-Build

The current automation workflow builds directly from the latest upstream Mesa sources and publishes a fresh driver package as a GitHub release artifact.

### Current build characteristics
- Driver family: Turnip + Zink
- Build source: latest upstream Mesa mainline
- Architecture target: aarch64-linux-android
- Packaging: automated ZIP release artifacts
- CI workflow: GitHub Actions
- Release model: continuous auto-builds with versioned artifacts

### Why this is useful
- Keeps the driver aligned with upstream fixes and performance improvements
- Reduces manual setup for users who want fresh Mesa builds
- Provides an easy way to test new Adreno driver changes in emulation stacks
- Makes driver sharing simpler and more reproducible

---

## Highlights

- Automated upstream Mesa builds from source
- CI/CD release packaging for quick distribution
- Support for Adreno-based GPU environments and emulation use cases
- Focus on Turnip and related Mesa GPU stack improvements
- Ready for local builds and custom experimentation

---

## Quick start

1. Download the latest released ZIP from the repository Releases page.
2. Do not extract the ZIP before loading it into your emulator or custom driver manager.
3. In your app/emulator, go to the GPU or custom driver configuration screen.
4. Install or select the driver archive as the active Vulkan driver.
5. Clear shader caches on first boot if needed and test compatibility.

> Note: The release artifact is meant to be used as a packaged driver bundle, not as a source tree.

---

## Local build workflow

This repository includes a build pipeline designed to fetch Mesa, set up the Android cross-compilation environment, and package the resulting driver.

### Prerequisites
- Linux environment (Ubuntu 22.04 or similar is recommended)
- Android NDK
- Python 3.10+
- Meson, Ninja, Flex, Bison, pkg-config
- Common build tooling such as CMake and Git

### Example build

```bash
# Clone the repository
git clone https://github.com/ovsky/Vulkan-Turnip-Adreno-Driver.git
cd Vulkan-Turnip-Adreno-Driver

# Set your NDK path
export NDK_HOME=/path/to/android-ndk

# Run the automated build script
./build_turnip.sh --release
```

The script is responsible for:
1. Fetching the current Mesa source tree
2. Generating the cross-compilation environment
3. Configuring the Turnip / Freedreno build
4. Compiling the Adreno Vulkan driver
5. Packaging the result into a distributable ZIP

---

## CI/CD pipeline

The project includes automated GitHub Actions workflows that:
- trigger on a schedule and manual dispatch
- check out the repository
- install dependencies
- run the Turnip build script
- publish the generated ZIP as a GitHub Release artifact

This is the heart of the auto-build model: each run publishes a fresh driver package from the latest upstream state.

---

## Technical overview

Building a graphics driver for Android user-space requires working around the system vendor stack and hooking into the selected Vulkan loader path. The project addresses that by providing a reproducible build pipeline around upstream Mesa sources, with Turnip as the core Vulkan driver stack and Zink as an optional OpenGL-over-Vulkan translation layer.

### Core idea
- Use upstream Mesa code as the basis for the driver
- Cross-compile for Android/aarch64 target usage
- Package the resulting Vulkan binary into a driver archive
- Let emulation layers or custom driver managers consume the package

### Why it matters
This approach helps keep the driver aligned with current upstream work while making it easier to share fresh driver builds across devices, emulators, and testing environments.

---

## Compatibility

This project is aimed at Qualcomm Snapdragon systems and Adreno-based GPU environments used in Android emulation and custom GPU stacks. It is designed around the broader Turnip/Freedreno ecosystem, which is widely used in user-space driver injection and emulation workflows.

Useful ecosystem references include:
- Adreno tools / custom driver communities
- Mesa Freedreno / Turnip development work
- Emulation-focused Vulkan driver integrations

---

## Acknowledgments

This project is inspired by the broader work of the upstream Mesa, Freedreno, and Adreno driver communities. Their shared work on upstream graphics stack development, performance optimization, and driver debugging is the foundation of projects like this one.

The repository also stands on the shoulders of earlier driver-sharing efforts and community testing work that made modern Adreno Vulkan experimentation possible.

---

<details>
<summary><strong>Previous release info (kept for reference)</strong></summary>

## Previous version: Turnip v26.7.0 R7

### Release overview
This release brought Revision 7 of the Turnip v26.7.0 driver stack. It was compiled directly from the bleeding-edge upstream Mesa main source tree and represented a significant update for newer Adreno GPU environments.

### What changed in the older R7 cycle
- Vulkan versioning and extension work continued to move forward
- Performance tuning improvements were added for command-buffer handling and memory behavior
- DXVK-related pipeline stalls and compatibility work were addressed
- Targeted updates helped improve behavior for newer Adreno architectures

### Older feature highlights
- Upstream synchronization with recent Mesa mainline work
- Optimized GMEM management and memory efficiency
- Zink translation refinements for legacy OpenGL-over-Vulkan use cases
- Stability fixes for overlays, UI rendering, and black-screen initialization issues

### Compatibility notes from the previous generation
- Supported hardware included Adreno 6xx, 7xx, and newer 8xx-focused setups
- Designed to work with emulation stacks using custom Vulkan driver injection
- Installation still followed the same pattern: load a packaged ZIP as a custom driver

### Older installation flow
1. Download the archived driver package
2. Keep the ZIP intact
3. Open the desired emulator or driver manager
4. Navigate to GPU or custom driver settings
5. Install the ZIP and select it as the active driver
6. Clear shader caches on first run if prompted

</details>

---

## License

This project is distributed under the MIT License for the tooling and scripts in the repository.

The compiled driver binaries themselves remain subject to the upstream Mesa and associated component licenses used by the relevant build stack.

---

## Project status

This repository is focused on delivering fresh, automated Turnip driver builds while keeping historical notes and older release information available for context and comparison.

The latest R29 auto-build direction keeps the project aligned with rapid upstream Mesa development while preserving the earlier release history as a reference point.
