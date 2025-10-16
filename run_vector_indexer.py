#!/usr/bin/env python3
"""
Entry point script for Vector Indexer - Contextual Retrieval Pipeline

This script can be run directly or called by cron jobs for automated processing.

Usage:
    python run_vector_indexer.py [--config CONFIG_PATH] [--health-check] [--dry-run]

Examples:
    # Run with default config
    python run_vector_indexer.py

    # Run with custom config
    python run_vector_indexer.py --config /path/to/config.yaml

    # Health check only
    python run_vector_indexer.py --health-check

    # Dry run (validate without processing)
    python run_vector_indexer.py --dry-run
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.vector_indexer.main_indexer import VectorIndexer


async def main():
    """Main entry point with command line argument parsing."""

    parser = argparse.ArgumentParser(
        description="Vector Indexer - Contextual Retrieval Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--config",
        type=str,
        default="src/vector_indexer/config/vector_indexer_config.yaml",
        help="Path to configuration file (default: src/vector_indexer/config/vector_indexer_config.yaml)",
    )

    parser.add_argument(
        "--health-check", action="store_true", help="Run health check only and exit"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and connectivity without processing documents",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress non-error output"
    )

    args = parser.parse_args()

    # Configure logging level based on arguments
    log_level = "INFO"
    if args.verbose:
        log_level = "DEBUG"
    elif args.quiet:
        log_level = "ERROR"

    try:
        # Initialize vector indexer with specified config
        indexer = VectorIndexer(config_path=args.config)

        if args.health_check:
            # Health check only
            print("🔍 Running health check...")
            health_ok = await indexer.run_health_check()

            if health_ok:
                print("✅ Health check passed!")
                return 0
            else:
                print("❌ Health check failed!")
                return 1

        elif args.dry_run:
            # Dry run - validate without processing
            print("🧪 Running dry run validation...")

            health_ok = await indexer.run_health_check()
            if not health_ok:
                print("❌ Validation failed!")
                return 1

            # Discover documents but don't process
            documents = indexer.document_loader.discover_all_documents()
            print(f"📄 Found {len(documents)} documents ready for processing")
            print("✅ Dry run validation passed!")
            return 0

        else:
            # Full processing run
            print("🚀 Starting Vector Indexer processing...")

            # Health check first
            health_ok = await indexer.run_health_check()
            if not health_ok:
                print("❌ Pre-processing health check failed!")
                return 1

            # Process all documents
            stats = await indexer.process_all_documents()

            # Return appropriate exit code
            if stats.documents_failed > 0:
                print(f"⚠️  Processing completed with {stats.documents_failed} failures")
                return 2  # Partial success
            else:
                print("✅ Processing completed successfully!")
                return 0

    except KeyboardInterrupt:
        print("\n⏹️  Processing interrupted by user")
        return 130
    except FileNotFoundError as e:
        print(f"❌ Configuration file not found: {e}")
        return 1
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        return 1


def cron_entry_point():
    """
    Entry point specifically designed for cron jobs.

    This function:
    - Uses minimal output suitable for cron logs
    - Returns appropriate exit codes for monitoring
    - Handles errors gracefully for automated systems
    """
    import logging

    # Configure minimal logging for cron
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - Vector Indexer - %(levelname)s - %(message)s",
    )

    try:
        # Run with default configuration
        result = asyncio.run(main())

        if result == 0:
            logging.info("Vector indexer completed successfully")
        elif result == 2:
            logging.warning("Vector indexer completed with some failures")
        else:
            logging.error("Vector indexer failed")

        return result

    except Exception as e:
        logging.error(f"Vector indexer fatal error: {e}")
        return 1


if __name__ == "__main__":
    # Run the async main function
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
