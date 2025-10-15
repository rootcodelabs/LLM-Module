"""Version manager for DVC operations and metadata handling."""

import asyncio
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from loguru import logger

from diff_identifier.diff_models import DiffConfig, DiffError, ProcessedFileInfo, VersionState
from diff_identifier.s3_ferry_client import S3FerryClient


class VersionManager:
    """Manages DVC operations and version tracking."""
    
    def __init__(self, config: DiffConfig):
        self.config = config
        self.datasets_path = Path(config.datasets_path)
        
    async def __aenter__(self):
        """Async context manager entry."""
        return self
        
    async def __aexit__(self, exc_type: Optional[type], exc_val: Optional[BaseException], exc_tb: Optional[object]) -> None:
        """Async context manager exit."""
        pass
        
    def is_dvc_initialized(self) -> bool:
        """Check if DVC is initialized in datasets directory."""
        dvc_dir = self.datasets_path / ".dvc"
        return dvc_dir.exists() and dvc_dir.is_dir()
    
    async def initialize_dvc(self) -> None:
        """
        Initialize DVC in datasets directory with S3 remote.
        
        Raises:
            DiffError: If DVC initialization fails
        """
        try:
            logger.info("Initializing DVC in datasets directory...")
            
            # Ensure datasets directory exists
            self.datasets_path.mkdir(parents=True, exist_ok=True)
            
            # Change to datasets directory for DVC operations
            original_cwd = os.getcwd()
            os.chdir(str(self.datasets_path))
            
            try:
                # Initialize DVC (no SCM integration)
                await self._run_dvc_command(["dvc", "init", "--no-scm"])
                
                # Add S3 remote
                remote_url = self.config.dvc_remote_url
                logger.info(f"Adding DVC remote: {remote_url}")
                await self._run_dvc_command(["dvc", "remote", "add", "-d", "rag-storage", remote_url])
                
                # Configure S3 credentials
                await self._run_dvc_command([
                    "dvc", "remote", "modify", "rag-storage", "endpointurl", self.config.s3_endpoint_url
                ])
                await self._run_dvc_command([
                    "dvc", "remote", "modify", "rag-storage", "access_key_id", self.config.s3_access_key_id
                ])
                await self._run_dvc_command([
                    "dvc", "remote", "modify", "rag-storage", "secret_access_key", self.config.s3_secret_access_key
                ])
                
                logger.info("DVC initialized successfully")
                
            finally:
                os.chdir(original_cwd)
                
        except Exception as e:
            raise DiffError(f"Failed to initialize DVC: {str(e)}", e)
    
    async def get_processed_files_metadata(self) -> Optional[VersionState]:
        """
        Download and parse processed files metadata from S3.
        
        Returns:
            VersionState if metadata exists, None if first run
            
        Raises:
            DiffError: If metadata exists but cannot be parsed
        """
        try:
            async with S3FerryClient(self.config) as s3_client:
                metadata_dict = await s3_client.download_metadata()
                
                if metadata_dict is None:
                    return None
                
                # Parse metadata into VersionState
                return VersionState(
                    last_updated=metadata_dict["last_updated"],
                    processed_files={
                        file_hash: ProcessedFileInfo(**file_info) 
                        for file_hash, file_info in metadata_dict["processed_files"].items()
                    },
                    total_processed=metadata_dict.get("total_processed", len(metadata_dict["processed_files"]))
                )
                
        except Exception as e:
            raise DiffError(f"Failed to get processed files metadata: {str(e)}", e)
    
    async def update_processed_files_metadata(self, processed_files: Dict[str, str]) -> None:
        """
        Update processed files metadata and upload to S3.
        
        Args:
            processed_files: Dict mapping file hash to file path for newly processed files
            
        Raises:
            DiffError: If metadata update fails
        """
        try:
            # Get existing metadata or create new
            existing_state = await self.get_processed_files_metadata()
            
            if existing_state:
                processed_files_dict = existing_state.processed_files
            else:
                processed_files_dict = {}
            
            # Add new processed files
            current_time = datetime.now().isoformat()
            for file_hash, file_path in processed_files.items():
                file_stats = Path(file_path).stat()
                processed_files_dict[file_hash] = ProcessedFileInfo(
                    content_hash=file_hash,
                    original_path=file_path,
                    file_size=file_stats.st_size,
                    processed_at=current_time
                )
            
            # Create new version state
            new_state = VersionState(
                last_updated=current_time,
                processed_files=processed_files_dict,
                total_processed=len(processed_files_dict)
            )
            
            # Convert to dict for JSON serialization
            metadata_dict = {
                "last_updated": new_state.last_updated,
                "total_processed": new_state.total_processed,
                "processed_files": {
                    file_hash: {
                        "content_hash": file_info.content_hash,
                        "original_path": file_info.original_path,
                        "file_size": file_info.file_size,
                        "processed_at": file_info.processed_at
                    }
                    for file_hash, file_info in new_state.processed_files.items()
                }
            }
            
            # Upload to S3
            async with S3FerryClient(self.config) as s3_client:
                success = await s3_client.upload_metadata(metadata_dict)
                
                if not success:
                    raise DiffError("Failed to upload metadata to S3")
                
            logger.info(f"Updated processed files metadata: {len(processed_files)} new files")
            
        except Exception as e:
            raise DiffError(f"Failed to update processed files metadata: {str(e)}", e)
    
    def scan_current_files(self) -> Dict[str, str]:
        """
        Scan datasets directory and calculate file hashes.
        
        Returns:
            Dict mapping file hash to file path
            
        Raises:
            DiffError: If file scanning fails
        """
        try:
            files_map = {}
            
            if not self.datasets_path.exists():
                logger.warning(f"Datasets path does not exist: {self.datasets_path}")
                return files_map
            
            # Find all cleaned.txt files
            cleaned_files = list(self.datasets_path.glob("**/cleaned.txt"))
            logger.info(f"Found {len(cleaned_files)} files to scan")
            
            for cleaned_file in cleaned_files:
                try:
                    # Calculate file hash
                    content = cleaned_file.read_bytes()
                    file_hash = hashlib.sha256(content).hexdigest()
                    
                    # Store relative path from datasets directory
                    relative_path = str(cleaned_file.relative_to(self.datasets_path.parent))
                    files_map[file_hash] = relative_path
                    
                    logger.debug(f"Scanned file: {relative_path} -> {file_hash[:12]}...")
                    
                except Exception as e:
                    logger.warning(f"Failed to process file {cleaned_file}: {e}")
                    continue
            
            logger.info(f"Successfully scanned {len(files_map)} files")
            return files_map
            
        except Exception as e:
            raise DiffError(f"Failed to scan current files: {str(e)}", e)
    
    def identify_changed_files(self, current_files: Dict[str, str], processed_state: Optional[VersionState]) -> Set[str]:
        """
        Identify files that have changed or are new.
        
        Args:
            current_files: Current files map (hash -> path)
            processed_state: Previously processed state
            
        Returns:
            Set of file paths that need processing
        """
        if processed_state is None:
            # First run - all files are new
            logger.info("First run detected - all files need processing")
            return set(current_files.values())
        
        current_hashes = set(current_files.keys())
        processed_hashes = set(processed_state.processed_files.keys())
        
        # Find new files (hashes not previously processed)
        new_hashes = current_hashes - processed_hashes
        new_file_paths = {current_files[file_hash] for file_hash in new_hashes}
        
        logger.info(f"Found {len(new_file_paths)} new/changed files out of {len(current_files)} total")
        
        return new_file_paths
    
    async def commit_dvc_changes(self) -> None:
        """
        Commit current datasets state to DVC and push to remote.
        
        Raises:
            DiffError: If DVC operations fail
        """
        try:
            original_cwd = os.getcwd()
            os.chdir(str(self.datasets_path))
            
            try:
                # Add all files to DVC tracking
                logger.info("Adding files to DVC tracking...")
                await self._run_dvc_command(["dvc", "add", "."])
                
                # Push to remote storage
                logger.info("Pushing to DVC remote storage...")
                await self._run_dvc_command(["dvc", "push"])
                
                logger.info("DVC commit completed successfully")
                
            finally:
                os.chdir(original_cwd)
                
        except Exception as e:
            raise DiffError(f"Failed to commit DVC changes: {str(e)}", e)
    
    async def _run_dvc_command(self, command: List[str]) -> str:
        """
        Run DVC command asynchronously.
        
        Args:
            command: DVC command as list of strings
            
        Returns:
            Command output
            
        Raises:
            DiffError: If command fails
        """
        try:
            logger.debug(f"Running DVC command: {' '.join(command)}")
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                raise DiffError(f"DVC command failed: {' '.join(command)} - {error_msg}")
            
            output = stdout.decode().strip()
            logger.debug(f"DVC command output: {output}")
            
            return output
            
        except Exception as e:
            if isinstance(e, DiffError):
                raise
            raise DiffError(f"Failed to run DVC command {' '.join(command)}: {str(e)}", e)
