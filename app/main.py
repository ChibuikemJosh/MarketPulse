from fastapi import FastAPI

from app.database.init import init_db
from app.cache.redis import RedisService

app = FastAPI(title="MarketPulse", version="1.0.0", docs_url="/docs")

init_db()  # Initialize the database and create necessary tables if they don't exist
RedisService()  # Initialize Redis connection pool

@app.get("/", tags=["Health Check"])
async def health():
    return {"status": "success"} 