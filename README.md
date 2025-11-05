# Importarr

A Docker container for importing adult scenes into [Whisparr](https://whisparr.com/). Importarr provides two powerful import methods:

1. **Stash Sync** - Automatically sync StashDB-tagged scenes from [Stash](https://stashapp.cc/) to Whisparr as monitored items
2. **File Import** - Import existing scene files from disk, intelligently processing folder structures and matching files to Whisparr metadata

Perfect for migrating large existing libraries or keeping Whisparr in sync with your Stash database.

## Features

- 🔄 **Dual Mode Operation** - Run Stash sync, file import, or both simultaneously
- ⏱️ **Flexible Scheduling** - One-time execution or continuous operation at configurable intervals
- 🧪 **Dry Run Mode** - Test imports without making any changes
- 📦 **Batch Processing** - Efficient handling of large libraries with configurable batch sizes
- 🎯 **Smart Folder Traversal** - Processes deepest folders first for accurate file detection
- 🔒 **Safe Operations** - Leaves unmatched files in place, only imports confirmed matches
- 🐳 **Easy Docker Deployment** - Simple configuration via environment variables

## Quick Start

### 1. Build the Image

```bash
docker build -t local/importarr:latest .
```

### 2. Configure docker-compose.yml

Update the volume mount to point to your import folder:

```yaml
volumes:
  - /path/to/your/import/folder:/import/man/scenes
```

Update environment variables with your Whisparr and Stash URLs/API keys.

### 3. Run

```bash
# Start in background
docker-compose up -d

# View logs
docker-compose logs -f importarr
```

## Configuration

All configuration is done via environment variables:

### General Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `IMPORTARR_MODE` | `both` | Import mode: `both`, `stash`, or `files` |
| `IMPORTARR_RUN_MODE` | `once` | Execution mode: `once` or `interval` |
| `IMPORTARR_INTERVAL_HOURS` | `24` | Hours between runs (when using `interval` mode) |
| `IMPORTARR_DRY_RUN` | `false` | Set to `true` to test without making changes |

### Whisparr Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPARR_URL` | `http://whisparr:6969` | Whisparr instance URL |
| `WHISPARR_API_KEY` | *(required)* | Whisparr API key |
| `WHISPARR_QUALITY_PROFILE_ID` | `1` | Quality profile ID for added scenes |
| `WHISPARR_ROOT_FOLDER_PATH` | *(auto)* | Root folder path (uses first if empty) |
| `WHISPARR_TAG_IDS` | *(empty)* | Comma-separated tag IDs to apply |

### Stash Sync Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `STASH_URL` | `http://stash:9999` | Stash instance URL |
| `STASH_API_KEY` | *(required for stash mode)* | Stash API key |
| `STASH_BATCH_SIZE` | `50` | Scenes per batch |
| `STASH_DELAY_BETWEEN_BATCHES` | `5` | Seconds to wait between batches |
| `STASH_DELAY_BETWEEN_REQUESTS` | `0.5` | Seconds to wait between individual requests |

### File Import Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `IMPORT_FOLDER` | `/import` | Import folder path inside container |
| `IMPORT_MODE` | `copy` | File operation: `move` or `copy` |
| `FILE_BATCH_SIZE` | `50` | Files per batch |
| `FILE_DELAY_BETWEEN_BATCHES` | `5` | Seconds to wait between batches |
| `FILE_DELAY_BETWEEN_SUBFOLDERS` | `5` | Seconds to wait between folders |
| `PROCESS_ROOT_FILES` | `false` | Process files in root folder |
| `MAX_SUBFOLDERS` | *(none)* | Limit number of subfolders to process |
| `MAX_DEPTH` | `10` | Maximum folder depth to scan |

## Usage Examples

### Example 1: One-Time Stash Sync (Dry Run)

Test syncing scenes from Stash to Whisparr without making changes:

```yaml
environment:
  IMPORTARR_MODE: "stash"
  IMPORTARR_RUN_MODE: "once"
  IMPORTARR_DRY_RUN: "true"
  WHISPARR_URL: "http://10.1.1.44:6969"
  WHISPARR_API_KEY: "your-api-key"
  STASH_URL: "http://10.1.1.30:9999"
  STASH_API_KEY: "your-stash-api-key"
```

```bash
docker-compose up
```

### Example 2: Daily File Import

Import files from disk every 24 hours:

```yaml
environment:
  IMPORTARR_MODE: "files"
  IMPORTARR_RUN_MODE: "interval"
  IMPORTARR_INTERVAL_HOURS: "24"
  IMPORT_MODE: "copy"  # Use "move" to relocate files
volumes:
  - /mnt/media/scenes:/import/man/scenes
```

```bash
docker-compose up -d
```

### Example 3: Full Library Migration

Run both Stash sync and file import once:

```yaml
environment:
  IMPORTARR_MODE: "both"
  IMPORTARR_RUN_MODE: "once"
  IMPORTARR_DRY_RUN: "false"
```

```bash
docker-compose up -d
```

## How It Works

### Stash Sync Mode

1. Fetches all scenes from your Stash instance
2. Filters scenes that have StashDB IDs
3. Checks which scenes already exist in Whisparr
4. Adds new scenes to Whisparr as monitored items
5. Whisparr automatically fetches metadata from StashDB

**Note:** Only scenes with StashDB IDs can be synced. Scenes without StashDB IDs are ignored.

### File Import Mode

1. Recursively scans the import folder (deepest folders first)
2. Uses Whisparr's API to identify which files match scenes in the database
3. Imports matched files using configurable batch sizes
4. Leaves unmatched files in place for manual review
5. Supports both `copy` (safe) and `move` (cleanup) modes

**Best Practice:** Start with `IMPORT_MODE: "copy"` to ensure files are correctly imported before switching to `move`.

## Networking

If running Whisparr and Stash in Docker containers on the same host docker dns can be used:


Use container names in URLs:
```yaml
WHISPARR_URL: "http://whisparr:6969"
STASH_URL: "http://stash:9999"
```

## Troubleshooting

### Check logs

```bash
docker-compose logs -f importarr
```

### Verify container is running

```bash
docker ps | grep importarr
```

### Test with dry run

Set `IMPORTARR_DRY_RUN: "true"` to test without making changes.

### Common issues

- **"No root folders found"** - Configure a root folder in Whisparr Settings → Media Management
- **"Scene not found in StashDB"** - Scene exists in Stash but not in StashDB's database
- **"Timeout scanning folder"** - Reduce `FILE_BATCH_SIZE` or increase timeout in code
- **"Already exists"** - Scene already in Whisparr (not an error, just informational)

## Security

- Store API keys securely using `.env` file (don't commit to git)
- Use `IMPORT_MODE: "copy"` initially to avoid data loss
- Test with `IMPORTARR_DRY_RUN: "true"` before production runs
- Ensure proper file permissions on mounted volumes

## Requirements

- Docker and Docker Compose
- Whisparr instance with API access
- (Optional) Stash instance with API access for Stash sync mode
- (Optional) Existing scene library for file import mode

## License

GPL License - See LICENSE file for details

## Contributing

Contributions welcome! Please open an issue or pull request.

## Acknowledgments

- Built for [Whisparr](https://whisparr.com/) - The adult content PVR
- Integrates with [Stash](https://stashapp.cc/) - Adult content organizer
- Uses [StashDB](https://stashdb.org/) - Community scene database

---

**Note:** This tool is designed for managing adult content libraries. Please ensure you comply with all applicable laws and terms of service.
