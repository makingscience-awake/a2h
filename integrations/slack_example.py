"""
A2H Slack Channel — Example implementation.

Shows how to build a real Slack delivery channel for A2H.
Replace the placeholder API calls with your Slack SDK.

    from a2h import Gateway
    from slack_example import SlackChannel

    gw = Gateway(channels=[SlackChannel(bot_token="xoxb-...")])
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# These would come from the a2h package
try:
    from a2h.models import Interaction, Notification
    from a2h.channels import ChannelCapability, SLACK_CAPABILITY
except ImportError:
    pass


@dataclass
class SlackChannel:
    """Delivers A2H requests as Slack interactive messages.

    Uses Block Kit to render:
    - Agent identity badge (name, verified status)
    - Question text
    - Context card (structured data)
    - Response buttons/inputs based on response_type
    - Deadline countdown
    """

    bot_token: str = ""
    default_channel: str | None = None

    @property
    def name(self) -> str:
        return "slack"

    @property
    def capability(self) -> ChannelCapability:
        return SLACK_CAPABILITY

    async def deliver_request(self, interaction: Interaction) -> bool:
        """Send an interactive Slack DM to the target human."""
        blocks = self._build_blocks(interaction)
        user_id = self._resolve_slack_user(interaction.to_name)

        if not user_id:
            logger.warning("Slack user not found for: %s", interaction.to_name)
            return False

        # TODO: Replace with actual Slack API call
        # await slack_client.chat_postMessage(
        #     channel=user_id,
        #     blocks=blocks,
        #     text=interaction.question,  # fallback for notifications
        # )

        logger.info("SLACK DM | %s | → %s | %s",
                     interaction.id, interaction.to_name, interaction.question[:60])
        return True

    async def deliver_notification(self, notification: Notification) -> bool:
        """Send a simple Slack DM notification."""
        user_id = self._resolve_slack_user(notification.to_name)
        if not user_id:
            return False

        # TODO: Replace with actual Slack API call
        # await slack_client.chat_postMessage(
        #     channel=user_id,
        #     text=f"📋 {notification.message}",
        # )

        logger.info("SLACK NOTIFY | %s | → %s | %s",
                     notification.id, notification.to_name, notification.message[:60])
        return True

    def _build_blocks(self, interaction: Interaction) -> list[dict]:
        """Build Slack Block Kit blocks for the request."""
        blocks: list[dict] = []

        # Agent identity header
        blocks.append({
            "type": "header",
            "text": {"type": "plain_text",
                     "text": f"🤖 {interaction.from_name} needs your input"}
        })

        # Question
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{interaction.question}*"}
        })

        # Context card
        if interaction.context:
            fields = []
            for key, value in list(interaction.context.items())[:8]:
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*{key}:* {value}"
                })
            blocks.append({"type": "section", "fields": fields})

        # Deadline
        if interaction.deadline:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn",
                              "text": f"⏰ Deadline: {interaction.deadline}"}]
            })

        blocks.append({"type": "divider"})

        # Response buttons based on type
        rt = interaction.response_type.value

        if rt == "approval":
            blocks.append({
                "type": "actions",
                "block_id": f"a2h_{interaction.id}",
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "✅ Approve"},
                     "style": "primary", "value": "approve",
                     "action_id": f"a2h_approve_{interaction.id}"},
                    {"type": "button", "text": {"type": "plain_text", "text": "❌ Reject"},
                     "style": "danger", "value": "reject",
                     "action_id": f"a2h_reject_{interaction.id}"},
                ]
            })

        elif rt == "choice" and interaction.options:
            elements = []
            for opt in interaction.options[:5]:  # Slack max 5 buttons
                elements.append({
                    "type": "button",
                    "text": {"type": "plain_text", "text": opt.label},
                    "value": opt.value,
                    "action_id": f"a2h_choice_{interaction.id}_{opt.value}",
                })
            blocks.append({
                "type": "actions",
                "block_id": f"a2h_{interaction.id}",
                "elements": elements,
            })

        elif rt == "confirm":
            blocks.append({
                "type": "actions",
                "block_id": f"a2h_{interaction.id}",
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Yes"},
                     "style": "primary", "value": "yes",
                     "action_id": f"a2h_yes_{interaction.id}"},
                    {"type": "button", "text": {"type": "plain_text", "text": "No"},
                     "value": "no",
                     "action_id": f"a2h_no_{interaction.id}"},
                ]
            })

        else:
            # Text/number — prompt to respond in dashboard
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn",
                         "text": "💬 _Respond in the dashboard for this request type._"}
            })

        return blocks

    def _resolve_slack_user(self, name: str) -> str | None:
        """Map A2H participant name to Slack user ID.

        In production, this would query the Slack API or a mapping table.
        """
        # TODO: Implement actual mapping
        # user_id = slack_user_mapping.get(name)
        # return user_id
        return f"U_{name.upper()}"  # placeholder
