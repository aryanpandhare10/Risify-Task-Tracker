"""
One-time setup for the Audit section: lets the app store files in your
Google Drive, and prints the values to paste into the app's secrets.

    pip install google-auth-oauthlib
    python scripts/drive_auth.py path/to/client_secret.json

A browser window opens: sign in with the Google account whose Drive should
hold the audit documents, and allow access. The app only gets the
"drive.file" permission: it can see and change only the files and folders
it creates itself, nothing else in your Drive.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
    with open(path) as fh:
        client = json.load(fh)
    client = client.get("installed") or client.get("web")
    if not client:
        sys.exit("That file isn't an OAuth client file (expected a Desktop app client).")

    flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
    # prompt=consent makes Google return a refresh token even if you've
    # authorised this client before.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        sys.exit("Google didn't return a refresh token. Remove the app's access at "
                 "https://myaccount.google.com/permissions and run this again.")

    print("\nDone. Add this to the END of the app's secrets "
          "(Streamlit Cloud: Manage app -> Settings -> Secrets):\n")
    print("[google_drive]")
    print(f'client_id = "{client["client_id"]}"')
    print(f'client_secret = "{client["client_secret"]}"')
    print(f'refresh_token = "{creds.refresh_token}"')
    print('root_folder_name = "Risify Audit"')


if __name__ == "__main__":
    main()
