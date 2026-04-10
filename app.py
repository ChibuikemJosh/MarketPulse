import json
import os
import sqlite3
import threading
import time
import math
import re
from datetime import datetime, timedelta
from collections import deque

# Data and APIs
import pandas as pd
import requests
import yfinance as yf
from tradingview_screener import Query

# Web Framework and Security
from flask import Flask, render_template, jsonify, request, session, flash, redirect
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

# Search and Logic
from rapidfuzz import fuzz

# Your Custom Logic
from helpers import get_market_news, get_stock_data

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================
ALPHA_VANTAGE_API_LIMIT = 25  # Max Alpha Vantage API calls per day (free tier limit)
DB_PATH = 'marketpulse.db'  # SQLite database filename
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'  # Standard datetime format for database timestamps