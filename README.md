# Creator Content Radar

A tool where a YouTube creator pastes their channel URL to get AI-powered niche profiling, competitor discovery, and trending content suggestions from YouTube.

## Tech Stack

- Python 3.11
- FastAPI (web framework)
- SQLModel (SQLite database)
- google-api-python-client (YouTube Data API)
- google-generativeai (Gemini AI)
- Plain HTML/JS frontend

## Prerequisites

- Python 3.11 or higher
- YouTube Data API v3 key
- Google Gemini API key

## Local Development

1. Clone the repository and navigate to the project directory

2. Create a `.env` file with your API credentials:
```bash
YOUTUBE_API_KEY=your_youtube_api_key
GEMINI_API_KEY=your_gemini_api_key
```

3. Install dependencies:
```bash
pip install -e .
```

4. Run the development server:
```bash
python -m uvicorn app.main:app --reload
```

5. Open your browser to `http://localhost:8000`

## Running Tests

```bash
pytest tests/
```

## Deployment (Render)

This project is configured for deployment on Render using Docker.

### Option A: Docker Deployment (Recommended)

1. Push your code to a Git repository
2. Create a new Web Service on Render
3. Connect your repository
4. Select "Docker" as the runtime
5. Add environment variables in Render's dashboard:
   - `YOUTUBE_API_KEY`
   - `GEMINI_API_KEY`
6. Deploy

The Dockerfile automatically uses the `PORT` environment variable provided by Render (defaults to 8000 for local development).

### Option B: Native Python Deployment

If you prefer not to use Docker, use these settings in Render:

- **Build Command**: `pip install .`
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Add the same environment variables as above in Render's dashboard.

## Project Structure

```
.
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── models.py            # Pydantic/SQLModel definitions
│   ├── db.py                # Database and caching layer
│   ├── config.py            # Configuration and settings
│   ├── channel_analyzer.py  # YouTube channel analysis
│   ├── competitor_finder.py # Competitor discovery
│   ├── topic_search.py      # YouTube content search
│   ├── classifier.py       # Content classification logic
│   └── ai_reasoning.py     # AI-powered insights
├── static/
│   └── index.html          # Frontend application
├── tests/                  # Automated tests
├── data/                   # SQLite database (created automatically)
├── Dockerfile              # Container configuration
├── pyproject.toml          # Python dependencies
└── .env.example            # Environment variables template
```

## License

MIT
