import os
import io
import json
import sys
import requests
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

URL = "https://pubfiles.pagasa.dost.gov.ph/tamss/weather/bulletin/"
SCOPES = ["https://www.googleapis.com/auth/drive"]

FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID")
SA_JSON = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")

if not FOLDER_ID or not SA_JSON:
    print("Missing GDRIVE_FOLDER_ID or GDRIVE_SERVICE_ACCOUNT_JSON env vars.")
    sys.exit(1)


def get_drive_service():
    info = json.loads(SA_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


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
