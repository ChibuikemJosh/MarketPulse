# Load Configuration JSON from server

import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# BRAND MAP - Load company symbols and aliases for search functionality
# ============================================================================

CONFIG_DIR = Path(__file__).resolve().parent

def load_brand_map():
    path = CONFIG_DIR / 'brand_config.json'

    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)  # {symbol: [alias1, alias2, ...]} for fuzzy matching

    except FileNotFoundError as e:
        logger.error("Brand config file not found", exc_info=True)  # Users need to provide brand_config.json
        return {}  # Graceful fallback if file not found

    except json.JSONDecodeError as e:
        logger.error("Brand config file is not valid JSON", exc_info=True)
        return {}  # Graceful fallback if JSON is invalid


def load_market_map():
    path = CONFIG_DIR / 'market_config.json'

    try:
        with open(path, 'r', encoding='utf-8') as file:
            return json.load(file)

    except FileNotFoundError as e:
        logger.error("Market config file not found", exc_info=True)  # Users need to provide market_config.json
        return {}  # Graceful fallback if file not found

    except json.JSONDecodeError as e:
        logger.error("Market config file is not valid JSON", exc_info=True)
        return {}  # Graceful fallback if JSON is invalid