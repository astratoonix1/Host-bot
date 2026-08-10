# Bot Maker & Auto-Filter Manager

A modular Telegram bot system (Pyrogram + Motor/MongoDB) that lets any user
spawn their own file-search "auto-filter" bot from a bot token, with zero
coding required.

## Structure

```
config.py            # Env var loading & validation
database.py           # Motor/MongoDB async data layer
bot_manager.py         # Runtime registry for spawned bot Clients
main.py               # Entry point: starts the manager + restores saved bots
plugins/
  start.py            # /start, /help
  creator.py           # /create setup wizard
  filter.py            # Auto file indexing + search
  settings.py          # /settings management panel
```

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in your values (or export them
   directly in your shell/host's environment settings).
3. Run the manager:
   ```
   python3 main.py
   ```

## How it works

- Users DM the **Main Manager Bot** and run `/create`.
- The wizard collects and validates a Bot Token, API ID, API Hash, and
  MongoDB URI, then saves them to the `user_bots` collection and boots a
  new Pyrogram `Client` for that bot in-process (`bot_manager.py`).
- Every spawned bot shares the same `plugins/` package, so each one gets
  auto-filter search and its own `/settings` panel automatically.
- Add a spawned bot as **admin** to a channel; every document/video/audio
  posted there is indexed into MongoDB (`indexed_files`, scoped per
  `bot_id`).
- Any plain-text message to that bot searches the index via case-insensitive
  regex and returns paginated inline results.
- On restart, `main.py` reloads every bot flagged `is_active: True` from
  MongoDB and starts them concurrently in the background.

## Notes for production

- Search-result callback data embeds the query text; Telegram caps
  `callback_data` at 64 bytes, so very long queries are truncated for
  pagination. Swap in a short-lived server-side cache keyed by an id if you
  need to support long queries reliably.
- Consider adding rate limiting and per-bot MongoDB URIs (the schema
  already stores each user's own `mongo_uri` for that purpose) if you want
  full per-user data isolation instead of a shared database.
- Run under a process manager (systemd, pm2, Docker) for restart resilience.
