# SmartXFlow – Odds & Volume Monitor

Web-based betting odds monitoring and scraping platform built with Flask and Supabase.

## Features

- Real-time odds scraping and monitoring
- Alarm engine for sharp moves, insider activity, and big money detection
- Chart.js powered data visualization
- Telegram notifications
- License management system

## Running

The application starts with a single command. In server mode (Replit), it automatically launches background workers for scraping and alarm processing.

```bash
python app.py
```

## Tech Stack

- Python 3.11, Flask
- Supabase (PostgreSQL)
- Chart.js for visualization
- BeautifulSoup for scraping
