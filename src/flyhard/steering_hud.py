"""Steering readouts shared by the split-screen and cabin presentation renders."""
from functools import lru_cache
import math
from pathlib import Path

from PIL import ImageDraw, ImageFont


@lru_cache(maxsize=8)
def font(size):
    return ImageFont.truetype(str(Path(__file__).resolve().parents[2]/'assets/fonts/Geist.ttf'),size)


def draw_steering_readout(canvas, *, requested_angle, wheel_angle, applied_steer):
    """Use the last recorded neural request and this camera frame's measurements.

    Angles are radians at the boundary. Positive values map to CARLA's right
    steering, negative values to left. Requests are highlighted at the same
    one-decimal-degree precision shown in the numeric readout.
    """
    if not all(math.isfinite(value) for value in [requested_angle,wheel_angle,applied_steer]):
        raise ValueError('Steering readouts require finite recorded values')
    requested = round(math.degrees(requested_angle),1) or 0.0
    wheel = round(math.degrees(wheel_angle),1) or 0.0
    steer = round(float(applied_steer),3) or 0.0
    size = max(18,round(canvas.width/80))
    face = font(size)
    margin = max(16,round(canvas.width/80))
    height = max(48,round(canvas.height*56/1080))
    top = canvas.height-height
    center = top+height//2
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0,top,canvas.width,canvas.height),fill='black')
    draw.line((margin,top,canvas.width-margin,top),fill='#242424')
    x = margin
    for label,active in [('Request left',requested < 0),('Request right',requested > 0)]:
        width = round(draw.textlength(label,font=face))+24
        draw.rounded_rectangle((x,center-18,x+width,center+18),radius=6,
            fill='#eeeeee' if active else '#111111',outline='#eeeeee' if active else '#333333')
        draw.text((x+12,center),label,anchor='lm',font=face,fill='black' if active else '#929292')
        x += width+10
    draw.text((x+18,center),f'Target {requested:+.1f}°',anchor='lm',font=face,fill='#cccccc')
    draw.text((canvas.width-margin,center),f'Wheel {wheel:+.1f}°    CARLA steer {steer:+.3f}',
        anchor='rm',font=face,fill='white')
    return {'request_left':requested < 0,'request_right':requested > 0,
        'target_degrees':requested,'wheel_degrees':wheel,'carla_steer':steer}
