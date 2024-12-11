from PIL import Image


async def favicon() -> Image.Image:
    """Generate a detailed favicon with color gradation from ASCII art."""

    ascii_art = [
        "    ********    ",
        "  **@@####@@**  ",
        " *@#$$$$$$##@* ",
        "*@#$$&&&&$$##@*",
        "*#$&&&**&&&$#@*",
        "@#$&******&$#@*",
        "@#$&******&$#@*",
        "@#$&******&$#@*",
        "@#$&******&$#@*",
        "*#$&&&**&&&$#*",
        "*@#$$&&&&$$#@*",
        " *@#$$$$$$#@* ",
        "  **@@##@@**  ",
        "    ********    ",
        "              ",
        "              ",
    ]

    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    pixels = img.load()
    assert pixels is not None

    colors = {
        "*": (100, 149, 237, 255),  # Base color (Cornflower blue)
        "@": (130, 169, 247, 255),  # Lighter shade
        "#": (80, 129, 217, 255),  # Darker shade
        "$": (150, 189, 255, 255),  # Highlight
        "&": (180, 209, 255, 255),  # Brightest highlight
        " ": (0, 0, 0, 0),  # Transparent
    }

    for y, row in enumerate(ascii_art):
        for x, char in enumerate(row):
            if char != " ":
                pixels[x, y] = colors[char]

    return img.resize((32, 32), Image.Resampling.NEAREST)
