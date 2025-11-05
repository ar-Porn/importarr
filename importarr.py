#!/usr/bin/env python3
"""
Importarr - Unified Stash & File Import Script for Whisparr
Supports both Stash scene sync and file import operations.
"""

import requests
import time
import json
import os
from typing import List, Dict, Optional
import sys
from datetime import datetime
import schedule

# ============== CONFIGURATION FROM ENV ==============
# General Settings
MODE = os.environ.get("IMPORTARR_MODE", "both")  # both, stash, files
RUN_MODE = os.environ.get("IMPORTARR_RUN_MODE", "once")  # once, interval
RUN_INTERVAL_HOURS = int(os.environ.get("IMPORTARR_INTERVAL_HOURS", "24"))
DRY_RUN = os.environ.get("IMPORTARR_DRY_RUN", "false").lower() == "true"

# Whisparr Settings
WHISPARR_URL = os.environ.get("WHISPARR_URL", "http://whisparr:9090")
WHISPARR_API_KEY = os.environ.get("WHISPARR_API_KEY", "")

# Stash Settings (for Stash sync mode)
STASH_URL = os.environ.get("STASH_URL", "http://stash:9999")
STASH_API_KEY = os.environ.get("STASH_API_KEY", "")
STASH_BATCH_SIZE = int(os.environ.get("STASH_BATCH_SIZE", "50"))
STASH_DELAY_BETWEEN_BATCHES = int(os.environ.get("STASH_DELAY_BETWEEN_BATCHES", "5"))
STASH_DELAY_BETWEEN_REQUESTS = float(os.environ.get("STASH_DELAY_BETWEEN_REQUESTS", "0.5"))

# File Import Settings (for file import mode)
IMPORT_FOLDER = os.environ.get("IMPORT_FOLDER", "/import")
IMPORT_MODE = os.environ.get("IMPORT_MODE", "copy")  # move or copy
FILE_BATCH_SIZE = int(os.environ.get("FILE_BATCH_SIZE", "50"))
FILE_DELAY_BETWEEN_BATCHES = int(os.environ.get("FILE_DELAY_BETWEEN_BATCHES", "5"))
FILE_DELAY_BETWEEN_SUBFOLDERS = int(os.environ.get("FILE_DELAY_BETWEEN_SUBFOLDERS", "5"))
PROCESS_ROOT_FILES = os.environ.get("PROCESS_ROOT_FILES", "false").lower() == "true"
MAX_SUBFOLDERS = os.environ.get("MAX_SUBFOLDERS", None)
MAX_SUBFOLDERS = int(MAX_SUBFOLDERS) if MAX_SUBFOLDERS else None
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", "10"))

# Whisparr Scene Add Settings
QUALITY_PROFILE_ID = int(os.environ.get("WHISPARR_QUALITY_PROFILE_ID", "1"))
ROOT_FOLDER_PATH = os.environ.get("WHISPARR_ROOT_FOLDER_PATH", "")
TAG_IDS_STR = os.environ.get("WHISPARR_TAG_IDS", "")
TAG_IDS = [int(t.strip()) for t in TAG_IDS_STR.split(",") if t.strip()] if TAG_IDS_STR else []

# ====================================================

whisparr_headers = {"X-Api-Key": WHISPARR_API_KEY}
stash_headers = {
    "ApiKey": STASH_API_KEY,
    "Content-Type": "application/json"
}

# Global stats
total_stats = {
    "stash": {
        "scenes_found": 0,
        "scenes_with_stashdb": 0,
        "scenes_added": 0,
        "scenes_already_exist": 0,
        "scenes_failed": 0,
        "batches_processed": 0
    },
    "files": {
        "subfolders_processed": 0,
        "files_imported": 0,
        "files_unmatched": 0,
        "batches_processed": 0
    }
}


# ============== STASH SYNC FUNCTIONS ==============

def get_root_folders() -> List[Dict]:
    """Get available root folders from Whisparr."""
    try:
        response = requests.get(
            f"{WHISPARR_URL}/api/v3/rootfolder",
            headers=whisparr_headers,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"WARNING: Failed to get root folders: {e}")
        return []


def get_stash_scenes() -> List[Dict]:
    """Fetch all scenes from Stash using GraphQL with detailed metadata."""
    print("Fetching scenes from Stash...")
    
    all_scenes = []
    page = 1
    per_page = 100
    
    query = """
    query FindScenes($filter: FindFilterType!) {
        findScenes(filter: $filter) {
            count
            scenes {
                id
                title
                date
                studio {
                    name
                }
                stash_ids {
                    endpoint
                    stash_id
                }
                performers {
                    name
                }
                files {
                    path
                }
            }
        }
    }
    """
    
    while True:
        variables = {
            "filter": {
                "page": page,
                "per_page": per_page,
                "sort": "id",
                "direction": "ASC"
            }
        }
        
        try:
            response = requests.post(
                f"{STASH_URL}/graphql",
                headers=stash_headers,
                json={"query": query, "variables": variables},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                print(f"ERROR: GraphQL errors: {data['errors']}")
                break
            
            scenes = data.get("data", {}).get("findScenes", {}).get("scenes", [])
            total_count = data.get("data", {}).get("findScenes", {}).get("count", 0)
            
            if not scenes:
                break
            
            all_scenes.extend(scenes)
            print(f"  Fetched {len(all_scenes)}/{total_count} scenes...")
            
            if len(all_scenes) >= total_count:
                break
            
            page += 1
            
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Failed to fetch scenes from Stash: {e}")
            break
    
    print(f"✓ Found {len(all_scenes)} total scenes in Stash")
    return all_scenes


def filter_stashdb_scenes(scenes: List[Dict]) -> List[Dict]:
    """Filter scenes to only those with StashDB IDs and extract metadata."""
    stashdb_scenes = []
    
    for scene in scenes:
        stash_ids = scene.get("stash_ids", [])
        
        for stash_id in stash_ids:
            endpoint = stash_id.get("endpoint", "")
            if "stashdb.org" in endpoint:
                studio = scene.get("studio")
                studio_name = studio.get("name") if studio else None
                
                performers = scene.get("performers", [])
                performer_names = [p.get("name") for p in performers if p.get("name")]
                
                stashdb_scenes.append({
                    "stash_id": stash_id.get("stash_id"),
                    "title": scene.get("title", "Unknown"),
                    "date": scene.get("date"),
                    "studio": studio_name,
                    "performers": performer_names,
                    "endpoint": endpoint,
                    "files": scene.get("files", [])
                })
                break
    
    return stashdb_scenes


def get_whisparr_movies() -> List[Dict]:
    """Get all movies/scenes currently in Whisparr."""
    try:
        response = requests.get(
            f"{WHISPARR_URL}/api/v3/movie",
            headers=whisparr_headers,
            timeout=180
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        print(f"WARNING: Timeout fetching existing movies (large library)")
        print(f"  Continuing without duplicate check - may see 'already exists' errors")
        return []
    except requests.exceptions.RequestException as e:
        print(f"WARNING: Failed to get existing Whisparr movies: {e}")
        return []


def add_scene_to_whisparr(stash_id: str, title: str, root_folder: str) -> bool:
    """Add a scene to Whisparr directly using StashDB ID."""
    if DRY_RUN:
        print(f"    [DRY RUN] Would add scene")
        return True
    
    try:
        add_data = {
            "title": title,
            "foreignId": stash_id,
            "stashId": stash_id,
            "qualityProfileId": QUALITY_PROFILE_ID,
            "monitored": True,
            "rootFolderPath": root_folder,
            "addOptions": {
                "searchForMovie": False,
                "monitor": "movieOnly"
            }
        }
        
        if TAG_IDS:
            add_data["tags"] = TAG_IDS
        
        add_response = requests.post(
            f"{WHISPARR_URL}/api/v3/movie",
            headers=whisparr_headers,
            json=add_data,
            timeout=30
        )
        add_response.raise_for_status()
        
        response_data = add_response.json()
        actual_title = response_data.get("title", title)
        print(f"    ✓ Added: {actual_title}")
        return True
        
    except requests.exceptions.HTTPError as e:
        if hasattr(e, 'response') and e.response is not None:
            status_code = e.response.status_code
            
            try:
                error_data = e.response.json()
                error_msg = str(error_data).lower()
                
                if status_code == 400 and ("already" in error_msg or "exist" in error_msg):
                    print(f"    Already exists in Whisparr")
                    total_stats["stash"]["scenes_already_exist"] += 1
                    return True
                
                if status_code == 404 or "not found" in error_msg:
                    print(f"    ⚠ Scene not found in StashDB metadata provider")
                    return False
                
                if "validation" in error_msg:
                    print(f"    ERROR: Validation failed - {error_data}")
                    return False
                
            except:
                pass
            
            print(f"    ERROR: HTTP {status_code}")
        else:
            print(f"    ERROR: Failed to add scene: {e}")
        
        return False
        
    except requests.exceptions.RequestException as e:
        print(f"    ERROR: Network error: {e}")
        return False


def process_stash_batch(batch: List[Dict], batch_num: int, total_batches: int, 
                        existing_stash_ids: set, root_folder: str) -> Dict:
    """Process a batch of Stash scenes."""
    status = "[DRY RUN]" if DRY_RUN else ""
    print(f"\n[Batch {batch_num}/{total_batches}] Processing {len(batch)} scenes {status}")
    print("-" * 60)
    
    added = 0
    failed = 0
    
    for scene in batch:
        stash_id = scene["stash_id"]
        title = scene["title"]
        studio = scene.get("studio")
        date = scene.get("date")
        
        print(f"  {title[:70]}{'...' if len(title) > 70 else ''}")
        if studio:
            print(f"    Studio: {studio}")
        if date:
            print(f"    Date: {date}")
        print(f"    StashDB ID: {stash_id}")
        
        if stash_id in existing_stash_ids:
            print(f"    Already exists (skipping)")
            total_stats["stash"]["scenes_already_exist"] += 1
            added += 1
            if STASH_DELAY_BETWEEN_REQUESTS > 0:
                time.sleep(STASH_DELAY_BETWEEN_REQUESTS)
            continue
        
        success = add_scene_to_whisparr(stash_id, title, root_folder)
        
        if success:
            added += 1
            existing_stash_ids.add(stash_id)
        else:
            failed += 1
        
        if STASH_DELAY_BETWEEN_REQUESTS > 0:
            time.sleep(STASH_DELAY_BETWEEN_REQUESTS)
    
    return {"added": added, "failed": failed}


def run_stash_sync():
    """Main Stash sync function."""
    print("\n" + "=" * 60)
    print("STASH SYNC MODE")
    print("=" * 60)
    print(f"Stash URL: {STASH_URL}")
    print(f"Whisparr URL: {WHISPARR_URL}")
    print(f"Batch Size: {STASH_BATCH_SIZE}")
    print(f"Dry Run: {DRY_RUN}")
    if TAG_IDS:
        print(f"Tags to apply: {TAG_IDS}")
    print("=" * 60)
    print()
    
    if DRY_RUN:
        print("⚠️ DRY RUN MODE - No scenes will be added to Whisparr\n")
    
    # Get root folder
    root_folders = get_root_folders()
    if not root_folders:
        print("ERROR: No root folders found in Whisparr")
        return False
    
    root_folder = ROOT_FOLDER_PATH if ROOT_FOLDER_PATH else root_folders[0].get("path")
    print(f"Using root folder: {root_folder}\n")
    
    # Get existing movies
    print("Fetching existing scenes from Whisparr...")
    existing_movies = get_whisparr_movies()
    existing_stash_ids = {
        m.get("stashId") for m in existing_movies 
        if m.get("stashId")
    }
    print(f"✓ Found {len(existing_movies)} existing scenes in Whisparr")
    print(f"  ({len(existing_stash_ids)} have StashDB IDs)\n")
    
    # Get scenes from Stash
    all_scenes = get_stash_scenes()
    total_stats["stash"]["scenes_found"] = len(all_scenes)
    
    if not all_scenes:
        print("No scenes found in Stash!")
        return True
    
    # Filter to StashDB scenes
    print("\nFiltering scenes with StashDB IDs...")
    stashdb_scenes = filter_stashdb_scenes(all_scenes)
    total_stats["stash"]["scenes_with_stashdb"] = len(stashdb_scenes)
    
    print(f"✓ Found {len(stashdb_scenes)} scenes with StashDB IDs")
    print(f"  ({len(all_scenes) - len(stashdb_scenes)} scenes without StashDB IDs will be ignored)")
    print()
    
    if not stashdb_scenes:
        print("No scenes with StashDB IDs found!")
        return True
    
    # Process in batches
    print(f"Adding scenes to Whisparr...")
    print(f"NOTE: Whisparr will automatically fetch metadata from StashDB for each scene")
    print()
    
    start_time = time.time()
    total_batches = (len(stashdb_scenes) + STASH_BATCH_SIZE - 1) // STASH_BATCH_SIZE
    
    for i in range(0, len(stashdb_scenes), STASH_BATCH_SIZE):
        batch = stashdb_scenes[i:i+STASH_BATCH_SIZE]
        batch_num = i // STASH_BATCH_SIZE + 1
        
        stats = process_stash_batch(batch, batch_num, total_batches, existing_stash_ids, root_folder)
        
        total_stats["stash"]["scenes_added"] += stats["added"]
        total_stats["stash"]["scenes_failed"] += stats["failed"]
        total_stats["stash"]["batches_processed"] += 1
        
        if i + STASH_BATCH_SIZE < len(stashdb_scenes) and STASH_DELAY_BETWEEN_BATCHES > 0:
            print(f"\nWaiting {STASH_DELAY_BETWEEN_BATCHES} seconds before next batch...")
            time.sleep(STASH_DELAY_BETWEEN_BATCHES)
    
    # Summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("Stash Sync Complete!")
    print("=" * 60)
    print(f"Time elapsed: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print(f"Total scenes in Stash: {total_stats['stash']['scenes_found']}")
    print(f"Scenes with StashDB IDs: {total_stats['stash']['scenes_with_stashdb']}")
    print(f"Batches processed: {total_stats['stash']['batches_processed']}")
    print(f"Scenes added to Whisparr: {total_stats['stash']['scenes_added']}")
    print(f"Scenes already existed: {total_stats['stash']['scenes_already_exist']}")
    print(f"Scenes failed: {total_stats['stash']['scenes_failed']}")
    print("=" * 60)
    
    return True


# ============== FILE IMPORT FUNCTIONS ==============

def count_files_in_folder(folder: str) -> int:
    """Count the number of files (not directories) in a folder."""
    try:
        items = os.listdir(folder)
        files = [item for item in items if os.path.isfile(os.path.join(folder, item))]
        return len(files)
    except Exception:
        return 0


def get_all_subfolders_recursive(root_path: str, max_depth: int = 10) -> List[tuple]:
    """Get all subdirectories recursively with their depth and file count."""
    all_folders = []
    
    def scan_directory(path: str, current_depth: int):
        if current_depth > max_depth:
            return
        
        try:
            items = os.listdir(path)
            subfolders = [
                os.path.join(path, item) 
                for item in items 
                if os.path.isdir(os.path.join(path, item))
            ]
            
            for subfolder in subfolders:
                file_count = count_files_in_folder(subfolder)
                all_folders.append((subfolder, current_depth, file_count))
                scan_directory(subfolder, current_depth + 1)
                
        except Exception as e:
            print(f"WARNING: Cannot read directory {path}: {e}")
    
    print("Scanning folder structure and counting files...")
    scan_directory(root_path, 1)
    all_folders.sort(key=lambda x: (-x[1], -x[2], x[0]))
    
    return all_folders


def get_files_to_import(folder: str) -> List[Dict]:
    """Fetch all files from a specific folder that Whisparr can see."""
    folder_name = os.path.basename(folder) or folder
    print(f"  Scanning: {folder_name}")
    
    try:
        response = requests.get(
            f"{WHISPARR_URL}/api/v3/manualimport",
            headers=whisparr_headers,
            params={
                "folder": folder,
                "filterExistingFiles": True
            },
            timeout=120
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        print(f"  WARNING: Timeout scanning folder (too many files?), skipping...")
        return []
    except requests.exceptions.RequestException as e:
        print(f"  ERROR: Failed to scan folder: {e}")
        return []


def filter_matched_files(files: List[Dict]) -> tuple[List[Dict], List[Dict], List[Dict]]:
    """Separate files into matched (importable), potential matches, and unmatched."""
    matched = []
    potential = []
    unmatched = []
    
    for file in files:
        rejections = file.get("rejections", [])
        scene = file.get("scene")
        movie = file.get("movie")
        
        scene_id = None
        if scene and scene.get("id"):
            scene_id = scene.get("id")
        elif movie and movie.get("id"):
            scene_id = movie.get("id")
        
        if scene_id:
            matched.append(file)
        elif scene or movie:
            potential.append({
                "file": file,
                "scene_title": (scene or movie).get("title", "Unknown") if (scene or movie) else "Unknown",
                "rejections": [r.get("reason", "Unknown") for r in rejections]
            })
        else:
            unmatched.append({
                "path": file.get("path", "Unknown"),
                "rejections": [r.get("reason", "Unknown") for r in rejections] if rejections else ["No scene/movie data in response"]
            })
    
    return matched, potential, unmatched


def import_file_batch(batch: List[Dict]) -> bool:
    """Import a batch of files using the command endpoint."""
    if DRY_RUN:
        return True
    
    try:
        formatted_files = []
        for file in batch:
            scene = file.get("scene")
            movie = file.get("movie")
            
            entity_id = None
            if scene and scene.get("id"):
                entity_id = scene["id"]
            elif movie and movie.get("id"):
                entity_id = movie["id"]
            
            if not entity_id:
                print(f"    WARNING: Skipping file without valid ID: {file.get('path', 'unknown')}")
                continue
            
            formatted_file = {
                "path": file["path"],
                "folderName": file.get("folderName", ""),
                "movieId": entity_id,
                "quality": file.get("quality", {}),
                "languages": file.get("languages", []),
                "releaseGroup": file.get("releaseGroup", ""),
                "downloadId": file.get("downloadId", ""),
                "importMode": IMPORT_MODE
            }
            formatted_files.append(formatted_file)
        
        if not formatted_files:
            print(f"    ERROR: No valid files to import in this batch")
            return False
        
        print(f"    Importing {len(formatted_files)} files...")
        
        command_data = {
            "name": "ManualImport",
            "files": formatted_files,
            "importMode": IMPORT_MODE
        }
        
        response = requests.post(
            f"{WHISPARR_URL}/api/v3/command",
            headers=whisparr_headers,
            json=command_data,
            timeout=120
        )
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("id"):
            command_id = result.get("id")
            print(f"    Import command queued (ID: {command_id})")
            return True
        else:
            print(f"    WARNING: Command response missing ID: {result}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"    ERROR: Failed to import batch: {e}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print(f"    Response: {e.response.text}")
        return False


def process_file_folder(folder: str, folder_num: int, total_folders: int, depth: int, file_count: int) -> Dict:
    """Process a single folder and return stats."""
    folder_name = os.path.basename(folder) or folder
    indent = "  " * (depth - 1)
    print(f"\n[{folder_num}/{total_folders}] {indent}Processing (depth {depth}, {file_count} files): {folder_name}")
    print("-" * 60)
    
    all_files = get_files_to_import(folder)
    
    if not all_files:
        print(f"  No files found or accessible")
        return {"imported": 0, "unmatched": 0, "batches": 0}
    
    print(f"  Found {len(all_files)} files")
    
    matched, potential, unmatched = filter_matched_files(all_files)
    
    print(f"  ✓ Matched: {len(matched)} | ? Potential: {len(potential)} | ✗ Unmatched: {len(unmatched)}")
    
    if potential:
        print(f"  Potential matches (no valid ID, cannot import):")
        for p in potential[:3]:
            print(f"    - {os.path.basename(p['file'].get('path', 'unknown'))}")
            print(f"      Scene: {p['scene_title']}")
            if p['rejections']:
                print(f"      Reasons: {', '.join(p['rejections'])}")
        if len(potential) > 3:
            print(f"    ... and {len(potential) - 3} more")
    
    if not matched:
        print(f"  Nothing to import from this folder")
        return {"imported": 0, "unmatched": len(unmatched) + len(potential), "batches": 0}
    
    print(f"  Importing {len(matched)} files...")
    
    total_batches = (len(matched) + FILE_BATCH_SIZE - 1) // FILE_BATCH_SIZE
    successful_batches = 0
    
    for i in range(0, len(matched), FILE_BATCH_SIZE):
        batch = matched[i:i+FILE_BATCH_SIZE]
        batch_num = i // FILE_BATCH_SIZE + 1
        
        status = "[DRY RUN]" if DRY_RUN else ""
        print(f"    Batch {batch_num}/{total_batches} ({len(batch)} files) {status}")
        
        success = import_file_batch(batch)
        if success:
            successful_batches += 1
        
        if i + FILE_BATCH_SIZE < len(matched) and FILE_DELAY_BETWEEN_BATCHES > 0:
            time.sleep(FILE_DELAY_BETWEEN_BATCHES)
    
    print(f"  ✓ Completed: {successful_batches}/{total_batches} batches")
    
    return {
        "imported": len(matched),
        "unmatched": len(unmatched) + len(potential),
        "batches": successful_batches
    }


def run_file_import():
    """Main file import function."""
    print("\n" + "=" * 60)
    print("FILE IMPORT MODE")
    print("=" * 60)
    print(f"Whisparr URL: {WHISPARR_URL}")
    print(f"Import Folder: {IMPORT_FOLDER}")
    print(f"Import Mode: {IMPORT_MODE}")
    print(f"Batch Size: {FILE_BATCH_SIZE}")
    print(f"Dry Run: {DRY_RUN}")
    print(f"Max Depth: {MAX_DEPTH}")
    if MAX_SUBFOLDERS:
        print(f"Max Subfolders: {MAX_SUBFOLDERS}")
    print("=" * 60)
    print()
    
    if DRY_RUN:
        print("⚠️ DRY RUN MODE - No files will be moved/copied\n")
    
    if not os.path.exists(IMPORT_FOLDER):
        print(f"ERROR: Import folder does not exist: {IMPORT_FOLDER}")
        return False
    
    print("Discovering subfolders recursively (deepest first, most files first)...")
    all_subfolders = get_all_subfolders_recursive(IMPORT_FOLDER, MAX_DEPTH)
    
    if MAX_SUBFOLDERS and len(all_subfolders) > MAX_SUBFOLDERS:
        print(f"Limiting to first {MAX_SUBFOLDERS} subfolders")
        all_subfolders = all_subfolders[:MAX_SUBFOLDERS]
    
    folders_to_process = []
    if PROCESS_ROOT_FILES:
        root_file_count = count_files_in_folder(IMPORT_FOLDER)
        folders_to_process.append((IMPORT_FOLDER, 0, root_file_count))
    folders_to_process.extend(all_subfolders)
    
    print(f"Found {len(all_subfolders)} subfolders")
    if all_subfolders:
        max_depth = max(depth for _, depth, _ in all_subfolders)
        total_files = sum(file_count for _, _, file_count in all_subfolders)
        print(f"Maximum folder depth: {max_depth}")
        print(f"Total files across all folders: {total_files}")
    if PROCESS_ROOT_FILES:
        print(f"Will also process root folder files")
    print(f"Total folders to process: {len(folders_to_process)}")
    print()
    
    if not folders_to_process:
        print("No folders to process!")
        return True
    
    start_time = time.time()
    
    for idx, (folder, depth, file_count) in enumerate(folders_to_process, 1):
        stats = process_file_folder(folder, idx, len(folders_to_process), depth, file_count)
        
        total_stats["files"]["subfolders_processed"] += 1
        total_stats["files"]["files_imported"] += stats["imported"]
        total_stats["files"]["files_unmatched"] += stats["unmatched"]
        total_stats["files"]["batches_processed"] += stats["batches"]
        
        if idx < len(folders_to_process) and FILE_DELAY_BETWEEN_SUBFOLDERS > 0:
            time.sleep(FILE_DELAY_BETWEEN_SUBFOLDERS)
    
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("File Import Complete!")
    print("=" * 60)
    print(f"Time elapsed: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print(f"Subfolders processed: {total_stats['files']['subfolders_processed']}")
    print(f"Batches processed: {total_stats['files']['batches_processed']}")
    print(f"Files imported: {total_stats['files']['files_imported']}")
    print(f"Files left behind (unmatched): {total_stats['files']['files_unmatched']}")
    print("=" * 60)
    
    return True


# ============== MAIN EXECUTION ==============

def run_all_imports():
    """Run the configured import modes."""
    print("\n" + "=" * 60)
    print(f"Importarr Starting - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print(f"Mode: {MODE}")
    print(f"Run Mode: {RUN_MODE}")
    if RUN_MODE == "interval":
        print(f"Interval: Every {RUN_INTERVAL_HOURS} hours")
    print("=" * 60)
    
    success = True
    
    if MODE in ["both", "stash"]:
        if not STASH_API_KEY:
            print("ERROR: STASH_API_KEY not set but stash mode is enabled")
            success = False
        else:
            try:
                if not run_stash_sync():
                    success = False
            except Exception as e:
                print(f"ERROR in stash sync: {e}")
                import traceback
                traceback.print_exc()
                success = False
    
    if MODE in ["both", "files"]:
        try:
            if not run_file_import():
                success = False
        except Exception as e:
            print(f"ERROR in file import: {e}")
            import traceback
            traceback.print_exc()
            success = False
    
    print("\n" + "=" * 60)
    print(f"Importarr Finished - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    return success


def main():
    """Main entry point."""
    if not WHISPARR_API_KEY:
        print("ERROR: WHISPARR_API_KEY environment variable is required")
        sys.exit(1)
    
    if MODE not in ["both", "stash", "files"]:
        print(f"ERROR: Invalid IMPORTARR_MODE: {MODE}")
        print("Valid options: both, stash, files")
        sys.exit(1)
    
    if RUN_MODE == "once":
        # Run once and exit
        success = run_all_imports()
        sys.exit(0 if success else 1)
    
    elif RUN_MODE == "interval":
        # Run on schedule
        print(f"Scheduling import to run every {RUN_INTERVAL_HOURS} hours")
        print(f"First run will start immediately...")
        
        # Run immediately on startup
        run_all_imports()
        
        # Schedule subsequent runs
        schedule.every(RUN_INTERVAL_HOURS).hours.do(run_all_imports)
        
        print(f"\nNext run scheduled in {RUN_INTERVAL_HOURS} hours")
        print("Press Ctrl+C to stop")
        
        # Keep running
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            print("\n\nImportarr stopped by user")
            sys.exit(0)
    
    else:
        print(f"ERROR: Invalid IMPORTARR_RUN_MODE: {RUN_MODE}")
        print("Valid options: once, interval")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nImportarr cancelled by user")
        sys.exit(0)
