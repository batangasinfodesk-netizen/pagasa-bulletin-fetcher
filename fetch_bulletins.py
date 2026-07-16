"""
Run this locally to generate a new GDRIVE_REFRESH_TOKEN.

1. pip install google-auth-oauthlib
2. Fill in CLIENT_ID and CLIENT_SECRET below (from Google Cloud Console > Clients > Desktop client 1)
3. Run: python get_refresh_token.py
4. A browser window will open - log in with the Google account that owns the Drive folder,
   and approve access.
5. The script will print a new refresh token. Copy it into the GDRIVE_REFRESH_TOKEN secret
   in GitHub (Settings > Secrets and variables > Actions).
"""

from google_auth_oauthlib.flow import InstalledAppFlow

# --- Fill these in ---
CLIENT_ID = "941704318073-l6e5rlgepajolsrr0jnvps3hhfmo82i2.apps.googleusercontent.com"
CLIENT_SECRET = "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"
# ----------------------

SCOPES = ["https://www.googleapis.com/auth/drive"]

CLIENT_CONFIG = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}


def main():
    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
    # access_type=offline + prompt=consent ensures Google issues a refresh token
    # even if this app has been authorized before.
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )

    print("\n" + "=" * 60)
    print("SUCCESS. Copy the refresh token below into your GDRIVE_REFRESH_TOKEN GitHub secret:")
    print("=" * 60)
    print(creds.refresh_token)
    print("=" * 60)


if __name__ == "__main__":
    main()
