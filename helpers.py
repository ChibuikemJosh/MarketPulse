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