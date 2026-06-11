import base64
import os
from datetime import datetime, timezone
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive",
]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

GOOGLE_DOC_EXPORT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


def _get_credentials() -> Credentials:
    if not os.path.exists(TOKEN_FILE):
        raise RuntimeError(
            'Google account not connected. Run: python -c "import google_services; '
            'google_services.setup_auth()" once, then restart the bot.'
        )
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError("Google credentials invalid. Re-run setup_auth().")
    return creds


def setup_auth() -> None:
    """One-time interactive setup - run manually from a terminal, NOT from the bot
    (opens a browser and blocks until you finish the consent flow)."""
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    print("Google account connected successfully.")


def _gmail():
    return build("gmail", "v1", credentials=_get_credentials())


def _calendar():
    return build("calendar", "v3", credentials=_get_credentials())


def _drive():
    return build("drive", "v3", credentials=_get_credentials())


# Gmail

def gmail_list_messages(max_results: int = 10, query: str = "") -> str:
    try:
        service = _gmail()
        results = service.users().messages().list(
            userId="me", maxResults=max_results, q=query
        ).execute()
        messages = results.get("messages", [])
        if not messages:
            return "No messages found."
        lines = []
        for msg in messages:
            full = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
            snippet = full.get("snippet", "")
            lines.append(
                f"{msg['id']} | From: {headers.get('From', '?')} | "
                f"Subject: {headers.get('Subject', '(no subject)')} | "
                f"Date: {headers.get('Date', '?')} | {snippet}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def _extract_gmail_body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        body = _extract_gmail_body(part)
        if body:
            return body
    return ""


def gmail_read_message(message_id: str) -> str:
    try:
        service = _gmail()
        msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        payload = msg.get("payload", {})
        headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
        body = _extract_gmail_body(payload)[:2000]
        return (
            f"From: {headers.get('From', '?')}\n"
            f"Subject: {headers.get('Subject', '(no subject)')}\n"
            f"Date: {headers.get('Date', '?')}\n\n"
            f"{body}"
        )
    except Exception as e:
        return f"Error: {e}"


def gmail_send_email(to: str, subject: str, body: str) -> str:
    try:
        service = _gmail()
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Email sent to {to} with subject '{subject}'"
    except Exception as e:
        return f"Error: {e}"


# Calendar

def calendar_list_events(max_results: int = 10) -> str:
    try:
        service = _calendar()
        now = datetime.now(timezone.utc).isoformat()
        results = service.events().list(
            calendarId="primary", timeMin=now, maxResults=max_results,
            singleEvents=True, orderBy="startTime",
        ).execute()
        events = results.get("items", [])
        if not events:
            return "No upcoming events found."
        lines = []
        for event in events:
            start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date"))
            end = event.get("end", {}).get("dateTime", event.get("end", {}).get("date"))
            lines.append(f"{event['id']} | {event.get('summary', '(no title)')} | {start} -> {end}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def calendar_create_event(summary: str, start: str, end: str, description: str = "") -> str:
    try:
        service = _calendar()
        event = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }
        created = service.events().insert(calendarId="primary", body=event).execute()
        return f"Event created: {created.get('summary')} ({start} -> {end})\n{created.get('htmlLink')}"
    except Exception as e:
        return f"Error: {e}"


# Drive

def drive_list_files(query: str = "", max_results: int = 10) -> str:
    try:
        service = _drive()
        results = service.files().list(
            q=query or None, pageSize=max_results, orderBy="modifiedTime desc",
            fields="files(id,name,mimeType,modifiedTime)",
        ).execute()
        files = results.get("files", [])
        if not files:
            return "No files found."
        return "\n".join(
            f"{f['id']} | {f['name']} | {f['mimeType']} | {f['modifiedTime']}"
            for f in files
        )
    except Exception as e:
        return f"Error: {e}"


def drive_read_file(file_id: str) -> str:
    try:
        service = _drive()
        meta = service.files().get(fileId=file_id, fields="mimeType,name").execute()
        mime_type = meta["mimeType"]
        if mime_type in GOOGLE_DOC_EXPORT_MIME:
            data = service.files().export(fileId=file_id, mimeType=GOOGLE_DOC_EXPORT_MIME[mime_type]).execute()
        else:
            data = service.files().get_media(fileId=file_id).execute()
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="replace")
        else:
            text = str(data)
        return f"{meta['name']}:\n{text[:3000]}"
    except Exception as e:
        return f"Error: {e}"


def drive_upload_file(name: str, content: str, mime_type: str = "text/plain") -> str:
    try:
        service = _drive()
        media = MediaInMemoryUpload(content.encode("utf-8"), mimetype=mime_type)
        created = service.files().create(body={"name": name}, media_body=media, fields="id,webViewLink").execute()
        return f"File created: {name}\n{created.get('webViewLink')}"
    except Exception as e:
        return f"Error: {e}"
