# Load Configuration JSON from server

import json
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# BRAND MAP - Load company symbols and aliases for search functionality
# ============================================================================

def load_brand_map():
    try:
        with open('brand_config.json', 'r', encoding='utf-8') as file:
            return json.load(file)  # {symbol: [alias1, alias2, ...]} for fuzzy matching
    except:
        logger.error("Retrieval of Brand_MAP Error")  # Users need to provide brand_config.json
        return {}  # Graceful fallback if file not found

def load_market_map():
    try:
        with open('market_config.json', 'r', encoding='utf-8') as file:
            return json.load(file)
    except:
        logger.error("Retrieval of MARKET_MAP Error")  # Users need to provide market_config.json
        return {}  # Graceful fallback if file not found