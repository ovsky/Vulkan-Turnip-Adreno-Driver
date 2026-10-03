## What this changes

<!-- Which variant(s) does this affect? a7xx / a7xx-oneui / a8xx-patchs2 / a8xx-patchs1 / tooling -->

## Why

<!-- The problem, not the solution. Link the issue if there is one. -->

## Provenance

- [ ] Upstream Mesa MR/commit: <!-- if this is already upstream, link it -->
- [ ] Community source and author: <!-- e.g. whitebelyash/mesa-tu8#gen8, StevenMXZ -->
- [ ] Test evidence: <!-- what you ran, and on what hardware if you have it -->

Every fix in a release must be traceable to a row in `docs/PATCHES.md`. If this
touches `patches/`, update that table in the same PR.

## Verification

- [ ] `python3 -m unittest discover -s tests -v` passes
- [ ] `./build_turnip.sh --dry-run -v <variant>` does what you expect
- [ ] Built and tested on real hardware: <!-- GPU / device -->
- [ ] If not tested on hardware, say so plainly — unverified driver patches are
      how emulator users lose an afternoon

## Risk

<!-- What could regress? Which GPUs, which emulators, which titles? -->

## Checklist

- [ ] Conventional commit message (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`)
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] `README.md` updated if user-facing behaviour changed
- [ ] `upstreams.yml` updated if a source was added, removed, or its head moved
- [ ] New correctness patch has an `assert` in `patches/patchs2/common/apply_common.sh`
- [ ] No `turnip_workdir/` artifacts committed