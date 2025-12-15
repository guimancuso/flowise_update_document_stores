import os
import sys
import logging
from typing import Dict, Any, List, Optional, TypedDict

import aiohttp
from dotenv import load_dotenv

REFRESHABLE_STATUSES = {
    "UPSERTED",
}

BUSY_STATUSES = {
    "SYNCING",
    "UPSERTING",
}

WAITING_STATUSES = {
    "STALE",
}

class LoaderConfig(TypedDict, total=False):
    source: str
    sourceType: str
    fileType: str
    url: str
    directoryPath: str
    recursive: bool
    textSplitter: Dict[str, Any]

class Loader(TypedDict, total=False):
    id: str
    loaderName: str
    status: str
    config: LoaderConfig

class VectorStoreConfig(TypedDict, total=False):
    id: str
    name: str

class EmbeddingConfig(TypedDict, total=False):
    name: str

class DocumentStore(TypedDict, total=False):
    id: str
    name: str
    status: str
    totalChunks: int
    totalChars: int
    description: str
    loaders: List[Loader]
    vectorStoreConfig: VectorStoreConfig
    embeddingConfig: EmbeddingConfig
    createdDate: str
    updatedDate: str

def setup_logging(name: str = "flowise", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger

logger = setup_logging()

def load_configuration() -> tuple[str, str]:
    load_dotenv()

    base_url = os.getenv("FLOWISE_BASE_URL")
    api_key = os.getenv("FLOWISE_API_KEY")

    if not base_url:
        logger.error("Error: FLOWISE_BASE_URL environment variable is not set")
        logger.error("Please set it in your .env file or environment")
        sys.exit(1)

    if not api_key:
        logger.error("Error: FLOWISE_API_KEY environment variable is not set")
        logger.error("Please set it in your .env file or environment")
        sys.exit(1)

    base_url = base_url.rstrip("/")

    return base_url, api_key

def get_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

async def fetch_all_document_stores(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str
) -> List[DocumentStore]:
    url = f"{base_url}/api/v1/document-store/store"
    headers = get_headers(api_key)

    logger.info(f"Fetching document stores from {url}")

    try:
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            data = await response.json()

            if isinstance(data, list):
                return data
            else:
                logger.warning(f"Warning: Unexpected response format: {type(data)}")
                return []

    except aiohttp.ClientResponseError as e:
        logger.error(f"HTTP Error {e.status}: {e.message}")
        raise
    except aiohttp.ClientError as e:
        logger.error(f"Network Error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected Error: {str(e)}")
        raise

async def fetch_document_store_status(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
    store_id: str
) -> Optional[DocumentStore]:
    url = f"{base_url}/api/v1/document-store/store/{store_id}"
    headers = get_headers(api_key)

    try:
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            return await response.json()

    except Exception as e:
        logger.warning(f"Failed to fetch status for store {store_id}: {str(e)}")
        return None
