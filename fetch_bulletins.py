import os
import io
import sys
import requests
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

URL = "https://pubfiles.pagasa.dost.gov.ph/tamss/weather/bulletin/"
SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_URI = "https://oauth2.googleapis.com/token"

# .strip() guards against a stray trailing newline/whitespace in the secret,
# which produces a folder ID Drive can't resolve (looks like a 404 "File not found").
FOLDER_ID = (os.environ.get("GDRIVE_FOLDER_ID") or "").strip()
CLIENT_ID = os.environ.get("GDRIVE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GDRIVE_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GDRIVE_REFRESH_TOKEN")

REQUIRED = {
    "GDRIVE_FOLDER_ID": FOLDER_ID,
    "GDRIVE_CLIENT_ID": CLIENT_ID,
    "GDRIVE_CLIENT_SECRET": CLIENT_SECRET,
    "GDRIVE_REFRESH_TOKEN": REFRESH_TOKEN,
}
missing = [k for k, v in REQUIRED.items() if not v]
if missing:
    print(f"Missing required env var(s): {', '.join(missing)}")
    sys.exit(1)

if "drive.google.com" in FOLDER_ID or "/" in FOLDER_ID:
    print(
        "ERROR: GDRIVE_FOLDER_ID looks like a full URL, not a bare folder ID.\n"
        "Set the secret to only the ID segment from the folder URL "
        "(drive.google.com/drive/folders/<THIS_PART>)."
    )
    sys.exit(1)


def get_drive_service():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    creds.refresh(Request())  # exchange refresh token for a fresh access token
    return build("drive", "v3", credentials=creds)


def check_folder_access(drive):
    """Fail fast with a clear message if the folder ID is wrong or not
    accessible by this account, instead of a confusing error later."""
    try:
        meta = drive.files().get(fileId=FOLDER_ID, fields="id, name, mimeType").execute()
    except Exception as e:
        print(
            f"ERROR: Could not access folder ID '{FOLDER_ID}'.\n"
            "Check that:\n"
            "  1. GDRIVE_FOLDER_ID is just the ID from the folder URL "
            "(drive.google.com/drive/folders/<THIS_PART>), no extra whitespace\n"
            "  2. The folder belongs to (or is shared with) the Google account "
            "you authorized when generating the refresh token\n"
            f"Original error: {e}"
        )
        sys.exit(1)

    if meta.get("mimeType") != "application/vnd.google-apps.folder":
        print(f"ERROR: ID '{FOLDER_ID}' is not a folder (found: {meta.get('name')}).")
        sys.exit(1)

    print(f"Confirmed access to folder: {meta.get('name')} ({FOLDER_ID})")


def get_pdf_links():
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if href.lower().endswith(".pdf"):
            # handle both relative and absolute hrefs
            if href.startswith("http"):
                links.append(href)
            else:
                links.append(URL + href.lstrip("/"))
    return links


def get_existing_drive_filenames(drive):
    """List filenames already present in the target Drive folder."""
    existing = set()
    page_token = None
    query = f"'{FOLDER_ID}' in parents and trashed = false"
    while True:
        resp = drive.files().list(
            q=query,
            spaces="drive",
            fields="nextPageToken, files(id, name)",
            pageToken=page_token,
        ).execute()
        for f in resp.get("files", []):
            existing.add(f["name"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return existing


def upload_to_drive(drive, filename, content_bytes):
    metadata = {"name": filename, "parents": [FOLDER_ID]}
    media = MediaIoBaseUpload(io.BytesIO(content_bytes), mimetype="application/pdf", resumable=False)
    drive.files().create(body=metadata, media_body=media, fields="id").execute()


def main():
    drive = get_drive_service()
    check_folder_access(drive)
    existing = get_existing_drive_filenames(drive)
    links = get_pdf_links()

    print(f"Found {len(links)} PDF(s) on PAGASA page.")
    print(f"{len(existing)} file(s) already in Drive folder.")

    new_count = 0
    for link in links:
        fname = requests.utils.unquote(link.split("/")[-1])
        if fname in existing:
            continue
        print(f"Downloading: {fname}")
        r = requests.get(link, timeout=30)
        r.raise_for_status()
        upload_to_drive(drive, fname, r.content)
        print(f"Uploaded: {fname}")
        new_count += 1

    print(f"Done. {new_count} new file(s) uploaded.")


if __name__ == "__main__":
    main()
