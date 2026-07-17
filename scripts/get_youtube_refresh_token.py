"""Run this ONCE, on your own computer (needs a real browser + your YouTube login).

It walks you through Google's OAuth consent screen, then prints a refresh
token. Paste that into the YT_REFRESH_TOKEN secret in GitHub — the automated
pipeline uses it forever after, with no further login needed.

Usage:
    pip install google-auth-oauthlib
    python get_youtube_refresh_token.py <YOUR_CLIENT_ID> <YOUR_CLIENT_SECRET>
"""
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    if len(sys.argv) != 3:
        print("Usage: python get_youtube_refresh_token.py <CLIENT_ID> <CLIENT_SECRET>")
        sys.exit(1)
    client_id, client_secret = sys.argv[1], sys.argv[2]

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)
    print("\n\n=== Save this as the YT_REFRESH_TOKEN secret in GitHub ===\n")
    print(creds.refresh_token)
    print("\n===========================================================\n")


if __name__ == "__main__":
    main()
