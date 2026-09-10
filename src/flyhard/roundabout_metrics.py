"""Predeclared route and indicator scoring, kept outside the policy inputs."""
import numpy as np


def episode_complete(episode):
    # The route follower stops within 3m of its goal; allow centimetre rounding.
    return episode["max_progress"] >= episode["length"] - 3.01 and episode["max_route_error_m"] < 5


def score_signals(progress, measured, route):
    p, s = np.asarray(progress), np.asarray(measured)
    ex = route["exit_s"]
    pre = p < ex - 40
    hold = (p >= ex - 14) & (p <= ex + 5)
    post = p >= ex + 20
    activation = np.flatnonzero(s == "right")
    first = float(p[activation[0]]) if len(activation) else None
    checks = {"completed": bool(p[-1] >= route["length"] - 3.01),
              "activation_window": first is not None and ex - 40 <= first <= ex - 16,
              "no_left": not bool(np.any(s == "left")),
              "no_early_signal": not bool(np.any(s[pre] != "off")),
              "held_through_exit": bool(hold.any() and np.all(s[hold] == "right")),
              "cancelled_after_exit": bool(post.any() and np.all(s[post] == "off"))}
    return {"checks": checks, "passed": all(checks.values()), "first_right_progress_m": first,
            "hold_right_fraction": float(np.mean(s[hold] == "right")) if hold.any() else None}
