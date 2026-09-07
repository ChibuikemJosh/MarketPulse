"""Instrument identity and provider-symbol normalization."""

from collections.abc import Mapping
from typing import Any

from app.config.loader import load_brand_map, load_market_map
from app.services.market_data.models import Instrument


_MARKET_DEFAULTS: dict[str, dict[str, str]] = {
    "america": {"exchange": "US", "currency": "USD", "timezone": "America/New_York"},
    "canada": {"exchange": "CA", "currency": "CAD", "timezone": "America/Toronto"},
    "nigeria": {"exchange": "NG", "currency": "NGN", "timezone": "Africa/Lagos"},
    "uk": {"exchange": "GB", "currency": "GBP", "timezone": "Europe/London"},
    "germany": {"exchange": "DE", "currency": "EUR", "timezone": "Europe/Berlin"},
    "france": {"exchange": "FR", "currency": "EUR", "timezone": "Europe/Paris"},
    "denmark": {"exchange": "DK", "currency": "DKK", "timezone": "Europe/Copenhagen"},
}


def _provider_symbols(symbol: str, tv_symbol: str, market: str) -> dict[str, str]:
    """Build conservative provider mappings without erasing the canonical symbol."""
    yfinance_symbol = symbol
    if market == "america" and symbol.endswith("-B"):
        yfinance_symbol = symbol
    tiingo_symbol = symbol.replace(".", "-")
    massive_symbol = symbol.replace(".", "-")
    return {
        "tradingview": tv_symbol,
        "tradingview_market": market,
        "yfinance": yfinance_symbol,
        "massive": massive_symbol,
        "tiingo": tiingo_symbol,
    }


def build_instrument(symbol: str, config: Mapping[str, Any], aliases: list[str] | None = None) -> Instrument:
    """Create an instrument from one market-config entry."""
    market = str(config.get("market", "")).lower()
    defaults = _MARKET_DEFAULTS.get(market, {})
    tv_symbol = str(config.get("tv_symbol") or symbol)
    exchange = str(config.get("exchange") or defaults.get("exchange") or market.upper() or "GLOBAL")
    return Instrument(
        symbol=symbol.upper().strip(),
        exchange=exchange,
        asset_type=str(config.get("asset_type", "stock")),
        currency=config.get("currency") or defaults.get("currency"),
        timezone=config.get("timezone") or defaults.get("timezone"),
        display_name=(aliases or [None])[0],
        provider_symbols=_provider_symbols(symbol.upper().strip(), tv_symbol, market),
    )


def load_instrument_registry() -> dict[str, Instrument]:
    """Load configured instruments keyed by canonical symbol."""
    brand_map = load_brand_map()
    market_map = load_market_map()
    registry: dict[str, Instrument] = {}
    for symbol, aliases in brand_map.items():
        config = market_map.get(symbol, {})
        registry[symbol.upper()] = build_instrument(
            symbol,
            config,
            aliases if isinstance(aliases, list) else None,
        )
    for symbol, config in market_map.items():
        if symbol.upper() not in registry:
            registry[symbol.upper()] = build_instrument(symbol, config)
    return registry


def resolve_instrument(raw_symbol: str, registry: dict[str, Instrument] | None = None) -> Instrument | None:
    """Resolve a configured symbol without collapsing exchange-qualified tickers."""
    normalized = raw_symbol.strip().upper()
    if ":" in normalized:
        normalized = normalized.rsplit(":", 1)[1]
    instruments = registry if registry is not None else load_instrument_registry()
    direct = instruments.get(normalized)
    if direct:
        return direct
    for instrument in instruments.values():
        if normalized in {value.upper() for value in instrument.provider_symbols.values()}:
            return instrument
    return None
