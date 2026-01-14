"""
Secret Providers

Implements various secret storage backends.
"""

import base64
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib


@dataclass
class SecretMetadata:
    """Metadata for a secret."""
    name: str
    version: str = "1"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    tags: Dict[str, str] = field(default_factory=dict)
    rotation_schedule: Optional[str] = None


@dataclass
class Secret:
    """Represents a secret value with metadata."""
    name: str
    value: str
    metadata: SecretMetadata = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = SecretMetadata(name=self.name)

    def is_expired(self) -> bool:
        """Check if secret has expired."""
        if self.metadata.expires_at:
            return datetime.utcnow() > self.metadata.expires_at
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (without sensitive value)."""
        return {
            "name": self.name,
            "version": self.metadata.version,
            "created_at": self.metadata.created_at.isoformat(),
            "updated_at": self.metadata.updated_at.isoformat(),
            "expires_at": self.metadata.expires_at.isoformat() if self.metadata.expires_at else None,
            "tags": self.metadata.tags,
        }


class SecretProvider(ABC):
    """Base class for secret providers."""

    def __init__(self):
        self.logger = logging.getLogger(f"secrets.{self.__class__.__name__}")
        self._connected = False

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the secret backend."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the secret backend."""
        pass

    @abstractmethod
    async def get_secret(self, name: str, version: Optional[str] = None) -> Optional[Secret]:
        """Retrieve a secret by name."""
        pass

    @abstractmethod
    async def set_secret(
        self,
        name: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store a secret."""
        pass

    @abstractmethod
    async def delete_secret(self, name: str) -> bool:
        """Delete a secret."""
        pass

    @abstractmethod
    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        """List available secrets."""
        pass

    def is_connected(self) -> bool:
        """Check if connected to backend."""
        return self._connected

    async def rotate_secret(self, name: str, new_value: str) -> bool:
        """Rotate a secret (update with new version)."""
        secret = await self.get_secret(name)
        if not secret:
            return False

        new_version = str(int(secret.metadata.version) + 1)
        metadata = {
            "version": new_version,
            "tags": secret.metadata.tags,
        }

        return await self.set_secret(name, new_value, metadata)


class VaultProvider(SecretProvider):
    """HashiCorp Vault secret provider."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:8200",
        token: Optional[str] = None,
        namespace: Optional[str] = None,
        mount_point: str = "secret",
        verify_ssl: bool = True
    ):
        super().__init__()
        self.url = url
        self.token = token or os.environ.get("VAULT_TOKEN", "")
        self.namespace = namespace
        self.mount_point = mount_point
        self.verify_ssl = verify_ssl
        self._client = None

    async def connect(self) -> bool:
        """Connect to Vault."""
        try:
            # In production, would use hvac library
            # import hvac
            # self._client = hvac.Client(
            #     url=self.url,
            #     token=self.token,
            #     namespace=self.namespace,
            #     verify=self.verify_ssl
            # )
            # self._connected = self._client.is_authenticated()

            # Mock for now
            self._connected = True
            self.logger.info(f"Connected to Vault at {self.url}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to Vault: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Vault."""
        self._client = None
        self._connected = False

    async def get_secret(self, name: str, version: Optional[str] = None) -> Optional[Secret]:
        """Get secret from Vault."""
        if not self._connected:
            return None

        try:
            # In production:
            # response = self._client.secrets.kv.v2.read_secret_version(
            #     path=name,
            #     mount_point=self.mount_point,
            #     version=version
            # )
            # data = response["data"]["data"]
            # metadata = response["data"]["metadata"]

            # Mock response
            self.logger.debug(f"Retrieved secret: {name}")
            return None  # Would return actual secret
        except Exception as e:
            self.logger.error(f"Failed to get secret {name}: {e}")
            return None

    async def set_secret(
        self,
        name: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store secret in Vault."""
        if not self._connected:
            return False

        try:
            # In production:
            # self._client.secrets.kv.v2.create_or_update_secret(
            #     path=name,
            #     secret={"value": value, **(metadata or {})},
            #     mount_point=self.mount_point
            # )

            self.logger.info(f"Stored secret: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store secret {name}: {e}")
            return False

    async def delete_secret(self, name: str) -> bool:
        """Delete secret from Vault."""
        if not self._connected:
            return False

        try:
            # In production:
            # self._client.secrets.kv.v2.delete_metadata_and_all_versions(
            #     path=name,
            #     mount_point=self.mount_point
            # )

            self.logger.info(f"Deleted secret: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete secret {name}: {e}")
            return False

    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        """List secrets in Vault."""
        if not self._connected:
            return []

        try:
            # In production:
            # response = self._client.secrets.kv.v2.list_secrets(
            #     path=prefix or "",
            #     mount_point=self.mount_point
            # )
            # return response["data"]["keys"]

            return []
        except Exception as e:
            self.logger.error(f"Failed to list secrets: {e}")
            return []


class AWSSecretsProvider(SecretProvider):
    """AWS Secrets Manager provider."""

    def __init__(
        self,
        region: str = "us-east-1",
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        profile: Optional[str] = None
    ):
        super().__init__()
        self.region = region
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.profile = profile
        self._client = None

    async def connect(self) -> bool:
        """Connect to AWS Secrets Manager."""
        try:
            # In production, would use boto3
            # import boto3
            # session = boto3.Session(
            #     aws_access_key_id=self.access_key_id,
            #     aws_secret_access_key=self.secret_access_key,
            #     profile_name=self.profile,
            #     region_name=self.region
            # )
            # self._client = session.client('secretsmanager')

            self._connected = True
            self.logger.info(f"Connected to AWS Secrets Manager in {self.region}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to AWS: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from AWS."""
        self._client = None
        self._connected = False

    async def get_secret(self, name: str, version: Optional[str] = None) -> Optional[Secret]:
        """Get secret from AWS Secrets Manager."""
        if not self._connected:
            return None

        try:
            # In production:
            # kwargs = {"SecretId": name}
            # if version:
            #     kwargs["VersionId"] = version
            # response = self._client.get_secret_value(**kwargs)
            # value = response.get("SecretString") or base64.b64decode(response["SecretBinary"]).decode()

            self.logger.debug(f"Retrieved secret: {name}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to get secret {name}: {e}")
            return None

    async def set_secret(
        self,
        name: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store secret in AWS Secrets Manager."""
        if not self._connected:
            return False

        try:
            # In production:
            # try:
            #     self._client.create_secret(Name=name, SecretString=value)
            # except self._client.exceptions.ResourceExistsException:
            #     self._client.put_secret_value(SecretId=name, SecretString=value)

            self.logger.info(f"Stored secret: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store secret {name}: {e}")
            return False

    async def delete_secret(self, name: str) -> bool:
        """Delete secret from AWS Secrets Manager."""
        if not self._connected:
            return False

        try:
            # In production:
            # self._client.delete_secret(SecretId=name, ForceDeleteWithoutRecovery=True)

            self.logger.info(f"Deleted secret: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete secret {name}: {e}")
            return False

    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        """List secrets in AWS Secrets Manager."""
        if not self._connected:
            return []

        try:
            # In production:
            # paginator = self._client.get_paginator('list_secrets')
            # secrets = []
            # for page in paginator.paginate():
            #     for secret in page['SecretList']:
            #         if not prefix or secret['Name'].startswith(prefix):
            #             secrets.append(secret['Name'])
            # return secrets

            return []
        except Exception as e:
            self.logger.error(f"Failed to list secrets: {e}")
            return []


class AzureKeyVaultProvider(SecretProvider):
    """Azure Key Vault provider."""

    def __init__(
        self,
        vault_url: str,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ):
        super().__init__()
        self.vault_url = vault_url
        self.tenant_id = tenant_id or os.environ.get("AZURE_TENANT_ID", "")
        self.client_id = client_id or os.environ.get("AZURE_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("AZURE_CLIENT_SECRET", "")
        self._client = None

    async def connect(self) -> bool:
        """Connect to Azure Key Vault."""
        try:
            # In production, would use azure-keyvault-secrets
            # from azure.identity import ClientSecretCredential
            # from azure.keyvault.secrets import SecretClient
            # credential = ClientSecretCredential(
            #     tenant_id=self.tenant_id,
            #     client_id=self.client_id,
            #     client_secret=self.client_secret
            # )
            # self._client = SecretClient(vault_url=self.vault_url, credential=credential)

            self._connected = True
            self.logger.info(f"Connected to Azure Key Vault at {self.vault_url}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to Azure: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Azure."""
        self._client = None
        self._connected = False

    async def get_secret(self, name: str, version: Optional[str] = None) -> Optional[Secret]:
        """Get secret from Azure Key Vault."""
        if not self._connected:
            return None

        try:
            # In production:
            # secret = self._client.get_secret(name, version=version)
            # return Secret(
            #     name=secret.name,
            #     value=secret.value,
            #     metadata=SecretMetadata(
            #         name=secret.name,
            #         version=secret.properties.version,
            #         created_at=secret.properties.created_on,
            #         expires_at=secret.properties.expires_on,
            #         tags=secret.properties.tags or {}
            #     )
            # )

            self.logger.debug(f"Retrieved secret: {name}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to get secret {name}: {e}")
            return None

    async def set_secret(
        self,
        name: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store secret in Azure Key Vault."""
        if not self._connected:
            return False

        try:
            # In production:
            # self._client.set_secret(name, value, tags=metadata.get("tags") if metadata else None)

            self.logger.info(f"Stored secret: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store secret {name}: {e}")
            return False

    async def delete_secret(self, name: str) -> bool:
        """Delete secret from Azure Key Vault."""
        if not self._connected:
            return False

        try:
            # In production:
            # poller = self._client.begin_delete_secret(name)
            # poller.wait()

            self.logger.info(f"Deleted secret: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete secret {name}: {e}")
            return False

    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        """List secrets in Azure Key Vault."""
        if not self._connected:
            return []

        try:
            # In production:
            # secrets = []
            # for secret in self._client.list_properties_of_secrets():
            #     if not prefix or secret.name.startswith(prefix):
            #         secrets.append(secret.name)
            # return secrets

            return []
        except Exception as e:
            self.logger.error(f"Failed to list secrets: {e}")
            return []


class LocalSecretProvider(SecretProvider):
    """
    Local encrypted secret storage.
    Suitable for development or air-gapped environments.
    """

    def __init__(
        self,
        storage_path: str = ".secrets",
        encryption_key: Optional[str] = None
    ):
        super().__init__()
        self.storage_path = Path(storage_path)
        self._encryption_key = encryption_key or os.environ.get("SECRET_ENCRYPTION_KEY", "")
        self._secrets: Dict[str, Secret] = {}

    async def connect(self) -> bool:
        """Initialize local storage."""
        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)

            # Load existing secrets
            secrets_file = self.storage_path / "secrets.json"
            if secrets_file.exists():
                data = json.loads(self._decrypt_file(secrets_file))
                for name, secret_data in data.items():
                    self._secrets[name] = Secret(
                        name=name,
                        value=secret_data["value"],
                        metadata=SecretMetadata(
                            name=name,
                            version=secret_data.get("version", "1"),
                            tags=secret_data.get("tags", {})
                        )
                    )

            self._connected = True
            self.logger.info("Local secret storage initialized")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize local storage: {e}")
            return False

    async def disconnect(self) -> None:
        """Save and close local storage."""
        await self._save()
        self._secrets.clear()
        self._connected = False

    async def get_secret(self, name: str, version: Optional[str] = None) -> Optional[Secret]:
        """Get secret from local storage."""
        return self._secrets.get(name)

    async def set_secret(
        self,
        name: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store secret in local storage."""
        try:
            meta = SecretMetadata(
                name=name,
                version=metadata.get("version", "1") if metadata else "1",
                tags=metadata.get("tags", {}) if metadata else {}
            )
            self._secrets[name] = Secret(name=name, value=value, metadata=meta)
            await self._save()
            return True
        except Exception as e:
            self.logger.error(f"Failed to store secret {name}: {e}")
            return False

    async def delete_secret(self, name: str) -> bool:
        """Delete secret from local storage."""
        if name in self._secrets:
            del self._secrets[name]
            await self._save()
            return True
        return False

    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        """List secrets in local storage."""
        if prefix:
            return [n for n in self._secrets.keys() if n.startswith(prefix)]
        return list(self._secrets.keys())

    async def _save(self) -> None:
        """Save secrets to disk."""
        data = {
            name: {
                "value": secret.value,
                "version": secret.metadata.version,
                "tags": secret.metadata.tags,
            }
            for name, secret in self._secrets.items()
        }
        secrets_file = self.storage_path / "secrets.json"
        self._encrypt_file(secrets_file, json.dumps(data))

    def _encrypt_file(self, path: Path, data: str) -> None:
        """Encrypt and write data to file."""
        if self._encryption_key:
            # Simple XOR encryption (in production, use proper encryption)
            key_bytes = self._encryption_key.encode()
            data_bytes = data.encode()
            encrypted = bytes(
                data_bytes[i] ^ key_bytes[i % len(key_bytes)]
                for i in range(len(data_bytes))
            )
            with open(path, 'wb') as f:
                f.write(base64.b64encode(encrypted))
        else:
            with open(path, 'w') as f:
                f.write(data)

    def _decrypt_file(self, path: Path) -> str:
        """Read and decrypt data from file."""
        if self._encryption_key:
            with open(path, 'rb') as f:
                encrypted = base64.b64decode(f.read())
            key_bytes = self._encryption_key.encode()
            decrypted = bytes(
                encrypted[i] ^ key_bytes[i % len(key_bytes)]
                for i in range(len(encrypted))
            )
            return decrypted.decode()
        else:
            with open(path, 'r') as f:
                return f.read()
