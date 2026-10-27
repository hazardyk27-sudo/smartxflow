# SmartXFlow — Hetzner Production Runtime

## Amaç

SmartXFlow production runtime tamamen Hetzner üzerinde çalışır. Replit production bağımlılığı değildir; yalnızca `preview` geliştirme/önizleme runner'ı olabilir.

Canonical akış:

```text
GitHub main
    |
    v
Hetzner /opt/smartxflow
    |
    +-- Nginx -> Gunicorn / Flask
    +-- Prematch Scraper
    +-- Live Scraper
    +-- Alarm Engine
    +-- Sinyal Engine
    +-- Polymarket Scraper
    +-- Learning Archive timers
    |
    v
Supabase
```

Production host:

- IP: `91.99.6.245`
- Domain: `smartxflow.com`
- Application root: `/opt/smartxflow`
- Application user: `smartxflow`
- Production branch: `main`

## Hard release rules

- GitHub tracked source/history is canonical.
- `preview` is development/Preview.
- `main` is the exact user-approved production SHA.
- Hetzner runs production.
- Never edit tracked production files directly on Hetzner.
- Never force-push, reset, rebase or cherry-pick around divergence.
- Production deploy happens only after explicit user approval and exact-SHA promotion to `main`.
- Replit source editing/deployment is not part of Hetzner production release.

See `/.agents/contracts/RELEASE_FLOW.md` for the canonical release procedure.

## Canonical production services

| Unit | Entrypoint / purpose |
|---|---|
| `smartxflow-web.service` | Gunicorn `web_runtime:app`, bound to `127.0.0.1:8000` |
| `smartxflow-scraper.service` | `prematch_authoritative_runtime.py` |
| `smartxflow-alarm.service` | `alarm_engine.py` |
| `smartxflow-sinyal.service` | `sinyal_engine_runtime.py` |
| `smartxflow-live.service` | `live_scraper.py` |
| `smartxflow-poly.service` | `polymarket_scraper.py` |
| `smartxflow-learning-archive-prematch.timer` | Prematch archive capture every 5 min |
| `smartxflow-learning-archive-postmatch.timer` | Postmatch settlement/diary every 10 min |

Tracked unit source files live under `deploy/systemd/` except the existing Sinyal unit at `deploy/smartxflow-sinyal.service`.

`deploy/sync_runtime_units.sh` installs the exact tracked units. It does not stop or restart services. Privileged commands are explicit and use the least-privilege sudo contract in `deploy/sudoers-smartxflow-deploy`.

## Production environment

The canonical variable list is `deploy/env.template`. Real secrets stay only in `/opt/smartxflow/.env`; never commit them.

Important production requirements include:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SESSION_SECRET`
- `Betwach_api_key`
- `LEARNING_ARCHIVE_ACCESS_SECRET`
- `SMARTXFLOW_LEARNING_API_BASE_URL=https://smartxflow.com`
- `SMARTXFLOW_MODE=server`

The web service also enforces `DISABLE_SCRAPER=true`, because collection belongs to dedicated systemd workers, not Gunicorn workers.

The prematch unit enforces `SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE=true`. A fresh `.env` template intentionally leaves the same flag `false` until the DB migration/postflight has been explicitly verified; systemd activation is the controlled production cutover point.

## Read-only preflight

Before any cutover or production release, run the tracked preflight against the exact intended production SHA:

```bash
cd /opt/smartxflow || exit 1
bash deploy/hetzner_preflight.sh <EXACT_40_CHARACTER_MAIN_SHA>
```

The preflight is read-only. It checks:

- branch, exact HEAD and clean tracked worktree;
- required environment variable presence without printing secret values;
- deploy-user sudo capability;
- installed systemd units vs tracked unit files;
- enabled/active service state;
- exact runtime entrypoints;
- authoritative prematch flag;
- duplicate local worker processes;
- `smartxflow.com` DNS;
- Gunicorn `127.0.0.1:8000` listener;
- Nginx state and HTTPS reachability.

`HETZNER_PREFLIGHT_OK` is required before a cutover is considered ready.

## GitHub Actions deploy

`.github/workflows/deploy.yml` deploys only `main` and must:

1. verify production is on branch `main` and the tracked worktree is clean;
2. fetch `origin/main`;
3. refuse divergence and use only fast-forward;
4. verify the requested GitHub SHA equals `origin/main` and final Hetzner HEAD;
5. preserve `/opt/smartxflow/.env` and runtime data;
6. sync canonical systemd units;
7. restart the six production services;
8. verify all six are active and boot-enabled;
9. verify their actual `ExecStart`/environment contract;
10. verify HEAD and tracked tree did not change during deployment.

No database migrations or destructive data actions are hidden inside this deploy workflow.

## DNS / HTTPS

Expected DNS:

```text
smartxflow.com      A  91.99.6.245
www.smartxflow.com  A  91.99.6.245
```

Nginx proxies HTTPS traffic to Gunicorn on `127.0.0.1:8000`. TLS is managed with Let's Encrypt/Certbot.

Useful read-only checks:

```bash
dig smartxflow.com +short
curl -I https://smartxflow.com
systemctl is-active nginx
systemctl is-active smartxflow-web
ss -ltn | grep '127.0.0.1:8000'
```

## Logs

```bash
tail -f /opt/smartxflow/logs/gunicorn-error.log
tail -f /opt/smartxflow/logs/scraper.log
tail -f /opt/smartxflow/logs/alarm.log
tail -f /opt/smartxflow/logs/sinyal.log
tail -f /opt/smartxflow/logs/live.log
tail -f /opt/smartxflow/logs/poly.log
```

Learning Archive systemd diagnostics:

```bash
systemctl status smartxflow-learning-archive-prematch.timer --no-pager
systemctl status smartxflow-learning-archive-postmatch.timer --no-pager
journalctl -u smartxflow-learning-archive-prematch.service -n 50 --no-pager
journalctl -u smartxflow-learning-archive-postmatch.service -n 100 --no-pager
```

## Replit after final cutover

After Hetzner has passed preflight and at least one complete production data cycle has been verified, Replit production workers must be stopped. Replit must not run:

- `scheduled_scraper.py` / `prematch_authoritative_runtime.py`
- `live_scraper.py`
- `alarm_engine.py`
- `sinyal_engine_runtime.py`
- `polymarket_scraper.py`

Replit may remain only as an optional exact-`preview` web runner. The final independence test is simple: with Replit fully stopped, `smartxflow.com`, prematch, live, alarm, signal, Poly and Learning Archive must all continue normally from Hetzner.
