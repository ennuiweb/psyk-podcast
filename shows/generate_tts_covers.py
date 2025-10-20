#!/usr/bin/env python3
"""Generate cover artwork for the TTS podcast feeds.

The layout mirrors the existing show covers: a flat primary background,
an overlapping darker arc, and centred typography. Colours are copied
from the corresponding non-TTS shows so the identity stays consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class Palette:
    primary: tuple[int, int, int]
    primary_dark: tuple[int, int, int]
    accent: tuple[int, int, int]
    metadata: tuple[int, int, int]


CANVAS_SIZE = 3000
TITLE_FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
BODY_FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
TITLE_FONT_SIZE = 320
SUBTITLE_FONT_SIZE = 180
METADATA_FONT_SIZE = 150
# Matches the vertical rhythm of the non-TTS artwork.
TITLE_SUBTITLE_GAP = 110
SUBTITLE_METADATA_GAP = 100
TITLE_Y_OFFSET = 1160


def load_fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    title_font = ImageFont.truetype(TITLE_FONT_PATH, TITLE_FONT_SIZE)
    subtitle_font = ImageFont.truetype(BODY_FONT_PATH, SUBTITLE_FONT_SIZE)
    metadata_font = ImageFont.truetype(BODY_FONT_PATH, METADATA_FONT_SIZE)
    return title_font, subtitle_font, metadata_font


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    y: int,
    fill: tuple[int, int, int],
) -> int:
    """Draw text centred horizontally and return the rendered height."""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (CANVAS_SIZE - text_width) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return text_height


def render_cover(
    *,
    output_path: Path,
    palette: Palette,
    title: str,
    subtitle: str,
    metadata: str,
    fonts: tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont],
) -> None:
    title_font, subtitle_font, metadata_font = fonts

    image = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), palette.primary)
    draw = ImageDraw.Draw(image)

    # Slightly oversized ellipse keeps the lower arc smooth while hiding the top edge.
    arc_bbox = (-240, 1600, CANVAS_SIZE + 240, CANVAS_SIZE + 1600)
    draw.ellipse(arc_bbox, fill=palette.primary_dark)

    current_y = TITLE_Y_OFFSET
    current_y += draw_centered_text(draw, title, title_font, current_y, fill=(248, 250, 252))
    current_y += TITLE_SUBTITLE_GAP
    current_y += draw_centered_text(draw, subtitle, subtitle_font, current_y, fill=palette.accent)
    current_y += SUBTITLE_METADATA_GAP
    draw_centered_text(draw, metadata, metadata_font, current_y, fill=palette.metadata)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def main() -> None:
    fonts = load_fonts()

    covers = (
        dict(
            output_path=Path("shows/intro-vt-tss/assets/cover.png"),
            palette=Palette(
                primary=(28, 61, 48),
                primary_dark=(12, 31, 24),
                accent=(34, 197, 94),
                metadata=(134, 160, 146),
            ),
            title="Intro + VT",
            subtitle="Tekst til tale",
            metadata="1. sem 2024",
        ),
        dict(
            output_path=Path("shows/social-psychology-tts/assets/cover.png"),
            palette=Palette(
                primary=(23, 42, 94),
                primary_dark=(16, 23, 40),
                accent=(56, 189, 248),
                metadata=(148, 163, 184),
            ),
            title="Socialpsykologi",
            subtitle="Tekst til tale",
            metadata="1. sem 2024",
        ),
    )

    for cover in covers:
        render_cover(**cover, fonts=fonts)


if __name__ == "__main__":
    main()
