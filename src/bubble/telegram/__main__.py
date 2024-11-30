import logging
import pathlib

import trio
import typer
from typer import Option

from bubble.telegram.bots import run_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = typer.Typer(add_completion=False)
home = pathlib.Path.home()


@app.command()
def main(
    bubble_path: str = Option(
        str(home / "bubble"), "--bubble", help="Bubble path"
    ),
) -> None:
    """Run the Telegram bot."""
    try:
        trio.run(run_bot, bubble_path)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")


if __name__ == "__main__":
    app()
