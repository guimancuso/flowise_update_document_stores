# Flowise Document Store Manager

A comprehensive Python toolset for managing Flowise document stores via API. This project provides two main tools: a document store lister and an automated refresh manager.

## Overview

This project contains procedural Python programs that interact with the Flowise API to:
- List and inspect document stores
- Automatically refresh document stores with progress monitoring
- Handle concurrent refresh operations
- Provide detailed status tracking and error handling

## Tools

### 1. Document Store Lister (`flowise_document_lister.py`)
Lists all available document stores in a Flowise instance with detailed information.

### 2. Document Store Refresher (`flowise_document_refresher.py`)
Automatically manages the refresh of Flowise document stores with:
- ✅ Intelligent filtering of refreshable stores
- ✅ Multi-selection support (single, ranges, comma-separated, or "all")
- ✅ Concurrent asynchronous refresh operations
- ✅ Real-time progress monitoring
- ✅ Elapsed time tracking
- ✅ Comprehensive error handling
- ✅ Summary reporting

### 3. Automatic Document Store Refresher (`flowise_document_refresher_auto.py`)
Command-line tool for automated refresh operations:
- ✅ Refresh by store ID or name
- ✅ Support for partial matching
- ✅ Batch refresh with `--all` flag
- ✅ List mode to view all stores
- ✅ Non-interactive for automation/scripting

## Features

### Document Store Refresher Features
- **Smart Status Detection**: Automatically identifies which stores can be refreshed based on their current status
- **Flexible Selection**: Support for multiple selection formats:
  - Single: `1`
  - Multiple: `1,3,5`
  - Ranges: `1-5`
  - Mixed: `1,3-5,7`
  - All: `all`
- **Concurrent Operations**: Refresh multiple stores simultaneously for maximum efficiency
- **Progress Tracking**: Real-time status updates with elapsed time for each operation
- **Robust Error Handling**: Graceful handling of network issues, timeouts, and API errors
- **Detailed Reporting**: Comprehensive summary with success/failure status and timing

## Prerequisites

- Python 3.8 or higher
- UV package manager
- A running Flowise instance
- Network access to the Flowise instance
- Valid Flowise API key

## Installation

1. Install UV if you haven't already:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Clone this repository:
```bash
git clone https://github.com/guimancuso/flowise_update_document_stores.git
cd flowise_update_document_stores
```

3. Create and activate a virtual environment:
```bash
# Create virtual environment
uv venv

# Activate on Linux/macOS
source .venv/bin/activate

# Or activate on Windows
.venv\Scripts\activate
```

4. Install dependencies:
```bash
uv sync
```

**Note:** Using `uv run` automatically uses the virtual environment, so you don't need to activate it manually for running commands.

## Configuration

1. Copy the example environment file:
```bash
cp env.example .env
```

2. Edit the `.env` file with your Flowise configuration:
```env
FLOWISE_BASE_URL=http://localhost:3000
FLOWISE_API_KEY=your_api_key_here
```

### Configuration Options

#### Required Settings

- **`FLOWISE_BASE_URL`**: The base URL of your Flowise instance (e.g., `http://localhost:3000` or `https://flowise.example.com`)
- **`FLOWISE_API_KEY`**: Your Flowise API key (required for authentication)

#### Optional Timeout Settings

- **`STATUS_CHECK_INTERVAL`**: Interval between status checks during refresh operations (in seconds)
  - Default: `15`
  - Example: `STATUS_CHECK_INTERVAL=30` (check every 30 seconds)

- **`MAX_REFRESH_TIMEOUT`**: Maximum time to wait for a refresh operation to complete (in seconds)
  - Default: `600` (10 minutes)
  - Example: `MAX_REFRESH_TIMEOUT=1800` (30 minutes for larger document stores)

## Usage

### Running the Document Store Lister

```bash
uv run python flowise_document_lister.py
```

### Running the Document Store Refresher

```bash
uv run python flowise_document_refresher.py
```

### Running the Automatic Document Store Refresher

```bash
# Refresh by store ID (full or partial)
uv run python flowise_document_refresher_auto.py --id abc123def456

# Refresh by store name (partial match, case-insensitive)
uv run python flowise_document_refresher_auto.py --name "My Documents"

# Refresh multiple stores
uv run python flowise_document_refresher_auto.py --id abc123 --name docs

# Refresh all stores with UPSERTED status
uv run python flowise_document_refresher_auto.py --all

# List all stores without refreshing
uv run python flowise_document_refresher_auto.py --list
```

#### Example Workflow

1. **List Available Stores**: The program automatically fetches all document stores
2. **View Refreshable Stores**: Only stores in a refreshable state are displayed
3. **Select Stores**: Choose which stores to refresh using the interactive prompt
4. **Monitor Progress**: Watch real-time updates as refreshes complete
5. **Review Summary**: See the final results with timing and status information

#### Example Output

```
🚀 Flowise Document Store Refresher
================================================================================
✅ Configuration loaded
   Base URL: http://localhost:3000
📡 Fetching document stores from http://localhost:3000/api/v1/document-store
✅ Found 5 total document store(s)
✅ Found 3 refreshable store(s)

================================================================================
📚 Refreshable Document Stores
================================================================================
  1. Technical Docs (ID: a1b2c3d4..., Status: SYNC)
  2. Product Catalog (ID: e5f6g7h8..., Status: UPSERTED)
  3. FAQ Database (ID: i9j0k1l2..., Status: STALE)
================================================================================

💡 Enter store numbers to refresh:
   Examples: '1' or '1,3,5' or '1-5' or 'all'
   Enter 'q' to quit

Your selection: 1,3

✅ Selected 2 store(s):
   • Technical Docs (ID: a1b2c3d4..., Status: SYNC)
   • FAQ Database (ID: i9j0k1l2..., Status: STALE)

Proceed with refresh? (y/n): y

🔄 Starting refresh for 2 store(s)...

🔄 Started refresh for: Technical Docs
🔄 Started refresh for: FAQ Database
⏳ Technical Docs: SYNCING (Elapsed: 3s)
⏳ FAQ Database: SYNCING (Elapsed: 3s)
⏳ Technical Docs: SYNCING (Elapsed: 6s)
⏳ FAQ Database: SYNCING (Elapsed: 6s)
✅ Technical Docs: Completed in 9s (Status: SYNC)
✅ FAQ Database: Completed in 12s (Status: SYNC)

================================================================================
📊 Refresh Summary
================================================================================
✅ Technical Docs
   Duration: 9s
   Result: SUCCESS - Final Status: SYNC

✅ FAQ Database
   Duration: 12s
   Result: SUCCESS - Final Status: SYNC

================================================================================
Total: 2 | Successful: 2 | Failed: 0
================================================================================
```

## API Endpoints Used

The tools interact with the following Flowise API endpoints:

- **`GET /api/v1/document-store/store`**: List all document stores
- **`GET /api/v1/document-store/store/{id}`**: Get specific document store status
- **`POST /api/v1/document-store/refresh/{id}`**: Trigger document store refresh

## Document Store Statuses

### Refreshable Statuses
- **`SYNC`**: Successfully synchronized (can be re-synced)
- **`UPSERTED`**: Documents have been upserted (can be refreshed)
- **`EMPTY`**: Empty but configured (can be populated)

### Busy Statuses (Not Refreshable)
- **`SYNCING`**: Currently syncing (in progress)
- **`UPSERTING`**: Currently upserting (in progress)

### Waiting Statuses (Not Refreshable)
- **`STALE`**: Store is awaiting update - should NOT be refreshed again until the current update cycle completes

### Other Statuses
- **`NEW`**: Newly created (may not have documents yet)

## Configuration Settings

The refresher uses the following default settings (configurable via environment variables):

- **Status Check Interval**: 15 seconds (configurable via `STATUS_CHECK_INTERVAL`)
- **Maximum Refresh Timeout**: 600 seconds / 10 minutes (configurable via `MAX_REFRESH_TIMEOUT`)

To customize these settings, add them to your `.env` file:

```env
# Example: Check status every 30 seconds and allow up to 30 minutes for completion
STATUS_CHECK_INTERVAL=30
MAX_REFRESH_TIMEOUT=1800
```

## Security Considerations

1. **API Key Protection**: Never commit `.env` file to version control
2. **HTTPS**: Use HTTPS for production Flowise instances
3. **Network Security**: Ensure secure network connection to Flowise
4. **Access Control**: Use API keys with appropriate permissions only

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built for [FlowiseAI](https://flowiseai.com/)
- Uses async programming with `aiohttp`
- Managed with UV package manager
