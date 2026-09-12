#!/usr/bin/env python3
"""Check that a rendered sponsor panel reproduces the delivered artwork's own values.

Renders one panel and compares its percentiles against the source texture. Whites
that come back dim mean the composite is dulling paid artwork; whites that come back
clipped mean it is being brightened beyond what the advertiser supplied. Both are
wrong, and this is what EXPOSURE in flyhard.sponsor_view is set from.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from flyhard.live_livery import verify_live_livery
from flyhard.sponsor_view import SponsorView


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--asset', required=True)
    parser.add_argument('--out', default='work')
    parser.add_argument('--tolerance', type=float, default=14.,
                        help='Permitted difference in the 99th percentile, in levels')
    args = parser.parse_args()

    manifest = verify_live_livery(args.asset, Path(args.out))
    sponsor = manifest['sponsors'][0]
    texture = np.asarray(Image.open(Path(args.asset)/sponsor['texture']).convert('RGB'))
    view = SponsorView(args.asset, manifest, [0., 0., .75])
    try:
        relative = np.eye(4)
        relative[:3, 3] = [-7.4, 0., 3.05]
        angle = np.radians(-11.5)
        relative[:3, :3] = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0],
                                     [-np.sin(angle), 0, np.cos(angle)]])
        rendered, _ = view.render(relative, 72, np.zeros((960, 1248, 3), np.float32),
                                  np.full((960, 1248), 900., np.float32))
    finally:
        view.close()
    # Only the highlights are comparable. The frame also contains the car structure
    # mesh, which exists so the panels self-occlude and which the native depth buffer
    # hides in a real frame, so its pixels drag the midtones and are not the subject.
    lit = rendered[rendered.sum(axis=2) > 8]
    if not len(lit):
        raise SystemExit('No sponsor pixels rendered; the panel is not in frame')
    source = {p: float(np.percentile(texture, p)) for p in (50, 90, 99)}
    shown = {p: float(np.percentile(lit, p)) for p in (50, 90, 99)}
    report = {'asset': str(args.asset), 'revision': manifest['revision'],
              'texture': sponsor['texture'], 'source_percentiles': source,
              'rendered_percentiles': shown,
              'highlight_difference': round(shown[99]-source[99], 1),
              'note': 'Only the 99th percentile is compared: it is the artwork\'s own '
                      'highlights. Lower percentiles include the structure mesh, which a '
                      'real frame hides behind the car.',
              'within_tolerance': abs(shown[99]-source[99]) <= args.tolerance}
    Path(args.out, 'sponsor-exposure.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    if not report['within_tolerance']:
        raise SystemExit('Rendered highlights do not match the delivered artwork')


if __name__ == '__main__':
    main()
