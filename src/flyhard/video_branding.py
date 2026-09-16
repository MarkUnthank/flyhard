"""Website wordmark in the unused right side of the black video header."""
from functools import lru_cache
from pathlib import Path

from PIL import ImageDraw, ImageFont


@lru_cache(maxsize=1)
def site_font():
    return ImageFont.truetype(str(Path(__file__).resolve().parents[2] / 'assets/fonts/Geist.ttf'), 26)


def draw_site_brand(canvas):
    assert canvas.size == (1920, 1080)
    ImageDraw.Draw(canvas).text((1896, 23), 'thedrivingfly.com', font=site_font(),
                               anchor='ra', fill='#eeeeee')
