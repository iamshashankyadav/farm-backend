"""Expo / FCM Push notification client.

Sends push notifications via the Expo Push API (which proxies to FCM for Android
and APNs for iOS devices).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def send_push_notification(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    expo_push_url: str = "https://exp.host/--/api/v2/push/send",
    access_token: str | None = None,
) -> bool:
    """Send push notification to a list of Expo / FCM device tokens."""
    if not tokens:
        return True

    messages = [
        {
            "to": token,
            "sound": "default",
            "title": title,
            "body": body,
            "data": data or {},
        }
        for token in tokens
    ]

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Content-Type": "application/json",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(expo_push_url, json=messages, headers=headers)
            if resp.status_code >= 400:
                logger.warning("Expo push API returned status %s: %s", resp.status_code, resp.text)
                return False
            logger.info("Sent push notification to %d device(s)", len(tokens))
            return True
    except Exception as exc:
        logger.warning("Failed to send push notification: %s", exc)
        return False
