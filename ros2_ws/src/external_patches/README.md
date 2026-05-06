# External patches

Local fixes applied to `vcs import`-fetched packages (declared in `../external.repos`).
Each `.patch` file is a unified diff produced by `git diff` against the package's pinned
version. The installer applies them idempotently after `vcs import`.

## Why patches live here, not as upstream PRs

For long-running upstream forks (Slamtec/rplidar_ros) we can't reasonably wait for
fixes to be merged, but we also don't want to maintain a soft fork because that
costs more than the patch. Tracking patches in-tree gives us:

- **Reproducibility:** the same `.patch` applied to the same upstream SHA always
  yields the same source.
- **Visibility:** the patch is reviewable in the repo with normal git tooling.
- **Easy upstream-bump path:** when bumping `version:` in `external.repos`, run
  `git apply --check` to see if the patch still applies cleanly.

## Current patches

| Patch | Target | What it fixes |
|---|---|---|
| `rplidar_ros-rxthread-eagain-fix.patch` | `rplidar_ros` (Slamtec) | RX thread dies on `select()`-then-`read()`-returns-0 race (EAGAIN with `O_NDELAY` non-blocking I/O). Replaces the kill-thread-on-zero-bytes branch with a 10ms sleep + retry. Without this, the LIDAR stops publishing scans intermittently after seconds-to-minutes. |

## Applying patches manually (debug)

```bash
cd ros2_ws/src/rplidar_ros
git apply --check ../external_patches/rplidar_ros-rxthread-eagain-fix.patch  # dry-run
git apply         ../external_patches/rplidar_ros-rxthread-eagain-fix.patch  # apply
```

To check whether a patch is already applied:
```bash
git apply --reverse --check ../external_patches/foo.patch && echo "already applied"
```
