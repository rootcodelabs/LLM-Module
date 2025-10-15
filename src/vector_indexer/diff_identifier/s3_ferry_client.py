"""S3Ferry client for file transfer operations."""

import json
import tempfile
import time
from typing import Any, Dict, Optional
import requests
from loguru import logger

from diff_identifier.diff_models import DiffConfig, DiffError
from constants import GET_S3_FERRY_PAYLOAD


class S3Ferry:
    """Client for interacting with S3Ferry service."""
    
    def __init__(self, url: str):
        self.url = url
    
    def transfer_file(self, destinationFilePath: str, destinationStorageType: str, sourceFilePath: str, sourceStorageType: str) -> requests.Response:  # noqa: N803
        """
        Transfer file using S3Ferry service.
        
        Args:
            destinationFilePath: Path where file should be stored
            destinationStorageType: "S3" or "FS" (filesystem)
            sourceFilePath: Path of source file  
            sourceStorageType: "S3" or "FS" (filesystem)
            
        Returns:
            requests.Response: Response from S3Ferry service
        """
        payload = GET_S3_FERRY_PAYLOAD(destinationFilePath, destinationStorageType, sourceFilePath, sourceStorageType)
        response = requests.post(self.url, json=payload)
        return response


class S3FerryClient:
    """High-level client for S3Ferry operations with metadata handling.
    
    S3Ferry service handles all S3 configuration internally.
    This client only needs to know the S3Ferry URL and metadata paths.
    """
    
    def __init__(self, config: DiffConfig):
        self.config = config
        self.s3_ferry = S3Ferry(config.s3_ferry_url)
        
    async def __aenter__(self):
        """Async context manager entry."""
        return self
        
    async def __aexit__(self, exc_type: Optional[type], exc_val: Optional[BaseException], exc_tb: Optional[object]) -> None:
        """Async context manager exit."""
        pass
        
    def upload_metadata(self, metadata: Dict[str, Any]) -> bool:
        """
        Upload metadata to S3 via S3Ferry.
        
        Args:
            metadata: Dictionary containing metadata to upload
            
        Returns:
            True if successful, False otherwise
            
        Raises:
            DiffError: If upload fails
        """
        try:
            # Create temporary file with metadata
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                json.dump(metadata, temp_file, indent=2)
                temp_file_path = temp_file.name
            
            try:
                # Transfer from FS to S3 using S3Ferry
                response = self._retry_with_backoff(
                    lambda: self.s3_ferry.transfer_file(
                        destinationFilePath=self.config.metadata_s3_path,
                        destinationStorageType="S3",
                        sourceFilePath=temp_file_path,
                        sourceStorageType="FS"
                    )
                )
                
                if response.status_code == 200:
                    logger.info(f"Metadata uploaded successfully to {self.config.metadata_s3_path}")
                    return True
                else:
                    logger.error(f"S3Ferry upload failed: {response.status_code} - {response.text}")
                    return False
                    
            finally:
                # Clean up temporary file
                import os
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}")
                
        except Exception as e:
            raise DiffError(f"Failed to upload metadata: {str(e)}", e)
    
    def download_metadata(self) -> Optional[Dict[str, Any]]:
        """
        Download metadata from S3 via S3Ferry.
        
        Returns:
            Dict containing metadata or None if not found
            
        Raises:
            DiffError: If download fails (except for file not found)
        """
        try:
            # Create temporary file for download
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_file:
                temp_file_path = temp_file.name
            
            try:
                # Transfer from S3 to FS using S3Ferry
                response = self._retry_with_backoff(
                    lambda: self.s3_ferry.transfer_file(
                        destinationFilePath=temp_file_path,
                        destinationStorageType="FS",
                        sourceFilePath=self.config.metadata_s3_path,
                        sourceStorageType="S3"
                    )
                )
                
                if response.status_code == 200:
                    # Read metadata from downloaded file
                    with open(temp_file_path, 'r') as f:
                        metadata = json.load(f)
                    logger.info(f"Metadata downloaded successfully from {self.config.metadata_s3_path}")
                    return metadata
                elif response.status_code == 404:
                    logger.info("No previous metadata found - this appears to be the first run")
                    return None
                else:
                    logger.error(f"S3Ferry download failed: {response.status_code} - {response.text}")
                    return None
                    
            finally:
                # Clean up temporary file
                import os
                try:
                    os.unlink(temp_file_path)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup temp file {temp_file_path}: {cleanup_error}")
                
        except json.JSONDecodeError as e:
            raise DiffError(f"Failed to parse downloaded metadata JSON: {str(e)}", e)
        except Exception as e:
            # Don't raise for file not found - it's expected on first run
            logger.warning(f"Failed to download metadata (may be first run): {str(e)}")
            return None
    
    def _retry_with_backoff(self, operation: Any) -> requests.Response:
        """
        Retry an operation with exponential backoff.
        
        Args:
            operation: Operation to retry
            
        Returns:
            Response from the operation
            
        Raises:
            DiffError: If all retries fail
        """
        last_exception = None
        
        for attempt in range(self.config.max_retries):
            try:
                response = operation()
                
                # Consider non-2xx responses as failures for retry purposes
                if response.status_code >= 400:
                    if attempt == self.config.max_retries - 1:
                        return response  # Last attempt - return the error response
                    
                    delay = min(1 * (2 ** attempt), self.config.max_delay_seconds)
                    time.sleep(delay)
                    continue
                    
                return response
                
            except Exception as e:
                last_exception = e
                
                if attempt == self.config.max_retries - 1:
                    raise DiffError(f"Operation failed after {self.config.max_retries} attempts: {str(e)}", e)
                
                delay = min(1 * (2 ** attempt), self.config.max_delay_seconds)
                time.sleep(delay)
        
        # Should not reach here, but just in case
        raise DiffError(f"Operation failed after {self.config.max_retries} attempts: {str(last_exception)}", last_exception)