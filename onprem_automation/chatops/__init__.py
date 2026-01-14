"""
ChatOps Integration

Provides chat-based automation through:
- Slack integration
- Microsoft Teams integration
- Discord integration
- Command parsing and execution
"""

from .bot import ChatBot, Command, CommandHandler
from .slack import SlackBot, SlackConfig
from .teams import TeamsBot, TeamsConfig
from .discord_bot import DiscordBot, DiscordConfig

__all__ = [
    "ChatBot",
    "Command",
    "CommandHandler",
    "SlackBot",
    "SlackConfig",
    "TeamsBot",
    "TeamsConfig",
    "DiscordBot",
    "DiscordConfig",
]
