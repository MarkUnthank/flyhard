# Website releases

Production website releases use GitHub pull requests and Cloudflare Builds.

- Make changes on a branch based on the latest `origin/main`, then open a PR targeting `main`. Never push directly to `main`.
- Treat requests such as "deploy it", "ship it", or "publish it" as requests to use this PR workflow. Merge only when the user has authorized merging. Cloudflare Builds deploys the merged commit.
- Do not manually publish production Worker code or assets for normal releases from any checkout, worktree, machine, or agent. This includes `wrangler deploy`, `wrangler versions upload`, `wrangler versions deploy`, OpenNext deploy/upload commands, npm deployment scripts, and equivalent Cloudflare API or dashboard actions. Do not bypass this rule using another tool or credential; the explicitly requested emergency rollback described below is the sole exception.
- Local builds, tests, and local previews are allowed. Building a Worker locally is not permission to publish it.
- Before proposing a merge, fetch `origin/main` and reconcile the PR with it. Keep unrelated and uncommitted work intact. If production contains changes missing from GitHub, flag that gap and keep the PR in draft until those changes are reconciled; do not deploy an older checkout over them.
- After an authorized merge, verify the Cloudflare Git build corresponds to the merged commit and check the live result before reporting deployment success.
- Emergency rollback requires an explicit user request to restore a production version. Check current deployment history immediately before acting, account for concurrent releases, and restore a known published version rather than rebuilding a local checkout. Verify the active version afterward.

These are agent workflow rules, not access controls. Do not remove or weaken them to complete a release. Credential restrictions are managed separately.

# Recording and sponsor artwork

Before **every** CARLA recording or finished-video render (including previews), download and build
the latest paid advertiser livery from production:

```sh
python3 scripts/refresh_live_livery.py
```

Read `work/latest-livery.json` for that run's immutable asset directory and transfer
its archive to the GPU Pod with `tar --no-same-owner`. Pass the selected directory
as `--asset` to recording/rendering commands. Each command must run
`flyhard.live_livery.verify_live_livery` before starting expensive work. If the live
revision changed, refresh again. Never fall back to a checked-in historical livery
when production is unavailable or the check fails.

Keep the snapshot fixed during a run. Save its manifest, source and checksums with
the recording. Verify the left door and rear view before exporting the full video.
Preserve separate sponsor meshes, existing UVs and alpha. Artwork transforms are
already baked into the PNGs; do not apply them again. Rebuild cached sponsor layers
when the source model changes. Credits and receipts must use the selected revision
and layout, with no hardcoded sponsor count.

For video iterations, retain visible request-left, request-right, wheel angle,
CARLA steering and stalk readouts. Keep `thedrivingfly.com` in the black header.
Use the saved causal simulation data; describe presentation interpolation accurately
and never invent neural activations or claim visual autonomous driving.
