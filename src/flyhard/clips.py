"""Addressable clip library so an edit can be recut without re-running CARLA.

Every capture writes one take directory holding its camera renders, its trace and
its own manifest. The library indexes those manifests; an edit plan refers to
takes by stable identifier and never by path, so re-ordering, trimming or
swapping a shot is a plan change rather than a new recording.
"""
from dataclasses import dataclass, asdict, field
import hashlib
import json
from pathlib import Path

SCHEMA = 'flyhard-clip-library-v1'
OUTCOMES = ('success', 'failure')
# Camera names come from flyhard.scenario_cameras; a take need not carry all of them.
CAMERAS = ('wide', 'chase', 'cabin')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def take_id(scenario, seed, attempt):
    """Stable identifier. Same scenario, seed and attempt always address the same take."""
    if not scenario or '/' in scenario:
        raise ValueError('Scenario must be a non-empty path-safe name')
    return f'{scenario}-s{int(seed):05d}-a{int(attempt):02d}'


@dataclass
class Take:
    scenario: str
    seed: int
    attempt: int
    outcome: str
    duration_seconds: float
    fps: int
    cameras: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    label: str = ''
    # Which policy drove it. A control condition looks exactly like a badly trained fly
    # from the outside, so a take that was not the trained policy has to say so on
    # itself; a caption or a folder name is not somewhere provenance can live.
    policy: str = 'trained'
    checkpoint_sha256: str = ''
    sponsor_revision: int = 0
    sponsor_layout: int = 0
    notes: str = ''

    @property
    def identifier(self):
        return take_id(self.scenario, self.seed, self.attempt)

    def validate(self):
        if self.outcome not in OUTCOMES:
            raise ValueError(f'Outcome must be one of {OUTCOMES}, got {self.outcome!r}')
        if not self.cameras:
            raise ValueError('A take must record at least one camera')
        unknown = set(self.cameras) - set(CAMERAS)
        if unknown:
            raise ValueError(f'Unknown cameras {sorted(unknown)}')
        if not self.duration_seconds > 0:
            raise ValueError('Duration must be positive')
        if self.fps <= 0:
            raise ValueError('fps must be positive')
        return self

    def record(self):
        return {'schema': SCHEMA, 'id': self.identifier, **asdict(self)}


class ClipLibrary:
    """Directory of takes grouped by scenario and outcome."""

    def __init__(self, root):
        self.root = Path(root)

    def directory(self, take):
        return self.root / take.scenario / take.outcome / take.identifier

    def register(self, take, *, verify=True):
        """Write a take manifest. Verifying checks every referenced camera file exists."""
        take.validate()
        directory = self.directory(take)
        directory.mkdir(parents=True, exist_ok=True)
        record = take.record()
        if verify:
            digests = {}
            for name, relative in take.cameras.items():
                path = directory / relative
                if not path.is_file():
                    raise FileNotFoundError(f'Camera {name} missing at {path}')
                digests[name] = sha(path)
            record['camera_sha256'] = digests
        (directory / 'take.json').write_text(json.dumps(record, indent=2) + '\n')
        return directory

    def takes(self):
        result = []
        for manifest in sorted(self.root.glob('*/*/*/take.json')):
            record = json.loads(manifest.read_text())
            if record.get('schema') != SCHEMA:
                raise ValueError(f'Unexpected clip schema in {manifest}')
            record['directory'] = str(manifest.parent)
            result.append(record)
        return result

    def find(self, scenario=None, outcome=None, camera=None, min_seconds=0.):
        """Select takes for an edit plan. Ordering is deterministic by identifier."""
        selected = []
        for record in self.takes():
            if scenario and record['scenario'] != scenario:
                continue
            if outcome and record['outcome'] != outcome:
                continue
            if camera and camera not in record['cameras']:
                continue
            if record['duration_seconds'] < min_seconds:
                continue
            selected.append(record)
        return sorted(selected, key=lambda r: r['id'])

    def resolve(self, identifier, camera, sponsored=True):
        """Absolute path to one camera render of one take.

        Sponsors are composited over the plain CARLA frame in a later pass and the
        plain frame is kept beside the result, so a sponsor-free cut costs a different
        filename rather than another recording. Where a camera was never sponsored the
        two are the same file and this returns it either way.
        """
        for record in self.takes():
            if record['id'] == identifier:
                if camera not in record['cameras']:
                    raise KeyError(f'Take {identifier} has no {camera} camera; has {sorted(record["cameras"])}')
                relative = Path(record['cameras'][camera])
                if not sponsored:
                    plain = relative.with_name(relative.name.replace('-sponsored', ''))
                    if (Path(record['directory'])/plain).exists():
                        relative = plain
                return Path(record['directory']) / relative, record
        raise KeyError(f'No take {identifier} in {self.root}')

    def index(self):
        """Aggregate manifest written at the library root for quick inspection."""
        records = self.takes()
        summary = {}
        for record in records:
            counts = summary.setdefault(record['scenario'], {'success': 0, 'failure': 0, 'seconds': 0.})
            counts[record['outcome']] += 1
            counts['seconds'] = round(counts['seconds'] + record['duration_seconds'], 3)
        payload = {'schema': SCHEMA, 'take_count': len(records), 'by_scenario': summary,
                   'takes': [{k: r[k] for k in ['id', 'scenario', 'outcome', 'duration_seconds',
                                                'label', 'directory']} for r in records]}
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'index.json').write_text(json.dumps(payload, indent=2) + '\n')
        return payload
