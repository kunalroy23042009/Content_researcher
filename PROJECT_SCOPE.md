# Creator Content Radar — Project Scope (v1)

**V1 includes:** YouTube channel analysis via the YouTube Data API, AI-powered niche profiling using Google Gemini (free tier), automatic competitor channel discovery, topic search across YouTube and Reddit (via `google-api-python-client` and `praw`), content classification into trending/popular/underrated categories, and AI-generated reasoning, insights, and content angle suggestions tailored to the creator's channel. The stack is Python 3.11, FastAPI, SQLModel with SQLite, a plain HTML/JS frontend, and free-tier deployment on Render.

**V1 explicitly excludes:** Instagram, TikTok (no free public search API exists for them — no scraping will be attempted), multi-user authentication, payments/billing, and a native mobile app.
