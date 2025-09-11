"""Test helpers for vault-based testing - Testcontainers version.

This module provides simplified helper functions for testing with Testcontainers.
Most functionality is now handled by conftest.py fixtures.
"""

from typing import List


# Legacy function names for backward compatibility - these will be simplified
# since Testcontainers provides predictable test data


def check_vault_available() -> bool:
    """
    Legacy helper - with Testcontainers, vault is always available during tests.
    Keep for backward compatibility but always return True in fixture context.
    """
    return True


def should_skip_aws_test() -> bool:
    """
    Legacy helper - with Testcontainers, AWS test data is always available.
    Keep for backward compatibility but always return False.
    """
    return False


def should_skip_azure_test() -> bool:
    """
    Legacy helper - with Testcontainers, Azure test data is always available.
    Keep for backward compatibility but always return False.
    """
    return False


def get_available_providers_from_vault() -> List[str]:
    """
    Legacy helper - with Testcontainers, providers are managed by fixtures.
    This function is mainly for documentation.
    """
    return ["aws", "azure"]  # Known test data providers
