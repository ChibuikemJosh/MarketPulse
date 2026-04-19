import os
from dotenv import load_dotenv

import yfinance as yf
import pandas as pd

import requests
from datetime import datetime, timedelta

import finnhub

import json
import re


def get_stock_data(symbol, period="1y", interval=None):
    """
    Fetches historical stock data from Yahoo Financce.
    Periods can be mo for months e.g. 1mo for 1 month,3mo for 3 months,
    y for years e.g. 1y for 1 year, 5y for 5 years, d for days, e.g 1d for 1 day, 7d for 7 days
    h for hours e.g 1h for 1 hour, 6h for 6 hours, m for minutes, e.g 1m for 1 minute, 30m for 30 minutes,
    ytd for start of the year still now and max for the vvery first day the stock started trdaing(IPO) until now
    """

    mapping = {
        "1d": ["5m", "1m", "2m", "15m"],
        "5d": ["15m", "5m", "30m", "60m"],
        "1mo": ["90m", "60m", "1d"],
        "3mo": ["1d", "90m"],
        "1y": ["1d", "1wk"],
        "5y": ["1wk", "1mo"]
    }

    if period not in mapping:
        period = "1d"

    allowed_intervals = mapping[period]
    if interval not in allowed_intervals:
        interval = allowed_intervals[0]

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]

        actions_df = ticker.actions

        if df.empty:
            return None

        return df, period, interval, actions_df

    except Exception as e:
        print(f"Error Type: {type(e).__name__}, Message: {e}")
        return None
    

# Load variables from .env into the environment
load_dotenv()


def get_market_news(symbol=None, end_timestamp=None, last_id=None):
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        return []

    client = finnhub.Client(api_key=api_key)
    time_to_strf = '%Y-%m-%d'

    try:
        if symbol:
            # --- COMPANY NEWS (Date Based) ---
            to_ts = int(end_timestamp) if end_timestamp else int(datetime.now().timestamp())
            from_ts = to_ts - (7 * 24 * 60 * 60)


            from_date = datetime.fromtimestamp(from_ts).strftime(time_to_strf)
            to_date = datetime.fromtimestamp(to_ts).strftime(time_to_strf)
            news = client.company_news(symbol.upper(), _from=from_date, to=to_date)

            # Filtering logic
            try:
                with open('brand_config.json', 'r', encoding='utf-8') as file:
                    brand_map = json.load(file)
            except (FileNotFoundError, json.JSONDecodeError):
                brand_map = {}

            aliases = brand_map.get(symbol.upper(), [])
            all_keywords = [k for k in ([symbol.upper()] + aliases) if k]

            if all_keywords:
                joined_keywords = "|".join([re.escape(k) for k in all_keywords])
                regex = re.compile(fr"(?<!\w)({joined_keywords})(?!\w)", re.IGNORECASE)
                return [item for item in news if re.search(regex, item.get('headline', ''))]

            return news

        else:
            # --- GENERAL NEWS (ID Based) ---
            # Finnhub returns the most recent 100-200 articles by default
            all_general = client.general_news('general', min_id=0)

            if last_id:
                # Filter locally: only keep news older than the last one seen
                # Assumes news IDs increase over time
                return [n for n in all_general if n.get('id', 0) < int(last_id)][:20]

            return all_general[:20]

    except Exception as e:
        print(f"Error fetching news: {e}")
        return []
