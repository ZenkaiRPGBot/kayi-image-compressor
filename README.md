# Kayi Image Compressor

**Compress smarter. Share faster.**

A production-ready Telegram image compression bot for the [Kayi Bots](https://t.me/KayiBots) ecosystem.

---

## Features

- **Auto Optimize** — One tap, best quality-to-size balance
- **Quality Presets** — Best Quality, Balanced, Smallest File, Lossless
- **Target Size** — Binary search to hit an exact file size in KB
- **Format Conversion** — JPEG, PNG, WebP input and output
- **Privacy First** — EXIF metadata stripped by default
- **Secure Webhook** — Secret token header validation
- **Resource Safe** — Single-worker process pool, 25s timeout, bounded queue
- **Force Subscribe** — Optional channel membership gate

---

## Supported Formats

| Input | Output |
|-------|--------|
| JPEG  | JPEG   |
| PNG   | PNG    |
| WebP  | WebP   |

---

## Limits

| Limit | Value |
|-------|-------|
| Max upload size | 8 MB |
| Max resolution | 12 MP |
| Daily compressions | 20 / user |
| Session TTL | 10 minutes |
| Processing timeout | 25 seconds |

---

## Setup

### 1. Create the bot

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Set name: `Kayi Image Compressor`
3. Choose a username ending in `Bot`
4. Copy the token

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set BOT_TOKEN and WEBHOOK_BASE_URL
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run locally (polling for development)

For quick local testing, use the webhook server pointed at a tunnel (e.g. ngrok):

```bash
ngrok http 10000
# Set WEBHOOK_BASE_URL=https://<ngrok-id>.ngrok-free.app in .env
python app/main.py
```

---

## Deployment (Render Free)

1. Push this repository to GitHub.
2. Create a new **Web Service** on [Render](https://render.com).
3. Connect your GitHub repo.
4. Set environment variables in Render dashboard:
   - `BOT_TOKEN`
   - `WEBHOOK_BASE_URL` (your Render URL, e.g. `https://kayi-image-compressor.onrender.com`)
   - `WEBHOOK_SECRET` (optional but recommended)
5. Render will auto-deploy on every push.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

## Running Benchmarks

```bash
python scripts/benchmark.py
```

---

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome screen |
| `/start help` | Open Help Center directly |
| `/help` | Compression guide and instructions |
| `/compress` | Compression hint (send image directly) |
| `/privacy` | Privacy and data handling policy |

---

## Architecture

```
app/
├── main.py              # Entry point: webhook server + startup
├── config.py            # Env-based configuration
├── bot/
│   ├── handlers/        # /start, /help, image upload, callbacks
│   ├── keyboards/       # Inline keyboard builders
│   ├── messages/        # All message text constants
│   └── middlewares/     # FSub + rate limit
├── compression/
│   ├── engine.py        # Main orchestration (runs in ProcessPoolExecutor)
│   ├── target_size.py   # Binary search target-size algorithm
│   ├── presets.py       # Quality presets (Best/Balanced/Smallest/Lossless)
│   ├── formats.py       # Format conversion, transparency handling
│   ├── metadata.py      # EXIF read, normalize, strip
│   ├── statistics.py    # Result stats dataclass
│   └── validation.py    # File validation (magic bytes, size, pixels)
├── services/
│   ├── sessions.py      # In-memory session store with TTL
│   ├── rate_limits.py   # Per-user daily/cooldown limits
│   ├── queue.py         # Bounded asyncio job queue
│   └── cleanup.py       # Temp file cleanup
└── web/
    ├── webhook.py       # aiohttp webhook handler
    └── health.py        # GET /health endpoint
```

---

## Privacy

All images are processed in a temporary file and deleted immediately after delivery.
EXIF metadata is stripped by default. No images are stored persistently.
Sessions expire after 10 minutes of inactivity and are not persisted across restarts.

---

## Links

- **Bot:** [@KayiImgShrinkBot](https://t.me/KayiImgShrinkBot)
- **Channel:** [@KayiBots](https://t.me/KayiBots)
- **Developer:** [@qouba](https://t.me/qouba)
