"""Async local and external instrument search."""

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from app.cache.redis import RedisService
from app.config.loader import CONFIG_DIR, load_brand_map
from app.core.constants import (
    ALPHAVANTAGE_DEFAULT_SCORE,
    FINAL_THRESHOLD,
    FUZZ_THRESHOLD,
    JUNK_SUFFIXES,
)
from app.services.alpha_vantage import fetch_symbol_matches
from app.services.market_data.models import Instrument
from app.services.market_data.normalization import load_instrument_registry, resolve_instrument

logger = logging.getLogger(__name__)
SEARCH_RESULT_LIMIT = 5


def clean_stock_name(raw_name: str | None) -> str:
    """Remove common corporate suffixes and punctuation from a display name."""
    if not raw_name:
        return ""
    cleaned = raw_name
    for suffix in JUNK_SUFFIXES:
        cleaned = cleaned.replace(suffix, "")
    return cleaned.replace(",", "").strip()


def _display_name(symbol: str, aliases: list[Any], cached_names: dict[str, str], provider_name: str | None = None) -> str:
    """Choose a display name with explicit precedence and a ticker fallback."""
    cached_name = cached_names.get(symbol.upper())
    if cached_name:
        return cached_name
    cleaned_provider_name = clean_stock_name(provider_name)
    if cleaned_provider_name:
        return cleaned_provider_name
    if aliases:
        return clean_stock_name(str(aliases[0]))
    return symbol


def _result(instrument: Instrument, name: str, score: float, trend: float) -> dict[str, Any]:
    """Build the internal scored result shape used before response cleanup."""
    return {"symbol": instrument.symbol, "name": name, "score": score, "trend": trend, "instrument_id": instrument.instrument_id}


def _public_result(item: dict[str, Any]) -> dict[str, Any]:
    """Remove ranking-only fields while retaining canonical identity."""
    return {"symbol": item["symbol"], "name": item["name"], "instrument_id": item["instrument_id"]}


def rank_configured_symbols(
    query: str,
    user_weights: dict[str, float],
    global_weights: dict[str, float],
    trends: dict[str, float],
    names: dict[str, str],
    seen: set[str],
    registry: dict[str, Instrument] | None = None,
) -> list[dict[str, Any]]:
    """Rank configured instruments without destroying exchange identity."""
    instruments = registry or load_instrument_registry()
    brand_map = load_brand_map()
    query_upper = query.strip().upper()
    query_lower = query.strip().lower()
    boost_multiplier = 1.0 if len(query) >= 2 else 0.2
    results: list[dict[str, Any]] = []

    for symbol, instrument in instruments.items():
        aliases = brand_map.get(symbol, [])
        aliases = aliases if isinstance(aliases, list) else []
        if query_upper == symbol:
            fuzzy_score = 110
        elif symbol.startswith(query_upper) or any(query_lower in str(alias).lower() for alias in aliases):
            fuzzy_score = 105
        else:
            fuzzy_score = max(
                fuzz.token_set_ratio(query_upper, symbol),
                max((fuzz.token_set_ratio(query_lower, str(alias).lower()) for alias in aliases), default=0),
            )
        if fuzzy_score < FUZZ_THRESHOLD:
            continue

        global_weight = float(global_weights.get(symbol, 0.0) or 0.0)
        user_weight = float(user_weights.get(symbol, 0.0) or 0.0)
        trend = float(trends.get(symbol, 0.0) or 0.0)
        trend_boost = abs(0.1 * min(100.0, trend) * boost_multiplier)
        total_score = fuzzy_score + 0.2 * user_weight + 0.1 * global_weight + trend_boost
        if total_score < FINAL_THRESHOLD or instrument.instrument_id in seen:
            continue

        seen.add(instrument.instrument_id)
        results.append(_result(instrument, _display_name(symbol, aliases, names, instrument.display_name), total_score, trend_boost))

    results.sort(key=lambda item: (item["score"], item["trend"], -len(item["symbol"])), reverse=True)
    return results[:SEARCH_RESULT_LIMIT]


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON beside its target and replace it atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


async def _persist_missing_name(symbol: str, name: str, redis: RedisService) -> None:
    """Cache a name in Redis and add it to brand configuration only when missing."""
    clean_name = clean_stock_name(name)
    if not clean_name:
        return
    await redis.set_cached_name(symbol, clean_name)
    path = CONFIG_DIR / "brand_config.json"
    lock = redis.get_cache_lock()
    async with lock:
        try:
            existing = load_brand_map()
            aliases = existing.get(symbol.upper())
            if aliases is None:
                existing[symbol.upper()] = [clean_name]
            elif clean_name not in aliases:
                existing[symbol.upper()].append(clean_name)
            else:
                return
            await asyncio.to_thread(_atomic_write_json, path, existing)
        except Exception:
            logger.error("Failed to persist discovered name for %s", symbol, exc_info=True)


async def search_external_symbols(
    query: str,
    redis: RedisService,
    user_weights: dict[str, float],
    seen: set[str],
    registry: dict[str, Instrument] | None = None,
) -> list[dict[str, Any]]:
    """Search Alpha Vantage and merge only valid, unseen instruments."""
    matches = await fetch_symbol_matches(query, redis)
    if not matches:
        return []

    instruments = registry or load_instrument_registry()
    results: list[dict[str, Any]] = []
    boost_multiplier = 1.0 if len(query) >= 2 else 0.2
    for match in matches:
        raw_symbol = match.get("1. symbol")
        raw_name = match.get("2. name")
        if not isinstance(raw_symbol, str) or not raw_symbol.strip():
            logger.warning("Ignoring malformed Alpha Vantage match: %r", match)
            continue

        instrument = resolve_instrument(raw_symbol, instruments)
        if instrument is None:
            canonical_symbol = raw_symbol.strip().upper()
            instrument = Instrument(
                symbol=canonical_symbol,
                asset_type="stock",
                display_name=clean_stock_name(raw_name) if isinstance(raw_name, str) else None,
                provider_symbols={"alpha_vantage": canonical_symbol},
            )
        if instrument.instrument_id in seen:
            continue

        cached_name = await redis.get_cached_name(instrument.symbol)
        name = cached_name or clean_stock_name(raw_name if isinstance(raw_name, str) else None) or instrument.symbol
        global_weight = await redis.get_global_weight(instrument.symbol) or 0.0
        trend = await redis.get_trending_score(instrument.symbol) or 0.0
        score = ALPHAVANTAGE_DEFAULT_SCORE + 0.2 * float(user_weights.get(instrument.symbol, 0.0) or 0.0)
        trend_boost = abs(0.1 * float(trend) * boost_multiplier)
        score += 0.1 * float(global_weight) + trend_boost
        if score < FINAL_THRESHOLD - 10:
            continue
        seen.add(instrument.instrument_id)
        results.append(_result(instrument, name, score, trend_boost))
        if not cached_name and name != instrument.symbol:
            await _persist_missing_name(instrument.symbol, name, redis)
        if len(results) >= SEARCH_RESULT_LIMIT:
            break
    return results


async def search_symbols(
    query: str,
    redis: RedisService,
    user_id: str | int | None = None,
    result_limit: int = SEARCH_RESULT_LIMIT,
) -> list[dict[str, Any]]:
    """Search configured instruments and use Alpha Vantage only when sparse."""
    normalized_query = query.strip()
    if not normalized_query:
        return []
    user_weights, global_weights, trends, names = await asyncio.gather(
        redis.get_user_weights(str(user_id)) if user_id is not None else asyncio.sleep(0, result={}),
        redis.get_global_weights(),
        redis.get_trending_scores(),
        redis.get_cached_names(),
    )
    registry = load_instrument_registry()
    seen: set[str] = set()
    results = rank_configured_symbols(normalized_query, user_weights, global_weights, trends, names, seen, registry)
    if len(results) < result_limit and len(normalized_query) > 3:
        results.extend(await search_external_symbols(normalized_query, redis, user_weights, seen, registry))
    results.sort(key=lambda item: (item["score"], item["trend"], -len(item["symbol"])), reverse=True)
    return [_public_result(item) for item in results[:result_limit]]
