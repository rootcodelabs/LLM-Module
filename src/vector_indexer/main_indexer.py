"""Main vector indexer script for processing documents with contextual retrieval."""

import argparse
import asyncio
import shutil
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from loguru import logger

# Add src to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from vector_indexer.config.config_loader import ConfigLoader
from vector_indexer.document_loader import DocumentLoader
from vector_indexer.contextual_processor import ContextualProcessor
from vector_indexer.qdrant_manager import QdrantManager
from vector_indexer.error_logger import ErrorLogger
from vector_indexer.models import ProcessingStats, DocumentInfo
from vector_indexer.diff_identifier import DiffDetector, create_diff_config, DiffError


class VectorIndexer:
    """Main vector indexer orchestrating the full pipeline."""

    def __init__(self, config_path: Optional[str] = None, signed_url: Optional[str] = None):
        # Load configuration
        self.config_path = (
            config_path or "src/vector_indexer/config/vector_indexer_config.yaml"
        )
        self.config = ConfigLoader.load_config(self.config_path)
        
        # Store signed URL for future dataset download implementation
        self.signed_url = signed_url

        # Initialize components
        self.document_loader = DocumentLoader(self.config)
        self.error_logger = ErrorLogger(self.config)

        # Initialize API client
        from vector_indexer.api_client import LLMOrchestrationAPIClient

        self.api_client = LLMOrchestrationAPIClient(self.config)

        # Initialize contextual processor with all required arguments
        self.contextual_processor = ContextualProcessor(
            self.api_client, self.config, self.error_logger
        )

        # Processing statistics
        self.stats = ProcessingStats()

        logger.info(f"Vector Indexer initialized with config: {self.config_path}")
        logger.info(f"Dataset path: {self.config.dataset_base_path}")
        logger.info(f"Max concurrent documents: {self.config.max_concurrent_documents}")
        logger.info(
            f"Max concurrent chunks: {self.config.max_concurrent_chunks_per_doc}"
        )
        
        if self.signed_url:
            logger.info(f"Signed URL provided: {self.signed_url[:50]}...")  # Log first 50 chars only

    async def process_all_documents(self) -> ProcessingStats:
        """
        Process all documents in the dataset with contextual retrieval.

        Returns:
            ProcessingStats: Overall processing statistics
        """
        logger.info("=" * 60)
        logger.info("Starting Vector Indexer - Contextual Retrieval Pipeline")
        logger.info("=" * 60)

        self.stats.start_time = datetime.now()

        try:
            # Step 1: Dataset download (future implementation)
            if self.signed_url:
                logger.info("Dataset download URL provided - download logic to be implemented")
                # TODO: Implement dataset download and extraction
                # await self._download_and_extract_dataset(self.signed_url)
            
            # Step 2: Diff identification - determine what files need processing
            logger.info("Step 1: Identifying changed files...")
            try:
                diff_config = create_diff_config()
                diff_detector = DiffDetector(diff_config)
                diff_result = await diff_detector.get_changed_files()
                
                logger.info("Diff identification complete:")
                logger.info(f"  • Total files scanned: {diff_result.total_files_scanned}")
                logger.info(f"  • Previously processed: {diff_result.previously_processed_count}")
                logger.info(f"  • Files needing processing: {len(diff_result.new_files)}")
                logger.info(f"  • Is first run: {diff_result.is_first_run}")
                
                if not diff_result.new_files:
                    logger.info("No new or changed files detected. Processing complete.")
                    self._cleanup_datasets()
                    return self.stats
                    
            except DiffError as e:
                logger.error(f"Diff identification failed: {e}")
                logger.info("Continuing with full document discovery as fallback")
                diff_result = None
                diff_detector = None

            # Initialize Qdrant collections
            async with QdrantManager(self.config) as qdrant_manager:
                await qdrant_manager.ensure_collections_exist()

                # Step 3: Document discovery (filtered by diff results if available)
                logger.info("Step 2: Discovering documents...")
                if diff_result and diff_result.new_files:
                    # Filter documents to only those identified as changed
                    documents = self._filter_documents_by_paths(diff_result.new_files)
                else:
                    # Fallback: discover all documents
                    documents = self.document_loader.discover_all_documents()

                if not documents:
                    logger.warning("No documents found to process")
                    self._cleanup_datasets()
                    return self.stats

                logger.info(f"Found {len(documents)} documents to process")
                self.stats.total_documents = len(documents)

                # Process documents with controlled concurrency
                semaphore = asyncio.Semaphore(self.config.max_concurrent_documents)
                tasks: List[asyncio.Task[int]] = []

                for doc_info in documents:
                    task = asyncio.create_task(
                        self._process_single_document(
                            doc_info, qdrant_manager, semaphore
                        )
                    )
                    tasks.append(task)

                # Execute all document processing tasks
                logger.info(
                    f"Processing {len(tasks)} documents with max {self.config.max_concurrent_documents} concurrent"
                )
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Collect results and handle exceptions
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        doc_info = documents[i]
                        logger.error(
                            f"Document processing failed: {doc_info.document_hash} - {result}"
                        )
                        self.stats.documents_failed += 1
                        self.error_logger.log_document_failure(
                            doc_info.document_hash, str(result)
                        )
                    else:
                        # Result should be number of chunks processed
                        self.stats.documents_processed += 1
                        if isinstance(result, int):
                            self.stats.total_chunks_processed += result

                # Calculate final statistics
                self.stats.end_time = datetime.now()

                # Step 4: Update processed files tracking
                if diff_detector and documents:
                    try:
                        processed_paths = [doc.cleaned_txt_path for doc in documents]
                        if processed_paths:
                            await diff_detector.mark_files_processed(processed_paths)
                            logger.info("Updated processed files tracking")
                    except Exception as e:
                        logger.warning(f"Failed to update processed files tracking: {e}")

                # Log final statistics
                self.error_logger.log_processing_stats(self.stats)
                self._log_final_summary()

                # Step 5: Cleanup datasets folder after successful processing
                self._cleanup_datasets()

                return self.stats

        except Exception as e:
            logger.error(f"Critical error in vector indexer: {e}")
            self.stats.end_time = datetime.now()
            self.error_logger.log_processing_stats(self.stats)
            raise
        finally:
            # Clean up API client AFTER all processing is complete
            try:
                await self.api_client.close()
            except Exception as e:
                logger.warning(f"Error closing API client: {e}")

    async def _process_single_document(
        self,
        doc_info: DocumentInfo,
        qdrant_manager: QdrantManager,
        semaphore: asyncio.Semaphore,
    ) -> int:
        """
        Process a single document with contextual retrieval.

        Args:
            doc_info: Document information
            qdrant_manager: Qdrant manager instance
            semaphore: Concurrency control semaphore

        Returns:
            int: Number of chunks processed
        """
        async with semaphore:
            logger.info(f"Processing document: {doc_info.document_hash}")

            try:
                # Load document content
                document = self.document_loader.load_document(doc_info)

                if not document:
                    logger.warning(f"Could not load document: {doc_info.document_hash}")
                    return 0

                # Process document with contextual retrieval
                contextual_chunks = await self.contextual_processor.process_document(
                    document
                )

                if not contextual_chunks:
                    logger.warning(
                        f"No chunks created for document: {doc_info.document_hash}"
                    )
                    return 0

                # Store chunks in Qdrant
                await qdrant_manager.store_chunks(contextual_chunks)

                logger.info(
                    f"Successfully processed document {doc_info.document_hash}: "
                    f"{len(contextual_chunks)} chunks"
                )

                return len(contextual_chunks)

            except Exception as e:
                logger.error(f"Error processing document {doc_info.document_hash}: {e}")
                self.error_logger.log_document_failure(doc_info.document_hash, str(e))
                raise

    def _log_final_summary(self):
        """Log final processing summary."""

        logger.info("VECTOR INDEXER PROCESSING COMPLETE")

        logger.info("Processing Statistics:")
        logger.info(f"   • Total Documents: {self.stats.total_documents}")
        logger.info(f"   • Successful Documents: {self.stats.documents_processed}")
        logger.info(f"   • Failed Documents: {self.stats.documents_failed}")
        logger.info(f"   • Total Chunks: {self.stats.total_chunks_processed}")
        logger.info(f"   • Failed Chunks: {self.stats.total_chunks_failed}")

        if self.stats.total_documents > 0:
            success_rate = (
                self.stats.documents_processed / self.stats.total_documents
            ) * 100
            logger.info(f"   • Success Rate: {success_rate:.1f}%")

        logger.info(f"   • Processing Duration: {self.stats.duration}")

        if self.stats.documents_failed > 0:
            logger.warning(
                f"  {self.stats.documents_failed} documents failed processing"
            )
            logger.info("   Check failure logs for details")

    async def run_health_check(self) -> bool:
        """
        Run health check on all components.

        Returns:
            bool: True if all components are healthy
        """
        logger.info("Running Vector Indexer health check...")

        try:
            # Check Qdrant connection
            async with QdrantManager(self.config) as qdrant_manager:
                # Test basic Qdrant connectivity by trying to list collections
                try:
                    qdrant_url = getattr(
                        self.config, "qdrant_url", "http://localhost:6333"
                    )
                    response = await qdrant_manager.client.get(
                        f"{qdrant_url}/collections"
                    )
                    if response.status_code == 200:
                        logger.info(" Qdrant server: Connected")

                        # Check if collections exist, create them if they don't
                        collections_info = {}
                        for collection_name in qdrant_manager.collections_config.keys():
                            info = await qdrant_manager.get_collection_info(
                                collection_name
                            )
                            if info:
                                count = await qdrant_manager.count_points(
                                    collection_name
                                )
                                collections_info[collection_name] = count
                                logger.info(
                                    f" Qdrant collection '{collection_name}': {count} points"
                                )
                            else:
                                logger.info(
                                    f" Qdrant collection '{collection_name}': Not found (will be created automatically)"
                                )
                    else:
                        logger.error(
                            f" Qdrant server not accessible: {response.status_code}"
                        )
                        return False
                except Exception as e:
                    logger.error(f" Qdrant connection failed: {e}")
                    return False

            # Check API client connectivity
            api_healthy = await self.api_client.health_check()
            if api_healthy:
                logger.info(" LLM Orchestration Service API: Connected")
            else:
                logger.error(" LLM Orchestration Service API: Not accessible")
                return False

            # Check dataset path
            if Path(self.config.dataset_base_path).exists():
                logger.info(f" Dataset path: {self.config.dataset_base_path}")
            else:
                logger.error(
                    f" Dataset path not found: {self.config.dataset_base_path}"
                )
                return False

            logger.info(" All health checks passed!")
            return True

        except Exception as e:
            logger.error(f" Health check failed: {e}")
            return False
        # NOTE: Don't close API client here - it will be used by main processing

    async def cleanup(self):
        """Clean up resources."""
        try:
            await self.api_client.close()
            logger.debug("API client closed successfully")
        except Exception as e:
            logger.warning(f"Error closing API client: {e}")
    
    def _filter_documents_by_paths(self, file_paths: List[str]) -> List[DocumentInfo]:
        """
        Filter documents by specific file paths.
        
        Args:
            file_paths: List of file paths to process
            
        Returns:
            List of DocumentInfo for matching files
        """
        documents = []
        
        for file_path in file_paths:
            try:
                file_path_obj = Path(file_path)
                
                # Ensure this is a cleaned.txt file
                if file_path_obj.name != "cleaned.txt":
                    logger.debug(f"Skipping non-cleaned.txt file: {file_path}")
                    continue
                
                # Get hash directory and collection directory
                hash_dir = file_path_obj.parent
                collection_dir = hash_dir.parent
                
                # Check if metadata file exists
                metadata_file = hash_dir / self.config.metadata_file
                if not metadata_file.exists():
                    logger.warning(f"Skipping file without metadata: {file_path}")
                    continue
                
                # Create DocumentInfo
                doc_info = DocumentInfo(
                    document_hash=hash_dir.name,
                    cleaned_txt_path=str(file_path_obj),
                    source_meta_path=str(metadata_file),
                    dataset_collection=collection_dir.name
                )
                
                documents.append(doc_info)
                logger.debug(f"Added document: {doc_info.document_hash}")
                
            except Exception as e:
                logger.warning(f"Failed to process file path {file_path}: {e}")
                continue
        
        logger.info(f"Filtered to {len(documents)} documents from {len(file_paths)} paths")
        return documents
    
    def _cleanup_datasets(self):
        """Remove datasets folder after processing."""
        try:
            datasets_path = Path(self.config.dataset_base_path)
            if datasets_path.exists():
                shutil.rmtree(str(datasets_path))
                logger.info(f"Datasets folder cleaned up: {datasets_path}")
            else:
                logger.debug(f"Datasets folder does not exist: {datasets_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup datasets folder: {e}")
            # Non-critical error - don't fail the entire process


async def main():
    """Main entry point for the vector indexer."""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Vector Indexer with Diff Identification")
    parser.add_argument("--signed-url", help="Signed URL for dataset download")
    args = parser.parse_args()

    # Configure logging
    logger.remove()  # Remove default handler
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
    )

    # Add file logging
    logger.add(
        "vector_indexer.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
    )

    indexer = None
    try:
        # Initialize vector indexer with signed URL
        indexer = VectorIndexer(signed_url=args.signed_url)

        # Run health check first
        logger.info("Performing pre-processing health check...")
        health_ok = await indexer.run_health_check()

        if not health_ok:
            logger.error("Health check failed. Aborting processing.")
            await indexer.cleanup()
            sys.exit(1)

        # Process all documents
        logger.info("Health check passed. Starting document processing...")
        stats = await indexer.process_all_documents()

        # Exit with appropriate code
        if stats.documents_failed > 0:
            logger.warning(
                f"Processing completed with {stats.documents_failed} failures"
            )
            return 2  # Partial success
        else:
            logger.info("Processing completed successfully")
            return 0

    except KeyboardInterrupt:
        logger.info("Processing interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    finally:
        # Ensure cleanup happens
        if indexer:
            await indexer.cleanup()


if __name__ == "__main__":
    # Run the async main function and exit with the returned code
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
