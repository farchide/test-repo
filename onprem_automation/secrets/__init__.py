"""
Secret Management

Provides secure secret management with support for:
- HashiCorp Vault
- AWS Secrets Manager
- Azure Key Vault
- Local encrypted storage
"""

from .manager import SecretManager, get_secret_manager
from .providers import (
    SecretProvider,
    VaultProvider,
    AWSSecretsProvider,
    AzureKeyVaultProvider,
    LocalSecretProvider,
)

__all__ = [
    "SecretManager",
    "get_secret_manager",
    "SecretProvider",
    "VaultProvider",
    "AWSSecretsProvider",
    "AzureKeyVaultProvider",
    "LocalSecretProvider",
]
