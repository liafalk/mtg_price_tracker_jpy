FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# No CMD -- docker-compose.yml sets the default (sleep infinity), and
# scraper.daily_run / scraper.crawl / etc. are invoked as one-off
# `docker compose run` commands rather than baked in as the image entrypoint,
# since which script to run depends on the day (cron picks daily_run;
# you might separately run sync_all or a manual crawl).
