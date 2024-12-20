import os
import base64
import re
import csv
from datetime import datetime
from email.message import EmailMessage
from bs4 import BeautifulSoup

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)
    return service

def search_job_emails(service, query="subject:(application OR applied OR applying)"):
    query = '("thank you for applying" OR "application received" OR "thanks for applying" OR "thanks for your interest in") newer_than:365d'
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])
    return messages

def get_email_content(service, msg_id):
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    payload = msg.get('payload', {})
    headers = payload.get('headers', [])

    subject = ''
    sender = ''
    date = ''
    for header in headers:
        name = header.get('name')
        value = header.get('value')
        if name.lower() == 'subject':
            subject = value
        elif name.lower() == 'from':
            sender = value
        elif name.lower() == 'date':
            date = value

    parts = payload.get('parts', [])
    body = ''
    if parts:
        # Try text/plain part first
        for part in parts:
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                    break
        # If no text/plain found, try text/html
        if not body:
            for part in parts:
                if part.get('mimeType') == 'text/html':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        html = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                        soup = BeautifulSoup(html, 'html.parser')
                        body = soup.get_text(separator="\n").strip()
                        break
    else:
        # No parts, maybe directly in body
        data = payload.get('body', {}).get('data', '')
        if data:
            body = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')

    snippet = msg.get('snippet', '')
    return subject, sender, date, body, snippet

def classify_outcome(body_text):
    body_lower = body_text.lower()

    # Simple rules-based classification:
    # These can be customized or expanded to be more precise.
    if re.search(r'we regret to inform|unfortunately|not moving forward', body_lower):
        return "Rejected"
    elif re.search(r'schedule an interview|invite you to interview|looking forward to interviewing', body_lower):
        return "Interview"
    elif re.search(r'offer you the position|extend an offer|congratulations on your offer', body_lower):
        return "Offer"
    else:
        return "Unknown/No Decision"

def main():
    service = get_gmail_service()
    messages = search_job_emails(service)

    processed_ids = set()
    if os.path.exists('processed_ids.txt'):
        with open('processed_ids.txt', 'r') as f:
            processed_ids = set(line.strip() for line in f)

    file_exists = os.path.exists('job_applications.csv')
    with open('job_applications.csv', 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Date', 'Sender', 'Subject', 'Snippet', 'Outcome']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        for msg in messages:
            msg_id = msg['id']
            if msg_id in processed_ids:
                continue

            subject, sender, date, body, snippet = get_email_content(service, msg_id)
            outcome = classify_outcome(body)

            writer.writerow({
                'Date': date,
                'Sender': sender,
                'Subject': subject,
                'Snippet': snippet,
                'Outcome': outcome
            })

            processed_ids.add(msg_id)

    with open('processed_ids.txt', 'w') as f:
        for pid in processed_ids:
            f.write(pid + '\n')

if __name__ == '__main__':
    main()
