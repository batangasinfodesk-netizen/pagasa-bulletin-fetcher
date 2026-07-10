import os
import io
import re
import sys
import requests
import pdfplumber
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

URL = "https://pubfiles.pagasa.dost.gov.ph/tamss/weather/bulletin/"
SCOPES = ["https://www.googleapis.com/auth/drive"]

ROOT_FOLDER_ID = (os.environ.get("GDRIVE_FOLDER_ID") or "").strip()
CLIENT_ID = os.environ.get("GDRIVE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GDRIVE_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GDRIVE_REFRESH_TOKEN")

if not all([ROOT_FOLDER_ID, CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
    print("Missing one or more required env vars: GDRIVE_FOLDER_ID, GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN")
    sys.exit(1)

_folder_cache = {}


def get_drive_service():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds)


def get_pdf_links():
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if href.lower().endswith(".pdf"):
            if href.startswith("http"):
                links.append(href)
            else:
                links.append(URL + href.lstrip("/"))
    return links


def extract_storm_name(filename):
    match = re.search(r"_([A-Za-z]+)\.pdf$", filename, re.IGNORECASE)
    if match:
        return match.group(1).capitalize()
    return "Unsorted"


def extract_year_from_pdf(content_bytes):
    try:
        with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
            text = ""
            for page in pdf.pages[:2]:
                page_text = page.extract_text() or ""
                text += page_text
                if text:
                    break
        match = re.search(r"\b(20\d{2})\b", text)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"WARNING: could not extract year from PDF text: {e}")
    return "Unknown Year"


def get_or_create_folder(drive, name, parent_id):
    cache_key = (parent_id, name)
    if cache_key in _folder_cache:
        return _folder_cache[cache_key]

    safe_name = name.replace("'", "\\'")
    query = (
        f"name = '{safe_name}' and '{parent_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    resp = drive.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    files = resp.get("files", [])
    if files:
        folder_id = files[0]["id"]
    else:
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = drive.files().create(body=metadata, fields="id").execute()
        folder_id = folder["id"]
        print(f"Created folder: {name} (under parent {parent_id})")

    _folder_cache[cache_key] = folder_id
    return folder_id


def file_exists_in_folder(drive, filename, folder_id):
    safe_name = filename.replace("'", "\\'")
    query = f"name = '{safe_name}' and '{folder_id}' in parents and trashed = false"
    resp = drive.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    return len(resp.get("files", [])) > 0


def upload_to_drive(drive, filename, content_bytes, folder_id):
    metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(content_bytes), mimetype="application/pdf", resumable=False)
    drive.files().create(body=metadata, media_body=media, fields="id").execute()


def verify_folder_access(drive):
    try:
        folder = drive.files().get(fileId=ROOT_FOLDER_ID, fields="id, name, mimeType").execute()
        print(f"DEBUG: Root folder found -> name={folder.get('name')!r}")
    except Exception as e:
        print(f"DEBUG: Could not access root folder with ID {ROOT_FOLDER_ID!r}: {e}")
        raise


def main():
    drive = get_drive_service()
    verify_folder_access(drive)
    links = get_pdf_links()
    print(f"Found {len(links)} PDF(s) on PAGASA page.")

    new_count = 0
    for link in links:
        fname = requests.utils.unquote(link.split("/")[-1])
        storm_name = extract_storm_name(fname)

        print(f"Downloading: {fname}")
        r = requests.get(link, timeout=30)
        r.raise_for_status()
        content = r.content

        year = extract_year_from_pdf(content)

        year_folder_id = get_or_create_folder(drive, year, ROOT_FOLDER_ID)
        storm_folder_id = get_or_create_folder(drive, storm_name, year_folder_id)

        if file_exists_in_folder(drive, fname, storm_folder_id):
            print(f"Already exists, skipping: {year}/{storm_name}/{fname}")
            continue

        upload_to_drive(drive, fname, content, storm_folder_id)
        print(f"Uploaded: {year}/{storm_name}/{fname}")
        new_count += 1

    print(f"Done. {new_count} new file(s) uploaded.")


if __name__ == "__main__":
    main()
