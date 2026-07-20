# Creator Content Radar

A tool where a YouTube creator pastes their channel URL to get AI-powered niche profiling, competitor discovery, and trending content suggestions from YouTube and Reddit.

## Features

- **Channel Analysis** — Paste any YouTube channel URL and get a full niche profile: niche, topics, content style, target audience, growth potential, and content recommendations
- **Competitor Discovery** — AI generates search queries to find similar channels in your niche, ranked by subscriber-count proximity and search overlap
- **Topic Search** — Search YouTube + Reddit for trending content in your niche. Results are classified as trending, popular, or underrated
- **AI Content Angles** — Get specific, actionable content ideas tailored to your channel's style and audience
- **Multi-AI Support** — Powered by Gemini, Groq, and OpenRouter with automatic fallback
- **User Authentication** — JWT-based auth with free/pro/business plans
- **Stripe Billing** — Subscription management with checkout and customer portal
- **Export** — Download analysis as PDF or CSV (Pro+ plan)
- **Rate Limiting** — Protects against API quota exhaustion
- **Caching** — SQLite/PostgreSQL cache for 24h to avoid redundant API calls
- **Monitoring** — Prometheus metrics at /metrics

## Quick Start

```bash
# Clone
git clone https://github.com/kunalroy23042009/Content_researcher.git
cd Content_researcher

# Install
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
uvicorn app.main:app --reload

# Open
# http://localhost:8000 — Landing page
# http://localhost:8000/app — App UI
# http://localhost:8000/docs — API docs
```

## Environment Variables

See `.env.example` for all required variables. You need at minimum:
- `YOUTUBE_API_KEY` — YouTube Data API v3 key
- `GEMINI_API_KEY` — Google Gemini API key
- `SECRET_KEY` — JWT secret (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)

Optional:
- `GROQ_API_KEY`, `OPENROUTER_API_KEY` — Alternative AI providers
- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` — Reddit search
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` — Payments
- `DATABASE_URL` — PostgreSQL URL for production

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/analyze-channel` | Analyze a YouTube channel |
| POST | `/find-competitors` | Find competitor channels |
| POST | `/search-topic` | Search YouTube + Reddit for topics |
| POST | `/api/auth/register` | Register a new user |
| POST | `/api/auth/login` | Login and get JWT |
| GET | `/api/auth/me` | Get current user |
| GET | `/api/billing/usage` | Get plan usage |
| POST | `/api/billing/checkout` | Create Stripe checkout |
| POST | `/api/billing/webhook` | Stripe webhook handler |
| POST | `/api/billing/portal` | Stripe customer portal |
| GET | `/api/analyze/{id}/export` | Export analysis (PDF/CSV) |
| GET | `/metrics` | Prometheus metrics |
| GET | `/health` | Health check |

## Tech Stack

- Python 3.11, FastAPI, Uvicorn
- SQLModel + SQLite (local) / PostgreSQL (production)
- Google YouTube Data API v3, Google Gemini, Groq, OpenRouter
- Reddit via PRAW
- JWT auth (python-jose + passlib)
- Stripe for payments
- SlowAPI for rate limiting
- Prometheus for monitoring
- Vanilla HTML/CSS/JS frontend

## Deployment

The app is configured for Render:

1. Connect your GitHub repo to Render
2. Set environment variables (see `.env.example`)
3. Render will auto-deploy from `main` using `render.yaml`

Docker is also supported:
```bash
docker build -t content-radar .
docker run -p 8000:8000 content-radar
```

## Testing

```bash
pytest --cov=app --cov-report=term-missing
```

## License

MIT
