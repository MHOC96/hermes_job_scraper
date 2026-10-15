# Hermes job agent

Hermes watches Sri Lankan job boards, filters postings against your criteria, deduplicates them in SQLite, and sends new matches to Telegram.

## Telegram setup

1. Open [@BotFather](https://t.me/BotFather) in Telegram and create a bot with `/newbot`. Copy the **bot token**.
2. Start a chat with your bot (send any message).
3. Obtain your **chat id**:
   - For a personal chat, message [@userinfobot](https://t.me/userinfobot) or call `getUpdates` on the Bot API after messaging your bot.
   - For a group, add the bot to the group and use the group chat id (often negative).
4. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

## Local install

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux: source .venv/bin/activate
pip install -e .
cp config.example.yaml config.yaml
cp .env.example .env
hermes config validate
hermes run --dry-run
hermes run
```

Optional environment variables:

- `HERMES_CONFIG_PATH` — path to `config.yaml` (default: `./config.yaml`)
- `HERMES_DB_PATH` — SQLite database path (default: `./data/hermes.db`)

## Configuring filters

Edit `config.yaml` (see `config.example.yaml`):

- **`role_keywords`** — job **title** must contain one of these (e.g. `intern`, `trainee`).
- **`track_keywords`** — at least one must match in **`match_fields`** (backend, AI, audit, BA, Power BI, etc.).
- **`location_include`** — Colombo-area names; jobs must match location/title/company or count as remote if `location_allow_remote` is true.
- **`max_posting_age_days`** — default `14` (today back two weeks); uses ITPro `datetime` and TopJobs opening date.
- **`include_undated`** — set `true` only if you want listings with no parseable date (default `false`).
- **`exclude_keywords`** — skip jobs whose matched fields contain these terms.
- **`match_fields`** — `title`, `company`, `location`, `url`, or `source`.
- Legacy **`job_titles`** / **`include_keywords`** — used only when `track_keywords` is empty.

## Sources

Built-in sources (enable under `sources` in config):

| Key | Site | Notes |
|-----|------|--------|
| `itpro` | [ITPro Jobs](https://itpro.lk/jobs) | Paginates `?p=N`, parses `article.job-card` |
| `topjobs` | [topjobs.lk](https://www.topjobs.lk) | Keyword search; uses `search_terms` or your job titles |

To add a source:

1. Implement `JobSource` in `src/hermes/sources/yoursource.py` with a `fetch(config) -> list[JobPosting]` method.
2. Register it in `src/hermes/sources/__init__.py` (`SOURCE_REGISTRY`).
3. Add a pydantic block under `SourcesConfig` in `config.py` and wire enable flags in `pipeline._enabled_sources`.

## VM deployment (systemd)

On a Linux VM as user `hermes`:

```bash
sudo useradd --system --home /opt/hermes_agent hermes || true
sudo mkdir -p /opt/hermes_agent
sudo cp -r . /opt/hermes_agent/
cd /opt/hermes_agent
python3 -m venv .venv
sudo -u hermes .venv/bin/pip install -e .
sudo cp deploy/hermes.service deploy/hermes.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hermes.timer
sudo systemctl start hermes.service   # manual run
```

Ensure `/opt/hermes_agent/.env` and `config.yaml` exist and are readable by `hermes`.

## CLI

```bash
hermes config validate
hermes run --dry-run
hermes run
```

Telegram sends **multiple messages** if needed (mixed **itpro** and **topjobs** per batch). Links show `View on itpro` / `View on topjobs`.

If you already ran `hermes run` once and only saw ITPro, older runs capped at 10 jobs with ITPro listed first. To resend everything (e.g. after an upgrade), delete the local database and run again:

```bash
# Windows PowerShell
Remove-Item -Force data\hermes.db -ErrorAction SilentlyContinue
hermes run
```
