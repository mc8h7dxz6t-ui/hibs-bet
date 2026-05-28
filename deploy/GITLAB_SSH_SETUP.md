# GitLab SSH (one-time)

GitHub (`origin`) is already synced from your Mac. GitLab (`gitlab`) drives CI deploy; production was stuck at `c624a43e` until `main` is pushed.

## Add your Mac key to GitLab

1. Copy your public key:

   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```

2. GitLab → **User Settings → SSH Keys** (or project **Deploy keys** with write access):  
   https://gitlab.com/-/user_settings/ssh_keys

3. Paste the key, save.

4. Test and push:

   ```bash
   ssh -T git@gitlab.com
   ./scripts/push_all_remotes.sh
   ```

`push_all_remotes.sh` uses `--force-with-lease` because GitLab `main` is a stale parallel branch; your laptop `main` is the full superset (DQ, players, stability) — no merge of the old line.

## Alternative: HTTPS token

Add to `.env` (never commit):

```bash
GITLAB_TOKEN=glpat-xxxxxxxx   # write_repository scope
```

Then `./scripts/push_all_remotes.sh` will push via HTTPS.

## No GitLab? Deploy anyway

```bash
./scripts/deploy_to_vps.sh
./scripts/vps_restart_test.sh
```

Same code path as CI rsync to `/opt/hibs-bet`.
