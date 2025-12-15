#!/usr/bin/env python3

import sys
import asyncio
from typing import Dict, List, Any

import aiohttp

from flowise_utils import (
    load_configuration,
    fetch_all_document_stores,
    DocumentStore,
    logger
)

def display_store_details(store: DocumentStore, index: int) -> None:
    store_id = store.get("id", "unknown")
    name = store.get("name", "Unnamed Store")
    status = store.get("status", "UNKNOWN")
    total_chunks = store.get("totalChunks", 0)
    total_chars = store.get("totalChars", 0)
    description = store.get("description", "")

    print(f"\n  {index}. {name}")
    print(f"     ID: {store_id}")
    print(f"     Status: {status}")

    if description:
        print(f"     Description: {description}")

    print(f"     Chunks: {total_chunks:,}")
    print(f"     Characters: {total_chars:,}")

    loaders = store.get("loaders", [])
    if loaders:
        print(f"     Loaders ({len(loaders)}):")
        for idx, loader in enumerate(loaders, start=1):
            loader_name = loader.get("loaderName", "Unknown")
            loader_status = loader.get("status", "Unknown")
            loader_id = loader.get("id", "unknown")

            loader_config = loader.get("config", {})

            print(f"       {idx}. {loader_name}")
            print(f"          ID: {loader_id}")
            print(f"          Status: {loader_status}")

            if loader_config:
                if "source" in loader_config:
                    print(f"          Source: {loader_config['source']}")
                if "sourceType" in loader_config:
                    print(f"          Source Type: {loader_config['sourceType']}")
                if "fileType" in loader_config:
                    print(f"          File Type: {loader_config['fileType']}")
                if "url" in loader_config:
                    print(f"          URL: {loader_config['url']}")
                if "directoryPath" in loader_config:
                    print(f"          Directory: {loader_config['directoryPath']}")
                if "recursive" in loader_config:
                    print(f"          Recursive: {loader_config['recursive']}")

                text_splitter = loader_config.get("textSplitter", {})
                if text_splitter:
                    chunk_size = text_splitter.get("chunkSize")
                    chunk_overlap = text_splitter.get("chunkOverlap")
                    if chunk_size:
                        print(f"          Chunk Size: {chunk_size}")
                    if chunk_overlap:
                        print(f"          Chunk Overlap: {chunk_overlap}")
    else:
        print(f"     Loaders: None configured")

    vector_store_config = store.get("vectorStoreConfig")
    if vector_store_config:
        vs_name = vector_store_config.get("name", "Unknown")
        vs_id = vector_store_config.get("id", "unknown")
        print(f"     Vector Store: {vs_name}")
        print(f"     Vector Store ID: {vs_id}")

        embedding_config = store.get("embeddingConfig")
        if embedding_config:
            embedding_name = embedding_config.get("name", "Unknown")
            print(f"     Embedding Model: {embedding_name}")

    created_date = store.get("createdDate")
    updated_date = store.get("updatedDate")

    if created_date:
        print(f"     Created: {created_date}")
    if updated_date:
        print(f"     Updated: {updated_date}")


def display_all_stores(stores: List[DocumentStore]) -> None:
    print("\n" + "=" * 80)
    print(f"Document Stores ({len(stores)} total)")
    print("=" * 80)

    if not stores:
        print("   No document stores found.")
        return

    by_status: Dict[str, List[DocumentStore]] = {}
    for store in stores:
        status = store.get("status", "UNKNOWN")
        if status not in by_status:
            by_status[status] = []
        by_status[status].append(store)

    print("\nSummary by Status:")
    for status, status_stores in sorted(by_status.items()):
        print(f"   - {status}: {len(status_stores)} store(s)")

    print("\n" + "-" * 80)
    for idx, store in enumerate(stores, start=1):
        display_store_details(store, idx)

    print("\n" + "=" * 80)

async def main() -> None:
    print("\nFlowise Document Store Lister")
    print("=" * 80)

    try:
        base_url, api_key = load_configuration()
        logger.info("Configuration loaded")
        logger.info(f"   Base URL: {base_url}")
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Failed to load configuration: {str(e)}")
        sys.exit(1)

    async with aiohttp.ClientSession() as session:
        try:
            all_stores = await fetch_all_document_stores(session, base_url, api_key)
            logger.info(f"Found {len(all_stores)} document store(s)")
        except Exception as e:
            logger.error(f"Failed to fetch document stores: {str(e)}")
            sys.exit(1)

        display_all_stores(all_stores)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\nUnexpected error: {str(e)}")
        sys.exit(1)
