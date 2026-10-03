#!/usr/bin/env bash
# =============================================================================
# apply_common.sh - apply a tier of cross-cutting Turnip patches, then prove
#                   they landed.
# =============================================================================
# These fixes are KGSL / gen8 correctness fixes, not per-platform cosmetics:
# they belong on every leg that talks to a Qualcomm GPU through KGSL. That is
# why they live outside the variant directories instead of being duplicated
# into each one.
#
# Tiers (chosen so no patch is ever applied twice -- patchs1/0003, /0004 and
# /0005 are byte-identical to a8xx-cube-coord-sanitize, a8xx-bindless-invalidate
# and a8xx-kgsl-ib-vbo-alias, and the patchs1 variant ships those directly):
#
#   kgsl   KGSL correctness, platform- and generation-agnostic.
#          Safe on a6xx/a7xx/a8xx.   -> all legs
#   a8xx   gen8-specific.            -> a8xx legs only (patchs1 ships its own
#                                       copies inside 0003/0004/0005)
#   all    kgsl + a8xx.              -> a8xx legs that do not ship their own
#
# Usage: apply_common.sh <mesa-dir> [tier]
#
# Design rule, unchanged from the original: a driver missing a fix must never
# be packaged. Every patch must apply cleanly AND its effect must be
# greppable in the tree afterwards. When Mesa upstream carries a fix, delete
# the patch here (and note it in docs/PATCHES.md) rather than letting it rot.
# =============================================================================
set -euo pipefail

MESA_DIR="${1:?usage: apply_common.sh <mesa-dir> [tier]}"
TIER="${2:-all}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

KGSL_PATCHES=(
    kgsl-syncobj-merge-ts-fd.patch
    kgsl-zero-timeout-poll.patch
)
A8XX_PATCHES=(
    a8xx-cube-coord-sanitize.patch
    a8xx-bindless-invalidate.patch
    a8xx-kgsl-ib-vbo-alias.patch
)

case "$TIER" in
    kgsl) PATCHES=("${KGSL_PATCHES[@]}") ;;
    a8xx) PATCHES=("${A8XX_PATCHES[@]}") ;;
    all)  PATCHES=("${KGSL_PATCHES[@]}" "${A8XX_PATCHES[@]}") ;;
    *) echo "apply_common: unknown tier '$TIER' (expected kgsl|a8xx|all)" >&2; exit 2 ;;
esac

# The evidence a patch must leave behind, keyed by patch file.
#
# This is deliberately a lookup rather than a flat list of assertions. A flat
# list has to be kept in sync with the tier membership by hand, and when it
# drifts the failure mode is the worst kind: the kgsl tier asserts an a8xx fix
# it never applied, so every single build dies on a missing string. Deriving the
# checks from the patch list makes that impossible, and makes a patch added
# without evidence a hard error instead of a silent no-op.
#
# Format: description | needle (grep -F) | path relative to the Mesa tree |
#         minimum number of occurrences
checks_for() {
    case "$1" in
        kgsl-syncobj-merge-ts-fd.patch)
            echo "kgsl syncobj timestamp->fd merged (both submit paths|int ret_fd = kgsl_syncobj_ts_to_fd(&ret)|src/freedreno/vulkan/tu_knl_kgsl.cc|2" ;;
        kgsl-zero-timeout-poll.patch)
            echo "KGSL retired-timestamp poll reports VK_TIMEOUT instead of spinning|kgsl_timestamp_retired(fd, context_id, timestamp) ? VK_SUCCESS : VK_TIMEOUT|src/freedreno/vulkan/tu_knl_kgsl.cc|1" ;;
        a8xx-cube-coord-sanitize.patch)
            echo "a8xx cube-map direction sanitisation enabled|cube_coord_hang_quirk = True|src/freedreno/common/freedreno_devices.py|1" ;;
        a8xx-bindless-invalidate.patch)
            echo "bindless descriptor invalidation plumbed through cmd buffer|SP_GFX_BINDLESS_INVALIDATE|src/freedreno/vulkan/tu_cmd_buffer.h|1" ;;
        a8xx-kgsl-ib-vbo-alias.patch)
            echo "KGSL index-buffer/VBO aliasing flag set|KGSL_MEMFLAGS_VBO|src/freedreno/vulkan/tu_knl_kgsl.cc|1" ;;
        *)
            return 1 ;;
    esac
}

cd "$MESA_DIR"

for p in "${PATCHES[@]}"; do
    [[ -f "$HERE/$p" ]] || { echo "[common/$TIER] missing patch file $p" >&2; exit 1; }
    echo "[common/$TIER] applying $p"
    rc=0
    # -N: ignore already-applied. --fuzz=3 absorbs upstream reindentation
    # without letting a patch silently land in the wrong place.
    out="$(patch -p1 -N --fuzz=3 --no-backup-if-mismatch < "$HERE/$p" 2>&1)" || rc=$?
    echo "$out" | sed 's/^/    /'
    if [ "$rc" != 0 ]; then
        echo "[common/$TIER] $p did not apply cleanly (patch exit $rc)." >&2
        echo "                 Rebase it onto this Mesa, or delete it if upstream now carries the fix." >&2
        exit 1
    fi
done

# Assert the result rather than trust the patch exit code.
assert() {
    local description="$1" needle="$2" file="$3" expected_count="${4:-1}"
    local count
    count="$(grep -cF -- "$needle" "$file" 2>/dev/null || true)"
    count="${count:-0}"
    if [ "$count" -lt "$expected_count" ]; then
        echo "[common/$TIER] FAILED: $description" >&2
        echo "                 expected >= $expected_count occurrence(s) of '$needle' in $file, found $count" >&2
        exit 1
    fi
    echo "[common/$TIER]   verified: $description"
}

for p in "${PATCHES[@]}"; do
    if ! spec="$(checks_for "$p")"; then
        echo "[common/$TIER] $p has no verification entry in checks_for()." >&2
        echo "                 Add the grep needle proving it landed, or a patch" >&2
        echo "                 can be added here and silently do nothing." >&2
        exit 1
    fi
    IFS='|' read -r description needle file expected_count <<< "$spec"
    assert "$description" "$needle" "$file" "$expected_count"
done

echo "[common/$TIER] ${#PATCHES[@]} patch(es) applied and verified"