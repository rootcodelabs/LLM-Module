#!/usr/bin/env python3
"""
Service Data Enrichment Script

This script receives service data, enriches it with LLM-generated context,
creates embeddings, and stores in Qdrant intent_collections.
"""

import sys
import json
import argparse
import asyncio
from loguru import logger

from intent_data_enrichment.models import ServiceData, EnrichedService, EnrichmentResult
from intent_data_enrichment.api_client import LLMAPIClient
from intent_data_enrichment.qdrant_manager import QdrantManager


def parse_arguments() -> ServiceData:
    """Parse command line arguments into ServiceData model."""
    parser = argparse.ArgumentParser(description="Service Data Enrichment")
    parser.add_argument("--service-id", type=str, required=True, help="Service ID")
    parser.add_argument("--name", type=str, required=True, help="Service name")
    parser.add_argument(
        "--description", type=str, required=True, help="Service description"
    )
    parser.add_argument("--examples-file", type=str, help="Path to examples JSON file")
    parser.add_argument("--entities-file", type=str, help="Path to entities JSON file")
    parser.add_argument("--ruuter-type", type=str, default="GET", help="Ruuter type")
    parser.add_argument(
        "--current-state", type=str, default="draft", help="Current state"
    )
    parser.add_argument(
        "--is-common",
        type=str,
        choices=["true", "false"],
        default="false",
        help="Is common service",
    )

    args = parser.parse_args()

    # Read and parse JSON arrays from files
    examples = []
    if args.examples_file:
        try:
            with open(args.examples_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    examples = json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read/parse examples file: {e}")

    entities = []
    if args.entities_file:
        try:
            with open(args.entities_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    entities = json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read/parse entities file: {e}")

    return ServiceData(
        service_id=args.service_id,
        name=args.name,
        description=args.description,
        examples=examples,
        entities=entities,
        ruuter_type=args.ruuter_type,
        current_state=args.current_state,
        is_common=args.is_common.lower() == "true",
    )


async def enrich_service(service_data: ServiceData) -> EnrichmentResult:
    """
    Main enrichment pipeline: generate context, create embedding, store in Qdrant.

    Args:
        service_data: Service data to enrich

    Returns:
        EnrichmentResult with success/failure information
    """
    try:
        # Step 1: Generate rich context using LLM
        logger.info("Step 1: Generating rich context with LLM")
        async with LLMAPIClient() as api_client:
            context = await api_client.generate_context(service_data)
            logger.success(f"Context generated: {len(context)} characters")

            # Step 2: Combine generated context with original metadata for embedding
            logger.info("Step 2: Combining context with original service metadata")
            combined_text_parts = [
                f"Service Name: {service_data.name}",
                f"Description: {service_data.description}",
            ]

            if service_data.examples:
                combined_text_parts.append(
                    f"Example Queries: {' | '.join(service_data.examples)}"
                )

            if service_data.entities:
                combined_text_parts.append(
                    f"Required Entities: {', '.join(service_data.entities)}"
                )

            # Add generated context last (enriched understanding)
            combined_text_parts.append(f"Enriched Context: {context}")

            combined_text = "\n".join(combined_text_parts)
            logger.info(f"Combined text length: {len(combined_text)} characters")

            # Step 3: Create embedding for combined text
            logger.info("Step 3: Creating embedding vector for combined text")
            embedding = await api_client.create_embedding(combined_text)
            logger.success(f"Embedding created: {len(embedding)}-dimensional vector")

        # Step 4: Prepare enriched service
        enriched_service = EnrichedService(
            id=service_data.service_id,
            name=service_data.name,
            description=service_data.description,
            examples=service_data.examples,
            entities=service_data.entities,
            context=context,
            embedding=embedding,
        )

        # Step 5: Store in Qdrant
        logger.info("Step 5: Storing in Qdrant")
        qdrant = QdrantManager()
        try:
            qdrant.connect()
            qdrant.ensure_collection()
            success = qdrant.upsert_service(enriched_service)
        finally:
            qdrant.close()

        if success:
            return EnrichmentResult(
                success=True,
                service_id=service_data.service_id,
                message=f"Service '{service_data.name}' enriched and indexed successfully",
                context_length=len(context),
                embedding_dimension=len(embedding),
                error=None,
            )
        else:
            return EnrichmentResult(
                success=False,
                service_id=service_data.service_id,
                message="Failed to store in Qdrant",
                context_length=None,
                embedding_dimension=None,
                error="Qdrant upsert operation failed",
            )

    except Exception as e:
        logger.error(f"Enrichment pipeline failed: {e}")
        return EnrichmentResult(
            success=False,
            service_id=service_data.service_id,
            message="Enrichment pipeline failed",
            context_length=None,
            embedding_dimension=None,
            error=str(e),
        )


def main() -> int:
    """Main entry point for service enrichment"""
    logger.info("Starting service data enrichment pipeline")

    try:
        # Parse arguments
        service_data = parse_arguments()
        logger.info(f"Service ID: {service_data.service_id}")
        logger.info(f"Service Name: {service_data.name}")
        logger.info(f"Examples: {len(service_data.examples)} provided")
        logger.info(f"Entities: {len(service_data.entities)} provided")

        # Run enrichment pipeline
        result = asyncio.run(enrich_service(service_data))

        # Log results
        if result.success:
            logger.success("Enrichment completed successfully")
            logger.info(f"Service: {result.service_id}")
            logger.info(f"Message: {result.message}")
            logger.info(f"Context Length: {result.context_length} characters")
            logger.info(f"Embedding Dimension: {result.embedding_dimension}")
            return 0
        else:
            logger.error("Enrichment failed")
            logger.error(f"Service: {result.service_id}")
            logger.error(f"Message: {result.message}")
            logger.error(f"Error: {result.error}")
            return 1

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
