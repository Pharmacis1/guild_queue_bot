import logging
import os

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()

logger = logging.getLogger(__name__)

# Resolve paths relative to project root (assuming logic/ is one level deep)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCOPES = ['https://www.googleapis.com/auth/drive.file']
TOKEN_FILE = os.path.join(BASE_DIR, 'token.json')
CLIENT_SECRET_FILE = os.path.join(BASE_DIR, 'client_secret.json')

class GoogleDriveService:
    def __init__(self):
        self.service = self._authenticate()
        self.folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        
    def _authenticate(self):
        """Authenticates using the user's token.json."""
        creds = None
        try:
            # Load existing credentials
            if os.path.exists(TOKEN_FILE):
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            
            # If there are no (valid) credentials available, let the user know
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                    except Exception as e:
                        logger.error(f"Error refreshing token: {e}")
                        return None
                else:
                    logger.error("No valid token.json found. Please run scripts/auth_drive.py to authenticate.")
                    return None

            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Drive: {e}")
            return None

    def upload_file(self, file_path):
        """Uploads a file to the configured Google Drive folder."""
        if not self.service:
            logger.error("Google Drive service is not initialized.")
            return False
            
        if not self.folder_id or self.folder_id == "replace_with_your_folder_id":
            logger.error("GOOGLE_DRIVE_FOLDER_ID is not set in environment variables.")
            return False

        if not os.path.exists(file_path):
            logger.error(f"File to upload not found: {file_path}")
            return False

        try:
            file_name = os.path.basename(file_path)
            file_metadata = {
                'name': file_name,
                'parents': [self.folder_id]
            }
            
            media = MediaFileUpload(file_path, resumable=True)
            
            logger.info(f"Starting upload of {file_name} to Google Drive...")
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            logger.info(f"File uploaded successfully. File ID: {file.get('id')}")
            return True
        except Exception as e:
            logger.error(f"Error uploading file to Google Drive: {e}")
            return False
