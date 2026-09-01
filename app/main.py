from fastapi import FastAPI

app = FastAPI(title="MarketPulse", version="1.0.0", docs_url="/docs")

@app.get("/", tags=["Health Check"])
async def health():
    return {"status": "success"} 