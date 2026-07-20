# Creator Content Radar — Full Build Prompt for IDE AI

> **How to use:** Paste everything below the line into your IDE AI (Cursor / Windsurf / Copilot / etc.) as a single prompt. Then execute phase by phase — do not ask the AI to do all phases at once. One phase per prompt, test it, then move to the next.

---

## CONTEXT — Read This First

You are working on **Creator Content Radar**, a Python/FastAPI web app that lets a YouTube creator paste their channel URL and get back: AI-powered niche profiling, competitor discovery, and trending content suggestions from YouTube and Reddit.

### Current State of the Codebase

The project is a **scaffold** — architecture is planned but core logic is unimplemented.

**Files that have REAL code:**
- `app/config.py` — pydantic-settings loading 4 API keys from `.env` (YOUTUBE_API_KEY, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, GEMINI_API_KEY). Working.
- `app/main.py` — FastAPI app with one `/health` endpoint and a `StaticFiles` mount serving `static/index.html`. Working but minimal.
- `app/__init__.py` — empty package marker.

**Files that are STUBS (only a docstring, no implementation):**
- `app/db.py` — "Database — SQLModel engine and session management for SQLite." — EMPTY
- `app/models.py` — "Models — SQLModel table definitions." — EMPTY
- `app/channel_analyzer.py` — "Channel analyzer — fetches YouTube channel data and builds a niche profile using AI." — EMPTY
- `app/topic_search.py` — "Topic search — queries YouTube and Reddit for content matching a given topic." — EMPTY
- `app/competitor_finder.py` — "Competitor finder — discovers related YouTube channels in the same niche." — EMPTY
- `app/ai_reasoning.py` — "AI reasoning — generates content angle suggestions using Gemini." — EMPTY
- `app/classifier.py` — "Classifier — labels content as trending, popular, or underrated." — EMPTY

**Other files:**
- `static/index.html` — placeholder "Coming soon." page
- `tests/test_main.py` — single test for `/health` endpoint
- `pyproject.toml` — dependencies defined (FastAPI, uvicorn, google-api-python-client, praw, google-generativeai, pydantic, pydantic-settings, httpx, sqlmodel)
- `PROJECT_SCOPE.md` — scope document (V1 definition)
- `data/.gitkeep` — empty data directory for SQLite DB

**Stack:** Python 3.11, FastAPI, SQLModel + SQLite, google-api-python-client (YouTube Data API v3), PRAW (Reddit API), google-generativeai (Gemini), plain HTML/JS frontend, deploy on Render.

**V1 Scope (from PROJECT_SCOPE.md):** YouTube channel analysis, AI niche profiling (Gemini), competitor discovery, topic search across YouTube + Reddit, content classification (trending/popular/underrated), AI-generated content angle suggestions. **Excludes:** Instagram/TikTok, multi-user auth, payments, mobile app.

---

## PHASE 0 — Audit, Restructure & Project Hygiene

### Goal
Make the existing scaffold clean, linted, and properly structured before writing any new logic.

### Tasks
1. Run `ruff check .` and `black --check .` — fix all issues.
2. Add a `requirements.txt` (pinned versions) alongside `pyproject.toml` for Render compatibility.
3. Create a `.env.example` file documenting all 4 required env vars with comments:
   ```
   # YouTube Data API v3 — https://console.cloud.google.com/apis/library/youtube-data-api
   YOUTUBE_API_KEY=
   # Reddit API — https://www.reddit.com/prefs/apps (create a "script" type app)
   REDDIT_CLIENT_ID=
   REDDIT_CLIENT_SECRET=
   REDDIT_USER_AGENT=creator-content-radar/0.1
   # Google Gemini — https://aistudio.google.com/apikey
   GEMINI_API_KEY=
   ```
4. Add `Procfile` for Render: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add `render.yaml` for free-tier deploy config (Python 3.11, auto-deploy from main).
6. Create directory structure:
   ```
   app/
     __init__.py
     config.py          (exists)
     main.py            (exists, will expand in Phase 7)
     db.py              (will implement in Phase 1)
     models.py          (will implement in Phase 1)
     schemas.py         (NEW — Pydantic request/response schemas)
     channel_analyzer.py
     competitor_finder.py
     topic_search.py
     classifier.py
     ai_reasoning.py
     routers/
       __init__.py
       analyze.py       (NEW — Phase 7)
       topics.py        (NEW — Phase 7)
     services/
       __init__.py
       youtube_client.py   (NEW — Phase 2)
       reddit_client.py    (NEW — Phase 4)
       gemini_client.py    (NEW — Phase 5)
   static/
     index.html        (will rebuild in Phase 8)
     app.js            (NEW — Phase 8)
     style.css         (NEW — Phase 8)
   tests/
     test_main.py      (exists)
     test_channel_analyzer.py  (NEW — per phase)
     ...
   ```
7. Add `app/routers/__init__.py` and `app/services/__init__.py` as empty packages.
8. Update `.gitignore` to also exclude `*.sqlite`, `*.sqlite3`.

### Acceptance Criteria
- `ruff check .` passes with zero errors.
- `black --check .` passes.
- `pip install -e ".[dev]"` succeeds.
- `uvicorn app.main:app` starts and `/health` returns `{"status": "ok"}`.
- `.env.example` exists and is committed.

---

## PHASE 1 — Database Models & Session Management

### Goal
Implement `app/db.py` and `app/models.py` with SQLModel tables and a database session dependency.

### Tasks for `app/models.py`
Define these SQLModel tables:

1. **ChannelAnalysis** — stores one analysis run for a channel:
   - `id: int (PK)`
   - `channel_url: str` (input URL)
   - `channel_id: str` (YouTube channel ID, resolved)
   - `channel_name: str`
   - `subscriber_count: int`
   - `video_count: int`
   - `view_count: int`
   - `niche_profile: str` (JSON string from Gemini)
   - `status: str` ("pending", "completed", "failed")
   - `created_date: datetime` (auto)
   - `updated_date: datetime` (auto)

2. **Competitor** — discovered competitor channels:
   - `id: int (PK)`
   - `analysis_id: int (FK → ChannelAnalysis.id)`
   - `channel_id: str`
   - `channel_name: str`
   - `subscriber_count: int`
   - `relevance_score: float`
   - `created_date: datetime`

3. **TopicResult** — topic search results:
   - `id: int (PK)`
   - `analysis_id: int (FK → ChannelAnalysis.id)`
   - `topic: str`
   - `platform: str` ("youtube" or "reddit")
   - `title: str`
   - `url: str`
   - `engagement_score: float`
   - `classification: str` ("trending", "popular", "underrated")
   - `created_date: datetime`

4. **ContentSuggestion** — AI-generated content ideas:
   - `id: int (PK)`
   - `analysis_id: int (FK → ChannelAnalysis.id)`
   - `title: str`
   - `angle: str` (content angle description)
   - `rationale: str`
   - `platform: str` (recommended platform)
   - `created_date: datetime`

### Tasks for `app/db.py`
- Create a `get_engine()` function returning a SQLModel engine.
- DB path: `data/content_radar.db` (use `sqlite:///./data/content_radar.db`).
- Create `get_session()` async generator / FastAPI dependency yielding sessions.
- Call `SQLModel.metadata.create_all(engine)` on startup (or use a lifespan handler in `main.py`).
- Add a `init_db()` function that creates the `data/` directory if missing and initializes tables.

### Tasks for `app/schemas.py` (NEW)
- Define Pydantic v2 request schemas: `AnalyzeRequest`, `TopicSearchRequest`.
- Define response schemas: `ChannelAnalysisResponse`, `CompetitorListResponse`, `TopicResultListResponse`, `ContentSuggestionListResponse`.
- Use `model_config = ConfigDict(from_attributes=True)` for ORM compatibility.

### Acceptance Criteria
- `app/db.py` can create an engine and a session.
- `SQLModel.metadata.create_all` runs without error.
- All 4 tables exist in SQLite (verify with `sqlite3 data/content_radar.db ".tables"`).
- `app/schemas.py` has all request/response schemas.
- Write `tests/test_db.py` — test that `init_db()` creates tables and a session can insert/query a `ChannelAnalysis` row.

---

## PHASE 2 — YouTube Channel Analyzer

### Goal
Implement `app/channel_analyzer.py` and `app/services/youtube_client.py`.

### Tasks for `app/services/youtube_client.py` (NEW)
- Build a `YouTubeClient` class using `googleapiclient.discovery.build("youtube", "v3", developerKey=...)`.
- Method: `resolve_channel(channel_url: str) -> dict` — takes any YouTube channel URL (handle `@name`, `/channel/UC...`, `/c/name`, `/user/name`) and returns channel ID + metadata.
  - For `@handle` URLs: use `channels.list(part="snippet,statistics", forHandle="@name")`.
  - For `/channel/UC...` URLs: use `channels.list(part="snippet,statistics", id="UC...")`.
  - For legacy `/c/name` or `/user/name`: use `search.list(part="snippet", type="channel", q="name")` then resolve.
- Method: `get_channel_videos(channel_id: str, max_results: int = 50) -> list[dict]` — fetch recent uploads via `search.list(channelId=..., order="date", type="video")`.
- Method: `get_video_stats(video_ids: list[str]) -> list[dict]` — batch fetch via `videos.list(part="statistics,snippet")` (50 IDs per call).
- Method: `get_channel_stats(channel_id: str) -> dict` — subscriber count, view count, video count.
- Handle quota errors (403) gracefully — return a structured error, don't crash.
- Rate-limit awareness: the free tier is 10,000 quota units/day. Log quota usage per call.

### Tasks for `app/channel_analyzer.py`
- Build `ChannelAnalyzer` class:
  - `__init__(self, yt_client: YouTubeClient, gemini_client)` — dependency injection.
  - `async analyze(self, channel_url: str) -> ChannelAnalysisResult`:
    1. Resolve channel URL → channel ID + stats.
    2. Fetch last 30-50 video IDs.
    3. Batch fetch video stats (views, likes, comments, publish date).
    4. Build a "channel summary" dict: name, subs, total views, avg views, top 10 videos by views, upload frequency, most common keywords in titles.
    5. Pass the summary to Gemini (via `ai_reasoning.py`) to generate a niche profile.
    6. Return structured result with raw stats + AI niche profile.
  - `get_top_keywords(self, video_titles: list[str]) -> list[tuple[str, int]]` — extract common words/phrases from titles, excluding stopwords.
- Cache results: before analyzing, check if a `ChannelAnalysis` for this `channel_id` exists and was created < 24 hours ago. If yes, return cached.

### Acceptance Criteria
- Can resolve `https://www.youtube.com/@Caruniverse_2.0` and return channel stats.
- Can fetch 50 recent video IDs and their stats.
- Returns a structured dict with channel metadata + video stats.
- Quota errors are handled gracefully (return error message, don't 500).
- Write `tests/test_channel_analyzer.py` — mock the YouTube API client, test `analyze()` returns expected structure.
- Write `tests/test_youtube_client.py` — mock API responses, test URL resolution for all 4 URL formats.

---

## PHASE 3 — Competitor Finder

### Goal
Implement `app/competitor_finder.py`.

### Tasks
- Build `CompetitorFinder` class:
  - `__init__(self, yt_client: YouTubeClient)`.
  - `async find_competitors(self, channel_id: str, channel_name: str, niche_keywords: list[str], max_results: int = 10) -> list[CompetitorResult]`:
    1. Use niche keywords (from the channel analysis) as search queries via `search.list(type="channel", q="keyword")`.
    2. For each result channel, fetch their stats (subs, views, video count).
    3. Score relevance: how many niche keywords appear in the competitor's channel description + recent video titles. Weight by subscriber similarity (channels within 0.5x–5x of the original channel's subs score higher — closer in size = more relevant competitor).
    4. Deduplicate (don't include the original channel).
    5. Sort by relevance score descending, return top N.
  - `score_relevance(self, competitor: dict, original_stats: dict, niche_keywords: list[str]) -> float`:
    - Keyword match score (0-50 points): percentage of keywords found in description + titles.
    - Size similarity score (0-30 points): `1 - abs(log10(competitor_subs / original_subs))`.
    - Activity score (0-20 points): uploaded in last 30 days = 20, 60 days = 10, 90+ = 0.
- Cache results in the `Competitor` table linked to the `ChannelAnalysis`.

### Acceptance Criteria
- Given a channel like `@Caruniverse_2.0`, returns 10 similar car-content channels.
- Relevance scores are between 0 and 100.
- Original channel is never in the results.
- Write `tests/test_competitor_finder.py` — mock YouTube API, test scoring logic and deduplication.

---

## PHASE 4 — Topic Search (YouTube + Reddit)

### Goal
Implement `app/topic_search.py` and `app/services/reddit_client.py`.

### Tasks for `app/services/reddit_client.py` (NEW)
- Build `RedditClient` class using `praw.Reddit(client_id=..., client_secret=..., user_agent=...)`.
- Method: `search_subreddit(self, query: str, subreddits: list[str], limit: int = 25) -> list[dict]`:
  - Search across specified subreddits (e.g., "cars", "BMW", "automotive", "carediting").
  - Return: title, url, score (upvotes), num_comments, subreddit, created_utc.
- Method: `get_trending_subreddits(self, niche: str) -> list[str]`:
  - Map niche keywords to relevant subreddit names (hardcoded mapping for V1, or use `reddit.subreddits.search_by_name`).

### Tasks for `app/topic_search.py`
- Build `TopicSearcher` class:
  - `__init__(self, yt_client: YouTubeClient, reddit_client: RedditClient)`.
  - `async search(self, niche_keywords: list[str], analysis_id: int) -> list[TopicResult]`:
    1. Search YouTube for each keyword via `search.list(type="video", order="viewCount", publishedAfter=<30 days ago>)`.
    2. Fetch stats for top 20 results per keyword.
    3. Search Reddit via `RedditClient.search_subreddit()`.
    4. Merge results, normalize into `TopicResult` objects.
    5. Pass to `Classifier` for trending/popular/underrated labeling.
    6. Save to `TopicResult` table.
- Deduplicate by URL/title similarity.
- Rate-limit: cap at 5 YouTube search queries (to conserve quota).

### Acceptance Criteria
- Given keywords `["BMW", "car edit", "car shorts"]`, returns YouTube + Reddit results.
- Results include title, URL, platform, engagement metrics.
- YouTube results are from the last 30 days.
- Reddit results include upvote count and comment count.
- Write `tests/test_topic_search.py` — mock both clients, test search + dedup logic.
- Write `tests/test_reddit_client.py` — mock PRAW, test subreddit search.

---

## PHASE 5 — AI Reasoning (Gemini Integration)

### Goal
Implement `app/ai_reasoning.py` and `app/services/gemini_client.py`.

### Tasks for `app/services/gemini_client.py` (NEW)
- Build `GeminiClient` class using `google.generativeai`.
- Method: `generate_niche_profile(self, channel_summary: dict) -> dict`:
  - Craft a prompt: "You are a YouTube strategy expert. Analyze this channel and return a JSON object with: niche (string), sub_niches (list), content_style (string), target_audience (string), content_gaps (list of strings), growth_opportunities (list of strings), content_angle_suggestions (list of {title, angle, platform, rationale})."
  - Pass channel summary as context (name, subs, avg views, top videos, upload frequency, keywords).
  - Use `gemini-1.5-flash` (free tier). Parse JSON response.
  - Handle rate limits (free tier: 15 RPM, 1500 RPD) — implement retry with exponential backoff.
  - Fallback: if JSON parsing fails, return a raw text profile with a flag `parsed: false`.
- Method: `generate_content_angles(self, niche_profile: dict, trending_topics: list[dict]) -> list[dict]`:
  - Prompt: "Given this channel's niche profile and these trending topics, generate 10 specific content ideas. Return JSON array of {title, angle, platform, rationale}."

### Tasks for `app/ai_reasoning.py`
- Build `AIReasoning` class:
  - `__init__(self, gemini_client: GeminiClient)`.
  - `async build_niche_profile(self, channel_summary: dict) -> dict` — wraps gemini_client, adds error handling.
  - `async generate_suggestions(self, niche_profile: dict, trending_topics: list[dict]) -> list[ContentSuggestion]` — wraps gemini_client, saves to DB.
  - Add response validation: check required fields exist, clamp list lengths, sanitize strings.

### Acceptance Criteria
- Given a channel summary dict, returns a parsed niche profile with all expected fields.
- Given trending topics, returns 10 content suggestions with title/angle/platform/rationale.
- Rate-limit errors are retried, not crashed.
- JSON parse failures are handled gracefully.
- Write `tests/test_ai_reasoning.py` — mock Gemini API, test profile generation + suggestion generation + error handling.

---

## PHASE 6 — Content Classifier

### Goal
Implement `app/classifier.py`.

### Tasks
- Build `Classifier` class:
  - `classify(self, topic: dict, all_topics: list[dict]) -> str`:
    - Returns one of: `"trending"`, `"popular"`, `"underrated"`.
  - **Trending:** published within 7 days AND engagement velocity (views/hour or upvotes/hour) is in the top 20% of the dataset.
  - **Popular:** total engagement (views or upvotes) is in the top 30% of the dataset, regardless of age.
  - **Underrated:** engagement is in the bottom 50% BUT quality signals exist (high like-to-view ratio, high comment density, high upvote ratio on Reddit).
  - **Default:** `"popular"` if none of the above match cleanly.
- `classify_batch(self, topics: list[dict]) -> list[dict]`:
  - Classify all topics together (percentiles are relative to the batch).
  - Attach `classification` field to each topic dict.
- Define engagement metrics:
  - YouTube: `engagement = views + (likes * 5) + (comments * 10)`
  - Reddit: `engagement = upvotes + (num_comments * 3)`
  - Normalize across platforms before comparison (min-max scaling per platform).

### Acceptance Criteria
- Given a list of 20 YouTube + Reddit results, each gets a classification.
- At least ~20% are "trending", ~30% "popular", rest "underrated" (approximately, not forced).
- A 1-day-old video with 100K views → "trending".
- A 6-month-old video with 5M views → "popular".
- A 3-day-old video with 500 views but 50% like ratio → "underrated".
- Write `tests/test_classifier.py` — test each classification path with edge cases.

---

## PHASE 7 — API Layer (FastAPI Routes)

### Goal
Wire everything together with proper API endpoints. Expand `app/main.py` and create router files.

### Tasks for `app/routers/analyze.py` (NEW)
- `POST /api/analyze` — accept `AnalyzeRequest` (channel_url), trigger full pipeline:
  1. Resolve channel + fetch stats.
  2. Generate niche profile (Gemini).
  3. Find competitors.
  4. Search topics (YouTube + Reddit).
  5. Classify topics.
  6. Generate content suggestions.
  7. Save everything to DB.
  8. Return `ChannelAnalysisResponse`.
- `GET /api/analyze/{analysis_id}` — retrieve a cached analysis.
- `GET /api/analyze/{analysis_id}/competitors` — get competitors for an analysis.
- `GET /api/analyze/{analysis_id}/topics` — get topic results for an analysis.
- `GET /api/analyze/{analysis_id}/suggestions` — get content suggestions.
- All endpoints should use `Depends(get_session)` for DB access.
- Return proper HTTP status codes (202 for async analysis started, 200 for cached, 422 for invalid URL, 429 for API quota exhausted, 500 for unexpected errors).

### Tasks for `app/routers/topics.py` (NEW)
- `POST /api/topics/search` — accept `TopicSearchRequest` (keywords, optional analysis_id), run topic search standalone.

### Tasks for `app/main.py` (UPDATE)
- Import and include routers: `app.include_router(analyze.router, prefix="/api")`.
- Add CORS middleware: allow all origins for V1 (will lock down in Phase 12).
- Add a lifespan handler that calls `init_db()` on startup.
- Keep the `/health` endpoint.
- Keep `StaticFiles` mount for frontend (but mount it AFTER API routes — API should take priority).

### Acceptance Criteria
- `POST /api/analyze` with `{"channel_url": "https://www.youtube.com/@Caruniverse_2.0"}` returns a full analysis.
- `GET /api/analyze/{id}` retrieves the cached analysis.
- All 4 sub-resources (competitors, topics, suggestions) are retrievable.
- Invalid URL returns 422 with a clear error message.
- API quota exhausted returns 429 with a message.
- Write `tests/test_api.py` — test all endpoints with mocked services.
- OpenAPI docs at `/docs` show all endpoints with schemas.

---

## PHASE 8 — Frontend (Replace Placeholder)

### Goal
Build a functional single-page UI in `static/index.html` + `static/app.js` + `static/style.css`. No framework — vanilla JS. Keep it simple, clean, and responsive.

### Tasks for `static/index.html`
- Layout:
  - Header: "Creator Content Radar" logo/title.
  - Input section: URL text field + "Analyze" button.
  - Loading state: spinner + "Analyzing channel..." message.
  - Results section (hidden until results arrive):
    - **Channel Overview Card**: name, subs, total views, video count, niche label.
    - **Niche Profile Card**: AI-generated niche description, sub-niches (as tags), target audience, content gaps, growth opportunities.
    - **Competitors Table**: name, subscribers, relevance score (with bar).
    - **Trending Topics Tab**: table of trending topics with title, platform badge, engagement, classification badge (trending=green, popular=blue, underrated=gray).
    - **Content Suggestions Card**: list of AI suggestions with title, angle, recommended platform, rationale.
  - Error state: red error message box.

### Tasks for `static/app.js`
- `analyzeChannel(url)` — POST to `/api/analyze`, show loading, render results.
- `renderChannelOverview(data)` — populate channel card.
- `renderNicheProfile(data)` — populate niche card.
- `renderCompetitors(data)` — build competitors table.
- `renderTopics(data)` — build topics table with filters (platform, classification).
- `renderSuggestions(data)` — build suggestions list.
- Error handling: show user-friendly errors (quota exhausted, invalid URL, server error).
- Add a "Copy" button on each content suggestion (copies title + angle to clipboard).

### Tasks for `static/style.css`
- Clean, modern design. Dark mode optional.
- Use CSS variables for theming.
- Responsive: works on mobile (single column) and desktop (grid layout).
- No external CSS framework (keep it lightweight).

### Acceptance Criteria
- Page loads, accepts a YouTube URL, and shows results after analysis.
- All 5 result sections render correctly.
- Works on mobile width (375px) and desktop (1440px).
- Loading and error states work.
- No console errors.
- Copy button works.

---

## PHASE 9 — Rate Limiting, Caching & Error Handling

### Goal
Make the backend production-safe for multiple users hitting the same APIs.

### Tasks
1. **Response caching** (Redis or in-memory for V1):
   - Add an in-memory LRU cache (use `cachetools.TTLCache`) for channel analysis results — TTL 24 hours.
   - Cache YouTube API responses (channel stats, search results) — TTL 6 hours.
   - Cache Gemini responses — TTL 24 hours.
2. **Rate limiting**:
   - Add `slowapi` middleware — limit `/api/analyze` to 5 requests/minute per IP.
   - Limit `/api/topics/search` to 10 requests/minute per IP.
3. **Global error handler**:
   - Add FastAPI exception handlers for: `ValueError` (400), `KeyError` (422), `httpx.HTTPError` (502), `googleapiclient.errors.HttpError` (429 or 502 depending on quota vs server).
   - All error responses should be JSON: `{"error": "message", "detail": "optional detail"}`.
4. **Structured logging**:
   - Use `structlog` or Python `logging` with JSON formatter.
   - Log: every API call (YouTube, Reddit, Gemini) with duration and quota cost.
   - Log: every user request with IP, endpoint, response time.
5. **Graceful degradation**:
   - If Reddit API is down, return YouTube-only results (don't fail the whole request).
   - If Gemini is rate-limited, return raw channel stats without AI profile (flag `ai_profile: false`).
   - If YouTube quota is exhausted, return a 429 with a "try again in X hours" message.

### Acceptance Criteria
- Repeated analysis of the same channel returns cached results within 24h.
- Rate limiter blocks the 6th request in a minute to `/api/analyze`.
- Reddit API failure doesn't crash the endpoint — YouTube results still return.
- Gemini rate-limit doesn't crash — partial results return.
- All errors return JSON, not HTML tracebacks.
- Logs are structured JSON.

---

## PHASE 10 — Testing & Quality

### Goal
Achieve 80%+ test coverage on all modules.

### Tasks
1. Unit tests for every module (already scaffolded per phase — ensure they exist):
   - `tests/test_youtube_client.py` — mock API, test all 4 URL formats + quota error.
   - `tests/test_reddit_client.py` — mock PRAW, test search + subreddit mapping.
   - `tests/test_gemini_client.py` — mock Gemini, test profile generation + rate limit retry.
   - `tests/test_channel_analyzer.py` — mock clients, test full analyze flow.
   - `tests/test_competitor_finder.py` — mock YouTube, test scoring + dedup.
   - `tests/test_topic_search.py` — mock both clients, test search + dedup.
   - `tests/test_classifier.py` — test all 3 classification paths + edge cases.
   - `tests/test_ai_reasoning.py` — test profile + suggestions + error handling.
   - `tests/test_api.py` — test all endpoints with `TestClient` + mocked services.
2. Integration test: `tests/test_integration.py` — full pipeline with mocked external APIs.
3. Add `pytest-cov` to dev dependencies.
4. Add `pytest-asyncio` for async test support.
5. Add GitHub Actions CI workflow:
   - Run `ruff check`, `black --check`, `pytest --cov` on every push.
   - Fail if coverage < 80%.
6. Add `conftest.py` with shared fixtures (mock YouTube client, mock Reddit client, mock Gemini client, test DB session).

### Acceptance Criteria
- `pytest --cov` reports ≥ 80% coverage across `app/`.
- All tests pass.
- CI runs on push.
- No flaky tests.

---

## PHASE 11 — Deployment & CI/CD

### Goal
Deploy to Render free tier with CI/CD.

### Tasks
1. **Render setup**:
   - `render.yaml`: web service from `main` branch, Python 3.11, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
   - Add environment variables in Render dashboard: `YOUTUBE_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `GEMINI_API_KEY`.
   - Use persistent disk for `data/` directory (SQLite DB).
2. **Dockerfile** (for portability):
   ```dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY pyproject.toml .
   RUN pip install -e .
   COPY . .
   EXPOSE 8000
   CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```
3. **Health check**: Render should hit `/health` for liveness.
4. **GitHub Actions**:
   - On push to `main`: run tests → if pass, auto-deploy to Render.
   - On PR: run tests only (no deploy).
5. **Migration strategy**: For V1, just `SQLModel.metadata.create_all()` on startup. Document that V2 will need Alembic.

### Acceptance Criteria
- App deploys to Render and is accessible via public URL.
- `/health` returns 200 on the deployed app.
- CI passes before deploy.
- `.env.example` is up to date.
- `Dockerfile` builds locally: `docker build -t content-radar .` and `docker run -p 8000:8000 content-radar` works.

---

## PHASE 12 — Production Hardening (SaaS Readiness)

### Goal
Prepare for real users: security, monitoring, user accounts, and the path to monetization.

### Tasks
1. **Authentication** (upgrade from V1 scope):
   - Add JWT-based auth using `python-jose` + `passlib`.
   - `User` model (email, hashed_password, created_date).
   - `POST /api/auth/register`, `POST /api/auth/login` (returns JWT).
   - `GET /api/auth/me` — current user.
   - Protect `/api/analyze` and `/api/topics/search` — require auth.
   - Free tier: 3 analyses per user per day (track in DB).
2. **Input validation**:
   - Validate YouTube URLs (regex for `youtube.com/@`, `youtube.com/channel/`, `youtube.com/c/`, `youtube.com/user/`).
   - Reject non-YouTube URLs with 422.
   - Sanitize all string inputs (prevent injection).
   - Add `pydantic` validators on all request schemas.
3. **Security**:
   - Add `SECURITY.md`.
   - Set CORS to specific origins (remove `*`).
   - Add rate limiting per user (not just per IP).
   - Add request size limit (1MB).
   - Use `httponly` cookies if adding web auth.
4. **Monitoring**:
   - Add `/metrics` endpoint (Prometheus format) with: request count, latency histogram, error rate, API quota usage.
   - Add Sentry integration for error tracking.
5. **Database upgrade**:
   - Switch from SQLite to PostgreSQL (Render managed Postgres free tier).
   - Add connection pooling (`psycopg2` + `SQLModel`).
   - Add Alembic for migrations.
6. **Background tasks** (for long analyses):
   - Use FastAPI `BackgroundTasks` or a simple task queue (Redis + RQ for V2).
   - `POST /api/analyze` returns 202 + `analysis_id` immediately.
   - Client polls `GET /api/analyze/{id}` until `status == "completed"`.

### Acceptance Criteria
- User can register, login, and get a JWT.
- Authenticated requests work; unauthenticated requests get 401.
- Free tier limit enforced (4th analysis in a day → 429).
- Invalid URLs rejected.
- CORS locked to specific origins.
- `/metrics` returns Prometheus metrics.
- PostgreSQL works in production.
- Background analysis works (returns 202, polls to completion).

---

## PHASE 13 — Monetization & SaaS Features

### Goal
Turn the free tool into a SaaS product with tiers and billing.

### Tasks
1. **Pricing tiers**:
   - **Free**: 3 analyses/month, YouTube + Reddit search, basic niche profile.
   - **Pro ($9/mo)**: 50 analyses/month, full competitor analysis, content suggestions, export to PDF.
   - **Business ($29/mo)**: Unlimited analyses, team seats, API access, priority queue.
2. **Stripe integration**:
   - Use `stripe` Python library.
   - `POST /api/billing/checkout` — create Stripe Checkout session.
   - `POST /api/billing/webhook` — Stripe webhook to update user's plan.
   - Store `stripe_customer_id`, `plan` ("free", "pro", "business") on User model.
3. **Usage tracking**:
   - Track analysis count per user per month in a `Usage` table.
   - Reset on billing cycle renewal.
   - Enforce limits in `/api/analyze`.
4. **Export features** (Pro+):
   - `GET /api/analyze/{id}/export?format=pdf` — generate PDF report (use `reportlab` or `weasyprint`).
   - `GET /api/analyze/{id}/export?format=csv` — CSV of topics + competitors.
5. **API access** (Business):
   - Generate API keys for users.
   - `X-API-Key` header auth alternative to JWT.
   - Document API at `/docs` (already there via FastAPI).

### Acceptance Criteria
- User can upgrade to Pro via Stripe Checkout.
- Webhook updates the plan.
- Free users hit a paywall after 3 analyses/month.
- PDF export works.
- API key auth works for Business tier.
- Stripe webhook is verified (signature check).

---

## PHASE 14 — Polish & Go-to-Market

### Goal
Final polish, SEO, and launch readiness.

### Tasks
1. **Landing page**: Replace `index.html` with a proper landing page that explains the product, shows a demo GIF, and has the URL input above the fold.
2. **SEO**: Add meta tags, Open Graph image, sitemap.xml, robots.txt.
3. **Documentation**:
   - `docs/` folder with: getting started, API reference (auto-generated from FastAPI), deployment guide, env var setup.
   - Update README.md with: what it does, screenshots, live demo link, setup instructions.
4. **Analytics**: Add PostHog or Plausible for product analytics (track: signup, analysis run, upgrade).
5. **Email**: Add email capture for waitlist/newsletter (Resend or Mailgun).
6. **Onboarding**: First-time user sees a 3-step tooltip walkthrough.
7. **Demo data**: Add a "Try with a demo channel" button that analyzes a pre-cached example (no API quota used).

### Acceptance Criteria
- Landing page looks professional.
- SEO meta tags present.
- Docs are complete and accurate.
- Analytics tracking works.
- Demo button works without API keys.
- README has live demo link.

---

## SUMMARY — Phase Dependencies

```
Phase 0 (Audit) → Phase 1 (DB) → Phase 2 (Channel Analyzer)
                                    ↓
                        Phase 3 (Competitors) → Phase 4 (Topic Search)
                                                    ↓
                              Phase 5 (AI Reasoning) → Phase 6 (Classifier)
                                                        ↓
                              Phase 7 (API) → Phase 8 (Frontend)
                                                ↓
                              Phase 9 (Rate Limit/Cache) → Phase 10 (Tests)
                                                            ↓
                              Phase 11 (Deploy) → Phase 12 (Hardening)
                                                    ↓
                              Phase 13 (Monetization) → Phase 14 (Polish)
```

**Critical path**: 0 → 1 → 2 → 7 → 8 → 11 (MVP deployable)
**Can run in parallel**: 3+4 (after 2), 5+6 (after 2), 9+10 (after 8)
**SaaS features**: 12+13+14 (after MVP is live)
