# Deployment Guide

How `kolably_backend` actually runs in production. Written by reverse-engineering
the live setup on 2026-07-21 — if reality drifts from this doc, trust the server
and update this file.

## Architecture

```
Internet
   │
   │  DNS: api.kolably.com  →  3.7.180.158 (A record, managed outside AWS —
   │                            NOT in Route53, check the domain registrar/DNS host)
   ▼
Elastic IP 3.7.180.158  (eipalloc-0c20f085d58304d4b, always stable across reboots)
   │
   ▼
EC2 instance i-01fa6671362957370  (ap-south-1 / Mumbai)
   - Type: t3.micro
   - AMI: Amazon Linux 2023 (al2023-ami-2023.10.20260302.1)
   - Key pair: kolably-backend-key  (.pem held locally, e.g. kolably-backend-key.pem)
   - Security group: kolably-backend-sg (sg-05a638a6e3935b385)
       - 22/tcp   0.0.0.0/0   (SSH)
       - 80/tcp   0.0.0.0/0   (HTTP → redirected to HTTPS)
       - 443/tcp  0.0.0.0/0   (HTTPS)
   │
   ▼
nginx (system package, systemd service "nginx")
   - Reverse proxy, TLS termination
   - Config: /etc/nginx/conf.d/api.kolably.com.conf
   - TLS cert: Let's Encrypt, via certbot's nginx plugin
   │
   ▼
Docker container "kolably-backend-prod"  (image: kolably-backend-cicd)
   - Maps host 8001 → container 8000
   - FastAPI app (uvicorn), started via Dockerfile CMD
   - Env vars loaded from --env-file .env at `docker run` time
```

**Stack:** FastAPI + Supabase (DB/auth) + Razorpay (payments) + Google Maps API.
See the main [README.md](../README.md) for the app-code layout.

## AWS Account

- Account ID: `047492347344`
- Region: **ap-south-1** (Mumbai) — resources are NOT in us-east-1/default, check
  this region first when debugging
- No load balancer, no ACM certificate, no CloudFront, no Route53 hosted zone —
  this is a single bare EC2 instance, not a managed AWS network stack

## DNS & TLS

- `api.kolably.com` is a plain A record pointing at the Elastic IP above. It is
  **not** managed in this AWS account's Route53 — check the domain registrar/
  external DNS provider if it ever needs to change.
- TLS certificate is Let's Encrypt, obtained and renewed via `certbot` using its
  **nginx plugin** (`authenticator = nginx`, `installer = nginx`). Certbot edits
  `/etc/nginx/conf.d/api.kolably.com.conf` directly to add the `listen 443 ssl`
  block, the HTTP→HTTPS redirect, and cert paths.
  - Cert name: `api.kolably.com`
  - Live paths: `/etc/letsencrypt/live/api.kolably.com/{fullchain,privkey}.pem`
  - Renewal is driven by the systemd unit **`certbot-renew.timer`**, which runs
    `certbot renew` and only actually renews certs within 30 days of expiry.

  > ⚠️ **Known gotcha (incident 2026-07-21):** `certbot-renew.timer` was
  > installed but **never enabled**, so it silently never ran. The cert issued
  > 2026-04-09 expired 2026-07-08 and nobody noticed until the API started
  > throwing TLS errors for API clients. Fixed by renewing manually
  > (`sudo certbot renew --cert-name api.kolably.com --no-random-sleep-on-renew`)
  > and running `sudo systemctl enable --now certbot-renew.timer`. **Verify this
  > timer is still enabled** (`systemctl list-timers '*certbot*'`) if SSL ever
  > breaks again — this is the #1 suspect.
  > Consider adding an external uptime/cert-expiry monitor so this is caught
  > within a day next time, not weeks.

- The `nginx/api.kolably.com.conf` checked into this repo is a **plain-HTTP-only
  reference copy** (port 80, no TLS block) — it does not reflect what's actually
  running on the server, since certbot rewrites the live file in place and that
  change is never synced back to git. Don't copy the repo's version over the
  live config without re-running certbot, or you'll drop TLS.

## CI/CD

`.github/workflows/deploy.yml` runs on every push to `main`:

1. Tars up the whole repo (`build_output/kolably_backend.tar.gz`)
2. Writes the deploy key from the `EC2_SSH_KEY` secret (base64-encoded in the
   secret, decoded on the runner) and `scp`s the archive to the instance
3. SSHes in as `${{ secrets.EC2_USER }}`@`${{ secrets.EC2_HOST }}` and:
   - Extracts the archive into a fresh `kolably_backend_v2/`
   - Copies the **existing `.env` from the previous deploy** into the new
     folder (the `.env` itself is never in git — it persists on the server
     across deploys and must be created/updated manually via SSH)
   - `docker build -t kolably-backend-cicd .`
   - `docker rm -f kolably-backend-prod || true` then
     `docker run -d --name kolably-backend-prod -p 8001:8000 --env-file .env kolably-backend-cicd`
   - `systemctl reload nginx`
   - Swaps `kolably_backend_v2` → `kolably_backend`, deleting the old folder

**Implications / gotchas:**
- There's no image versioning/tagging — `kolably-backend-cicd:latest` is always
  overwritten, so there's no built-in rollback. To roll back, you'd need to
  check out an older commit locally and manually redeploy, or keep a manual
  backup of a known-good image (`docker tag`/`docker save`) before risky deploys.
- `git` is **not installed** on the EC2 instance — the server-side
  `kolably_backend/.git` directory is just an artifact carried inside the tar
  archive (from the CI runner's checkout), not a usable local clone. Don't
  expect `git pull`/`git log` to work over SSH on the box.
- First-time `.env` setup on a fresh instance has to be done by hand (SCP or
  paste over SSH) — the pipeline only ever copies forward an `.env` that
  already exists.

## Server Access

```bash
chmod 400 kolably-backend-key.pem
ssh -i kolably-backend-key.pem ec2-user@3.7.180.1583
```

Useful checks once connected:

```bash
sudo docker ps                                   # confirm app container is up
sudo docker logs -f kolably-backend-prod         # app logs
sudo systemctl status nginx                      # reverse proxy
sudo certbot certificates                        # TLS cert status/expiry
systemctl list-timers '*certbot*'                # confirm auto-renew is enabled
sudo tail -f /var/log/letsencrypt/letsencrypt.log
```

## Manual Redeploy (without pushing to `main`)

```bash
scp -i kolably-backend-key.pem -r . ec2-user@3.7.180.158:~/kolably_backend_manual
ssh -i kolably-backend-key.pem ec2-user@3.7.180.158
cd kolably_backend_manual
sudo docker build -t kolably-backend-cicd .
sudo docker rm -f kolably-backend-prod
sudo docker run -d --name kolably-backend-prod -p 8001:8000 --env-file .env kolably-backend-cicd
sudo systemctl reload nginx
```

## Credentials Hygiene

- `.env` on the server holds live Supabase/Razorpay/Google Maps secrets — never
  commit it, and be careful with `cat`/logging it over SSH sessions that might
  be recorded.
