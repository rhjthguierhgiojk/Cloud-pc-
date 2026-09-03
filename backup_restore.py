#!/usr/bin/env python3
import os
import sys
import shutil
import zipfile
import logging
from pathlib import Path
from datetime import datetime

try:
    import dropbox
    from dropbox.files import WriteMode
    from dropbox.exceptions import ApiError, AuthError
except ImportError:
    print("Please install dropbox: pip install dropbox")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DROPBOX_TOKEN = os.getenv("DROPBOX_TOKEN")
RDP_USERNAME = os.getenv("RDP_USERNAME", "Winn_core")
MODE = os.getenv("BACKUP_MODE", "backup")  # "backup" or "restore"

if not DROPBOX_TOKEN:
    logging.error("DROPBOX_TOKEN is missing")
    sys.exit(1)

dbx = dropbox.Dropbox(DROPBOX_TOKEN)
DROPBOX_FOLDER = "/rdp-backups"
LATEST_ZIP = f"{DROPBOX_FOLDER}/latest_backup.zip"

# Folders we want to backup / restore
USER_PROFILE = Path(f"C:/Users/{RDP_USERNAME}")
FOLDERS_TO_BACKUP = [
    USER_PROFILE / "Desktop",
    USER_PROFILE / "Documents",
    USER_PROFILE / "Downloads",
    USER_PROFILE / "Pictures",
    USER_PROFILE / "Videos",
    USER_PROFILE / "Music",
    USER_PROFILE / "AppData" / "Roaming",
    USER_PROFILE / "AppData" / "Local",
    Path("C:/ProgramData"),
]

# Folders to skip inside AppData\Local (to avoid huge useless caches)
SKIP_FOLDERS = {
    "Temp", "Cache", "Caches", "Code Cache", "GPUCache",
    "ShaderCache", "Temporary Internet Files", "INetCache"
}


def create_zip(zip_path: Path):
    logging.info("Creating backup zip...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for folder in FOLDERS_TO_BACKUP:
            if not folder.exists():
                logging.warning(f"Folder not found, skipping: {folder}")
                continue

            for root, dirs, files in os.walk(folder):
                # Skip unwanted cache folders
                dirs[:] = [d for d in dirs if d not in SKIP_FOLDERS]

                for file in files:
                    file_path = Path(root) / file
                    # Keep the original structure starting from C:/
                    arcname = str(file_path).replace("\\", "/").replace("C:/", "")
                    try:
                        zipf.write(file_path, arcname)
                    except Exception as e:
                        logging.warning(f"Could not add {file_path}: {e}")

    logging.info(f"Zip created: {zip_path}")


def upload_to_dropbox(local_zip: Path):
    logging.info("Uploading to Dropbox...")
    with open(local_zip, "rb") as f:
        dbx.files_upload(f.read(), LATEST_ZIP, mode=WriteMode("overwrite"))
    logging.info("Upload completed → /rdp-backups/latest_backup.zip")


def download_from_dropbox(local_zip: Path):
    logging.info("Downloading latest backup from Dropbox...")
    try:
        metadata, res = dbx.files_download(LATEST_ZIP)
        with open(local_zip, "wb") as f:
            f.write(res.content)
        logging.info("Download completed")
        return True
    except ApiError as e:
        if e.error.is_path() and e.error.get_path().is_not_found():
            logging.warning("No previous backup found on Dropbox")
            return False
        raise


def restore_from_zip(zip_path: Path):
    logging.info("Restoring files...")
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        for member in zipf.namelist():
            target = Path("C:/") / member
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with zipf.open(member) as source, open(target, "wb") as target_file:
                    shutil.copyfileobj(source, target_file)
            except Exception as e:
                logging.warning(f"Could not restore {member}: {e}")
    logging.info("Restore completed")


def main():
    temp_zip = Path("C:/temp_backup.zip")

    if MODE == "restore":
        if download_from_dropbox(temp_zip):
            restore_from_zip(temp_zip)
            temp_zip.unlink(missing_ok=True)
        else:
            logging.info("Starting with a clean environment")
    else:  # backup
        create_zip(temp_zip)
        upload_to_dropbox(temp_zip)
        temp_zip.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
