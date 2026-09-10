"""Passive spring-return horn button operated by the fly's right foreleg.

The existing point-grip abstraction is an engineered coupling. Only fly leg
joints are actuated. Button displacement is the sole source of beep events.
"""
import numpy as np

from flyhard.parking_rig import PassiveSlider


class HornButton(PassiveSlider):
    press_threshold = .55

    def __init__(self, root, foot):
        super().__init__(root, foot, 'horn_button', 'rf')

    @property
    def pressed(self):
        return self.value >= self.press_threshold


def make_horn_rig():
    from flyhard.cockpit import WheelRig

    class HornRig(WheelRig):
        # Both 10 Hz decisions and 60 Hz camera frames are exact multiples.
        timestep = 1 / 60000
        command_period = 1 / 300

        def prepare_controls(self):
            self.prepare_diagnostic_ik()
            self.horn.prepare_diagnostic_ik()
            self.wheel_hold = self.diagnostic_action(0.)

        def step_horn(self, right_foreleg_targets):
            action = np.asarray(right_foreleg_targets)
            if action.shape != (7,) or not np.isfinite(action).all():
                raise ValueError('Horn controller must supply seven finite leg targets')
            self.horn.apply(action, self.max_joint_target_rate * self.command_period)
            self.step(self.wheel_hold)

    return HornRig(horn_control=True)
