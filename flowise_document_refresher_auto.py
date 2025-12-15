#!/usr/bin/env python3

import asyncio
import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

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


def get_store_display_name(store: DocumentStore) -> str:
    name = store.get("name", "Unnamed Store")
    store_id = store.get("id", "unknown")
    status = store.get("status", "UNKNOWN")

    return f"{name} (ID: {store_id[:8]}..., Status: {status})"


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


def find_stores_by_criteria(
    all_stores: List[DocumentStore],
    store_ids: Optional[List[str]] = None,
    store_names: Optional[List[str]] = None,
    all_stores_flag: bool = False
) -> List[DocumentStore]:
    """
    Find stores based on IDs, names, or all flag.
    """
    if all_stores_flag:
        return all_stores

    matching_stores = []

    if store_ids:
        for store_id in store_ids:
            for store in all_stores:
                if store.get("id", "").startswith(store_id) or store.get("id") == store_id:
                    if store not in matching_stores:
                        matching_stores.append(store)

    if store_names:
        for store_name in store_names:
            for store in all_stores:
                if store_name.lower() in store.get("name", "").lower():
                    if store not in matching_stores:
                        matching_stores.append(store)

    return matching_stores


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flowise Document Store Refresher - Automatic Mode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Refresh by store ID (full or partial)
  %(prog)s --id abc123def456
  %(prog)s --id abc123

  # Refresh by store name (partial match)
  %(prog)s --name "My Documents"
  %(prog)s --name docs

  # Refresh multiple stores
  %(prog)s --id abc123 --id def456 --name "My Store"

  # Refresh all UPSERTED stores
  %(prog)s --all

  # List all stores without refreshing
  %(prog)s --list
        """
    )

    parser.add_argument(
        "--id",
        action="append",
        dest="store_ids",
        help="Document store ID (full or partial). Can be used multiple times."
    )

    parser.add_argument(
        "--name",
        action="append",
        dest="store_names",
        help="Document store name (partial match, case-insensitive). Can be used multiple times."
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Refresh all stores with UPSERTED status"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List all document stores and exit (no refresh)"
    )

    return parser.parse_args()


def list_all_stores(stores: List[DocumentStore]) -> None:
    """Display all document stores."""
    print("\n" + "=" * 80)
    print("All Document Stores")
    print("=" * 80)

    if not stores:
        print("No document stores found.")
        return

    for idx, store in enumerate(stores, start=1):
        name = store.get("name", "Unnamed Store")
        store_id = store.get("id", "unknown")
        status = store.get("status", "UNKNOWN")
        total_chunks = store.get("totalChunks", 0)

        print(f"\n{idx}. {name}")
        print(f"   ID: {store_id}")
        print(f"   Status: {status}")
        print(f"   Chunks: {total_chunks:,}")

        loaders = store.get("loaders", [])
        if loaders:
            print(f"   Loaders: {len(loaders)}")

    print("\n" + "=" * 80)


async def main() -> None:
    args = parse_arguments()

    print("\nFlowise Document Store Refresher - Automatic Mode")
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

        if args.list:
            list_all_stores(all_stores)
            sys.exit(0)

        if not args.store_ids and not args.store_names and not args.all:
            print("\nError: You must specify at least one of:")
            print("   --id <store_id>")
            print("   --name <store_name>")
            print("   --all")
            print("\nUse --list to see all available stores")
            print("Use --help for more information")
            sys.exit(1)

        target_stores = find_stores_by_criteria(
            all_stores,
            store_ids=args.store_ids,
            store_names=args.store_names,
            all_stores_flag=args.all
        )

        if not target_stores:
            print("\nNo stores matched your criteria.")
            print("Use --list to see all available stores")
            sys.exit(1)

        refreshable_stores = []
        skipped_stores = []

        for store in target_stores:
            status = store.get("status", "UNKNOWN").upper()
            if status in REFRESHABLE_STATUSES:
                refreshable_stores.append(store)
            else:
                skipped_stores.append((store, status))

        if skipped_stores:
            print("\nSkipping stores with non-UPSERTED status:")
            for store, status in skipped_stores:
                print(f"   - {get_store_display_name(store)}")

        if not refreshable_stores:
            print("\nNo stores with UPSERTED status to refresh.")
            sys.exit(0)

        target_stores = refreshable_stores

        print(f"\nWill refresh {len(target_stores)} store(s):")
        for store in target_stores:
            print(f"   - {get_store_display_name(store)}")

        print(f"\nStarting automatic refresh...")

        tasks = [
            refresh_and_monitor(session, base_url, api_key, store)
            for store in target_stores
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
