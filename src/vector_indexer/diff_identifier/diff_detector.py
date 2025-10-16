"""Main diff detector for identifying changed files."""

import os
from pathlib import Path
from typing import List
from loguru import logger

from diff_identifier.diff_models import DiffConfig, DiffError, DiffResult
from diff_identifier.version_manager import VersionManager


class DiffDetector:
    """Main orchestrator for diff identification."""
    
    def __init__(self, config: DiffConfig):
        self.config = config
        self.version_manager = VersionManager(config)
        
    async def get_changed_files(self) -> DiffResult:
        """
        Get list of files that need processing.
        
        Returns:
            DiffResult with files to process and metadata
            
        Raises:
            DiffError: If diff detection fails critically
        """
        try:
            logger.info("Starting diff identification process...")
            
            # Check if DVC is initialized
            if not self.version_manager.is_dvc_initialized():
                logger.info("DVC not initialized - setting up for first run")
                return await self._handle_first_run()
            
            # Get previously processed files
            logger.info("Loading processed files metadata...")
            processed_state = await self.version_manager.get_processed_files_metadata()
            
            # Scan current files
            logger.info("Scanning current dataset files...")
            current_files = self.version_manager.scan_current_files()
            
            if not current_files:
                logger.info("No files found in datasets directory")
                return DiffResult(
                    new_files=[],
                    total_files_scanned=0,
                    previously_processed_count=0 if processed_state is None else processed_state.total_processed,
                    is_first_run=False
                )
            
            # Identify changed files
            changed_file_paths = self.version_manager.identify_changed_files(current_files, processed_state)
            
            result = DiffResult(
                new_files=list(changed_file_paths),
                total_files_scanned=len(current_files),
                previously_processed_count=0 if processed_state is None else processed_state.total_processed,
                is_first_run=processed_state is None
            )
            
            logger.info(f"Diff identification complete: {len(result.new_files)} files need processing")
            return result
            
        except Exception as e:
            # Log error but don't fail - fall back to processing all files
            logger.error(f"Diff identification failed: {e}")
            logger.info("Falling back to processing all files as safety measure")
            
            try:
                # Get all files as fallback
                current_files = self.version_manager.scan_current_files()
                return DiffResult(
                    new_files=list(current_files.values()),
                    total_files_scanned=len(current_files),
                    previously_processed_count=0,
                    is_first_run=True
                )
            except Exception as fallback_error:
                raise DiffError(f"Both diff identification and fallback failed: {fallback_error}", e)
    
    async def mark_files_processed(self, processed_file_paths: List[str]) -> None:
        """
        Mark files as successfully processed.
        
        Args:
            processed_file_paths: List of file paths that were processed successfully
            
        Raises:
            DiffError: If marking files fails
        """
        try:
            if not processed_file_paths:
                logger.info("No files to mark as processed")
                return
            
            logger.info(f"Marking {len(processed_file_paths)} files as processed...")
            
            # Calculate hashes for processed files
            processed_files = {}
            for file_path in processed_file_paths:
                try:
                    full_path = Path(file_path)
                    if full_path.exists():
                        content = full_path.read_bytes()
                        import hashlib
                        file_hash = hashlib.sha256(content).hexdigest()
                        processed_files[file_hash] = file_path
                        logger.debug(f"Processed: {file_path} -> {file_hash[:12]}...")
                    else:
                        logger.warning(f"Processed file not found: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to hash processed file {file_path}: {e}")
            
            if not processed_files:
                logger.warning("No valid processed files to record")
                return
            
            # Update metadata
            await self.version_manager.update_processed_files_metadata(processed_files)
            
            # Commit to DVC if initialized
            if self.version_manager.is_dvc_initialized():
                await self.version_manager.commit_dvc_changes()
            
            logger.info(f"Successfully marked {len(processed_files)} files as processed")
            
        except Exception as e:
            raise DiffError(f"Failed to mark files as processed: {str(e)}", e)
    
    async def _handle_first_run(self) -> DiffResult:
        """
        Handle first run setup.
        
        Returns:
            DiffResult for first run
            
        Raises:
            DiffError: If first run setup fails
        """
        try:
            logger.info("Setting up DVC for first run...")
            
            # Initialize DVC
            await self.version_manager.initialize_dvc()
            
            # Get all files for processing
            current_files = self.version_manager.scan_current_files()
            
            logger.info(f"First run setup complete: {len(current_files)} files to process")
            
            return DiffResult(
                new_files=list(current_files.values()),
                total_files_scanned=len(current_files),
                previously_processed_count=0,
                is_first_run=True
            )
            
        except Exception as e:
            raise DiffError(f"First run setup failed: {str(e)}", e)


def create_diff_config() -> DiffConfig:
    """
    Create DiffConfig from environment variables.
    
    Hybrid approach:
    - S3Ferry handles metadata operations (processed files tracking)
    - DVC needs direct S3 access for version control operations
    
    Returns:
        DiffConfig instance
        
    Raises:
        DiffError: If required environment variables are missing
    """
    try:
        # S3Ferry Configuration
        s3_ferry_url = os.getenv("S3_FERRY_URL", "http://rag-s3-ferry:3000/v1/files/copy")
        
        # Path configurations
        datasets_path = os.getenv("DATASETS_PATH", "datasets")
        metadata_filename = os.getenv("METADATA_FILENAME", "processed-metadata.json")
        
        # S3 configuration (required for DVC operations)
        s3_bucket_name = "rag-search"
        s3_bucket_path = "resources"
        s3_endpoint_url = "http://minio:9000"
        s3_access_key_id = "minioadmin"
        s3_secret_access_key = "minioadmin"
        
        # Validate required S3 credentials for DVC
        if not all([s3_bucket_name, s3_endpoint_url, s3_access_key_id, s3_secret_access_key]):
            missing = [var for var, val in [
                ("S3_DATA_BUCKET_NAME", s3_bucket_name),
                ("S3_ENDPOINT_URL", s3_endpoint_url), 
                ("S3_ACCESS_KEY_ID", s3_access_key_id),
                ("S3_SECRET_ACCESS_KEY", s3_secret_access_key)
            ] if not val]
            raise DiffError(f"Missing required S3 environment variables for DVC: {', '.join(missing)}")
        
        # Build paths
        # S3Ferry is already configured with bucket context, so no need for s3_bucket_path prefix
        metadata_s3_path = f"datasets/{metadata_filename}"
        dvc_remote_url = f"s3://{s3_bucket_name}/{s3_bucket_path}/datasets/dvc-cache"
        
        config = DiffConfig(
            s3_ferry_url=s3_ferry_url,
            metadata_s3_path=metadata_s3_path,
            datasets_path=datasets_path,
            metadata_filename=metadata_filename,
            dvc_remote_url=dvc_remote_url,
            s3_endpoint_url=str(s3_endpoint_url),
            s3_access_key_id=str(s3_access_key_id),
            s3_secret_access_key=str(s3_secret_access_key)
        )
        
        logger.info("Diff configuration loaded successfully")
        logger.debug(f"S3Ferry URL: {config.s3_ferry_url}")
        logger.debug(f"Metadata S3 Path: {config.metadata_s3_path}") 
        logger.debug(f"DVC Remote URL: {config.dvc_remote_url}")
        logger.debug(f"Datasets Path: {config.datasets_path}")
        
        return config
        
    except Exception as e:
        raise DiffError(f"Failed to create diff configuration: {str(e)}", e)
