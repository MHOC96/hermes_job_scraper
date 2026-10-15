# Hermes job agent

Hermes scrapes Sri Lankan job boards (**[ITPro.lk](https://itpro.lk/jobs)** and **[topjobs.lk](https://www.topjobs.lk)** / topjob.lk), filters listings against your criteria, keeps a **14-day** posting window (configurable), deduplicates in **SQLite**, and sends **new** matches to **Telegram**.

Repository: [github.com/MHOC96/hermes_job_scraper](https://github.com/MHOC96/hermes_job_scraper)

Built with **Python 3.10+** and **[Scrapling](https://github.com/D4Vinci/Scrapling)** (`Fetcher.get`).

---

## What gets committed to git

| Tracked | Not tracked (local / VM only) |
|---------|-------------------------------|
| `src/`, `pyproject.toml`, `deploy/` | `.env` (Telegram token) |
| `config.example.yaml`, `.env.example` | `config.yaml` (your live filters) |
| `README.md` | `*.pem`, `data/`, `*.db`, `*.pdf` |

Copy examples on each machine:

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

---

## Telegram setup

1. Create a bot with [@BotFather](https://t.me/BotFather) (`/newbot`) and copy the **bot token**.
2. Open your bot in Telegram and send any message.
3. Get your **chat id** ([@userinfobot](https://t.me/userinfobot) or `getUpdates` on the [Bot API](https://core.telegram.org/bots/api)).
4. Put both values in `.env`:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Never commit `.env` or paste tokens in chat.

---

## Local install (Windows or Linux)

```bash
git clone https://github.com/MHOC96/hermes_job_scraper.git
cd hermes_job_scraper
python -m venv .venv
```

```bash
# Linux / macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate
```

```bash
pip install -e .
cp config.example.yaml config.yaml
cp .env.example .env
# edit config.yaml and .env
hermes config validate
hermes run --dry-run
hermes run
```

Optional environment variables:

- `HERMES_CONFIG_PATH` — path to `config.yaml` (default: `./config.yaml`)
- `HERMES_DB_PATH` — SQLite path (default: `./data/hermes.db`)

---

## Configuring filters

Edit `config.yaml` (start from `config.example.yaml`):

| Key | Purpose |
|-----|---------|
| **`role_keywords`** | Title must match one of these (`intern`, `internship`, `trainee`). Uses word boundaries so **internal** ≠ **intern**. |
| **`track_keywords`** | At least one must match in `match_fields` (backend, AI, audit, BA, Power BI, etc.). |
| **`location_include`** | Colombo-area (and nearby) names; also checks title/company. |
| **`location_allow_remote`** | Allow listings marked remote / WFH. |
| **`max_posting_age_days`** | Default `14` — ITPro posting time + TopJobs opening date. |
| **`include_undated`** | `false` = drop jobs with no parseable date. |
| **`exclude_keywords`** | Skip if any match field contains these terms. |
| **`sources.itpro.max_pages`** | ITPro listing pages per run. |
| **`sources.topjobs.search_terms`** | TopJobs keyword searches (one fetch per term). |
| **`sources.topjobs.max_pages`** | Pages per keyword. |

Legacy **`job_titles`** / **`include_keywords`** apply only when **`track_keywords`** is empty.

Reload: edit `config.yaml` and run again — no redeploy needed on the VM.

---

## Job sources

| Key | Site | Notes |
|-----|------|--------|
| `itpro` | [itpro.lk/jobs](https://itpro.lk/jobs) | `article.job-card`, pagination `?p=N` |
| `topjobs` | [topjobs.lk](https://www.topjobs.lk) | JSP search; `topjob.lk` redirects here |

To add another site: implement `JobSource` in `src/hermes/sources/`, register in `sources/__init__.py`, extend `SourcesConfig` in `config.py`.

---

## Telegram notifications

- Sends **multiple messages** if needed (8 jobs per message).
- **Interleaves** `itpro` and `topjobs` so both appear in early batches.
- Each link is labeled **View on itpro** / **View on topjobs**.
- Only **new** jobs (not already in SQLite) are sent.

Reset and resend all current matches (e.g. after a big config change):

```bash
# Linux
rm -f data/hermes.db && hermes run

# Windows PowerShell
Remove-Item -Force data\hermes.db -ErrorAction SilentlyContinue; hermes run
```

---

## Azure VM deployment (Ubuntu)

Example: VM **hermes-vps**, user **azureuser**, app path **`/opt/hermes_agent`**.

### 1. SSH from Windows

Fix PEM permissions if OpenSSH complains:

```powershell
icacls "D:\path\to\hermes-vps_key.pem" /inheritance:r
icacls "D:\path\to\hermes-vps_key.pem" /grant:r "$($env:USERNAME):(R)"
```

```powershell
ssh -i "D:\path\to\hermes-vps_key.pem" azureuser@<VM_PUBLIC_IP>
```

### 2. Clone on the VM

```bash
sudo mkdir -p /opt/hermes_agent
sudo chown azureuser:azureuser /opt/hermes_agent
git clone https://github.com/MHOC96/hermes_job_scraper.git /opt/hermes_agent
cd /opt/hermes_agent
```

### 3. Secrets and config (from your PC)

`config.yaml` and `.env` are **not** in git. Copy once:

```powershell
scp -i "D:\path\to\hermes-vps_key.pem" .env config.yaml azureuser@<VM_PUBLIC_IP>:/opt/hermes_agent/
```

Or on the VM: `cp config.example.yaml config.yaml` and `nano .env`.

### 4. Install and test

```bash
cd /opt/hermes_agent
sudo apt update
sudo apt install -y python3 python3-venv python3-pip build-essential git
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .
mkdir -p data
chmod 600 .env
.venv/bin/hermes config validate
.venv/bin/hermes run --dry-run
.venv/bin/hermes run
```

First live run can take **1–2 minutes** (many TopJobs keyword pages).

### 5. Hourly systemd timer

```bash
sudo useradd --system --home /opt/hermes_agent --shell /usr/sbin/nologin hermes 2>/dev/null || true
sudo chown -R hermes:hermes /opt/hermes_agent
sudo cp deploy/hermes.service deploy/hermes.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hermes.timer
sudo systemctl start hermes.service
```

Check logs:

```bash
sudo journalctl -u hermes.service -n 50 --no-pager
sudo systemctl list-timers | grep hermes
```

The VM must be **running** at timer fire times (hourly). Outbound HTTPS is required; no inbound ports needed for Hermes.

### 6. Update after `git push`

On the VM:

```bash
cd /opt/hermes_agent
git pull
.venv/bin/pip install -e .
sudo systemctl start hermes.service
```

---

## CLI

```bash
hermes config validate
hermes run --dry-run    # no DB write, no Telegram
hermes run              # scrape, filter, dedupe, notify
```

---

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| `UNPROTECTED PRIVATE KEY FILE` | Restrict PEM ACLs with `icacls` (see above). |
| No Telegram | Message the bot first; check `.env` on the VM; test outbound internet. |
| Only ITPro in old runs | Upgrade to latest code; delete `data/hermes.db` and run again. |
| `Permission denied` on VM | `sudo chown -R hermes:hermes /opt/hermes_agent` after `git pull`. |
