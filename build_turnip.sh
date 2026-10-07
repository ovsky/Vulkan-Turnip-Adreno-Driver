#!/usr/bin/env bash
# =============================================================================
# build_turnip.sh - build AdrenoTools Turnip packages from upstream Mesa plus
#                   the community patch overlay in patches/
# =============================================================================
# What this produces
# -----------------
# A ZIP containing libvulkan_freedreno.so + meta.json, ready to install via
# AdrenoTools in Eden, Winlator, Yuzu/Sudachi/Suyu, Vita3K, Skyline/Strato and
# anything else using the libadrenotools injection model.
#
# The driver is compiled from upstream Mesa mainline (see upstreams.yml) with
# the fixes from StevenMXZ / K11MCH1 / MrPurple and friends applied on top, so
# it stays current without depending on a personal Mesa fork that stops being
# updated. Correctness patches must verifiably land before anything is
# packaged; optional tuning is skipped with a loud warning if Mesa has since
# refactored its anchor.
#
# Quick start
# -----------
#     ./build_turnip.sh --list                 # what can be built
#     ./build_turnip.sh --variant a8xx-patchs1 # build one
#     ./build_turnip.sh --all                  # build every variant
#     ./build_turnip.sh --dry-run -v a7xx      # show the plan, touch nothing
#
# Useful environment overrides
# ----------------------------
#     MESA_REPO MESA_REF MESA_COMMIT   pick the Mesa base
#     BUILD_VERSION                    release/build number baked into the name
#     TURNIP_LTO=0                     disable LTO
#     USE_CCACHE=1                     wrap the compiler in ccache
#     COMMON_PATCHES=0                 skip the cross-cutting KGSL tier
#     A7XX_REVERT_D32S8=0              keep the upstream D32S8 workaround
#     WORKDIR=...                      scratch directory (default turnip_workdir)
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$REPO_ROOT/scripts"
PATCHES_DIR="$REPO_ROOT/patches"
MANIFEST="$REPO_ROOT/upstreams.yml"

if [[ -t 1 ]]; then
    C_RESET=$'\033[0m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
    C_RED=$'\033[31m'; C_BLUE=$'\033[34m'; C_BOLD=$'\033[1m'
else
    C_RESET=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BLUE=""; C_BOLD=""
fi

log()   { printf '%s==>%s %s\n' "$C_BLUE$C_BOLD" "$C_RESET" "$*"; }
ok()    { printf '%s  ok%s  %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn()  { printf '%swarn%s  %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
die()   { printf '%sfail%s  %s\n' "$C_RED$C_BOLD" "$C_RESET" "$*" >&2; exit 1; }
step()  { printf '\n%s--- %s%s\n' "$C_BOLD" "$*" "$C_RESET"; }

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKDIR="${WORKDIR:-$REPO_ROOT/turnip_workdir}"
MESA_DIR="$WORKDIR/mesa"
BUILD_ROOT="$WORKDIR/build"

NDK_VERSION="${NDK_VERSION:-android-ndk-r29}"
NDK="$WORKDIR/$NDK_VERSION/toolchains/llvm/prebuilt/linux-x86_64/bin"

PLATFORM_SDK="${PLATFORM_SDK:-36}"
MIN_API="${MIN_API:-28}"
LIBRARY_NAME="${LIBRARY_NAME:-libvulkan_freedreno.so}"

TURNIP_LTO="${TURNIP_LTO:-1}"
USE_CCACHE="${USE_CCACHE:-0}"
COMMON_PATCHES="${COMMON_PATCHES:-1}"
A7XX_REVERT_D32S8="${A7XX_REVERT_D32S8:-1}"
META_AUTHOR="${META_AUTHOR:-AdrenoTools community (see docs/PATCHES.md)}"

BUILD_VERSION="${BUILD_VERSION:-${GITHUB_RUN_NUMBER:-$(date -u +%Y%m%d)}}"

VARIANT=""
DRY_RUN=0
MESA_REPO_OVERRIDE="${MESA_REPO:-}"
MESA_REF_OVERRIDE="${MESA_REF:-}"
MESA_COMMIT="${MESA_COMMIT:-}"

# ---------------------------------------------------------------------------
# Variant catalogue - the single source of truth for names and descriptions.
# ---------------------------------------------------------------------------
ALL_VARIANTS=(a7xx a7xx-oneui a8xx-patchs2 a8xx-patchs1)

variant_field() {
    case "$1" in
        a7xx)
            case "$2" in
                slug) echo "A7xx" ;;
                name) echo "Turnip A7xx" ;;
                desc) echo "Adreno 6xx/7xx: upstream Mesa with the D32S8 EARLY_Z_LATE_Z workaround reverted and has_early_preamble disabled" ;;
                gen)  echo "a7xx" ;;
            esac ;;
        a7xx-oneui)
            case "$2" in
                slug) echo "A7xx-OneUI-Glitch" ;;
                name) echo "Turnip A7xx OneUI Glitch" ;;
                desc) echo "Adreno 6xx/7xx with the OneUI 8g2 overlay flicker/texture-corruption fix applied" ;;
                gen)  echo "a7xx" ;;
            esac ;;
        a8xx-patchs2)
            case "$2" in
                slug) echo "A8xx-Patchs2" ;;
                name) echo "Turnip A8xx Patchs2" ;;
                desc) echo "Adreno 8xx gen8: KGSL correctness tier + gen8 stack + 64 KiB shared memory + A840v2" ;;
                gen)  echo "a8xx" ;;
            esac ;;
        a8xx-patchs1)
            case "$2" in
                slug) echo "A8xx-Patched-Patchs1" ;;
                name) echo "Turnip A8xx Patched Patchs1" ;;
                desc) echo "Adreno 8xx gen8: Android/Bionic gralloc recipe (AIMapper + UBWC swapchain) + mesh-shader emulation + half-warp subgroups + KGSL IB caching" ;;
                gen)  echo "a8xx" ;;
            esac ;;
        *) die "unknown variant '$1'" ;;
    esac
}

usage() {
    # Print the leading comment block as the help text. Walking to the first
    # non-comment line rather than a hardcoded line range means editing the
    # header above can never make --help spill the first few lines of code.
    awk '
        NR == 1 && /^#!/ { next }
        /^#/      { sub(/^# ?/, ""); print; next }
        { exit }
    ' "${BASH_SOURCE[0]}"
    cat <<'EOF'

Options:
  --list                 list buildable variants and exit
  --all                  build every variant sequentially
  -v, --variant NAME     build a single variant
  --dry-run              print the plan and exit without touching anything
  --print-config         print the fully resolved configuration and exit
  -h, --help             this text

Variants:
EOF
    local v
    for v in "${ALL_VARIANTS[@]}"; do
        printf '  %-16s %s\n' "$v" "$(variant_field "$v" desc)"
    done
}

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --list)     printf '%s\n' "${ALL_VARIANTS[@]}"; exit 0 ;;
        --all)      VARIANT="__all__"; shift ;;
        -v|--variant) VARIANT="${2:?--variant needs a value}"; shift 2 ;;
        --dry-run)  DRY_RUN=1; shift ;;
        --print-config) PRINT_CONFIG=1; shift ;;
        -h|--help)  usage; exit 0 ;;
        *)          die "unknown argument '$1' (try --help)" ;;
    esac
done

[[ -n "$VARIANT" ]] || VARIANT="a8xx-patchs1"

if [[ "$VARIANT" != "__all__" ]]; then
    case " ${ALL_VARIANTS[*]} " in
        *" $VARIANT "*) ;;
        *) die "unknown variant '$VARIANT'. Try --list." ;;
    esac
fi

[[ -f "$MANIFEST" ]] || die "upstream manifest not found: $MANIFEST"
[[ -d "$PATCHES_DIR" ]] || die "patch directory not found: $PATCHES_DIR"

# ---------------------------------------------------------------------------
# upstreams.yml reader.
#
# Deliberately a tiny awk reader rather than a full YAML dependency: the build
# must work on a bare CI image, and only two scalars are ever needed. If either
# cannot be resolved we fail loudly instead of guessing a Mesa URL.
# ---------------------------------------------------------------------------
manifest_value() {
    local key="$1"
    awk -v key="$key" '
        /^base:[[:space:]]*$/ { inbase = 1; next }
        inbase && /^[A-Za-z_][A-Za-z0-9_]*:/ { exit }
        inbase && $1 == key ":" {
            sub(/^[^:]+:[[:space:]]*/, "")
            gsub(/^"|"$/, "")
            print
            exit
        }
    ' "$MANIFEST"
}

MESA_REPO="${MESA_REPO_OVERRIDE:-$(manifest_value repo)}"
MESA_REF="${MESA_REF_OVERRIDE:-$(manifest_value ref)}"

[[ -n "$MESA_REPO" ]] || die "could not read base.repo from $MANIFEST (set MESA_REPO)"
[[ -n "$MESA_REF" ]]  || die "could not read base.ref from $MANIFEST (set MESA_REF)"

log "Mesa base: $MESA_REPO@$MESA_REF${MESA_COMMIT:+ (pinned to $MESA_COMMIT)}"

# --print-config reports the fully resolved configuration. It has to run after
# the manifest is read above, which is why it is a flag rather than an inline
# case in the argument loop.
if [[ "${PRINT_CONFIG:-0}" == 1 ]]; then
    printf 'mesa_repo=%s\n' "$MESA_REPO"
    printf 'mesa_ref=%s\n' "$MESA_REF"
    printf 'mesa_commit=%s\n' "${MESA_COMMIT:-<resolved at build time>}"
    printf 'variants=%s\n' "$([[ "$VARIANT" == "__all__" ]] && echo "${ALL_VARIANTS[*]}" || echo "$VARIANT")"
    printf 'workdir=%s\n' "$WORKDIR"
    printf 'ndk=%s\n' "$NDK_VERSION"
    printf 'platform_sdk=%s\n' "$PLATFORM_SDK"
    printf 'min_api=%s\n' "$MIN_API"
    printf 'lto=%s\n' "$TURNIP_LTO"
    printf 'ccache=%s\n' "$USE_CCACHE"
    printf 'common_patches=%s\n' "$COMMON_PATCHES"
    printf 'a7xx_revert_d32s8=%s\n' "$A7XX_REVERT_D32S8"
    printf 'build_version=%s\n' "$BUILD_VERSION"
    exit 0
fi

# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------
check_deps() {
    local missing=() dep
    for dep in git meson ninja patchelf unzip curl flex bison zip glslangValidator \
               python3 patch ccache; do
        case "$dep" in
            ccache) [[ "$USE_CCACHE" == 1 ]] || continue ;;
            meson) command -v meson >/dev/null 2>&1 || command -v meson.py >/dev/null 2>&1 || missing+=("$dep") ;;
            *) command -v "$dep" >/dev/null 2>&1 || missing+=("$dep") ;;
        esac
    done

    if (( ${#missing[@]} > 0 )); then
        printf '%s\n' "${missing[@]}" | sed 's/^/  - /' >&2
        # --dry-run is meant to be runnable anywhere, including from a machine
        # that has no cross-compile toolchain at all, so it reports instead of
        # aborting.
        if (( DRY_RUN )); then
            warn "dry run: missing tools above would abort a real build"
            return 0
        fi
        die "missing build dependencies (Debian/Ubuntu):
       sudo apt-get install -y git meson ninja-build patchelf unzip curl \\
         flex bison zip glslang-tools python3 patch ccache python3-pip
       then: pip3 install --break-system-packages mako"
    fi

    python3 -c 'import mako' >/dev/null 2>&1 \
        || warn "python 'mako' not importable - install it with: pip3 install mako"
}

# ---------------------------------------------------------------------------
# Toolchain
# ---------------------------------------------------------------------------
prepare_ndk() {
    if [[ ! -d "$NDK" ]]; then
        log "Downloading $NDK_VERSION (~600 MB, cached in $WORKDIR)"
        if (( DRY_RUN )); then return 0; fi
        curl -fsSL --retry 3 --retry-delay 5 \
            "https://dl.google.com/android/repository/${NDK_VERSION}-linux.zip" \
            -o "$WORKDIR/${NDK_VERSION}-linux.zip" \
            || die "failed to download $NDK_VERSION"
        unzip -q "$WORKDIR/${NDK_VERSION}-linux.zip" -d "$WORKDIR" \
            || die "failed to extract $NDK_VERSION"
    fi
    [[ -d "$NDK" ]] || die "NDK toolchain missing at $NDK"
}

# Highest API-level clang the NDK actually ships, rather than assuming 36.
detect_api_clang() {
    local v
    for v in 36 35 34 33 32 31; do
        if [[ -f "$NDK/aarch64-linux-android${v}-clang" ]]; then
            echo "$v"; return 0
        fi
    done
    return 1
}

# ---------------------------------------------------------------------------
# Mesa checkout - always re-fetched so a build never inherits a dirty tree.
# ---------------------------------------------------------------------------
prepare_mesa() {
    if (( DRY_RUN )); then return 0; fi

    mkdir -p "$WORKDIR"
    rm -rf "$MESA_DIR"
    mkdir -p "$MESA_DIR"

    git -C "$MESA_DIR" init -q
    git -C "$MESA_DIR" remote add origin "$MESA_REPO"

    if [[ -n "$MESA_COMMIT" ]]; then
        log "Fetching pinned Mesa $MESA_COMMIT"
        git -C "$MESA_DIR" fetch -q --depth=1 origin "$MESA_COMMIT" \
            || die "cannot fetch $MESA_COMMIT from $MESA_REPO"
    else
        log "Fetching Mesa $MESA_REF"
        git -C "$MESA_DIR" fetch -q --depth=1 origin "refs/heads/$MESA_REF" \
            || die "cannot fetch $MESA_REF from $MESA_REPO"
    fi

    git -C "$MESA_DIR" checkout -q --detach FETCH_HEAD

    # Mesa's own idea of its version, used for the release name and meta.json.
    MESA_FACTS_JSON="$(python3 "$SCRIPTS_DIR/mesa_facts.py" "$MESA_DIR")" \
        || die "could not determine Mesa/Vulkan versions from the source tree"
    read_facts "$MESA_FACTS_JSON"

    ok "Mesa $MESA_VERSION / Vulkan $VULKAN_VERSION / ${MESA_SHA_SHORT}"
}

MESA_VERSION=""; MESA_SHA_SHORT=""; VULKAN_VERSION=""; MESA_SHA=""

# Consume mesa_facts.py's JSON in a single subprocess, emitting shell
# assignments. shlex.quote matters here: these values end up inside release
# names and meta.json, and an unquoted Mesa version string would break the eval
# rather than merely look untidy.
read_facts() {
    local json="$1"
    local assignments
    assignments="$(printf '%s' "$json" | python3 -c '
import json, shlex, sys
facts = json.load(sys.stdin)
wanted = (
    ("mesa_version", "MESA_VERSION"),
    ("vulkan_version", "VULKAN_VERSION"),
    ("git_sha", "MESA_SHA"),
    ("git_sha_short", "MESA_SHA_SHORT"),
)
for key, name in wanted:
    print("{}={}".format(name, shlex.quote(facts[key])))
')" || die "could not parse Mesa build facts"
    eval "$assignments"
}

# ---------------------------------------------------------------------------
# Patch application
# ---------------------------------------------------------------------------
optional_step() {
    # optional_step <label> [--require] --expect PATH::ANCHOR -- cmd...
    python3 "$SCRIPTS_DIR/optional_step.py" "$@"
}

apply_kgsl_tier() {
    # KGSL correctness fixes. These are generation-agnostic, so they go on
    # every leg, not just the a8xx ones. Disabled with COMMON_PATCHES=0.
    [[ "$COMMON_PATCHES" == 1 ]] || { warn "COMMON_PATCHES=0 - skipping the KGSL correctness tier"; return 0; }
    (( DRY_RUN )) && { log "[dry-run] would apply the KGSL correctness tier"; return 0; }

    bash "$PATCHES_DIR/patchs2/common/apply_common.sh" "$MESA_DIR" kgsl
}

apply_a8xx_tier() {
    [[ "$COMMON_PATCHES" == 1 ]] || { warn "COMMON_PATCHES=0 - skipping the a8xx tier"; return 0; }
    (( DRY_RUN )) && { log "[dry-run] would apply the a8xx tier"; return 0; }

    bash "$PATCHES_DIR/patchs2/common/apply_common.sh" "$MESA_DIR" a8xx
}

apply_a7xx_quirks() {
    (( DRY_RUN )) && { log "[dry-run] would apply the a7xx quirks"; return 0; }

    local devices="src/freedreno/common/freedreno_devices.py"

    log "a7xx: reverting the upstream D32S8 EARLY_Z_LATE_Z workaround"
    if [[ "$A7XX_REVERT_D32S8" == 1 ]]; then
        python3 "$SCRIPTS_DIR/apply_d32s8_revert.py" || die "D32S8 revert failed"
    else
        warn "A7XX_REVERT_D32S8=0 - keeping the upstream D32S8 workaround"
    fi

    log "a7xx: disabling has_early_preamble on a7xx_gen1"
    if grep -A20 'a7xx_gen1 = GPUProps(' "$devices" | grep -q 'has_early_preamble = False'; then
        ok "has_early_preamble = False already present"
    else
        sed -i '/a7xx_gen1 = GPUProps(/a \        has_early_preamble = False,' "$devices" \
            || die "could not patch $devices"
    fi

    # freedreno_devices.py generates the device table; a syntax error here
    # surfaces much later as an inscrutable build failure.
    python3 -m py_compile "$devices" || die "$devices is not valid Python after patching"
    ok "freedreno_devices.py compiles"
}

apply_oneui_glitch() {
    (( DRY_RUN )) && { log "[dry-run] would apply the OneUI 8g2 fix"; return 0; }
    log "a7xx: applying the OneUI 8g2 overlay glitch fix"
    patch -p1 -N --fuzz=3 --no-backup-if-mismatch \
        < "$PATCHES_DIR/a7xx/8g2_ui_glitch.patch" \
        || die "8g2_ui_glitch.patch did not apply - rebase it onto this Mesa"
}

apply_patchs2_a8xx() {
    # Guard before any real patching: `patch -p1` run from the repository root
    # would try to edit *this* repository's files and start prompting.
    (( DRY_RUN )) && { log "[dry-run] would apply the Patchs2 a8xx stack"; return 0; }

    log "a8xx: applying the gen8 stack"
    patch -p1 -N --fuzz=4 --no-backup-if-mismatch \
        < "$PATCHES_DIR/patchs2/a8xx_gen8.patch" \
        || die "a8xx_gen8.patch did not apply - rebase it onto this Mesa"

    log "a8xx: raising shared memory 32 KiB -> 64 KiB"
    optional_step "a8xx shared memory" \
        --expect "src/freedreno/common/freedreno_devices.py::cs_shared_mem_size = 32 * 1024" \
        -- python3 "$PATCHES_DIR/patchs2/a8xx_shared_mem.py"

    log "a8xx: adding the A840v2 device entry"
    optional_step "a840v2" \
        --expect "src/freedreno/common/freedreno_devices.py::0xffff44050a31" \
        -- python3 "$PATCHES_DIR/patchs2/a840v2.py"

    # These scripts rewrite the device table, so re-validate it at the end.
    python3 -m py_compile src/freedreno/common/freedreno_devices.py \
        || die "freedreno_devices.py is not valid Python after patching"
}

apply_patchs1_android() {
    (( DRY_RUN )) && { log "[dry-run] would apply the Patchs1 Android recipe"; return 0; }

    local script
    local -a steps=(
        "fix_gralloc_flushall.py|src/util/u_gralloc/u_gralloc_fallback.c::uint32_t gmsm"
        "fix_a8xx_dev_info.py|src/freedreno/common/freedreno_dev_info.h::force_render_mode_reason"
        "apply_a8xx_gpus.py|src/freedreno/common/freedreno_devices.py::a8xx"
        "apply_a7xx_gen1_quirks.py|src/freedreno/common/freedreno_devices.py::a7xx_gen1 = GPUProps("
        "apply_a7xx_gen2_ubwc_hint.py|src/freedreno/common/freedreno_devices.py::enable_tp_ubwc_flag_hint"
        "add_aimapper_gralloc.py|src/util/u_gralloc::u_gralloc"
        "add_ubwc_swapchain_usage.py|src/vulkan/runtime/vk_android.c::ahb_usage_props"
    )

    log "a8xx: applying the Android/Bionic recipe"
    for entry in "${steps[@]}"; do
        script="${entry%%|*}"
        local expect="${entry#*|}"
        optional_step "patchs1/$script" \
            --expect "$expect" \
            -- python3 "$PATCHES_DIR/patchs1/android/$script"
    done

    log "a8xx: tuning the autotuner balance variant"
    # OPTIONAL on purpose: tu_autotune.cc was removed when Mesa replaced the
    # autotuner, so this must skip cleanly rather than break the build.
    optional_step "patchs1/autotuner balance" \
        --expect "src/freedreno/vulkan/tu_autotune.cc::drawcall_count" \
        -- python3 "$PATCHES_DIR/patchs1/android/apply_balance_variant.py"

    local count=0 patch_file
    for patch_file in "$PATCHES_DIR"/patchs1/000*.patch; do
        [[ -f "$patch_file" ]] || continue
        count=$((count + 1))
        log "a8xx: $(basename "$patch_file")"
        git -C "$MESA_DIR" apply --check "$patch_file" \
            || die "$(basename "$patch_file") does not apply to this Mesa - rebase or drop it"
        git -C "$MESA_DIR" apply "$patch_file"
    done
    (( count > 0 )) || die "no patchs1 patches found in $PATCHES_DIR/patchs1"

    python3 -m py_compile src/freedreno/common/freedreno_devices.py \
        || die "freedreno_devices.py is not valid Python after patching"
}

# ---------------------------------------------------------------------------
# Android/Bionic compatibility fixes.
#
# Mesa's android_stub headers do not match Bionic, and the NDK's clang is far
# stricter than the desktop GCC Mesa normally builds with. These are mechanical
# source fixes, not behavioural ones.
# ---------------------------------------------------------------------------
apply_android_ndk_fixes() {
    (( DRY_RUN )) && { log "[dry-run] would apply the Android/Bionic fixes"; return 0; }

    log "Android/Bionic: relaxing the native_handle_t stub definitions"
    sed -i 's/typedef const native_handle_t\* buffer_handle_t;/typedef void* buffer_handle_t;/g' \
        include/android_stub/cutils/native_handle.h || true
    sed -i 's/, hnd->handle/, (void *)hnd->handle/g' \
        src/util/u_gralloc/u_gralloc_fallback.c || true
    # Bionic's native_handle_t members are non-const, so the upstream
    # chained dereference does not type-check under NDK clang.
    sed -i -E 's/([a-z_]+)->handle->/((const native_handle_t *)\1->handle)->/g' \
        src/vulkan/runtime/vk_android.c || true

    # The stub headers trip -Werror=gnu-empty-initializer; drop it from -Werror.
    sed -i '/-Werror=gnu-empty-initializer/d' meson.build || true

    ok "Android/Bionic source fixes applied"
}

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
build_android() {
    local variant="$1"
    local build_dir="$BUILD_ROOT/$variant"
    local output_dir="$WORKDIR/out/$variant"
    local wrapper=""
    [[ "$USE_CCACHE" == 1 ]] && wrapper="ccache"

    local lto_flag="-Db_lto=false"
    [[ "$TURNIP_LTO" == 1 ]] && lto_flag="-Db_lto=true"

    # Dry run returns before probing the NDK, so it works on a machine with no
    # Android toolchain installed.
    if (( DRY_RUN )); then
        log "[dry-run] would configure + compile $variant (LTO=$TURNIP_LTO, ccache=$USE_CCACHE)"
        return 0
    fi

    local api_clang
    api_clang="$(detect_api_clang)" \
        || die "no aarch64-linux-android clang found in $NDK (is $NDK_VERSION complete?)"

    rm -rf "$build_dir" "$output_dir"
    mkdir -p "$build_dir"

    # Mesa builds against its own android_stub headers, which do not match
    # Bionic and which the NDK's clang diagnoses far more strictly than the
    # desktop GCC Mesa normally uses. These are mechanical suppressions for
    # that mismatch, not -Werror being disabled wholesale: Mesa does not turn
    # on -Werror for a release build, but the stub headers still trip warnings
    # that would otherwise be errors on some NDK versions.
    local ndk_warnings="'--start-no-unused-arguments' '-Wno-error' '-Wno-error=gnu-empty-initializer' '-Wno-gnu-empty-initializer' '-Wno-deprecated-declarations' '-Wno-incompatible-pointer-types-discards-qualifiers' '-Wno-incompatible-pointer-types'"

    cat > "$build_dir/android-aarch64.txt" <<EOF
[binaries]
ar = '$NDK/llvm-ar'
c = [$wrapper'$NDK/aarch64-linux-android${api_clang}-clang', $ndk_warnings]
cpp = [$wrapper'$NDK/aarch64-linux-android${api_clang}-clang++', '-fno-exceptions', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '--start-no-unused-arguments', '-static-libstdc++', '--end-no-unused-arguments', $ndk_warnings]
c_ld = '$NDK/ld.lld'
cpp_ld = '$NDK/ld.lld'
strip = '$NDK/llvm-strip'
pkg-config = ['env', 'PKG_CONFIG_LIBDIR=$NDK/pkg-config', '/usr/bin/pkg-config']

[built-in options]
c_args = ['-D__ANDROID__']
cpp_args = ['-D__ANDROID__']
c_link_args = ['-fuse-ld=lld']
cpp_link_args = ['-fuse-ld=lld']

[properties]
needs_exe_wrapper = true

[host_machine]
system = 'android'
cpu_family = 'aarch64'
cpu = 'armv8'
endian = 'little'
EOF

    cat > "$build_dir/native.txt" <<'EOF'
[binaries]
c = 'clang'
cpp = 'clang++'
ar = 'llvm-ar'
strip = 'llvm-strip'
c_ld = 'ld.lld'
cpp_ld = 'ld.lld'

[built-in options]
c_link_args = ['-fuse-ld=lld']
cpp_link_args = ['-fuse-ld=lld']

[host_machine]
system = 'linux'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
EOF

    # Mesa's llvm dependency would otherwise latch onto a *host* LLVM when one
    # is installed, which is wrong for an aarch64 Android target.
    log "Configuring $variant (Mesa $MESA_VERSION, API $api_clang, LTO=$TURNIP_LTO)"
    meson setup "$build_dir" \
        --cross-file "$build_dir/android-aarch64.txt" \
        --native-file "$build_dir/native.txt" \
        --prefix "$output_dir" \
        -Dbuildtype=release \
        -Doptimization=3 \
        -Dstrip=true \
        "$lto_flag" \
        -Dllvm=disabled \
        -Dplatforms=android \
        -Dvideo-codecs= \
        -Dplatform-sdk-version="$PLATFORM_SDK" \
        -Dandroid-stub=true \
        -Dgallium-drivers= \
        -Dvulkan-drivers=freedreno \
        -Dvulkan-beta=true \
        -Dfreedreno-kmds=kgsl \
        -Degl=disabled \
        -Dandroid-libbacktrace=disabled

    log "Compiling $variant (this is the long part)"
    ninja -C "$build_dir" install

    [[ -f "$output_dir/lib/$LIBRARY_NAME" ]] \
        || die "build finished but $output_dir/lib/$LIBRARY_NAME is missing"
}

# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------
package_variant() {
    local variant="$1"
    local output_dir="$WORKDIR/out/$variant"
    local slug name desc

    slug="$(variant_field "$variant" slug)"
    name="$(variant_field "$variant" name)"
    desc="$(variant_field "$variant" desc)"

    if (( DRY_RUN )); then
        # Versions come from the Mesa tree, which a dry run never fetches, so
        # show the shape of the name with explicit placeholders rather than a
        # plausible-looking string with holes in it.
        log "[dry-run] would package $slug as:"
        log "[dry-run]   Turnip_${slug}_mesa<MESA-VERSION>_vk<VULKAN-VERSION>_R${BUILD_VERSION}_<COMMIT>.zip"
        return 0
    fi

    # Name carries everything needed to identify a build years from now:
    # driver leg, Mesa version, Vulkan version, build number, source commit.
    local zip_name="Turnip_${slug}_mesa${MESA_VERSION}_vk${VULKAN_VERSION}_R${BUILD_VERSION}_${MESA_SHA_SHORT}.zip"
    local zip_path="$WORKDIR/$zip_name"

    rm -f "$zip_path"

    python3 "$SCRIPTS_DIR/make_meta.py" \
        --mesa-dir "$MESA_DIR" \
        --variant "$variant" \
        --build-version "$BUILD_VERSION" \
        --name "$name" \
        --description "$desc" \
        --author "$META_AUTHOR" \
        --vendor Mesa \
        --min-api "$MIN_API" \
        --library-name "$LIBRARY_NAME" \
        --out "$output_dir/lib/meta.json" >/dev/null \
        || die "could not generate meta.json for $variant"

    log "Packaging $zip_name"
    ( cd "$output_dir/lib" && zip -9 -q "$zip_path" "$LIBRARY_NAME" meta.json ) \
        || die "zip failed for $variant"

    ( cd "$WORKDIR" && sha256sum "$zip_name" > "${zip_name}.sha256" ) \
        || die "checksum failed for $variant"

    log "Verifying $zip_name"
    python3 "$SCRIPTS_DIR/verify_package.py" "$zip_path" \
        --library-name "$LIBRARY_NAME" \
        --expect-package-version "$BUILD_VERSION" \
        --expect-name-prefix "$name" \
        --expect-vulkan-version "$VULKAN_VERSION" \
        || die "package verification failed for $variant - refusing to publish"

    ok "$zip_path"
    echo "$zip_path"
}

# ---------------------------------------------------------------------------
# Per-variant orchestration
# ---------------------------------------------------------------------------
build_variant() {
    local variant="$1"

    step "Variant $variant ($(variant_field "$variant" desc))"

    prepare_mesa
    # In a dry run the Mesa tree was never fetched, so there is nothing to
    # change into; the patch steps below only log their intent.
    (( DRY_RUN )) || cd "$MESA_DIR"

    case "$(variant_field "$variant" gen)" in
        a7xx)
            apply_a7xx_quirks
            [[ "$variant" == "a7xx-oneui" ]] && apply_oneui_glitch
            # Correctness tier only: the a8xx tier would not apply here.
            apply_kgsl_tier
            ;;
        a8xx)
            # The patchs1 leg ships its own copies of the a8xx fixes inside
            # 0003/0004/0005, so only the KGSL tier is shared with it.
            [[ "$variant" == "a8xx-patchs2" ]] && apply_a8xx_tier
            [[ "$variant" == "a8xx-patchs2" ]] && apply_patchs2_a8xx
            [[ "$variant" == "a8xx-patchs1" ]] && apply_patchs1_android
            apply_kgsl_tier
            ;;
        *) die "internal error: unhandled generation for $variant" ;;
    esac

    apply_android_ndk_fixes

    if (( DRY_RUN )); then
        log "[dry-run] would syntax-check freedreno_devices.py"
    else
        log "freedreno_devices.py final syntax check"
        python3 -m py_compile src/freedreno/common/freedreno_devices.py \
            || die "freedreno_devices.py is not valid Python after patching"
    fi

    build_android "$variant"
    package_variant "$variant" | tail -1
}

main() {
    step "Preconditions"
    check_deps
    (( DRY_RUN )) || ok "all required tools present"
    prepare_ndk

    if [[ "$DRY_RUN" == 1 ]]; then
        log "DRY RUN - no files will be modified"
    fi

    step "Plan"
    log "workdir   : $WORKDIR"
    log "variants  : $([[ "$VARIANT" == "__all__" ]] && echo "${ALL_VARIANTS[*]}" || echo "$VARIANT")"
    log "LTO       : $TURNIP_LTO"
    log "ccache    : $USE_CCACHE"
    log "KGSL tier : $COMMON_PATCHES"

    if [[ "$VARIANT" == "__all__" ]]; then
        local v
        for v in "${ALL_VARIANTS[@]}"; do
            build_variant "$v"
        done
    else
        build_variant "$VARIANT"
    fi

    step "Done"
    if [[ "$DRY_RUN" == 1 ]]; then
        log "Dry run complete - nothing was built."
    else
        log "Packages in $WORKDIR:"
        ls -1 "$WORKDIR"/Turnip_*.zip 2>/dev/null | sed 's/^/  /' || true
    fi
}

main "$@"
