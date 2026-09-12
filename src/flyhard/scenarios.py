"""Registry of trainable scenarios, so one data/training script serves all of them.

Each entry names the modules that define a behaviour: the geometry and scoring, the
training-only teacher, and the native CARLA world. Everything downstream reads the
registry rather than importing a particular scenario, which is what keeps the
pedal policy identical across behaviours instead of quietly specialising per task.
"""
import importlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    name: str
    core: str
    teacher: str
    world: str
    world_class: str
    claim: str

    @property
    def modules(self):
        return importlib.import_module(self.core), importlib.import_module(self.teacher)

    def sources(self):
        return [f"src/{m.replace('.', '/')}.py" for m in (self.core, self.teacher)]

    def load_world(self):
        return getattr(importlib.import_module(self.world), self.world_class)


REGISTRY = {
    'crossing': Scenario(
        name='crossing', core='flyhard.crossing', teacher='flyhard.crossing_teacher',
        world='flyhard.crossing_world', world_class='CrossingWorld',
        claim='Supervised pedal control for stopping at a marked pedestrian crossing.'),
    'junction': Scenario(
        name='junction', core='flyhard.junction', teacher='flyhard.junction_teacher',
        world='flyhard.junction_world', world_class='JunctionWorld',
        claim='Supervised pedal control for giving way at an unsignalled junction, '
              'including to a vehicle under blue lights arriving from either side.'),
}


def get(name):
    if name not in REGISTRY:
        raise ValueError(f'Unknown scenario {name!r}; have {sorted(REGISTRY)}')
    return REGISTRY[name]
