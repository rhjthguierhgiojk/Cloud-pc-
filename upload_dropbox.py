#!/usr/bin/env python3
"""
Uploads the persist folder created by the RDP workflow to Dropbox.
"""

import os
import sys
import logging
import time
from pathlib import Path

try:
    import dropbox
    from dropbox.files import WriteMode, UploadSessionCursor, CommitInfo
    from dropbox.exceptions import ApiError, AuthError
except Exception:
    print("The 'dropbox' package is required. Install with: pip install dropbox", file=sys.stderr)
    raise

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DROPBOX_TOKEN = os.getenv("DROPBOX_TOKEN")
RDP_USERNAME = os.getenv("RDP_USERNAME", "Winn_core")
RDP_PERSIST_REL = os.getenv("RDP_PERSIST_REL", "Persist")
GITHUB_RUN_ID = os.getenv("GITHUB_RUN_ID", "local-run")

if not DROPBOX_TOKEN:
    logging.error("DROPBOX_TOKEN environment variable is not set.")
    sys.exit(1)

local_root = Path(f"C:/Users/{RDP_USERNAME}/{RDP_PERSIST_REL}")
if not local_root.exists():
    logging.warning("Persist folder does not exist: %s", local_root)
    sys.exit(0)

try:
    dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    dbx.users_get_current_account()
except AuthError:
    logging.error("Dropbox authentication failed. Check DROPBOX_TOKEN.")
    sys.exit(1)
except Exception as e:
    logging.error("Failed to initialize Dropbox client: %s", e)
    sys.exit(1)

DROPBOX_ROOT = f"/rdp-backups/{GITHUB_RUN_ID}"
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB


def upload_file(local_path: Path, dest_path: str):
    size = local_path.stat().st_size
    dest_path = dest_path.replace("\\", "/")
    logging.info("Uploading %s -> %s (%d bytes)", local_path, dest_path, size)

    try:
        with local_path.open("rb") as f:
            if size <= 150 * 1024 * 1024:
                data = f.read()
                dbx.files_upload(data, dest_path, mode=WriteMode("overwrite"))
            else:
                logging.info("Starting chunked upload for %s", local_path)
                session_start_result = dbx.files_upload_session_start(f.read(CHUNK_SIZE))
                cursor = UploadSessionCursor(session_id=session_start_result.session_id, offset=f.tell())
                commit = CommitInfo(path=dest_path, mode=WriteMode("overwrite"))

                while f.tell() < size:
                    remaining = size - f.tell()
                    chunk = f.read(CHUNK_SIZE)
                    if remaining <= CHUNK_SIZE:
                        dbx.files_upload_session_finish(chunk, cursor, commit)
                    else:
                        dbx.files_upload_session_append_v2(chunk, cursor)
                        cursor.offset = f.tell()
    except Exception as e:
        logging.error("Failed to upload %s: %s", local_path, e)


def main():
    logging.info("Starting upload from %s to %s", local_root, DROPBOX_ROOT)
    for root, dirs, files in os.walk(local_root):
        rel_root = Path(root).relative_to(local_root)
        dropbox_dir = f"{DROPBOX_ROOT}/{rel_root.as_posix()}" if str(rel_root) != "." else DROPBOX_ROOT

        for fname in files:
            local_path = Path(root) / fname
            dest_path = f"{dropbox_dir}/{fname}"
            upload_file(local_path, dest_path)

    logging.info("Upload run complete.")


if __name__ == "__main__":
    main()
