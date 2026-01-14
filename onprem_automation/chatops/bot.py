"""
ChatOps Bot Base Classes

Provides base classes for chat bot implementations.
"""

import asyncio
import logging
import re
import shlex
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
import functools


class PermissionLevel(int, Enum):
    """Permission levels for commands."""
    PUBLIC = 0
    USER = 1
    OPERATOR = 2
    ADMIN = 3


@dataclass
class User:
    """Represents a chat user."""
    id: str
    name: str
    email: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    permission_level: PermissionLevel = PermissionLevel.USER


@dataclass
class Message:
    """Represents a chat message."""
    id: str
    text: str
    user: User
    channel: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    thread_id: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Command:
    """Represents a parsed command."""
    name: str
    args: List[str] = field(default_factory=list)
    kwargs: Dict[str, str] = field(default_factory=dict)
    raw_text: str = ""
    message: Optional[Message] = None


@dataclass
class CommandResponse:
    """Response from a command execution."""
    text: str
    success: bool = True
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    ephemeral: bool = False  # Only visible to requesting user
    thread_reply: bool = True  # Reply in thread


class CommandHandler:
    """
    Decorator-based command handler.

    Example:
    ```python
    handler = CommandHandler(prefix="!")

    @handler.command("deploy", permission=PermissionLevel.OPERATOR)
    async def deploy_cmd(ctx: Command) -> CommandResponse:
        target = ctx.args[0] if ctx.args else "production"
        return CommandResponse(f"Deploying to {target}...")

    @handler.command("status")
    async def status_cmd(ctx: Command) -> CommandResponse:
        return CommandResponse("All systems operational")
    ```
    """

    def __init__(
        self,
        prefix: str = "!",
        case_sensitive: bool = False
    ):
        self.prefix = prefix
        self.case_sensitive = case_sensitive
        self._commands: Dict[str, Dict[str, Any]] = {}
        self._aliases: Dict[str, str] = {}
        self._logger = logging.getLogger("chatops.handler")

    def command(
        self,
        name: str,
        aliases: Optional[List[str]] = None,
        description: str = "",
        usage: str = "",
        permission: PermissionLevel = PermissionLevel.USER,
        hidden: bool = False
    ) -> Callable:
        """Decorator to register a command."""
        def decorator(func: Callable) -> Callable:
            cmd_name = name if self.case_sensitive else name.lower()

            self._commands[cmd_name] = {
                "name": name,
                "handler": func,
                "description": description or func.__doc__ or "",
                "usage": usage,
                "permission": permission,
                "hidden": hidden,
                "aliases": aliases or [],
            }

            # Register aliases
            for alias in aliases or []:
                alias_key = alias if self.case_sensitive else alias.lower()
                self._aliases[alias_key] = cmd_name

            self._logger.debug(f"Registered command: {name}")

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    def parse(self, text: str) -> Optional[Command]:
        """Parse a message into a command."""
        if not text.startswith(self.prefix):
            return None

        # Remove prefix
        text = text[len(self.prefix):].strip()

        if not text:
            return None

        # Parse command and arguments
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()

        if not parts:
            return None

        cmd_name = parts[0]
        if not self.case_sensitive:
            cmd_name = cmd_name.lower()

        args = []
        kwargs = {}

        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                kwargs[key] = value
            else:
                args.append(part)

        return Command(
            name=cmd_name,
            args=args,
            kwargs=kwargs,
            raw_text=text
        )

    async def execute(
        self,
        command: Command,
        user: User
    ) -> CommandResponse:
        """Execute a command."""
        # Resolve alias
        cmd_name = command.name
        if cmd_name in self._aliases:
            cmd_name = self._aliases[cmd_name]

        # Get command
        cmd_info = self._commands.get(cmd_name)
        if not cmd_info:
            return CommandResponse(
                text=f"Unknown command: {command.name}. Use `{self.prefix}help` for available commands.",
                success=False
            )

        # Check permissions
        if user.permission_level.value < cmd_info["permission"].value:
            return CommandResponse(
                text="You don't have permission to use this command.",
                success=False,
                ephemeral=True
            )

        # Execute handler
        try:
            handler = cmd_info["handler"]
            if asyncio.iscoroutinefunction(handler):
                result = await handler(command)
            else:
                result = handler(command)

            if isinstance(result, str):
                return CommandResponse(text=result)
            elif isinstance(result, CommandResponse):
                return result
            else:
                return CommandResponse(text=str(result))

        except Exception as e:
            self._logger.error(f"Command {command.name} failed: {e}")
            return CommandResponse(
                text=f"Command failed: {str(e)}",
                success=False
            )

    def get_commands(
        self,
        include_hidden: bool = False
    ) -> List[Dict[str, Any]]:
        """Get list of available commands."""
        commands = []
        for name, info in self._commands.items():
            if info["hidden"] and not include_hidden:
                continue
            commands.append({
                "name": info["name"],
                "description": info["description"],
                "usage": info["usage"],
                "permission": info["permission"].name,
                "aliases": info["aliases"],
            })
        return commands

    def generate_help(
        self,
        permission_level: PermissionLevel = PermissionLevel.USER
    ) -> str:
        """Generate help text for available commands."""
        lines = ["**Available Commands:**\n"]

        for name, info in sorted(self._commands.items()):
            if info["hidden"]:
                continue
            if info["permission"].value > permission_level.value:
                continue

            usage = info["usage"] or name
            desc = info["description"].split("\n")[0]  # First line only
            lines.append(f"`{self.prefix}{usage}` - {desc}")

            if info["aliases"]:
                aliases = ", ".join(f"`{a}`" for a in info["aliases"])
                lines.append(f"  Aliases: {aliases}")

        return "\n".join(lines)


class ChatBot(ABC):
    """
    Base class for chat bot implementations.

    Subclasses should implement platform-specific connection
    and message handling.
    """

    def __init__(self, handler: Optional[CommandHandler] = None):
        self.handler = handler or CommandHandler()
        self.logger = logging.getLogger(f"chatops.{self.__class__.__name__}")
        self._connected = False
        self._user_cache: Dict[str, User] = {}

        # Register built-in commands
        self._register_builtin_commands()

    def _register_builtin_commands(self) -> None:
        """Register built-in commands."""

        @self.handler.command(
            "help",
            aliases=["h", "?"],
            description="Show available commands"
        )
        async def help_cmd(ctx: Command) -> CommandResponse:
            if ctx.args:
                # Help for specific command
                cmd_name = ctx.args[0].lower()
                cmd_info = self.handler._commands.get(cmd_name)
                if cmd_info:
                    text = f"**{cmd_info['name']}**\n"
                    text += f"{cmd_info['description']}\n"
                    if cmd_info["usage"]:
                        text += f"\nUsage: `{self.handler.prefix}{cmd_info['usage']}`"
                    return CommandResponse(text=text)
                return CommandResponse(text=f"Unknown command: {ctx.args[0]}")

            return CommandResponse(text=self.handler.generate_help())

        @self.handler.command(
            "ping",
            description="Check if bot is responsive"
        )
        async def ping_cmd(ctx: Command) -> CommandResponse:
            return CommandResponse(text="Pong! 🏓")

        @self.handler.command(
            "version",
            description="Show bot version"
        )
        async def version_cmd(ctx: Command) -> CommandResponse:
            return CommandResponse(text="OnPrem Automation Bot v1.0.0")

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the chat platform."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the chat platform."""
        pass

    @abstractmethod
    async def send_message(
        self,
        channel: str,
        text: str,
        thread_id: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Send a message to a channel."""
        pass

    async def handle_message(self, message: Message) -> Optional[CommandResponse]:
        """Handle an incoming message."""
        # Parse command
        command = self.handler.parse(message.text)
        if not command:
            return None

        command.message = message

        # Get user with permissions
        user = await self.get_user(message.user.id)

        # Execute command
        response = await self.handler.execute(command, user)

        # Send response
        if response.text:
            thread_id = message.thread_id or message.id if response.thread_reply else None
            await self.send_message(
                channel=message.channel,
                text=response.text,
                thread_id=thread_id,
                attachments=response.attachments
            )

        return response

    async def get_user(self, user_id: str) -> User:
        """Get user information with caching."""
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        user = await self._fetch_user(user_id)
        self._user_cache[user_id] = user
        return user

    async def _fetch_user(self, user_id: str) -> User:
        """Fetch user information from platform. Override in subclass."""
        return User(id=user_id, name="Unknown")

    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected

    async def send_notification(
        self,
        channel: str,
        title: str,
        message: str,
        severity: str = "info",
        fields: Optional[Dict[str, str]] = None
    ) -> bool:
        """Send a formatted notification."""
        # Color based on severity
        colors = {
            "info": "#0000FF",
            "success": "#00FF00",
            "warning": "#FFFF00",
            "error": "#FF0000",
            "critical": "#FF0000",
        }

        attachment = {
            "title": title,
            "text": message,
            "color": colors.get(severity, "#808080"),
            "fields": [
                {"title": k, "value": v, "short": True}
                for k, v in (fields or {}).items()
            ]
        }

        return await self.send_message(
            channel=channel,
            text="",
            attachments=[attachment]
        )
