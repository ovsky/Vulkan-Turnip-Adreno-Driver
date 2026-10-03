# Patch layout

Every fix shipped in a release has to be traceable from here. See
[`docs/PATCHES.md`](../docs/PATCHES.md) for provenance and attribution.

```
patches/
├── patchs2/common/     KGSL + gen8 correctness fixes, applied by tier
├── patchs2/            gen8 stack and device-table patches (A8xx Patchs2 leg)
├── patchs1/            Android/Bionic recipe + 0001-0006 (A8xx Patchs1 leg)
├── a7xx/               A7xx-only fixes
└── legacy/             kept for reference, applied by nothing
```

## Tiers

`patchs2/common/apply_common.sh` applies fixes in two tiers, then **proves**
each one landed before compiling. A driver that silently lost a correctness
fix is worse than no driver, so a missing anchor fails the build.

| Tier    | Contents                                                                  | Applied to              |
|---------|---------------------------------------------------------------------------|-------------------------|
| `kgsl`  | `kgsl-syncobj-merge-ts-fd`, `kgsl-zero-timeout-poll`                        | every variant           |
| `a8xx`  | `a8xx-cube-coord-sanitize`, `a8xx-bindless-invalidate`, `a8xx-kgsl-ib-vbo-alias` | Patchs2 leg only  |

The `a8xx` tier is **not** applied to the Patchs1 leg on purpose:
`patchs1/0003`, `0004` and `0005` are byte-identical to those three patches,
and applying both would conflict. Patchs1 gets the KGSL tier plus its own
copies.

The KGSL tier went from Patchs2-only to every variant because those are KGSL
bugs, not platform bugs — they affect a6xx/a7xx exactly as much as a8xx.
Disable with `COMMON_PATCHES=0` if a future Mesa change ever conflicts.

## Required vs optional

Two different failure policies, because they are two different problems:

| Kind       | Policy | Where |
|------------|--------|-------|
| Correctness| Must apply, or the build fails | `kgsl` / `a8xx` tiers, `0001`-`0006` |
| Tuning     | Skip with a warning if the anchor is gone | `apply_balance_variant.py`, `a8xx_shared_mem.py`, `a840v2.py` |

Optional steps run through `scripts/optional_step.py`, which checks the
upstream anchor first. Mesa refactors constantly; when `tu_autotune.cc`
disappeared, a raw `open()` would have thrown a traceback forty minutes into a
compile instead of saying "this tuning step no longer applies".

`A7xx_REVERT_D32S8=0` keeps the upstream workaround on the a7xx legs.

## legacy/

Not applied to anything, deliberately:

| File | Why it is dead |
|------|----------------|
| `force_sysmem_no_autotuner.patch` | Unconditional `return true` at the top of `use_sysmem_rendering()`, killing the autotuner outright. Crude, and it defeats GMEM for GPUs that work fine with it. |
| `quest3.patch` | Quest 3 (`0x43050B00`) device entries. Now handled through the device tables in the active patches, so applying this would duplicate them. |
| `tu_gen8_clean.patch` | Snapshot of StevenMXZ's gen8 branch as a flat diff. Superseded by `patchs2/` and by upstream Mesa. |
| `vk_sync_timeline.patch` | **Not a patch.** It is a complete replacement `vk_sync_timeline.c`, despite the name — `patch` would never apply it. |
| `tu_gen8.patch`, `39751.patch`, `tu8_kgsl_26.patch` | Older root-level snapshots from before the patch set was curated. Same fixes as the active `patchs1`/`patchs2` sets, rebased onto an older Mesa; applying them on top of the current tree would conflict. |

The first four were committed at `patches/` top level while
`build_turnip.sh` never referenced that directory, so none of them reached a
single build. The last three were loose in the repository root. Keeping them
under `legacy/` makes that explicit instead of leaving files at the top level
that look load-bearing and are not.

## Adding a patch

1. Add it under the tier it belongs to, and extend the `assert` block in
   `apply_common.sh` so its effect is verified, not just its exit status.
2. Record provenance in [`docs/PATCHES.md`](../docs/PATCHES.md).
3. Re-read a patch that landed upstream instead: delete it and note the MR
   rather than letting a re-implementation rot.