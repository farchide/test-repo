"""
Slack Bot Implementation

Provides Slack integration for ChatOps.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .bot import ChatBot, CommandHandler, Message, User, PermissionLevel, CommandResponse


@dataclass
class SlackConfig:
    """Slack bot configuration."""
    bot_token: str = ""
    app_token: str = ""  # For Socket Mode
    signing_secret: str = ""

    # Permission mapping (Slack user groups to permission levels)
    admin_groups: List[str] = field(default_factory=list)
    operator_groups: List[str] = field(default_factory=list)

    # Channels
    notification_channel: str = ""
    alert_channel: str = ""

    def __post_init__(self):
        # Load from environment if not provided
        self.bot_token = self.bot_token or os.environ.get("SLACK_BOT_TOKEN", "")
        self.app_token = self.app_token or os.environ.get("SLACK_APP_TOKEN", "")
        self.signing_secret = self.signing_secret or os.environ.get("SLACK_SIGNING_SECRET", "")


class SlackBot(ChatBot):
    """
    Slack bot implementation.

    Example usage:
    ```python
    config = SlackConfig(
        bot_token="xoxb-...",
        app_token="xapp-...",
        admin_groups=["S012345"],
        notification_channel="#ops-notifications"
    )

    bot = SlackBot(config)

    @bot.handler.command("deploy", permission=PermissionLevel.OPERATOR)
    async def deploy(ctx):
        env = ctx.args[0] if ctx.args else "staging"
        return f"Starting deployment to {env}..."

    await bot.connect()
    ```
    """

    def __init__(
        self,
        config: SlackConfig,
        handler: Optional[CommandHandler] = None
    ):
        super().__init__(handler or CommandHandler(prefix="!"))
        self.config = config
        self._client = None
        self._socket_client = None

    async def connect(self) -> bool:
        """Connect to Slack using Socket Mode."""
        try:
            # In production, would use slack_sdk
            # from slack_sdk.web.async_client import AsyncWebClient
            # from slack_sdk.socket_mode.aiohttp import SocketModeClient
            #
            # self._client = AsyncWebClient(token=self.config.bot_token)
            # self._socket_client = SocketModeClient(
            #     app_token=self.config.app_token,
            #     web_client=self._client
            # )
            #
            # # Register message handler
            # @self._socket_client.on("message")
            # async def handle_message(event):
            #     await self._on_message(event)
            #
            # await self._socket_client.connect()

            self._connected = True
            self.logger.info("Connected to Slack")
            return True

        except Exception as e:
            self.logger.error(f"Failed to connect to Slack: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Slack."""
        if self._socket_client:
            # await self._socket_client.close()
            pass
        self._connected = False
        self.logger.info("Disconnected from Slack")

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_id: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Send a message to a Slack channel."""
        try:
            # In production:
            # await self._client.chat_postMessage(
            #     channel=channel,
            #     text=text,
            #     thread_ts=thread_id,
            #     attachments=attachments
            # )

            self.logger.debug(f"Sent message to {channel}: {text[:50]}...")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            return False

    async def _on_message(self, event: Dict[str, Any]) -> None:
        """Handle incoming Slack message event."""
        try:
            # Ignore bot messages
            if event.get("bot_id"):
                return

            # Parse message
            message = Message(
                id=event.get("ts", ""),
                text=event.get("text", ""),
                user=User(
                    id=event.get("user", ""),
                    name=event.get("user", "")
                ),
                channel=event.get("channel", ""),
                thread_id=event.get("thread_ts"),
                raw_data=event
            )

            await self.handle_message(message)

        except Exception as e:
            self.logger.error(f"Error handling message: {e}")

    async def _fetch_user(self, user_id: str) -> User:
        """Fetch Slack user information."""
        try:
            # In production:
            # result = await self._client.users_info(user=user_id)
            # user_info = result["user"]
            #
            # # Determine permission level
            # permission = PermissionLevel.USER
            # groups = await self._get_user_groups(user_id)
            #
            # if any(g in self.config.admin_groups for g in groups):
            #     permission = PermissionLevel.ADMIN
            # elif any(g in self.config.operator_groups for g in groups):
            #     permission = PermissionLevel.OPERATOR
            #
            # return User(
            #     id=user_id,
            #     name=user_info.get("real_name", user_info.get("name", "")),
            #     email=user_info.get("profile", {}).get("email"),
            #     permission_level=permission
            # )

            return User(id=user_id, name=user_id)

        except Exception as e:
            self.logger.error(f"Failed to fetch user {user_id}: {e}")
            return User(id=user_id, name="Unknown")

    async def _get_user_groups(self, user_id: str) -> List[str]:
        """Get Slack user groups for permission checking."""
        # In production, would query Slack API
        return []

    async def send_notification(
        self,
        channel: str,
        title: str,
        message: str,
        severity: str = "info",
        fields: Optional[Dict[str, str]] = None
    ) -> bool:
        """Send a Slack notification with Block Kit formatting."""
        # Emoji based on severity
        emojis = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨",
        }
        emoji = emojis.get(severity, "📌")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {title}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            }
        ]

        if fields:
            field_blocks = []
            for key, value in fields.items():
                field_blocks.append({
                    "type": "mrkdwn",
                    "text": f"*{key}*\n{value}"
                })

            # Add fields in pairs
            for i in range(0, len(field_blocks), 2):
                section = {"type": "section", "fields": field_blocks[i:i+2]}
                blocks.append(section)

        blocks.append({"type": "divider"})

        try:
            # In production:
            # await self._client.chat_postMessage(
            #     channel=channel,
            #     blocks=blocks,
            #     text=f"{title}: {message}"  # Fallback text
            # )

            self.logger.debug(f"Sent notification to {channel}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send notification: {e}")
            return False

    async def send_interactive_message(
        self,
        channel: str,
        text: str,
        actions: List[Dict[str, Any]]
    ) -> bool:
        """Send an interactive message with buttons."""
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text
                }
            },
            {
                "type": "actions",
                "elements": actions
            }
        ]

        try:
            # In production:
            # await self._client.chat_postMessage(
            #     channel=channel,
            #     blocks=blocks,
            #     text=text
            # )

            return True

        except Exception as e:
            self.logger.error(f"Failed to send interactive message: {e}")
            return False

    async def request_approval(
        self,
        channel: str,
        title: str,
        description: str,
        approval_id: str,
        requester: str
    ) -> bool:
        """Send an approval request with approve/reject buttons."""
        actions = [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "✅ Approve"},
                "style": "primary",
                "action_id": f"approve_{approval_id}",
                "value": approval_id
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "❌ Reject"},
                "style": "danger",
                "action_id": f"reject_{approval_id}",
                "value": approval_id
            }
        ]

        text = f"*{title}*\n\n{description}\n\nRequested by: <@{requester}>"

        return await self.send_interactive_message(channel, text, actions)
