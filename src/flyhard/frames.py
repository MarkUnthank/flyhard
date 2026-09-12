"""Turning CARLA's raw sensor buffers into pictures and distances.

Pixel arithmetic with no simulator behind it, so it can be checked without one. Both
of these are on the recording loop's critical path at every captured frame, and at six
megapixels the obvious spellings of them cost more in copying than the work itself.
"""
import numpy as np


def colour(bgra):
    """The RGB picture from a BGRA sensor buffer.

    Gathering the three channels by index walks the buffer once. Slicing to a reversed
    view and copying that walks it backwards for the same bytes and takes three times
    as long; the result is identical either way.
    """
    return bgra[..., [2, 1, 0]]


def depth_metres(bgra):
    """CARLA packs depth into 24 bits across the colour channels, scaled to 1 km.

    Read straight off the BGRA buffer the sensor delivers, rather than off an RGB copy
    of it: the channels are about to be indexed one at a time regardless, so the copy
    buys nothing and costs a full-frame gather.
    """
    packed = (bgra[:, :, 2].astype(np.float32)+bgra[:, :, 1].astype(np.float32)*256.
              + bgra[:, :, 0].astype(np.float32)*65536.)
    return 1000.*packed/(256.**3-1)
