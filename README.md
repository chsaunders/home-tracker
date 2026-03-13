# 🏡 Barrington Home Tracker

A home-buying decision support system for Barrington, Rhode Island. Paste a Zillow or Redfin listing URL, and it automatically pulls property data, compares pricing against recent sales, scores the location (schools, flood risk), and generates an AI-powered summary telling you whether the price makes sense.

## What It Does

- **Automatic data extraction** — paste a listing URL and the backend scrapes all property details (price, beds, baths, sqft, features, photos, price history)
- **Comp-based price analysis** — finds recently sold homes nearby, calculates price per square foot, and tells you if the listing is over/under priced
- **Location scoring** — school ratings (GreatSchools), flood risk (FEMA), walkability (Walk Score)
- **AI-powered summaries** — Claude analyzes all the data and gives you a narrative assessment with pros, cons, and a verdict
- **Personal notes & ratings** — add your own observations after visiting, rate homes, tag them
- **Tablet-friendly dashboard** — designed for iPad Safari, works on any device

## Quick Start (Local)

```bash
# Clone and enter the project
cd home-tracker

# Install dependencies
pip install -r requirements.txt

# Set up your environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY (required for AI summaries)

# Run the server
python main.py
```

Open http://localhost:8000 in your browser.

## Deploy to Railway (Recommended for iPad)

1. Push this project to a GitHub repository
2. Go to [railway.app](https://railway.app) and sign in with GitHub
3. Click **New Project** → **Deploy from GitHub repo** → select this repo
4. Add environment variables in Railway's dashboard:
   - `ANTHROPIC_API_KEY` — your Claude API key (get one at [console.anthropic.com](https://console.anthropic.com))
   - `GREATSCHOOLS_API_KEY` — optional, for live school data
   - `WALKSCORE_API_KEY` — optional, for walkability scores
5. Railway will auto-deploy. Access your dashboard at the provided URL.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for AI summaries |
| `GREATSCHOOLS_API_KEY` | No | GreatSchools API key for school ratings |
| `WALKSCORE_API_KEY` | No | Walk Score API key for walkability |
| `DATABASE_URL` | No | Defaults to `sqlite:///./home_tracker.db` |
| `PORT` | No | Defaults to `8000` |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/listings` | Add a listing by URL |
| `GET` | `/api/listings` | List all tracked homes |
| `GET` | `/api/listings/{id}` | Get full listing detail |
| `DELETE` | `/api/listings/{id}` | Remove a listing |
| `POST` | `/api/listings/{id}/notes` | Update notes/rating |
| `POST` | `/api/listings/{id}/reanalyze` | Re-run all analysis |
| `GET` | `/api/health` | Health check |

## Project Structure

```
home-tracker/
├── main.py                    # FastAPI app entry point
├── backend/
│   ├── database.py            # SQLite + SQLAlchemy setup
│   ├── models.py              # Database models
│   ├── schemas.py             # API request/response schemas
│   ├── routers/
│   │   └── listings.py        # All API endpoints
│   └── services/
│       ├── scraper.py         # Zillow/Redfin data extraction
│       ├── analyzer.py        # Comp search and price analysis
│       ├── location.py        # School, flood, walkability scoring
│       └── summarizer.py      # Claude AI summaries
├── frontend/
│   └── index.html             # React dashboard (single file, no build)
├── requirements.txt
├── Procfile                   # Railway deployment
├── railway.toml
└── .env.example
```

## How Scoring Works

**Price Score** — compares listing $/sqft against median of 5-10 recent comparable sales within 2 miles. Scale: -1 (very overpriced) to +1 (great deal).

**School Score** — pulls ratings from GreatSchools API or uses known Barrington baseline data. Barrington consistently rates 8-9/10 across all levels.

**Flood Risk** — queries FEMA's National Flood Hazard Layer for the property's flood zone. Important for coastal Barrington properties.

**Overall Score** — weighted composite: Price (3x), Schools (3x), Flood Risk (2x), Walkability (1x).

**AI Verdict** — Claude synthesizes all data into: Strong Buy, Fair Deal, Overpriced, or Pass.
