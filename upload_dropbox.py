#!/usr/bin/env python3
"""
Zip a folder and upload to Dropbox.
Reads env:
  DROPBOX_TOKEN     - required: Dropbox API OAuth2 access token
  RDP_USERNAME      - name of the RDP user (to build the persist path)
  RDP_PERSIST_REL   - relative folder inside the RDP user's profile (e.g., Persist)
  GITHUB_RUN_ID     - used for naming the remote file
"""
import os
import sys
import time
import shutil
from pathlib import Path

try:
    import dropbox
    from dropbox.files import WriteMode, UploadSessionCursor, CommitInfo
except Exception as e:
    print("Missing dropbox package; please pip install dropbox", file=sys.stderr)
    raise

# Config
TOKEN = os.environ.get("DROPBOX_TOKEN")
RDP_USERNAME = os.environ.get("RDP_USERNAME", "RDP")
RDP_PERSIST_REL = os.environ.get("RDP_PERSIST_REL", "Persist")
RUN_ID = os.environ.get("GITHUB_RUN_ID", "local")

if not TOKEN:
    print("ERROR: DROPBOX_TOKEN not set", file=sys.stderr)
    sys.exit(1)

persist_dir = Path(f"C:/Users/{RDP_USERNAME}/{RDP_PERSIST_REL}")
if not persist_dir.exists():
    print(f"No persist directory found at {persist_dir}; nothing to upload.")
    sys.exit(0)

# Create ZIP
zip_base = Path(os.environ.get("TEMP", "/tmp")) / f"rdp-persist-{RUN_ID}"
zip_file = zip_base.with_suffix(".zip")
if zip_file.exists():
    zip_file.unlink()
print(f"Creating zip {zip_file} from {persist_dir} ...")
shutil.make_archive(str(zip_base), 'zip', root_dir=str(persist_dir))
if not zip_file.exists():
    print("Failed to create zip", file=sys.stderr)
    sys.exit(1)

file_size = zip_file.stat().st_size
print(f"Zip size: {file_size / (1024*1024):.2f} MB")

dbx = dropbox.Dropbox(TOKEN)
dropbox_path = f"/rdp-backups/{RUN_ID}.zip"

# Upload logic with chunked session support for > 150 MB
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunk; adjust if needed
SINGLE_UPLOAD_LIMIT = 150 * 1024 * 1024  # 150 MB

max_retries = 5
backoff_factor = 2

def do_single_upload(path, dest):
    with path.open("rb") as f:
        data = f.read()
    for attempt in range(1, max_retries + 1):
        try:
            dbx.files_upload(data, dest, mode=WriteMode('add'), mute=False)
            return True
        except Exception as exc:
            print(f"Single upload attempt {attempt} failed: {exc}")
            if attempt == max_retries:
                raise
            time.sleep(backoff_factor ** attempt)
    return False

def do_chunked_upload(path, dest):
    with path.open("rb") as f:
        session_id = None
        cursor = None
        uploaded = 0
        # start
        chunk = f.read(CHUNK_SIZE)
        for attempt in range(1, max_retries + 1):
            try:
                res = dbx.files_upload_session_start(chunk)
                session_id = res.session_id
                uploaded = len(chunk)
                cursor = UploadSessionCursor(session_id=session_id, offset=uploaded)
                break
            except Exception as exc:
                print(f"start session attempt {attempt} failed: {exc}")
                if attempt == max_retries:
                    raise
                time.sleep(backoff_factor ** attempt)

        # append
        while uploaded < file_size:
            to_read = min(CHUNK_SIZE, file_size - uploaded)
            chunk = f.read(to_read)
            if file_size - uploaded <= CHUNK_SIZE:
                # finish
                commit = CommitInfo(path=dest, mode=WriteMode('add'), mute=False)
                for attempt in range(1, max_retries + 1):
                    try:
                        dbx.files_upload_session_finish(chunk, cursor, commit)
                        uploaded += len(chunk)
                        return True
                    except Exception as exc:
                        print(f"finish attempt {attempt} failed: {exc}")
                        if attempt == max_retries:
                            raise
                        time.sleep(backoff_factor ** attempt)
            else:
                for attempt in range(1, max_retries + 1):
                    try:
                        dbx.files_upload_session_append_v2(chunk, cursor)
                        uploaded += len(chunk)
                        cursor.offset = uploaded
                        break
                    except Exception as exc:
                        print(f"append attempt {attempt} failed: {exc}")
                        if attempt == max_retries:
                            raise
                        time.sleep(backoff_factor ** attempt)
    return False

try:
    if file_size <= SINGLE_UPLOAD_LIMIT:
        print("Using single upload endpoint...")
        do_single_upload(zip_file, dropbox_path)
    else:
        print("Using chunked upload session...")
        do_chunked_upload(zip_file, dropbox_path)
    print("Upload completed:", dropbox_path)
finally:
    try:
        zip_file.unlink()
        print("Cleaned up local zip.")
    except Exception:
        pass                        uploaded += len(chunk)
                        return True
                    except Exception as exc:
                        print(f"finish attempt {attempt} failed: {exc}")
                        if attempt == max_retries:
                            raise
                        time.sleep(backoff_factor ** attempt)
            else:
                for attempt in range(1, max_retries + 1):
                    try:
                        dbx.files_upload_session_append_v2(chunk, cursor)
                        uploaded += len(chunk)
                        cursor.offset = uploaded
                        break
                    except Exception as exc:
                        print(f"append attempt {attempt} failed: {exc}")
                        if attempt == max_retries:
                            raise
                        time.sleep(backoff_factor ** attempt)
    return False

try:
    if file_size <= SINGLE_UPLOAD_LIMIT:
        print("Using single upload endpoint...")
        do_single_upload(zip_file, dropbox_path)
    else:
        print("Using chunked upload session...")
        do_chunked_upload(zip_file, dropbox_path)
    print("Upload completed:", dropbox_path)
finally:
    try:
        zip_file.unlink()
        print("Cleaned up local zip.")
    except Exception:
        pass
