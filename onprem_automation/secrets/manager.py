"""
Secret Manager

Unified interface for managing secrets across multiple providers.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Type
from dataclasses import dataclass

from .providers import (
    SecretProvider,
    Secret,
    SecretMetadata,
    VaultProvider,
    AWSSecretsProvider,
    AzureKeyVaultProvider,
    LocalSecretProvider,
)


@dataclass
class SecretReference:
    """Reference to a secret for use in configurations."""
    provider: str
    path: str
    key: Optional[str] = None  # For JSON secrets

    @classmethod
    def parse(cls, ref: str) -> "SecretReference":
        """
        Parse a secret reference string.

        Format: provider://path[#key]
        Examples:
            vault://secret/myapp/database#password
            aws://myapp/api-key
            local://credentials/admin
        """
        if "://" not in ref:
            return cls(provider="local", path=ref)

        provider, rest = ref.split("://", 1)
        if "#" in rest:
            path, key = rest.rsplit("#", 1)
        else:
            path, key = rest, None

        return cls(provider=provider, path=path, key=key)

    def __str__(self) -> str:
        result = f"{self.provider}://{self.path}"
        if self.key:
            result += f"#{self.key}"
        return result


class SecretCache:
    """In-memory cache for secrets with TTL."""

    def __init__(self, default_ttl: int = 300):
        self._cache: Dict[str, tuple[Secret, datetime]] = {}
        self._default_ttl = default_ttl
        self._logger = logging.getLogger("secrets.cache")

    def get(self, key: str) -> Optional[Secret]:
        """Get secret from cache if not expired."""
        if key in self._cache:
            secret, expires = self._cache[key]
            if datetime.utcnow() < expires:
                return secret
            else:
                del self._cache[key]
        return None

    def set(self, key: str, secret: Secret, ttl: Optional[int] = None) -> None:
        """Cache a secret with TTL."""
        expires = datetime.utcnow() + timedelta(seconds=ttl or self._default_ttl)
        self._cache[key] = (secret, expires)

    def invalidate(self, key: str) -> None:
        """Remove secret from cache."""
        if key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()

    def cleanup(self) -> int:
        """Remove expired entries and return count."""
        now = datetime.utcnow()
        expired = [k for k, (_, expires) in self._cache.items() if now >= expires]
        for key in expired:
            del self._cache[key]
        return len(expired)


class SecretManager:
    """
    Unified secret management across multiple providers.

    Example usage:
    ```python
    manager = SecretManager()

    # Configure providers
    manager.add_provider("vault", VaultProvider(
        url="https://vault.example.com",
        token="my-token"
    ))
    manager.add_provider("aws", AWSSecretsProvider(
        region="us-west-2"
    ))

    # Connect all providers
    await manager.connect_all()

    # Get secrets
    db_password = await manager.get_secret("vault://database/credentials#password")
    api_key = await manager.get_secret("aws://myapp/api-key")

    # Use in configurations
    config = await manager.resolve_secrets({
        "database": {
            "password": "${vault://database/credentials#password}"
        }
    })
    ```
    """

    def __init__(
        self,
        cache_ttl: int = 300,
        enable_cache: bool = True
    ):
        self._providers: Dict[str, SecretProvider] = {}
        self._cache = SecretCache(cache_ttl) if enable_cache else None
        self._logger = logging.getLogger("secrets.manager")
        self._default_provider: Optional[str] = None

    def add_provider(
        self,
        name: str,
        provider: SecretProvider,
        default: bool = False
    ) -> None:
        """Add a secret provider."""
        self._providers[name] = provider
        if default or not self._default_provider:
            self._default_provider = name
        self._logger.info(f"Added secret provider: {name}")

    def remove_provider(self, name: str) -> None:
        """Remove a secret provider."""
        if name in self._providers:
            del self._providers[name]
            if self._default_provider == name:
                self._default_provider = next(iter(self._providers), None)

    def get_provider(self, name: str) -> Optional[SecretProvider]:
        """Get a provider by name."""
        return self._providers.get(name)

    async def connect_all(self) -> Dict[str, bool]:
        """Connect all providers."""
        results = {}
        for name, provider in self._providers.items():
            results[name] = await provider.connect()
        return results

    async def disconnect_all(self) -> None:
        """Disconnect all providers."""
        for provider in self._providers.values():
            await provider.disconnect()

    async def get_secret(
        self,
        reference: str,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        Get a secret value by reference.

        Args:
            reference: Secret reference (e.g., "vault://path/to/secret#key")
            use_cache: Whether to use cache

        Returns:
            Secret value or None
        """
        ref = SecretReference.parse(reference)

        # Check cache first
        cache_key = str(ref)
        if use_cache and self._cache:
            cached = self._cache.get(cache_key)
            if cached:
                return self._extract_value(cached, ref.key)

        # Get from provider
        provider = self._providers.get(ref.provider)
        if not provider:
            self._logger.error(f"Unknown provider: {ref.provider}")
            return None

        secret = await provider.get_secret(ref.path)
        if not secret:
            return None

        # Cache the secret
        if self._cache:
            self._cache.set(cache_key, secret)

        return self._extract_value(secret, ref.key)

    def _extract_value(self, secret: Secret, key: Optional[str]) -> str:
        """Extract value from secret, optionally parsing as JSON."""
        if not key:
            return secret.value

        try:
            import json
            data = json.loads(secret.value)
            return data.get(key, "")
        except (json.JSONDecodeError, TypeError):
            return secret.value

    async def set_secret(
        self,
        reference: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store a secret.

        Args:
            reference: Secret reference
            value: Secret value
            metadata: Optional metadata

        Returns:
            True if successful
        """
        ref = SecretReference.parse(reference)

        provider = self._providers.get(ref.provider)
        if not provider:
            self._logger.error(f"Unknown provider: {ref.provider}")
            return False

        success = await provider.set_secret(ref.path, value, metadata)

        # Invalidate cache
        if success and self._cache:
            self._cache.invalidate(str(ref))

        return success

    async def delete_secret(self, reference: str) -> bool:
        """Delete a secret."""
        ref = SecretReference.parse(reference)

        provider = self._providers.get(ref.provider)
        if not provider:
            return False

        success = await provider.delete_secret(ref.path)

        if success and self._cache:
            self._cache.invalidate(str(ref))

        return success

    async def list_secrets(
        self,
        provider_name: Optional[str] = None,
        prefix: Optional[str] = None
    ) -> Dict[str, List[str]]:
        """List secrets from providers."""
        results = {}

        providers = (
            {provider_name: self._providers[provider_name]}
            if provider_name and provider_name in self._providers
            else self._providers
        )

        for name, provider in providers.items():
            results[name] = await provider.list_secrets(prefix)

        return results

    async def resolve_secrets(
        self,
        config: Dict[str, Any],
        secret_pattern: str = r"\$\{([^}]+)\}"
    ) -> Dict[str, Any]:
        """
        Resolve secret references in a configuration dictionary.

        Replaces ${provider://path#key} patterns with actual secret values.

        Args:
            config: Configuration dictionary
            secret_pattern: Regex pattern for secret references

        Returns:
            Configuration with resolved secrets
        """
        import re

        async def resolve_value(value: Any) -> Any:
            if isinstance(value, str):
                # Find all secret references
                matches = re.findall(secret_pattern, value)
                for match in matches:
                    secret_value = await self.get_secret(match)
                    if secret_value:
                        value = value.replace(f"${{{match}}}", secret_value)
                return value
            elif isinstance(value, dict):
                return {k: await resolve_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [await resolve_value(v) for v in value]
            else:
                return value

        return await resolve_value(config)

    async def rotate_secret(
        self,
        reference: str,
        new_value: str
    ) -> bool:
        """Rotate a secret with a new value."""
        ref = SecretReference.parse(reference)

        provider = self._providers.get(ref.provider)
        if not provider:
            return False

        success = await provider.rotate_secret(ref.path, new_value)

        if success and self._cache:
            self._cache.invalidate(str(ref))

        return success

    def invalidate_cache(self, reference: Optional[str] = None) -> None:
        """Invalidate cache entries."""
        if not self._cache:
            return

        if reference:
            self._cache.invalidate(reference)
        else:
            self._cache.clear()

    def get_status(self) -> Dict[str, Any]:
        """Get manager status."""
        return {
            "providers": {
                name: {
                    "connected": provider.is_connected(),
                    "type": provider.__class__.__name__
                }
                for name, provider in self._providers.items()
            },
            "default_provider": self._default_provider,
            "cache_enabled": self._cache is not None,
        }


# Global secret manager instance
_secret_manager: Optional[SecretManager] = None


def get_secret_manager() -> SecretManager:
    """Get the global secret manager instance."""
    global _secret_manager
    if _secret_manager is None:
        _secret_manager = SecretManager()
        # Add default local provider
        _secret_manager.add_provider("local", LocalSecretProvider(), default=True)
    return _secret_manager


def reset_secret_manager() -> None:
    """Reset the global secret manager (for testing)."""
    global _secret_manager
    _secret_manager = None
