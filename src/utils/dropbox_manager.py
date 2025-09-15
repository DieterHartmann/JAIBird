"""
Dropbox integration for JAIBird Stock Trading Platform.
Handles uploading and managing SENS PDFs in Dropbox.
"""

import os
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

import dropbox
from dropbox.exceptions import AuthError, ApiError

from .config import get_config


logger = logging.getLogger(__name__)


class DropboxManagerError(Exception):
    """Custom exception for Dropbox manager errors."""
    pass


class DropboxManager:
    """Manages Dropbox operations for SENS PDF storage."""
    
    def __init__(self):
        self.config = get_config()
        self.dbx = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Dropbox client with authentication."""
        try:
            self.dbx = dropbox.Dropbox(self.config.dropbox_access_token)
            
            # Test the connection
            account_info = self.dbx.users_get_current_account()
            logger.info(f"Connected to Dropbox account: {account_info.email}")
            
        except AuthError as e:
            logger.error(f"Dropbox authentication failed: {e}")
            raise DropboxManagerError(f"Authentication failed: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize Dropbox client: {e}")
            raise DropboxManagerError(f"Initialization failed: {e}")
    
    def _ensure_folder_exists(self, folder_path: str):
        """Ensure a folder exists in Dropbox, create if it doesn't."""
        try:
            self.dbx.files_get_metadata(folder_path)
            logger.debug(f"Dropbox folder exists: {folder_path}")
        except ApiError as e:
            if e.error.is_path_not_found():
                try:
                    self.dbx.files_create_folder_v2(folder_path)
                    logger.info(f"Created Dropbox folder: {folder_path}")
                except ApiError as create_error:
                    logger.error(f"Failed to create Dropbox folder {folder_path}: {create_error}")
                    raise DropboxManagerError(f"Could not create folder: {create_error}")
            else:
                logger.error(f"Error checking Dropbox folder {folder_path}: {e}")
                raise DropboxManagerError(f"Folder check failed: {e}")
    
    def upload_pdf(self, local_path: str, sens_number: str, company_name: str) -> Optional[str]:
        """
        Upload a PDF file to Dropbox and return the Dropbox path.
        
        Args:
            local_path: Path to the local PDF file
            sens_number: SENS number for organizing files
            company_name: Company name for organizing files
            
        Returns:
            Dropbox path of uploaded file, or None if upload failed
        """
        try:
            local_file = Path(local_path)
            if not local_file.exists():
                logger.error(f"Local file does not exist: {local_path}")
                return None
            
            # Create organized folder structure: /JAIBird/SENS/YYYY/MM/
            current_date = datetime.now()
            year_folder = f"{self.config.dropbox_folder}{current_date.year}/"
            month_folder = f"{year_folder}{current_date.month:02d}/"
            
            # Ensure folders exist
            self._ensure_folder_exists(self.config.dropbox_folder.rstrip('/'))
            self._ensure_folder_exists(year_folder.rstrip('/'))
            self._ensure_folder_exists(month_folder.rstrip('/'))
            
            # Create filename with SENS number and company
            safe_company = "".join(c for c in company_name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_company = safe_company.replace(' ', '_')
            filename = f"SENS_{sens_number}_{safe_company}.pdf"
            dropbox_path = f"{month_folder}{filename}"
            
            # Check if file already exists
            try:
                existing_file = self.dbx.files_get_metadata(dropbox_path)
                logger.info(f"File already exists in Dropbox: {dropbox_path}")
                return dropbox_path
            except ApiError as e:
                if not e.error.is_path_not_found():
                    logger.error(f"Error checking existing file: {e}")
                    return None
            
            # Upload the file
            with open(local_file, 'rb') as f:
                file_content = f.read()
            
            # Upload in chunks if file is large (>150MB)
            file_size = len(file_content)
            if file_size > 150 * 1024 * 1024:  # 150MB
                logger.info(f"Large file detected ({file_size} bytes), using chunked upload")
                return self._upload_large_file(file_content, dropbox_path)
            else:
                # Regular upload for smaller files
                self.dbx.files_upload(
                    file_content,
                    dropbox_path,
                    mode=dropbox.files.WriteMode.overwrite,
                    autorename=False
                )
            
            logger.info(f"Successfully uploaded to Dropbox: {dropbox_path} ({file_size} bytes)")
            return dropbox_path
            
        except Exception as e:
            logger.error(f"Failed to upload {local_path} to Dropbox: {e}")
            return None
    
    def _upload_large_file(self, file_content: bytes, dropbox_path: str) -> Optional[str]:
        """Upload large files using chunked upload."""
        try:
            CHUNK_SIZE = 4 * 1024 * 1024  # 4MB chunks
            
            # Start upload session
            session_start_result = self.dbx.files_upload_session_start(
                file_content[:CHUNK_SIZE]
            )
            cursor = dropbox.files.UploadSessionCursor(
                session_id=session_start_result.session_id,
                offset=CHUNK_SIZE
            )
            
            # Upload remaining chunks
            while cursor.offset < len(file_content):
                chunk_end = min(cursor.offset + CHUNK_SIZE, len(file_content))
                chunk = file_content[cursor.offset:chunk_end]
                
                if chunk_end == len(file_content):
                    # Final chunk
                    commit = dropbox.files.CommitInfo(path=dropbox_path)
                    self.dbx.files_upload_session_finish(chunk, cursor, commit)
                else:
                    # Intermediate chunk
                    self.dbx.files_upload_session_append_v2(chunk, cursor)
                    cursor.offset = chunk_end
            
            logger.info(f"Large file uploaded successfully: {dropbox_path}")
            return dropbox_path
            
        except Exception as e:
            logger.error(f"Failed to upload large file: {e}")
            return None
    
    def download_pdf(self, dropbox_path: str, local_path: str) -> bool:
        """
        Download a PDF from Dropbox to local storage.
        
        Args:
            dropbox_path: Path to file in Dropbox
            local_path: Local path to save the file
            
        Returns:
            True if download successful, False otherwise
        """
        try:
            # Ensure local directory exists
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Download the file
            metadata, response = self.dbx.files_download(dropbox_path)
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"Downloaded from Dropbox: {dropbox_path} -> {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download {dropbox_path}: {e}")
            return False
    
    def list_files(self, folder_path: str = None) -> List[dict]:
        """
        List files in a Dropbox folder.
        
        Args:
            folder_path: Dropbox folder path (defaults to SENS folder)
            
        Returns:
            List of file information dictionaries
        """
        if folder_path is None:
            folder_path = self.config.dropbox_folder.rstrip('/')
        
        try:
            files = []
            result = self.dbx.files_list_folder(folder_path, recursive=True)
            
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    files.append({
                        'name': entry.name,
                        'path': entry.path_display,
                        'size': entry.size,
                        'modified': entry.client_modified,
                        'content_hash': entry.content_hash
                    })
            
            # Handle pagination
            while result.has_more:
                result = self.dbx.files_list_folder_continue(result.cursor)
                for entry in result.entries:
                    if isinstance(entry, dropbox.files.FileMetadata):
                        files.append({
                            'name': entry.name,
                            'path': entry.path_display,
                            'size': entry.size,
                            'modified': entry.client_modified,
                            'content_hash': entry.content_hash
                        })
            
            logger.info(f"Listed {len(files)} files in {folder_path}")
            return files
            
        except Exception as e:
            logger.error(f"Failed to list files in {folder_path}: {e}")
            return []
    
    def delete_file(self, dropbox_path: str) -> bool:
        """
        Delete a file from Dropbox.
        
        Args:
            dropbox_path: Path to file in Dropbox
            
        Returns:
            True if deletion successful, False otherwise
        """
        try:
            self.dbx.files_delete_v2(dropbox_path)
            logger.info(f"Deleted from Dropbox: {dropbox_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {dropbox_path}: {e}")
            return False
    
    def get_file_info(self, dropbox_path: str) -> Optional[dict]:
        """
        Get information about a file in Dropbox.
        
        Args:
            dropbox_path: Path to file in Dropbox
            
        Returns:
            File information dictionary or None if not found
        """
        try:
            metadata = self.dbx.files_get_metadata(dropbox_path)
            if isinstance(metadata, dropbox.files.FileMetadata):
                return {
                    'name': metadata.name,
                    'path': metadata.path_display,
                    'size': metadata.size,
                    'modified': metadata.client_modified,
                    'content_hash': metadata.content_hash
                }
        except Exception as e:
            logger.error(f"Failed to get info for {dropbox_path}: {e}")
        
        return None
    
    def create_shared_link(self, dropbox_path: str) -> Optional[str]:
        """
        Create a shared link for a file in Dropbox.
        
        Args:
            dropbox_path: Path to file in Dropbox
            
        Returns:
            Shared link URL or None if creation failed
        """
        try:
            # Check if shared link already exists
            try:
                existing_links = self.dbx.sharing_list_shared_links(path=dropbox_path)
                if existing_links.links:
                    return existing_links.links[0].url
            except:
                pass  # No existing links, create new one
            
            # Create new shared link
            shared_link = self.dbx.sharing_create_shared_link_with_settings(dropbox_path)
            logger.info(f"Created shared link for {dropbox_path}")
            return shared_link.url
            
        except Exception as e:
            logger.error(f"Failed to create shared link for {dropbox_path}: {e}")
            return None
    
    def get_storage_usage(self) -> dict:
        """Get Dropbox storage usage information."""
        try:
            usage = self.dbx.users_get_space_usage()
            return {
                'used': usage.used,
                'allocated': usage.allocation.get_individual().allocated if hasattr(usage.allocation, 'get_individual') else 0,
                'used_gb': round(usage.used / (1024**3), 2),
                'allocated_gb': round(usage.allocation.get_individual().allocated / (1024**3), 2) if hasattr(usage.allocation, 'get_individual') else 0
            }
        except Exception as e:
            logger.error(f"Failed to get storage usage: {e}")
            return {'error': str(e)}
