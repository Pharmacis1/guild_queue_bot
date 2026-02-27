import os
import pytest
from unittest.mock import patch, MagicMock
import logging

from logic.google_drive import GoogleDriveService, TOKEN_FILE

# Ensure environment variables won't randomly pass/fail tests based on local dev configs
@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "test_folder_123")
    monkeypatch.setattr("logic.google_drive.TOKEN_FILE", "fake_token.json")
    monkeypatch.setattr("os.path.exists", MagicMock(return_value=False))

# --- Authentication Tests ---

def test_auth_no_token_file(monkeypatch, caplog):
    with patch("os.path.exists", return_value=False):
        with caplog.at_level(logging.ERROR):
            service = GoogleDriveService()
            assert service.service is None
            assert "No valid token.json found" in caplog.text

def test_auth_invalid_token_no_refresh(monkeypatch, caplog):
    # Simulate token exists but is invalid and cannot be refreshed
    with patch("os.path.exists", return_value=True):
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = None
        
        with patch("logic.google_drive.Credentials.from_authorized_user_file", return_value=mock_creds):
            with caplog.at_level(logging.ERROR):
                service = GoogleDriveService()
                assert service.service is None
                assert "No valid token.json found" in caplog.text

def test_auth_expired_token_successful_refresh(monkeypatch):
    with patch("os.path.exists", return_value=True):
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "some_refresh_token"
        mock_creds.refresh = MagicMock()
        
        with patch("logic.google_drive.Credentials.from_authorized_user_file", return_value=mock_creds):
            with patch("logic.google_drive.build", return_value="mock_build_service"):
                service = GoogleDriveService()
                mock_creds.refresh.assert_called_once()
                assert service.service == "mock_build_service"

def test_auth_expired_token_failed_refresh(monkeypatch, caplog):
    with patch("os.path.exists", return_value=True):
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "some_refresh_token"
        
        # Make refresh() throw an exception
        mock_creds.refresh.side_effect = Exception("Network Error")
        
        with patch("logic.google_drive.Credentials.from_authorized_user_file", return_value=mock_creds):
            with caplog.at_level(logging.ERROR):
                service = GoogleDriveService()
                assert service.service is None
                assert "Error refreshing token: Network Error" in caplog.text

def test_auth_valid_token(monkeypatch):
    with patch("os.path.exists", return_value=True):
        mock_creds = MagicMock()
        mock_creds.valid = True
        
        with patch("logic.google_drive.Credentials.from_authorized_user_file", return_value=mock_creds):
            with patch("logic.google_drive.build", return_value="mock_build_service"):
                service = GoogleDriveService()
                assert service.service == "mock_build_service"

def test_auth_unexpected_exception(monkeypatch, caplog):
    with patch("os.path.exists", return_value=True):
        with patch("logic.google_drive.Credentials.from_authorized_user_file", side_effect=Exception("Disk Error")):
            with caplog.at_level(logging.ERROR):
                service = GoogleDriveService()
                assert service.service is None
                assert "Failed to authenticate with Google Drive: Disk Error" in caplog.text

# --- Upload Tests ---

@pytest.fixture
def logged_in_service():
    with patch("logic.google_drive.GoogleDriveService._authenticate", return_value="mock_build_service"):
        return GoogleDriveService()

def test_upload_missing_service():
    with patch("logic.google_drive.GoogleDriveService._authenticate", return_value=None):
        service = GoogleDriveService()
        assert service.upload_file("test.db") is False

def test_upload_missing_folder_id(logged_in_service):
    logged_in_service.folder_id = None
    assert logged_in_service.upload_file("test.db") is False
    
    logged_in_service.folder_id = "replace_with_your_folder_id"
    assert logged_in_service.upload_file("test.db") is False

def test_upload_file_not_found(logged_in_service):
    with patch("os.path.exists", return_value=False):
        assert logged_in_service.upload_file("missing.db") is False

def test_upload_successful(logged_in_service):
    # Mock os.path.exists specifically for the target file
    def mock_exists(path):
        return path == "target.db"
    
    with patch("os.path.exists", side_effect=mock_exists):
        with patch("logic.google_drive.MediaFileUpload", return_value="mock_media"):
            
            # Create a Deep Mock chain: self.service.files().create().execute() -> {"id": "123"}
            mock_execute = MagicMock(return_value={"id": "uploaded_id_123"})
            mock_create = MagicMock(return_value=MagicMock(execute=mock_execute))
            mock_files = MagicMock(return_value=MagicMock(create=mock_create))
            
            logged_in_service.service = MagicMock(files=mock_files)
            
            result = logged_in_service.upload_file("target.db")
            assert result is True
            mock_create.assert_called_once()
            args, kwargs = mock_create.call_args
            assert kwargs["body"]["name"] == "target.db"
            assert kwargs["body"]["parents"] == ["test_folder_123"]
            assert kwargs["media_body"] == "mock_media"

def test_upload_exception(logged_in_service, caplog):
    def mock_exists(path):
        return path == "target.db"
        
    with patch("os.path.exists", side_effect=mock_exists):
        with patch("logic.google_drive.MediaFileUpload", return_value="mock_media"):
            
            mock_create = MagicMock(side_effect=Exception("API Quota Exceeded"))
            mock_files = MagicMock(return_value=MagicMock(create=mock_create))
            logged_in_service.service = MagicMock(files=mock_files)
            
            with caplog.at_level(logging.ERROR):
                result = logged_in_service.upload_file("target.db")
                assert result is False
                assert "Error uploading file to Google Drive: API Quota Exceeded" in caplog.text
