# 📈 MarketPulse AI

**MarketPulse AI** is a next-generation financial intelligence platform. It transcends traditional dashboards by combining real-time global market data with an advanced AI analyst powered by **Gemini 1.5 Flash**. The platform doesn't just show you numbers; it synthesizes news sentiment, historical price action, and user-specific financial goals to provide actionable investment reasoning.

---

## 🧠 AI Analyst & Intelligence

MarketPulse features a **Dual-Core AI Strategy** to provide context-aware financial advice:

* **Contextual Stock Analysis (Quote Mode):** When viewing a specific asset, the AI automatically ingests:
    * **Finnhub Real-time News:** Summarized into key market catalysts.
    * **Trend Synthesis:** 7-day and 30-day performance analysis from `yfinance`.
    * **Investment Guardrails:** Personalized Buy/Hold/Sell logic based on your target ROI and investment capital.
* **General Financial Reasoning (Global Mode):** A router-based chat system that handles general inquiries about Taxes, Forex, Crypto, and Macroeconomics without needing specific asset data.
* **Hybrid Prediction Engine:** Blends qualitative news sentiment with quantitative historical patterns to forecast short-term and long-term volatility.

---

## 🚀 Key Features

* **Real-Time Global Tracking:** Multi-market synchronization (US, Nigeria, Europe) using the TradingView Screener API.
* **Personalized Discovery:** A search engine powered by `rapidfuzz` and a custom **Exponential Decay Algorithm** that ranks assets based on your interaction history.
* **Live AI Sidekick:** A persistent, collapsible chat panel that remains "market-aware" as you navigate different assets.
* **Hybrid Data Fetching:** A triple-layer fallback system (TradingView -> Finnhub -> yfinance) ensuring zero-downtime data availability.

---

## 🛠️ Tech Stack (The "Free" Tier Powerhouse)

* **Reasoning Engine:** Google Gemini 1.5 Flash (API)
* **Financial Data:** Finnhub API (News & Sentiment), yfinance (Historical Price)
* **Market Monitoring:** TradingView Screener API
* **Backend:** Python (Flask) & SQLite (Personalized Click-stream Data)
* **Frontend:** JavaScript (AJAX/Fetch for non-blocking AI chat) & Chart.js

---

## 📦 Setup & Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/ChibuikemJosh/MarketPulse.git](https://github.com/ChibuikemJosh/MarketPulse.git)
   cd MarketPulse

⚠️ Financial Disclaimer
For Educational Purposes Only. All AI-generated suggestions, Buy/Hold/Sell recommendations, and price predictions are probabilistic outputs. MarketPulse does NOT provide certified financial advice. Trading involves high risk. The developers are not liable for financial losses incurred through the use of this software