"""
Server Connectors

Provides real connections to servers:
- SSH for Linux/Unix systems (using Paramiko)
- WinRM for Windows systems (using pywinrm)
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
import time
import io

from .base import (
    BaseConnector, ConnectionConfig, ConnectionError,
    AuthenticationError, CommandExecutionError
)

# Import Paramiko for SSH
try:
    import paramiko
    from paramiko.ssh_exception import (
        AuthenticationException,
        SSHException,
        NoValidConnectionsError
    )
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False
    paramiko = None

# Import pywinrm for Windows
try:
    import winrm
    from winrm.exceptions import (
        WinRMTransportError,
        InvalidCredentialsError
    )
    WINRM_AVAILABLE = True
except ImportError:
    WINRM_AVAILABLE = False
    winrm = None


@dataclass
class SSHConnectionConfig(ConnectionConfig):
    """SSH connection configuration."""
    port: int = 22
    key_filename: str = None
    passphrase: str = None
    allow_agent: bool = True
    look_for_keys: bool = True
    compress: bool = False
    timeout: int = 30


@dataclass
class WinRMConnectionConfig(ConnectionConfig):
    """WinRM connection configuration."""
    port: int = 5985  # HTTP, use 5986 for HTTPS
    transport: str = "ntlm"  # ntlm, kerberos, basic, credssp
    use_ssl: bool = False
    verify_ssl: bool = True
    read_timeout: int = 30
    operation_timeout: int = 20


class SSHConnector(BaseConnector):
    """
    SSH connector using Paramiko.

    Provides SSH access to Linux/Unix systems:
    - Command execution
    - SFTP file transfer
    - Key-based and password authentication
    - Sudo support
    """

    def __init__(self, config: SSHConnectionConfig, logger=None):
        super().__init__(config, logger)
        self.config: SSHConnectionConfig = config
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None

    def connect(self) -> bool:
        """
        Establish SSH connection.

        Returns:
            True if connection successful

        Raises:
            ConnectionError: If connection fails
            AuthenticationError: If authentication fails
        """
        if not PARAMIKO_AVAILABLE:
            raise ConnectionError(
                "Paramiko is not installed. Install with: pip install paramiko"
            )

        try:
            self.logger.info(f"SSH connecting to: {self.config.host}")

            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": self.config.host,
                "port": self.config.port,
                "username": self.config.username,
                "timeout": self.config.timeout,
                "allow_agent": self.config.allow_agent,
                "look_for_keys": self.config.look_for_keys,
                "compress": self.config.compress,
            }

            # Add authentication method
            if self.config.key_filename:
                connect_kwargs["key_filename"] = self.config.key_filename
                if self.config.passphrase:
                    connect_kwargs["passphrase"] = self.config.passphrase
            else:
                connect_kwargs["password"] = self.config.password

            self._client.connect(**connect_kwargs)
            self._connected = True
            self._connection_time = time.time()

            self.logger.info(f"SSH connected to: {self.config.host}")
            return True

        except AuthenticationException as e:
            raise AuthenticationError(f"SSH authentication failed: {str(e)}")
        except NoValidConnectionsError as e:
            raise ConnectionError(f"SSH connection refused: {str(e)}")
        except SSHException as e:
            raise ConnectionError(f"SSH error: {str(e)}")
        except Exception as e:
            raise ConnectionError(f"SSH connection failed: {str(e)}")

    def disconnect(self) -> None:
        """Close SSH connection."""
        if self._sftp:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None

        if self._client:
            try:
                self._client.close()
                self.logger.info(f"SSH disconnected from: {self.config.host}")
            except Exception as e:
                self.logger.warning(f"Error during SSH disconnect: {e}")
            finally:
                self._client = None
                self._connected = False

    def health_check(self) -> Dict[str, Any]:
        """Check SSH connection health."""
        if not self._connected or not self._client:
            return {"status": "disconnected", "host": self.config.host}

        try:
            start = time.time()
            transport = self._client.get_transport()
            if transport and transport.is_active():
                latency = time.time() - start
                return {
                    "status": "healthy",
                    "host": self.config.host,
                    "latency_ms": round(latency * 1000, 2),
                }
            return {"status": "unhealthy", "host": self.config.host, "error": "Transport inactive"}
        except Exception as e:
            return {"status": "unhealthy", "host": self.config.host, "error": str(e)}

    def execute_command(
        self,
        command: str,
        timeout: int = 60,
        get_pty: bool = False
    ) -> Tuple[str, str, int]:
        """
        Execute a command on the remote server.

        Args:
            command: Command to execute
            timeout: Command timeout in seconds
            get_pty: Allocate pseudo-terminal

        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        if not self._connected:
            raise ConnectionError("Not connected via SSH")

        try:
            stdin, stdout, stderr = self._client.exec_command(
                command,
                timeout=timeout,
                get_pty=get_pty
            )

            exit_code = stdout.channel.recv_exit_status()
            stdout_str = stdout.read().decode('utf-8', errors='ignore')
            stderr_str = stderr.read().decode('utf-8', errors='ignore')

            return stdout_str, stderr_str, exit_code

        except Exception as e:
            raise CommandExecutionError(f"Command execution failed: {str(e)}")

    def execute_sudo(
        self,
        command: str,
        sudo_password: str = None,
        timeout: int = 60
    ) -> Tuple[str, str, int]:
        """
        Execute a command with sudo.

        Args:
            command: Command to execute
            sudo_password: Password for sudo (uses connection password if not provided)
            timeout: Command timeout

        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        password = sudo_password or self.config.password
        full_command = f"echo '{password}' | sudo -S {command}"
        return self.execute_command(full_command, timeout=timeout, get_pty=True)

    def get_sftp(self) -> paramiko.SFTPClient:
        """Get or create SFTP client."""
        if not self._sftp:
            self._sftp = self._client.open_sftp()
        return self._sftp

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        callback=None
    ) -> Dict[str, Any]:
        """
        Upload a file via SFTP.

        Args:
            local_path: Local file path
            remote_path: Remote destination path
            callback: Progress callback function

        Returns:
            Dict with upload status
        """
        try:
            sftp = self.get_sftp()
            sftp.put(local_path, remote_path, callback=callback)
            return {
                "status": "success",
                "message": f"Uploaded {local_path} to {remote_path}",
                "remote_path": remote_path
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def download_file(
        self,
        remote_path: str,
        local_path: str,
        callback=None
    ) -> Dict[str, Any]:
        """
        Download a file via SFTP.

        Args:
            remote_path: Remote file path
            local_path: Local destination path
            callback: Progress callback function

        Returns:
            Dict with download status
        """
        try:
            sftp = self.get_sftp()
            sftp.get(remote_path, local_path, callback=callback)
            return {
                "status": "success",
                "message": f"Downloaded {remote_path} to {local_path}",
                "local_path": local_path
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def read_file(self, remote_path: str) -> str:
        """Read a remote file and return contents."""
        sftp = self.get_sftp()
        with sftp.open(remote_path, 'r') as f:
            return f.read().decode('utf-8')

    def write_file(self, remote_path: str, content: str) -> Dict[str, Any]:
        """Write content to a remote file."""
        try:
            sftp = self.get_sftp()
            with sftp.open(remote_path, 'w') as f:
                f.write(content.encode('utf-8'))
            return {"status": "success", "path": remote_path}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def file_exists(self, remote_path: str) -> bool:
        """Check if a remote file exists."""
        try:
            sftp = self.get_sftp()
            sftp.stat(remote_path)
            return True
        except FileNotFoundError:
            return False

    # ==================== System Operations ====================

    def get_os_info(self) -> Dict[str, Any]:
        """Get OS information."""
        stdout, _, _ = self.execute_command("cat /etc/os-release 2>/dev/null || uname -a")
        return {"status": "success", "info": stdout}

    def get_hostname(self) -> str:
        """Get hostname."""
        stdout, _, _ = self.execute_command("hostname -f")
        return stdout.strip()

    def get_uptime(self) -> str:
        """Get system uptime."""
        stdout, _, _ = self.execute_command("uptime")
        return stdout.strip()

    def get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage information."""
        stdout, _, _ = self.execute_command("df -h")
        return {"status": "success", "output": stdout}

    def get_memory_usage(self) -> Dict[str, Any]:
        """Get memory usage information."""
        stdout, _, _ = self.execute_command("free -h")
        return {"status": "success", "output": stdout}

    def get_running_processes(self, top_n: int = 10) -> Dict[str, Any]:
        """Get top processes by CPU usage."""
        stdout, _, _ = self.execute_command(f"ps aux --sort=-%cpu | head -{top_n + 1}")
        return {"status": "success", "output": stdout}

    def service_status(self, service_name: str) -> Dict[str, Any]:
        """Check service status."""
        stdout, stderr, exit_code = self.execute_command(
            f"systemctl status {service_name} 2>&1 || service {service_name} status 2>&1"
        )
        return {
            "status": "success" if exit_code == 0 else "stopped",
            "service": service_name,
            "output": stdout,
            "exit_code": exit_code
        }

    def restart_service(self, service_name: str) -> Dict[str, Any]:
        """Restart a service."""
        stdout, stderr, exit_code = self.execute_sudo(
            f"systemctl restart {service_name} || service {service_name} restart"
        )
        return {
            "status": "success" if exit_code == 0 else "error",
            "service": service_name,
            "output": stdout + stderr,
            "exit_code": exit_code
        }


class WinRMConnector(BaseConnector):
    """
    Windows Remote Management (WinRM) connector.

    Provides remote access to Windows systems:
    - PowerShell command execution
    - CMD command execution
    - File operations via PowerShell
    """

    def __init__(self, config: WinRMConnectionConfig, logger=None):
        super().__init__(config, logger)
        self.config: WinRMConnectionConfig = config
        self._session = None

    def connect(self) -> bool:
        """
        Establish WinRM connection.

        Returns:
            True if connection successful

        Raises:
            ConnectionError: If connection fails
            AuthenticationError: If authentication fails
        """
        if not WINRM_AVAILABLE:
            raise ConnectionError(
                "pywinrm is not installed. Install with: pip install pywinrm"
            )

        try:
            self.logger.info(f"WinRM connecting to: {self.config.host}")

            # Build endpoint URL
            protocol = "https" if self.config.use_ssl else "http"
            endpoint = f"{protocol}://{self.config.host}:{self.config.port}/wsman"

            self._session = winrm.Session(
                endpoint,
                auth=(self.config.username, self.config.password),
                transport=self.config.transport,
                server_cert_validation='ignore' if not self.config.verify_ssl else 'validate',
                read_timeout_sec=self.config.read_timeout,
                operation_timeout_sec=self.config.operation_timeout,
            )

            # Test connection by running a simple command
            result = self._session.run_cmd('hostname')
            if result.status_code != 0:
                raise ConnectionError("Connection test failed")

            self._connected = True
            self._connection_time = time.time()
            self.logger.info(f"WinRM connected to: {self.config.host}")
            return True

        except InvalidCredentialsError as e:
            raise AuthenticationError(f"WinRM authentication failed: {str(e)}")
        except WinRMTransportError as e:
            raise ConnectionError(f"WinRM transport error: {str(e)}")
        except Exception as e:
            raise ConnectionError(f"WinRM connection failed: {str(e)}")

    def disconnect(self) -> None:
        """Close WinRM session."""
        self._session = None
        self._connected = False
        self.logger.info(f"WinRM session closed for: {self.config.host}")

    def health_check(self) -> Dict[str, Any]:
        """Check WinRM connection health."""
        if not self._connected or not self._session:
            return {"status": "disconnected", "host": self.config.host}

        try:
            start = time.time()
            result = self._session.run_cmd('echo ok')
            latency = time.time() - start

            if result.status_code == 0:
                return {
                    "status": "healthy",
                    "host": self.config.host,
                    "latency_ms": round(latency * 1000, 2),
                }
            return {"status": "unhealthy", "host": self.config.host}
        except Exception as e:
            return {"status": "unhealthy", "host": self.config.host, "error": str(e)}

    def run_cmd(self, command: str) -> Tuple[str, str, int]:
        """
        Run a CMD command.

        Args:
            command: Command to execute

        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        if not self._connected:
            raise ConnectionError("Not connected via WinRM")

        try:
            result = self._session.run_cmd(command)
            return (
                result.std_out.decode('utf-8', errors='ignore'),
                result.std_err.decode('utf-8', errors='ignore'),
                result.status_code
            )
        except Exception as e:
            raise CommandExecutionError(f"CMD execution failed: {str(e)}")

    def run_powershell(self, script: str) -> Tuple[str, str, int]:
        """
        Run a PowerShell script.

        Args:
            script: PowerShell script to execute

        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        if not self._connected:
            raise ConnectionError("Not connected via WinRM")

        try:
            result = self._session.run_ps(script)
            return (
                result.std_out.decode('utf-8', errors='ignore'),
                result.std_err.decode('utf-8', errors='ignore'),
                result.status_code
            )
        except Exception as e:
            raise CommandExecutionError(f"PowerShell execution failed: {str(e)}")

    # ==================== System Operations ====================

    def get_hostname(self) -> str:
        """Get hostname."""
        stdout, _, _ = self.run_cmd('hostname')
        return stdout.strip()

    def get_os_info(self) -> Dict[str, Any]:
        """Get Windows OS information."""
        script = """
        $os = Get-CimInstance Win32_OperatingSystem
        @{
            Name = $os.Caption
            Version = $os.Version
            BuildNumber = $os.BuildNumber
            Architecture = $os.OSArchitecture
            LastBoot = $os.LastBootUpTime
        } | ConvertTo-Json
        """
        stdout, _, _ = self.run_powershell(script)
        return {"status": "success", "info": stdout}

    def get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage information."""
        script = """
        Get-CimInstance Win32_LogicalDisk |
        Where-Object {$_.DriveType -eq 3} |
        Select-Object DeviceID, Size, FreeSpace |
        ConvertTo-Json
        """
        stdout, _, _ = self.run_powershell(script)
        return {"status": "success", "output": stdout}

    def get_services(self, filter_running: bool = False) -> Dict[str, Any]:
        """Get Windows services."""
        script = "Get-Service"
        if filter_running:
            script += " | Where-Object {$_.Status -eq 'Running'}"
        script += " | Select-Object Name, Status, DisplayName | ConvertTo-Json"
        stdout, _, _ = self.run_powershell(script)
        return {"status": "success", "services": stdout}

    def get_service_status(self, service_name: str) -> Dict[str, Any]:
        """Get status of a specific service."""
        script = f"Get-Service -Name '{service_name}' | Select-Object Name, Status, DisplayName | ConvertTo-Json"
        stdout, stderr, exit_code = self.run_powershell(script)
        return {
            "status": "success" if exit_code == 0 else "error",
            "service": service_name,
            "output": stdout,
            "error": stderr
        }

    def restart_service(self, service_name: str) -> Dict[str, Any]:
        """Restart a Windows service."""
        script = f"Restart-Service -Name '{service_name}' -Force -PassThru | Select-Object Name, Status | ConvertTo-Json"
        stdout, stderr, exit_code = self.run_powershell(script)
        return {
            "status": "success" if exit_code == 0 else "error",
            "service": service_name,
            "output": stdout,
            "error": stderr
        }

    def start_service(self, service_name: str) -> Dict[str, Any]:
        """Start a Windows service."""
        script = f"Start-Service -Name '{service_name}' -PassThru | Select-Object Name, Status | ConvertTo-Json"
        stdout, stderr, exit_code = self.run_powershell(script)
        return {
            "status": "success" if exit_code == 0 else "error",
            "service": service_name,
            "output": stdout
        }

    def stop_service(self, service_name: str) -> Dict[str, Any]:
        """Stop a Windows service."""
        script = f"Stop-Service -Name '{service_name}' -Force -PassThru | Select-Object Name, Status | ConvertTo-Json"
        stdout, stderr, exit_code = self.run_powershell(script)
        return {
            "status": "success" if exit_code == 0 else "error",
            "service": service_name,
            "output": stdout
        }

    def get_installed_updates(self) -> Dict[str, Any]:
        """Get installed Windows updates."""
        script = """
        Get-HotFix | Select-Object HotFixID, Description, InstalledOn |
        Sort-Object InstalledOn -Descending |
        ConvertTo-Json
        """
        stdout, _, _ = self.run_powershell(script)
        return {"status": "success", "updates": stdout}

    def check_pending_updates(self) -> Dict[str, Any]:
        """Check for pending Windows updates."""
        script = """
        $Session = New-Object -ComObject Microsoft.Update.Session
        $Searcher = $Session.CreateUpdateSearcher()
        $SearchResult = $Searcher.Search("IsInstalled=0")
        $SearchResult.Updates | Select-Object Title, MsrcSeverity | ConvertTo-Json
        """
        stdout, stderr, exit_code = self.run_powershell(script)
        return {
            "status": "success" if exit_code == 0 else "error",
            "updates": stdout,
            "error": stderr
        }

    def install_updates(self) -> Dict[str, Any]:
        """Install pending Windows updates."""
        script = """
        $Session = New-Object -ComObject Microsoft.Update.Session
        $Searcher = $Session.CreateUpdateSearcher()
        $SearchResult = $Searcher.Search("IsInstalled=0 and Type='Software'")

        if ($SearchResult.Updates.Count -gt 0) {
            $Downloader = $Session.CreateUpdateDownloader()
            $Downloader.Updates = $SearchResult.Updates
            $Downloader.Download()

            $Installer = $Session.CreateUpdateInstaller()
            $Installer.Updates = $SearchResult.Updates
            $Result = $Installer.Install()

            @{
                ResultCode = $Result.ResultCode
                RebootRequired = $Result.RebootRequired
                UpdatesInstalled = $SearchResult.Updates.Count
            } | ConvertTo-Json
        } else {
            @{Message = "No updates available"} | ConvertTo-Json
        }
        """
        stdout, stderr, exit_code = self.run_powershell(script)
        return {
            "status": "success" if exit_code == 0 else "error",
            "result": stdout,
            "error": stderr
        }

    def reboot(self, force: bool = False, timeout: int = 0) -> Dict[str, Any]:
        """Reboot the Windows server."""
        force_flag = "-Force" if force else ""
        script = f"Restart-Computer {force_flag} -Timeout {timeout}"
        stdout, stderr, exit_code = self.run_powershell(script)
        return {
            "status": "success" if exit_code == 0 else "error",
            "message": "Reboot initiated",
            "error": stderr
        }
