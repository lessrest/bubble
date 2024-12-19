import os

from typing import Optional
from pathlib import Path

import httpx


class RecraftAPI:
    """Client for interacting with the Recraft.ai API"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Recraft API client

        Args:
            api_key: Recraft API key. If not provided, will try to get from RECRAFT_API_KEY env var
        """
        self.api_key = api_key or os.getenv("RECRAFT_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Recraft API key must be provided or set in RECRAFT_API_KEY env var"
            )

        self.base_url = "https://external.api.recraft.ai/v1"

    async def remove_background(self, image_path: str | Path) -> str:
        """Remove background from an image using Recraft API

        Args:
            image_path: Path to the image file

        Returns:
            URL of the processed image with background removed

        Raises:
            httpx.HTTPError: If the API request fails
            FileNotFoundError: If the image file doesn't exist
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=60) as client:
            with open(image_path, "rb") as f:
                files = {"file": f}
                response = await client.post(
                    f"{self.base_url}/images/removeBackground",
                    headers=headers,
                    files=files,
                )
                response.raise_for_status()

            result = response.json()
            return result["image"]["url"]

    async def modify_background(
        self, image_path: str | Path, prompt: str
    ) -> str:
        """Modify the background of an image using Recraft API

        Args:
            image_path: Path to the image file
            prompt: Text prompt describing the desired background

        Returns:
            URL of the processed image with modified background

        Raises:
            httpx.HTTPError: If the API request fails
            FileNotFoundError: If the image file doesn't exist
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with httpx.AsyncClient(timeout=60) as client:
            with open(image_path, "rb") as f:
                files = {"image": f}
                data = {"prompt": prompt}
                response = await client.post(
                    f"{self.base_url}/images/replaceBackground",
                    headers=headers,
                    files=files,
                    data=data,
                )
                response.raise_for_status()

            result = response.json()
            return result["data"][0]["url"]


# Example usage:
"""
async def main():
    recraft = RecraftAPI()
    url = await recraft.remove_background("path/to/image.png")
    print(f"Processed image URL: {url}")
"""
