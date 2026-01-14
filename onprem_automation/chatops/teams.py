"""
Microsoft Teams Bot Implementation

Provides Teams integration for ChatOps.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .bot import ChatBot, CommandHandler, Message, User, PermissionLevel, CommandResponse


@dataclass
class TeamsConfig:
    """Microsoft Teams bot configuration."""
    app_id: str = ""
    app_password: str = ""
    tenant_id: str = ""

    # Permission mapping (Teams groups to permission levels)
    admin_groups: List[str] = field(default_factory=list)
    operator_groups: List[str] = field(default_factory=list)

    # Channels
    notification_channel: str = ""
    alert_channel: str = ""

    def __post_init__(self):
        # Load from environment if not provided
        self.app_id = self.app_id or os.environ.get("TEAMS_APP_ID", "")
        self.app_password = self.app_password or os.environ.get("TEAMS_APP_PASSWORD", "")
        self.tenant_id = self.tenant_id or os.environ.get("TEAMS_TENANT_ID", "")


class TeamsBot(ChatBot):
    """
    Microsoft Teams bot implementation.

    Example usage:
    ```python
    config = TeamsConfig(
        app_id="...",
        app_password="...",
        tenant_id="...",
        admin_groups=["group-id"],
        notification_channel="channel-id"
    )

    bot = TeamsBot(config)

    @bot.handler.command("status")
    async def status(ctx):
        return "All systems operational"

    await bot.start_server(port=3978)
    ```
    """

    def __init__(
        self,
        config: TeamsConfig,
        handler: Optional[CommandHandler] = None
    ):
        super().__init__(handler or CommandHandler(prefix="@bot "))
        self.config = config
        self._adapter = None
        self._bot_framework = None

    async def connect(self) -> bool:
        """Initialize Teams bot adapter."""
        try:
            # In production, would use botbuilder-core
            # from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
            #
            # settings = BotFrameworkAdapterSettings(
            #     app_id=self.config.app_id,
            #     app_password=self.config.app_password
            # )
            # self._adapter = BotFrameworkAdapter(settings)

            self._connected = True
            self.logger.info("Teams bot adapter initialized")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize Teams adapter: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect Teams bot."""
        self._connected = False
        self.logger.info("Teams bot disconnected")

    async def send_message(
        self,
        channel: str,
        text: str,
        thread_id: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """Send a message to a Teams channel."""
        try:
            # In production:
            # from botbuilder.core import TurnContext
            # from botbuilder.schema import Activity, ActivityTypes
            #
            # activity = Activity(
            #     type=ActivityTypes.message,
            #     text=text,
            #     attachments=attachments
            # )
            #
            # await context.send_activity(activity)

            self.logger.debug(f"Sent message to {channel}: {text[:50]}...")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            return False

    async def _on_message(self, turn_context: Any) -> None:
        """Handle incoming Teams message."""
        try:
            # In production, turn_context would be TurnContext from botbuilder
            activity = turn_context.activity

            # Parse message
            message = Message(
                id=activity.id,
                text=activity.text or "",
                user=User(
                    id=activity.from_property.id,
                    name=activity.from_property.name or ""
                ),
                channel=activity.conversation.id,
                thread_id=activity.conversation.id,
                raw_data=activity.as_dict()
            )

            await self.handle_message(message)

        except Exception as e:
            self.logger.error(f"Error handling message: {e}")

    async def _fetch_user(self, user_id: str) -> User:
        """Fetch Teams user information."""
        try:
            # In production, would use Microsoft Graph API
            # to get user details and group memberships

            return User(id=user_id, name=user_id)

        except Exception as e:
            self.logger.error(f"Failed to fetch user {user_id}: {e}")
            return User(id=user_id, name="Unknown")

    async def send_notification(
        self,
        channel: str,
        title: str,
        message: str,
        severity: str = "info",
        fields: Optional[Dict[str, str]] = None
    ) -> bool:
        """Send a Teams notification with Adaptive Card."""
        # Color based on severity
        colors = {
            "info": "accent",
            "success": "good",
            "warning": "warning",
            "error": "attention",
            "critical": "attention",
        }
        color = colors.get(severity, "default")

        # Build Adaptive Card
        card = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": title,
                    "weight": "bolder",
                    "size": "large",
                    "color": color
                },
                {
                    "type": "TextBlock",
                    "text": message,
                    "wrap": True
                }
            ]
        }

        if fields:
            facts = [{"title": k, "value": v} for k, v in fields.items()]
            card["body"].append({
                "type": "FactSet",
                "facts": facts
            })

        attachment = {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card
        }

        return await self.send_message(channel, "", attachments=[attachment])

    async def send_interactive_message(
        self,
        channel: str,
        text: str,
        actions: List[Dict[str, Any]]
    ) -> bool:
        """Send an interactive message with action buttons."""
        card = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": text,
                    "wrap": True
                }
            ],
            "actions": actions
        }

        attachment = {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card
        }

        return await self.send_message(channel, "", attachments=[attachment])

    async def request_approval(
        self,
        channel: str,
        title: str,
        description: str,
        approval_id: str,
        requester: str
    ) -> bool:
        """Send an approval request with Adaptive Card."""
        card = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": f"🔔 {title}",
                    "weight": "bolder",
                    "size": "large"
                },
                {
                    "type": "TextBlock",
                    "text": description,
                    "wrap": True
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Requested by", "value": requester},
                        {"title": "Request ID", "value": approval_id}
                    ]
                }
            ],
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "✅ Approve",
                    "style": "positive",
                    "data": {
                        "action": "approve",
                        "approval_id": approval_id
                    }
                },
                {
                    "type": "Action.Submit",
                    "title": "❌ Reject",
                    "style": "destructive",
                    "data": {
                        "action": "reject",
                        "approval_id": approval_id
                    }
                }
            ]
        }

        attachment = {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card
        }

        return await self.send_message(channel, "", attachments=[attachment])

    async def start_server(self, host: str = "0.0.0.0", port: int = 3978) -> None:
        """Start the bot's HTTP server."""
        # In production, would use aiohttp or similar to create webhook endpoint
        # from aiohttp import web
        #
        # async def messages(req: web.Request) -> web.Response:
        #     body = await req.json()
        #     activity = Activity().deserialize(body)
        #     auth_header = req.headers.get("Authorization", "")
        #
        #     response = await self._adapter.process_activity(
        #         activity, auth_header, self._on_message
        #     )
        #     return web.Response(status=response.status)
        #
        # app = web.Application()
        # app.router.add_post("/api/messages", messages)
        # await web._run_app(app, host=host, port=port)

        self.logger.info(f"Teams bot server would start on {host}:{port}")
