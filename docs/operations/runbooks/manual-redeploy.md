---
title: Manually redeploy closeloop on lifekit-vps
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [operations, runbook, deploy]
runs-in: lifekit-vps
estimated-duration: 3 minutes
---

# Manually redeploy closeloop on lifekit-vps

## When to run this

- The GitHub Actions deploy job failed and you want the latest `main` running now.
- The Actions workflow is stuck in `BuildFailed` state (see [../../guides/deploy.md](../../guides/deploy.md#known-issue-2026-07-01)) — until that's unstuck, this is the primary deploy path.
- You want to test a build change on the VPS before merging.

## Prerequisites

- ssh access to `lifekit-vps` (Tailscale reachable).
- sudo-as-`lifekit` on the VPS.
- The change is on `origin/main` (or another branch you name explicitly).

## Steps

1. **SSH to the VPS.**

   ```bash
   ssh lifekit-vps
   ```

2. **Pull the latest main into `~/closeloop`.**

   ```bash
   sudo -u lifekit bash -c 'cd ~/closeloop && git fetch --all && git checkout main && git reset --hard origin/main'
   ```

   Expected: `HEAD is now at <sha> <commit subject>`.

3. **Build the image.**

   ```bash
   sudo -u lifekit bash -c 'cd ~/closeloop && docker build -t closeloop:latest .'
   ```

   Expected: `naming to docker.io/library/closeloop:latest done`.

4. **Swap the singleton container.**

   ```bash
   sudo -u lifekit bash -c '
     docker rm -f closeloop 2>/dev/null || true
     docker run -d --name closeloop --restart unless-stopped \
       -p 127.0.0.1:8372:8372 -e PORT=8372 -v closeloop-data:/data closeloop:latest
   '
   ```

   Expected: a container ID printed on stdout.

5. **Verify healthy.**

   ```bash
   for i in 1 2 3 4 5; do
     if curl -fsS http://127.0.0.1:8372/health; then echo OK; break; fi
     sleep 2
   done
   ```

   Expected: `{"status":"ok",...}`.

## Verification

- `docker ps | grep closeloop` shows the container as **`Up N seconds (healthy)`**.
- `curl -fsS https://lifekit-vps.tail1cb676.ts.net:8372/health` returns JSON (auth required for other routes).
- The `closeloop-data` volume is preserved (data persists across restarts).

## Rollback

If step 5 fails to become healthy within ~30 seconds:

1. Grab logs: `sudo -u lifekit docker logs --tail 100 closeloop`.
2. Redeploy the previous image tag (Docker keeps the last `latest`):

   ```bash
   # If you tagged the previous build (e.g., closeloop:sha-abc123), roll back to it:
   sudo -u lifekit bash -c '
     docker rm -f closeloop
     docker run -d --name closeloop --restart unless-stopped \
       -p 127.0.0.1:8372:8372 -e PORT=8372 -v closeloop-data:/data closeloop:<previous-sha>
   '
   ```

3. If no previous tagged image survives, redeploy from the previous git commit (`git reset --hard <sha>~1` and repeat steps 3–5).

## Follow-up

- If GitHub Actions is still stuck: track the [`enable-github-actions.md`](INDEX.md) runbook (wanted, not yet written) for the fix.
- If you had to roll back: bump `last_reviewed` on the offending change's docs; consider a post-incident review under [../incidents/](../incidents/INDEX.md).
