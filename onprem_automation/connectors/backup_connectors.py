"""
Backup Solution Connectors

Provides real connections to enterprise backup solutions:
- Veeam Backup & Replication (REST API)
- Commvault (REST API)
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import time
import json
from datetime import datetime, timedelta

from .base import (
    BaseConnector, ConnectionConfig, ConnectionError,
    AuthenticationError
)

# Import aiohttp for async HTTP requests
try:
    import aiohttp
    import asyncio
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

# Import requests for sync HTTP
try:
    import requests
    from requests.auth import HTTPBasicAuth
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None


@dataclass
class VeeamConnectionConfig(ConnectionConfig):
    """Veeam Backup & Replication connection configuration."""
    port: int = 9419  # Enterprise Manager REST API port
    api_version: str = "v1"
    verify_ssl: bool = False


@dataclass
class CommvaultConnectionConfig(ConnectionConfig):
    """Commvault connection configuration."""
    port: int = 81  # WebConsole port
    api_version: str = "v2"
    verify_ssl: bool = True


class VeeamConnector(BaseConnector):
    """
    Veeam Backup & Replication REST API connector.

    Provides access to:
    - Backup job management
    - Restore operations
    - SureBackup verification
    - Repository management
    - Session monitoring
    """

    def __init__(self, config: VeeamConnectionConfig, logger=None):
        super().__init__(config, logger)
        self.config: VeeamConnectionConfig = config
        self._session = None
        self._token = None
        self._token_expiry = None
        self._base_url = f"https://{config.host}:{config.port}/api"

    def connect(self) -> bool:
        """
        Authenticate with Veeam REST API.

        Returns:
            True if authentication successful

        Raises:
            ConnectionError: If connection fails
            AuthenticationError: If authentication fails
        """
        if not REQUESTS_AVAILABLE:
            raise ConnectionError(
                "requests is not installed. Install with: pip install requests"
            )

        try:
            self.logger.info(f"Connecting to Veeam: {self.config.host}")

            self._session = requests.Session()
            self._session.verify = self.config.verify_ssl

            # Veeam Enterprise Manager OAuth2 authentication
            auth_url = f"{self._base_url}/oauth2/token"
            auth_data = {
                "grant_type": "password",
                "username": self.config.username,
                "password": self.config.password,
            }

            response = self._session.post(
                auth_url,
                data=auth_data,
                timeout=self.config.timeout
            )

            if response.status_code == 200:
                token_data = response.json()
                self._token = token_data.get("access_token")
                expires_in = token_data.get("expires_in", 3600)
                self._token_expiry = datetime.now() + timedelta(seconds=expires_in)

                # Set authorization header for future requests
                self._session.headers.update({
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                })

                self._connected = True
                self._connection_time = time.time()
                self.logger.info(f"Successfully authenticated with Veeam: {self.config.host}")
                return True
            elif response.status_code == 401:
                raise AuthenticationError("Invalid Veeam credentials")
            else:
                raise ConnectionError(f"Veeam authentication failed: {response.status_code}")

        except requests.exceptions.SSLError as e:
            raise ConnectionError(f"SSL error connecting to Veeam: {str(e)}")
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Connection error: {str(e)}")
        except Exception as e:
            raise ConnectionError(f"Veeam connection failed: {str(e)}")

    def disconnect(self) -> None:
        """Close Veeam session."""
        if self._session:
            try:
                # Veeam doesn't require explicit logout
                self._session.close()
            except Exception:
                pass
            finally:
                self._session = None
                self._token = None
                self._connected = False
                self.logger.info("Disconnected from Veeam")

    def health_check(self) -> Dict[str, Any]:
        """Check Veeam API health."""
        if not self._connected:
            return {"status": "disconnected", "host": self.config.host}

        try:
            start = time.time()
            response = self._session.get(
                f"{self._base_url}/serverInfo",
                timeout=self.config.timeout
            )
            latency = time.time() - start

            if response.status_code == 200:
                info = response.json()
                return {
                    "status": "healthy",
                    "host": self.config.host,
                    "latency_ms": round(latency * 1000, 2),
                    "version": info.get("ProductVersion"),
                    "build": info.get("BuildNumber"),
                }
            return {"status": "unhealthy", "host": self.config.host}
        except Exception as e:
            return {"status": "unhealthy", "host": self.config.host, "error": str(e)}

    def _refresh_token_if_needed(self) -> None:
        """Refresh token if it's about to expire."""
        if self._token_expiry and datetime.now() >= self._token_expiry - timedelta(minutes=5):
            self.connect()

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        params: Dict = None
    ) -> Dict[str, Any]:
        """Make an API request."""
        self._refresh_token_if_needed()

        url = f"{self._base_url}/{endpoint}"

        try:
            response = self._session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=self.config.timeout
            )

            if response.status_code in [200, 201, 202]:
                return {"status": "success", "data": response.json() if response.text else {}}
            elif response.status_code == 204:
                return {"status": "success", "data": {}}
            else:
                return {
                    "status": "error",
                    "code": response.status_code,
                    "message": response.text
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ==================== Backup Job Operations ====================

    def list_backup_jobs(self) -> Dict[str, Any]:
        """List all backup jobs."""
        return self._api_request("GET", "jobs")

    def get_backup_job(self, job_id: str) -> Dict[str, Any]:
        """Get details of a specific backup job."""
        return self._api_request("GET", f"jobs/{job_id}")

    def start_backup_job(self, job_id: str) -> Dict[str, Any]:
        """Start a backup job."""
        return self._api_request("POST", f"jobs/{job_id}/start")

    def stop_backup_job(self, job_id: str) -> Dict[str, Any]:
        """Stop a running backup job."""
        return self._api_request("POST", f"jobs/{job_id}/stop")

    def get_job_sessions(self, job_id: str, limit: int = 10) -> Dict[str, Any]:
        """Get recent sessions for a backup job."""
        return self._api_request(
            "GET",
            f"jobs/{job_id}/sessions",
            params={"limit": limit}
        )

    # ==================== Restore Operations ====================

    def list_restore_points(self, vm_name: str = None) -> Dict[str, Any]:
        """List available restore points."""
        params = {}
        if vm_name:
            params["vmName"] = vm_name
        return self._api_request("GET", "restorePoints", params=params)

    def get_restore_point(self, restore_point_id: str) -> Dict[str, Any]:
        """Get details of a restore point."""
        return self._api_request("GET", f"restorePoints/{restore_point_id}")

    def start_instant_recovery(
        self,
        restore_point_id: str,
        target_host: str = None,
        vm_name: str = None
    ) -> Dict[str, Any]:
        """Start instant VM recovery."""
        data = {
            "restorePointId": restore_point_id,
        }
        if target_host:
            data["targetHost"] = target_host
        if vm_name:
            data["vmName"] = vm_name

        return self._api_request("POST", "instantRecovery", data=data)

    def start_file_restore(
        self,
        restore_point_id: str,
        files: List[str],
        destination_path: str
    ) -> Dict[str, Any]:
        """Start file-level restore."""
        data = {
            "restorePointId": restore_point_id,
            "files": files,
            "destinationPath": destination_path
        }
        return self._api_request("POST", "fileRestore", data=data)

    # ==================== SureBackup Operations ====================

    def list_surebackup_jobs(self) -> Dict[str, Any]:
        """List SureBackup verification jobs."""
        return self._api_request("GET", "sureBackupJobs")

    def start_surebackup_job(self, job_id: str) -> Dict[str, Any]:
        """Start a SureBackup verification job."""
        return self._api_request("POST", f"sureBackupJobs/{job_id}/start")

    def get_surebackup_session(self, session_id: str) -> Dict[str, Any]:
        """Get SureBackup session details."""
        return self._api_request("GET", f"sureBackupSessions/{session_id}")

    # ==================== Repository Operations ====================

    def list_repositories(self) -> Dict[str, Any]:
        """List backup repositories."""
        return self._api_request("GET", "repositories")

    def get_repository(self, repo_id: str) -> Dict[str, Any]:
        """Get repository details."""
        return self._api_request("GET", f"repositories/{repo_id}")

    def get_repository_usage(self, repo_id: str) -> Dict[str, Any]:
        """Get repository storage usage."""
        return self._api_request("GET", f"repositories/{repo_id}/usage")

    # ==================== Session/Task Operations ====================

    def list_sessions(self, limit: int = 100) -> Dict[str, Any]:
        """List recent backup sessions."""
        return self._api_request("GET", "sessions", params={"limit": limit})

    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get session details."""
        return self._api_request("GET", f"sessions/{session_id}")

    def list_running_tasks(self) -> Dict[str, Any]:
        """List currently running tasks."""
        return self._api_request("GET", "runningTasks")


class CommvaultConnector(BaseConnector):
    """
    Commvault REST API connector.

    Provides access to:
    - Backup operations
    - Client management
    - Job management
    - Storage policies
    """

    def __init__(self, config: CommvaultConnectionConfig, logger=None):
        super().__init__(config, logger)
        self.config: CommvaultConnectionConfig = config
        self._session = None
        self._token = None
        self._base_url = f"http{'s' if config.verify_ssl else ''}://{config.host}:{config.port}/webconsole/api"

    def connect(self) -> bool:
        """
        Authenticate with Commvault API.

        Returns:
            True if authentication successful
        """
        if not REQUESTS_AVAILABLE:
            raise ConnectionError(
                "requests is not installed. Install with: pip install requests"
            )

        try:
            self.logger.info(f"Connecting to Commvault: {self.config.host}")

            self._session = requests.Session()
            self._session.verify = self.config.verify_ssl

            # Commvault login
            login_url = f"{self._base_url}/Login"
            login_data = {
                "mode": 4,
                "username": self.config.username,
                "password": self.config.password
            }

            response = self._session.post(
                login_url,
                json=login_data,
                timeout=self.config.timeout
            )

            if response.status_code == 200:
                result = response.json()
                if "token" in result:
                    self._token = result["token"]
                    self._session.headers.update({
                        "Authtoken": self._token,
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    })
                    self._connected = True
                    self._connection_time = time.time()
                    self.logger.info(f"Successfully authenticated with Commvault: {self.config.host}")
                    return True

            raise AuthenticationError("Commvault authentication failed")

        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Connection error: {str(e)}")
        except Exception as e:
            raise ConnectionError(f"Commvault connection failed: {str(e)}")

    def disconnect(self) -> None:
        """Logout from Commvault."""
        if self._session and self._token:
            try:
                self._session.post(f"{self._base_url}/Logout")
            except Exception:
                pass
            finally:
                self._session.close()
                self._session = None
                self._token = None
                self._connected = False
                self.logger.info("Logged out from Commvault")

    def health_check(self) -> Dict[str, Any]:
        """Check Commvault API health."""
        if not self._connected:
            return {"status": "disconnected", "host": self.config.host}

        try:
            start = time.time()
            response = self._session.get(
                f"{self._base_url}/CommServ",
                timeout=self.config.timeout
            )
            latency = time.time() - start

            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "host": self.config.host,
                    "latency_ms": round(latency * 1000, 2),
                }
            return {"status": "unhealthy", "host": self.config.host}
        except Exception as e:
            return {"status": "unhealthy", "host": self.config.host, "error": str(e)}

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        params: Dict = None
    ) -> Dict[str, Any]:
        """Make an API request."""
        url = f"{self._base_url}/{endpoint}"

        try:
            response = self._session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=self.config.timeout
            )

            if response.status_code in [200, 201, 202]:
                return {"status": "success", "data": response.json() if response.text else {}}
            else:
                return {
                    "status": "error",
                    "code": response.status_code,
                    "message": response.text
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ==================== Client Operations ====================

    def list_clients(self) -> Dict[str, Any]:
        """List all clients."""
        return self._api_request("GET", "Client")

    def get_client(self, client_id: str) -> Dict[str, Any]:
        """Get client details."""
        return self._api_request("GET", f"Client/{client_id}")

    def get_client_by_name(self, client_name: str) -> Dict[str, Any]:
        """Get client by name."""
        return self._api_request("GET", "Client", params={"clientName": client_name})

    # ==================== Subclient Operations ====================

    def list_subclients(self, client_id: str = None) -> Dict[str, Any]:
        """List subclients."""
        params = {}
        if client_id:
            params["clientId"] = client_id
        return self._api_request("GET", "Subclient", params=params)

    def get_subclient(self, subclient_id: str) -> Dict[str, Any]:
        """Get subclient details."""
        return self._api_request("GET", f"Subclient/{subclient_id}")

    # ==================== Job Operations ====================

    def list_jobs(self, limit: int = 100) -> Dict[str, Any]:
        """List recent jobs."""
        return self._api_request("GET", "Job", params={"limit": limit})

    def get_job(self, job_id: str) -> Dict[str, Any]:
        """Get job details."""
        return self._api_request("GET", f"Job/{job_id}")

    def kill_job(self, job_id: str) -> Dict[str, Any]:
        """Kill a running job."""
        return self._api_request("POST", f"Job/{job_id}/action/kill")

    def suspend_job(self, job_id: str) -> Dict[str, Any]:
        """Suspend a running job."""
        return self._api_request("POST", f"Job/{job_id}/action/suspend")

    def resume_job(self, job_id: str) -> Dict[str, Any]:
        """Resume a suspended job."""
        return self._api_request("POST", f"Job/{job_id}/action/resume")

    # ==================== Backup Operations ====================

    def run_backup(self, subclient_id: str, backup_level: str = "Incremental") -> Dict[str, Any]:
        """
        Start a backup job.

        Args:
            subclient_id: Subclient ID to backup
            backup_level: Full, Incremental, or Differential
        """
        data = {
            "taskInfo": {
                "subTasks": [{
                    "subTask": {
                        "subTaskType": 2,
                        "operationType": 2
                    },
                    "options": {
                        "backupOpts": {
                            "backupLevel": backup_level
                        }
                    }
                }]
            }
        }
        return self._api_request("POST", f"Subclient/{subclient_id}/action/backup", data=data)

    # ==================== Restore Operations ====================

    def browse_backup(self, client_id: str, path: str = "\\") -> Dict[str, Any]:
        """Browse backup data."""
        data = {"paths": [path]}
        return self._api_request("POST", f"Client/{client_id}/browse", data=data)

    def start_restore(
        self,
        client_id: str,
        paths: List[str],
        destination_client: str = None,
        destination_path: str = None
    ) -> Dict[str, Any]:
        """
        Start a restore operation.

        Args:
            client_id: Source client ID
            paths: List of paths to restore
            destination_client: Target client (in-place if not specified)
            destination_path: Target path (original location if not specified)
        """
        data = {
            "taskInfo": {
                "subTasks": [{
                    "subTask": {
                        "subTaskType": 3,
                        "operationType": 1001
                    },
                    "options": {
                        "restoreOptions": {
                            "browseOption": {
                                "listMedia": False,
                                "backupset": {}
                            },
                            "destination": {
                                "destPath": [destination_path] if destination_path else [],
                                "destClient": {
                                    "clientName": destination_client
                                } if destination_client else {}
                            },
                            "fileOption": {
                                "sourceItem": paths
                            }
                        }
                    }
                }]
            }
        }
        return self._api_request("POST", f"Client/{client_id}/restore", data=data)

    # ==================== Storage Policy Operations ====================

    def list_storage_policies(self) -> Dict[str, Any]:
        """List storage policies."""
        return self._api_request("GET", "StoragePolicy")

    def get_storage_policy(self, policy_id: str) -> Dict[str, Any]:
        """Get storage policy details."""
        return self._api_request("GET", f"StoragePolicy/{policy_id}")

    # ==================== Media Agent Operations ====================

    def list_media_agents(self) -> Dict[str, Any]:
        """List media agents."""
        return self._api_request("GET", "MediaAgent")

    def get_media_agent(self, ma_id: str) -> Dict[str, Any]:
        """Get media agent details."""
        return self._api_request("GET", f"MediaAgent/{ma_id}")

    # ==================== Library Operations ====================

    def list_libraries(self) -> Dict[str, Any]:
        """List disk/tape libraries."""
        return self._api_request("GET", "Library")

    def get_library_usage(self, library_id: str) -> Dict[str, Any]:
        """Get library storage usage."""
        return self._api_request("GET", f"Library/{library_id}/usage")
