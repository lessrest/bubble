from typing import Optional
import httpx
import rich
import structlog
import trio
import logging
from pydantic import SecretStr
from rdflib import URIRef
from bubble.cred import get_service_credential
from bubble.prfx import AI  # You'll need to add TG namespace to prfx.py
from bubble.repo import loading_bubble_from
import pathlib

logger = structlog.get_logger()

console = rich.console.Console()


class TelegramError(Exception):
    """Base exception for Telegram-related errors"""

    pass


class TelegramBot:
    """Simple Telegram Bot API client using httpx"""

    API_BASE = "https://api.telegram.org/bot"

    def __init__(self, token: SecretStr):
        self.token = token
        self.client = httpx.AsyncClient(
            base_url=f"{self.API_BASE}{token.get_secret_value()}"
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def get_me(self) -> dict:
        """Test the auth token and get basic info about the bot"""
        response = await self.client.get("/getMe")
        response.raise_for_status()
        return response.json()

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: Optional[str] = None,
    ) -> dict:
        """Send a text message to a chat"""
        data = {
            "chat_id": chat_id,
            "text": text,
        }
        if parse_mode:
            data["parse_mode"] = parse_mode

        response = await self.client.post("/sendMessage", json=data)
        response.raise_for_status()
        return response.json()

    async def get_updates(
        self, offset: Optional[int] = None, timeout: int = 30
    ) -> list[dict]:
        """Get updates (new messages) from Telegram"""
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset

        response = await self.client.get(
            "/getUpdates", params=params, timeout=timeout + 10
        )
        response.raise_for_status()
        return response.json()["result"]

    async def poll_updates(self, handle_update) -> None:
        """Poll for updates and process them with the given handler"""
        last_update_id: Optional[int] = None

        logger.info("Starting update polling...")

        while True:
            try:
                offset = last_update_id + 1 if last_update_id else None
                updates = await self.get_updates(offset=offset)

                for update in updates:
                    await handle_update(update)
                    last_update_id = update["update_id"]

            except* Exception as e:
                console.print_exception()
                logger.error(f"Error while polling: {e}")
                await trio.sleep(5)  # Wait before retrying


class UpdateHandler:
    """Handles Telegram bot updates"""

    def __init__(self, bot: TelegramBot):
        self.bot = bot

    async def __call__(self, update: dict) -> None:
        """Process a single update"""
        console.print(update)

        if "message" not in update:
            return

        message = update["message"]
        if "text" not in message:
            return

        chat_id = message["chat"]["id"]
        text = message["text"]

        logger.info(
            f"Received message from {message['from'].get('username', 'Unknown')}: {text}"
        )

        # Echo the message back for now
        await self.bot.send_message(
            chat_id=chat_id, text=f"You said: {text}", parse_mode="HTML"
        )


async def get_telegram_bot() -> TelegramBot:
    """Get a configured Telegram bot instance using credentials from the graph"""
    token = await get_service_credential(
        URIRef(AI.TelegramBotService)
    )  # You'll need to add this to your ontology
    return TelegramBot(token)


async def run_bot(bubble_path: Optional[str] = None) -> None:
    """Run the bot with default update handler"""
    if bubble_path is None:
        bubble_path = str(pathlib.Path.home() / "bubble")

    async with loading_bubble_from(trio.Path(bubble_path)):
        async with await get_telegram_bot() as bot:
            me = await bot.get_me()
            logger.info(f"Starting bot @{me['result']['username']}")

            handler = UpdateHandler(bot)
            await bot.poll_updates(handler)
