#!/usr/bin/env python3

import asyncio
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Set

import aiohttp

from flowise_utils import (
    load_configuration,
    get_headers,
    fetch_all_document_stores,
    fetch_document_store_status,
    DocumentStore,
    REFRESHABLE_STATUSES,
    BUSY_STATUSES,
    WAITING_STATUSES,
    logger
)

# Load timeout settings from environment variables with defaults
STATUS_CHECK_INTERVAL = int(os.getenv("STATUS_CHECK_INTERVAL", "15"))
MAX_REFRESH_TIMEOUT = int(os.getenv("MAX_REFRESH_TIMEOUT", "600"))

async def _try_refresh_request(
    session: aiohttp.ClientSession,
    url: str,
    headers: Dict[str, str],
    payload: Optional[Dict[str, Any]],
    debug_mode: bool,
    method: str = "POST"
) -> Tuple[bool, int, str, Dict[str, str]]:
    try:
        request_method = session.post if method == "POST" else session.put

        if payload is None:
            async with request_method(url, headers=headers) as response:
                response_text = await response.text()
                response_headers = dict(response.headers)
                if debug_mode:
                    logger.debug(f"DEBUG: Response Status: {response.status}")
                    logger.debug(f"DEBUG: Response Headers: {response_headers}")
                    if response_text:
                        logger.debug(f"DEBUG: Response Body: {response_text}")
                response.raise_for_status()
                return (True, response.status, response_text, response_headers)
        else:
            async with request_method(url, headers=headers, json=payload) as response:
                response_text = await response.text()
                response_headers = dict(response.headers)
                if debug_mode:
                    logger.debug(f"DEBUG: Response Status: {response.status}")
                    logger.debug(f"DEBUG: Response Headers: {response_headers}")
                    if response_text:
                        logger.debug(f"DEBUG: Response Body: {response_text}")
                response.raise_for_status()
                return (True, response.status, response_text, response_headers)
    except aiohttp.ClientResponseError as e:
        response_text = ""
        response_headers = {}
        try:
            if e.response:
                response_text = await e.response.text()
                response_headers = dict(e.response.headers)
        except:
            pass
        return (False, e.status, response_text, response_headers)
    except Exception as e:
        return (False, 0, str(e), {})


async def trigger_refresh(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
    store_id: str
) -> bool:
    url = f"{base_url}/api/v1/document-store/refresh/{store_id}"
    headers = get_headers(api_key)

    debug_mode = os.getenv("DEBUG", "false").lower() == "true"

    if debug_mode:
        logger.debug(f"DEBUG: Triggering refresh for store {store_id}")
        logger.debug(f"DEBUG: URL: {url}")
        logger.debug(f"DEBUG: Headers (masked): Authorization=Bearer ***")

    attempts = [
        ("POST", None, "POST with no body"),
        ("POST", {}, "POST with empty JSON object"),
        ("POST", {"items": []}, "POST with empty items array"),
        ("PUT", None, "PUT with no body"),
        ("PUT", {}, "PUT with empty JSON object"),
    ]

    last_error_status = 0
    last_error_message = ""
    last_error_headers = {}

    for method, payload, description in attempts:
        if debug_mode:
            logger.debug(f"\nDEBUG: Attempting {description}")
            logger.debug(f"DEBUG: Payload: {payload}")

        success, status, response_text, response_headers = await _try_refresh_request(
            session, url, headers, payload, debug_mode, method
        )

        if success:
            if debug_mode:
                logger.debug(f"DEBUG: Success with {description}")
            return True
        else:
            last_error_status = status
            last_error_message = response_text
            last_error_headers = response_headers
            if debug_mode:
                logger.debug(f"DEBUG: Failed with {description} - Status {status}")
                if response_headers:
                    logger.debug(f"DEBUG: Error Headers: {response_headers}")
                if response_text:
                    logger.debug(f"DEBUG: Error Body: {response_text}")

    error_detail = ""
    if last_error_message:
        error_detail = f"\n   API Response: {last_error_message}"

    if last_error_headers and debug_mode:
        logger.debug(f"\nDEBUG: Last Error Headers: {last_error_headers}")

    if last_error_status > 0:
        logger.error(f"Failed to trigger refresh for store {store_id}: HTTP {last_error_status}{error_detail}")
    else:
        logger.error(f"Failed to trigger refresh for store {store_id}: {last_error_message}")

    if last_error_status == 500:
        logger.info(f"Hint: HTTP 500 indicates an internal server error in Flowise.")
        logger.info(f"   Possible causes:")
        logger.info(f"   - The document store may not have any loaders configured")
        logger.info(f"   - The vector store configuration may be invalid")
        logger.info(f"   - Check the Flowise server logs for more details")

    return False

def filter_refreshable_stores(stores: List[DocumentStore]) -> List[DocumentStore]:
    refreshable = []

    for store in stores:
        status = store.get("status", "UNKNOWN").upper()

        if status in WAITING_STATUSES:
            continue

        if status in BUSY_STATUSES:
            continue

        if status in REFRESHABLE_STATUSES:
            refreshable.append(store)

    return refreshable


def get_store_display_name(store: DocumentStore) -> str:
    name = store.get("name", "Unnamed Store")
    store_id = store.get("id", "unknown")
    status = store.get("status", "UNKNOWN")

    return f"{name} (ID: {store_id[:8]}..., Status: {status})"


def get_store_detailed_info(store: DocumentStore) -> str:
    info_lines = []

    name = store.get("name", "Unnamed Store")
    store_id = store.get("id", "unknown")
    status = store.get("status", "UNKNOWN")
    total_chunks = store.get("totalChunks", 0)

    info_lines.append(f"{name}")
    info_lines.append(f"  ID: {store_id}")
    info_lines.append(f"  Status: {status}")
    info_lines.append(f"  Chunks: {total_chunks:,}")

    loaders = store.get("loaders", [])
    if loaders:
        info_lines.append(f"  Loaders: {len(loaders)}")
        for idx, loader in enumerate(loaders, start=1):
            loader_name = loader.get("loaderName", "Unknown")
            loader_config = loader.get("config", {})

            info_lines.append(f"    {idx}. {loader_name}")

            if "sourceType" in loader_config:
                info_lines.append(f"       Type: {loader_config['sourceType']}")
            if "source" in loader_config:
                source = loader_config['source']
                if len(source) > 50:
                    source = source[:47] + "..."
                info_lines.append(f"       Source: {source}")

    return "\n".join(info_lines)

def display_stores_menu(stores: List[DocumentStore]) -> None:
    print("\n" + "=" * 80)
    print("Refreshable Document Stores (UPSERTED status only)")
    print("=" * 80)

    for idx, store in enumerate(stores, start=1):
        detailed_info = get_store_detailed_info(store)
        lines = detailed_info.split("\n")
        if lines:
            lines[0] = f"  {idx}. {lines[0]}"
            for i in range(1, len(lines)):
                lines[i] = f"     {lines[i]}"
            print("\n".join(lines))
            print()

    print("=" * 80)


def parse_user_selection(user_input: str, max_index: int) -> List[int]:
    user_input = user_input.strip().lower()

    if user_input == "all":
        return list(range(1, max_index + 1))

    selected = set()

    parts = user_input.split(",")

    for part in parts:
        part = part.strip()

        if "-" in part:
            try:
                start, end = part.split("-", 1)
                start = int(start.strip())
                end = int(end.strip())

                if start < 1 or end > max_index or start > end:
                    print(f"Invalid range: {part}")
                    continue

                selected.update(range(start, end + 1))
            except ValueError:
                print(f"Invalid range format: {part}")
                continue
        else:
            try:
                num = int(part)
                if 1 <= num <= max_index:
                    selected.add(num)
                else:
                    print(f"Invalid selection: {num}")
            except ValueError:
                print(f"Invalid input: {part}")
                continue

    return sorted(list(selected))


def prompt_user_selection(stores: List[DocumentStore]) -> List[DocumentStore]:
    display_stores_menu(stores)

    print("\nEnter store numbers to refresh:")
    print("   Examples: '1' or '1,3,5' or '1-5' or 'all'")
    print("   Enter 'q' to quit\n")

    while True:
        user_input = input("Your selection: ").strip()

        if user_input.lower() == "q":
            print("\nExiting...")
            sys.exit(0)

        selected_indices = parse_user_selection(user_input, len(stores))

        if not selected_indices:
            print("No valid stores selected. Please try again.\n")
            continue

        selected_stores = [stores[idx - 1] for idx in selected_indices]

        print(f"\nSelected {len(selected_stores)} store(s):")
        for store in selected_stores:
            print(f"   - {get_store_display_name(store)}")

        confirm = input("\nProceed with refresh? (y/n): ").strip().lower()
        if confirm == "y":
            return selected_stores
        else:
            print("\nLet's try again.\n")
            display_stores_menu(stores)


class RefreshMonitor:
    def __init__(self, store: DocumentStore):
        self.store = store
        self.store_id = store.get("id")
        self.store_name = store.get("name", "Unnamed Store")
        self.start_time = time.time()
        self.status = "STARTING"
        self.completed = False
        self.error: Optional[str] = None
        self.final_status: Optional[str] = None
        self.iteration_count = 0
        self.last_chunks = 0
        self.initial_chunks = store.get("totalChunks", 0)


def format_elapsed_time(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


async def monitor_refresh_progress(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
    monitor: RefreshMonitor
) -> RefreshMonitor:
    print(f"\n{'─' * 60}")
    print(f"Started refresh for: {monitor.store_name}")
    print(f"   Initial chunks: {monitor.initial_chunks:,}")
    print(f"{'─' * 60}")

    while True:
        elapsed = time.time() - monitor.start_time

        if elapsed > MAX_REFRESH_TIMEOUT:
            monitor.error = f"Timeout after {format_elapsed_time(elapsed)}"
            monitor.completed = True
            print(f"\n{monitor.store_name}: Timeout after {format_elapsed_time(elapsed)}")
            print(f"   Total iterations: {monitor.iteration_count}")
            print(f"{'─' * 60}")
            break

        store_data = await fetch_document_store_status(
            session, base_url, api_key, monitor.store_id
        )

        if store_data is None:
            print(f"{monitor.store_name}: Failed to fetch status, retrying...")
            await asyncio.sleep(STATUS_CHECK_INTERVAL)
            continue

        monitor.iteration_count += 1

        current_status = store_data.get("status", "UNKNOWN").upper()
        monitor.status = current_status

        current_chunks = store_data.get("totalChunks", 0)
        chunks_delta = current_chunks - monitor.last_chunks if monitor.iteration_count > 1 else 0
        monitor.last_chunks = current_chunks

        elapsed_str = format_elapsed_time(elapsed)
        iteration_info = f"[Check #{monitor.iteration_count}]"

        if current_status in REFRESHABLE_STATUSES:
            monitor.completed = True
            monitor.final_status = current_status
            print(f"\n{monitor.store_name}: Completed in {elapsed_str} {iteration_info}")
            print(f"   Final status: {current_status}")
            print(f"   Final chunks: {current_chunks:,} (Initial: {monitor.initial_chunks:,})")
            print(f"   Total iterations: {monitor.iteration_count}")
            print(f"{'─' * 60}")
            break

        elif current_status in BUSY_STATUSES:
            chunk_info = f"Chunks: {current_chunks:,}"
            if chunks_delta > 0:
                chunk_info += f" (+{chunks_delta:,} since last check)"
            elif chunks_delta < 0:
                chunk_info += f" ({chunks_delta:,} since last check)"

            print(f"{monitor.store_name}: {current_status} {iteration_info}")
            print(f"   {chunk_info}")
            print(f"   Elapsed: {elapsed_str} | Next check in {STATUS_CHECK_INTERVAL}s")
            print()
            await asyncio.sleep(STATUS_CHECK_INTERVAL)
            continue

        elif current_status in WAITING_STATUSES:
            print(f"{monitor.store_name}: {current_status} (Awaiting update) {iteration_info}")
            print(f"   Chunks: {current_chunks:,}")
            print(f"   Elapsed: {elapsed_str}")
            await asyncio.sleep(STATUS_CHECK_INTERVAL)
            continue

        else:
            print(f"{monitor.store_name}: Status {current_status} {iteration_info}")
            print(f"   Chunks: {current_chunks:,}")
            print(f"   Elapsed: {elapsed_str}")
            await asyncio.sleep(STATUS_CHECK_INTERVAL)

    return monitor


async def refresh_and_monitor(
    session: aiohttp.ClientSession,
    base_url: str,
    api_key: str,
    store: DocumentStore
) -> RefreshMonitor:
    monitor = RefreshMonitor(store)

    success = await trigger_refresh(session, base_url, api_key, monitor.store_id)

    if not success:
        monitor.error = "Failed to trigger refresh"
        monitor.completed = True
        return monitor

    return await monitor_refresh_progress(session, base_url, api_key, monitor)


def display_summary(monitors: List[RefreshMonitor]) -> None:
    print("\n" + "=" * 80)
    print("Refresh Summary")
    print("=" * 80)

    successful = 0
    failed = 0

    for monitor in monitors:
        elapsed = time.time() - monitor.start_time
        elapsed_str = format_elapsed_time(elapsed)

        if monitor.error:
            failed += 1
            status_icon = "X"
            status_msg = f"FAILED - {monitor.error}"
        else:
            successful += 1
            status_icon = "V"
            status_msg = f"SUCCESS - Final Status: {monitor.final_status}"

        print(f"{status_icon} {monitor.store_name}")
        print(f"   Duration: {elapsed_str}")
        print(f"   Status Checks: {monitor.iteration_count}")
        print(f"   Initial Chunks: {monitor.initial_chunks:,}")
        print(f"   Final Chunks: {monitor.last_chunks:,}")

        chunk_diff = monitor.last_chunks - monitor.initial_chunks
        if chunk_diff > 0:
            print(f"   Chunks Added: +{chunk_diff:,}")
        elif chunk_diff < 0:
            print(f"   Chunks Changed: {chunk_diff:,}")
        else:
            print(f"   Chunks Changed: No change")

        print(f"   Result: {status_msg}")
        print()

    print("=" * 80)
    print(f"Total: {len(monitors)} | Successful: {successful} | Failed: {failed}")
    print("=" * 80)


async def main() -> None:
    print("\nFlowise Document Store Refresher")
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
            logger.info(f"Found {len(all_stores)} total document store(s)")
        except Exception as e:
            logger.error(f"Failed to fetch document stores: {str(e)}")
            sys.exit(1)

        if not all_stores:
            print("\nNo document stores found in your Flowise instance.")
            print("   Please create some document stores first.")
            sys.exit(0)

        refreshable_stores = filter_refreshable_stores(all_stores)
        logger.info(f"Found {len(refreshable_stores)} refreshable store(s) with UPSERTED status")

        if not refreshable_stores:
            print("\nNo refreshable document stores found.")
            print("   Only stores with UPSERTED status can be refreshed.")
            print("   Stores may be currently busy (SYNCING, UPSERTING), waiting (STALE),")
            print("   or in other states (SYNC, EMPTY, NEW).")
            print("\n   Current store statuses:")
            for store in all_stores:
                print(f"   - {get_store_display_name(store)}")
            sys.exit(0)

        selected_stores = prompt_user_selection(refreshable_stores)

        print(f"\nStarting refresh for {len(selected_stores)} store(s)...\n")

        tasks = [
            refresh_and_monitor(session, base_url, api_key, store)
            for store in selected_stores
        ]

        monitors = await asyncio.gather(*tasks)

        display_summary(monitors)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\nUnexpected error: {str(e)}")
        sys.exit(1)
