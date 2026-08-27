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

        def _is_finance_relevant(headline, summary=""):
            """Score articles for finance relevance (0=filter out, 1=medium, 2=high priority).

            High quality (2): Strong finance keywords + no irrelevant content
            Medium quality (1): Has finance keywords (weak or strong) but contains some irrelevant content
            Low quality (0): No finance keywords or only irrelevant content

            Geopolitical keywords are allowed if paired with finance keywords.
            """
            # Strong indicators of finance relevance (primary focus)
            strong_finance_keywords = [
                "stock", "market", "trading", "earnings", "dividend",
                "ipo", "acquisition", "merger", "profit", "revenue",
                "analyst", "securities", "etf", "nasdaq", "s&p", "dow",
                "volatility", "ratings", "upgrade", "downgrade", "buyback", "share",
                "portfolio", "investment", "investor", "fund"
            ]

            # Weak indicators of finance relevance (secondary)
            weak_finance_keywords = [
                "company", "ceo", "cfo", "growth", "economy", "recession",
                "inflation", "interest rate", "fed", "wall street", "bear market",
                "bull market", "crypto", "bitcoin", "blockchain", "fintech",
                "bond", "yen", "dollar", "euro", "currency", "commodities",
                "oil", "gold", "startup", "venture", "sector", "bullish",
                "bearish", "price target", "quarterly", "annual report"
            ]

            # Truly irrelevant content to deprioritize
            irrelevant_keywords = [
                "sports", "nfl", "nba", "soccer", "football", "celebrity",
                "royal", "scandal", "arrest", "lawsuit", "suicide", "death",
                "weather", "hurricane", "disease", "pandemic", "health", "covid", "virus"
            ]

            content = (headline + " " + summary).lower()

            # Check for irrelevant keywords
            has_irrelevant = any(
                re.search(fr"\b{re.escape(keyword)}\b", content)
                for keyword in irrelevant_keywords
            )

            # Check for strong finance keywords
            has_strong_finance = any(
                re.search(fr"\b{re.escape(keyword)}\b", content)
                for keyword in strong_finance_keywords
            )

            # Check for weak finance keywords
            has_weak_finance = any(
                re.search(fr"\b{re.escape(keyword)}\b", content)
                for keyword in weak_finance_keywords
            )

            # Scoring logic: prioritize strong finance keywords
            if has_strong_finance:
                # Strong finance found: score 2 if clean, 1 if has irrelevant
                return 1 if has_irrelevant else 2
            elif has_weak_finance:
                # Weak finance found: only score 1 if no irrelevant content
                return 0 if has_irrelevant else 1
            else:
                # No finance keywords detected
                return 0

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
                return [n for n in all_general if n.get('id', 0) < int(last_id)][:25]

            # Score all articles for finance relevance (returns 0, 1, or 2)
            scored_news = []
            for article in all_general:
                score = _is_finance_relevant(article.get('headline', ''), article.get('summary', ''))
                if score > 0:  # Only keep articles with finance relevance
                    scored_news.append((article, score))

            # Sort by score (descending): score 2 first, then score 1
            # This prioritizes strong finance keywords + clean articles first
            scored_news.sort(key=lambda x: x[1], reverse=True)

            # Extract just the articles (remove scores)
            filtered_news = [article for article, score in scored_news]

            return filtered_news[:15]

    except Exception as e:
        print(f"Error fetching news: {e}")
        return []