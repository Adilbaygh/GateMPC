"""Tests for the closed-loop pool, its controllers and the ASCE indicators.

The trivial-problem and boundary tests the project brief asks for live here. The
one that matters most is the last group: the mismatch between what the plant does
and what the controller believes must actually reach the loop, or the whole H2
experiment measures nothing.
"""
import math
import random

import pytest

from gatempc.canal import G, GateLaw, MPC, PI, Pool, Result, simulate

IDEAL = GateLaw(gamma=18.9105, alpha=1.0, beta=0.5, name="ideal")
POOL = Pool(length=7000.0, bottom_width=7.0, side_slope=1.5,
            target_depth=2.1, tailwater_depth=1.9)
DT = 900.0
A_MIN, A_MAX = 0.0, 2.3


def const(v):
    return lambda _t: v


def run(plant, model, controller, duration=24 * 3600.0, inflow=11.0,
        offtake=1.0, level0=None, noise=0.0, seed=0):
    return simulate(POOL, plant, model, controller, const(inflow), const(offtake),
                    duration, DT, POOL.target_depth,
                    POOL.target_depth if level0 is None else level0,
                    noise, random.Random(seed), A_MIN, A_MAX)


# ---------------------------------------------------------------- gate law

def test_the_law_and_its_inverse_are_consistent():
    law = GateLaw(25.5580, 1.0005, 0.5086)
    for q in (2.0, 7.5, 13.0):
        for dh in (0.2, 0.6, 1.4):
            a = law.opening_for(q, dh)
            assert law.discharge(a, dh) == pytest.approx(q, rel=1e-12)


def test_a_shut_gate_or_no_head_passes_nothing():
    assert IDEAL.discharge(0.0, 1.0) == 0.0
    assert IDEAL.discharge(1.0, 0.0) == 0.0
    assert IDEAL.discharge(1.0, -0.5) == 0.0
    assert IDEAL.opening_for(0.0, 1.0) == 0.0


def test_capacity_matching_equalises_the_two_laws_at_the_reference():
    fitted = GateLaw(25.5580, 1.0005, 0.5086, "fitted")
    matched = fitted.matched_to(IDEAL, a_ref=1.3007, dh_ref=0.2)
    assert matched.discharge(1.3007, 0.2) == pytest.approx(
        IDEAL.discharge(1.3007, 0.2), rel=1e-12)
    assert (matched.alpha, matched.beta) == (fitted.alpha, fitted.beta)


def test_matching_leaves_a_difference_everywhere_else():
    """If it did not, there would be nothing for H2 to measure."""
    fitted = GateLaw(25.5580, 1.0005, 0.5086)
    matched = fitted.matched_to(IDEAL, 1.3007, 0.2)
    far = abs(matched.discharge(0.5, 1.5) / IDEAL.discharge(0.5, 1.5) - 1)
    assert far > 1e-4, "the exponents must still separate the laws away from the point"


# ---------------------------------------------------------------- pool

def test_pool_geometry_follows_from_the_asce_numbers():
    assert POOL.top_width == pytest.approx(7.0 + 2 * 1.5 * 2.1)
    assert POOL.storage_area == pytest.approx(7000.0 * POOL.top_width)
    assert 0 < POOL.delay < 4 * 3600, "delay should be hours, not days"


# ---------------------------------------------------------------- trivial

def test_at_equilibrium_nothing_moves():
    """Trivial problem: balanced inflow, level on target, no noise."""
    matched = IDEAL
    ctrl = PI(kp=0.0, ki=0.0)
    res = run(matched, matched, ctrl, inflow=11.0, offtake=1.0)
    ind = res.indicators(POOL.target_depth, DT)
    # feedforward alone passes inflow minus offtake, so the level holds
    assert ind["MAE"] < 1e-6
    assert ind["IAW"] < 1e-6


def test_a_disturbed_level_is_brought_back_by_the_controller():
    ctrl = PI(kp=8.0, ki=0.004)
    res = run(IDEAL, IDEAL, ctrl, level0=POOL.target_depth + 0.05)
    assert abs(res.level[-1] - POOL.target_depth) < 0.05 * 0.5, \
        "the controller should remove at least half the initial offset"


def step_inflow(before, after, when):
    return lambda t: before if t < when else after


def test_without_control_a_step_in_inflow_runs_the_level_away():
    """A guard on the guard: the disturbance must actually disturb.

    A CONSTANT inflow is not a disturbance -- the initial operating point
    already balances it, and the level holds however dumb the controller is. The
    ASCE scenarios disturb by STEPPING the inflow, so the test must too.
    """
    ctrl = PI(kp=0.0, ki=0.0)
    res = simulate(POOL, IDEAL, IDEAL, ctrl,
                   step_inflow(11.0, 13.5, 2 * 3600.0), const(1.0),
                   24 * 3600.0, DT, POOL.target_depth, POOL.target_depth,
                   0.0, random.Random(0), A_MIN, A_MAX)
    assert res.level[-1] > POOL.target_depth + 0.01, \
        "an uncontrolled pool must drift when the inflow steps up"


def test_the_controller_holds_the_level_against_the_step_that_defeats_no_control():
    """The pair to the test above: same disturbance, but now controlled."""
    open_loop = simulate(POOL, IDEAL, IDEAL, PI(0.0, 0.0),
                         step_inflow(11.0, 13.5, 2 * 3600.0), const(1.0),
                         24 * 3600.0, DT, POOL.target_depth, POOL.target_depth,
                         0.0, random.Random(0), A_MIN, A_MAX)
    closed = simulate(POOL, IDEAL, IDEAL, PI(8.0, 0.004),
                      step_inflow(11.0, 13.5, 2 * 3600.0), const(1.0),
                      24 * 3600.0, DT, POOL.target_depth, POOL.target_depth,
                      0.0, random.Random(0), A_MIN, A_MAX)
    drift_open = abs(open_loop.level[-1] - POOL.target_depth)
    drift_closed = abs(closed.level[-1] - POOL.target_depth)
    assert drift_closed < 0.2 * drift_open, \
        "feedback must remove most of the drift, or the loop is not closed"


def test_the_controller_never_sees_the_inflow():
    """[C98] p.25 allows the level and the gate position, nothing else.

    Two runs with the SAME initial operating point but different later inflow
    must produce the same first command: if the controller could see the inflow,
    it would already differ at the first step.
    """
    a = simulate(POOL, IDEAL, IDEAL, PI(8.0, 0.004),
                 step_inflow(11.0, 13.5, 2 * 3600.0), const(1.0),
                 4 * 3600.0, DT, POOL.target_depth, POOL.target_depth,
                 0.0, random.Random(0), A_MIN, A_MAX)
    b = simulate(POOL, IDEAL, IDEAL, PI(8.0, 0.004),
                 step_inflow(11.0, 2.7, 2 * 3600.0), const(1.0),
                 4 * 3600.0, DT, POOL.target_depth, POOL.target_depth,
                 0.0, random.Random(0), A_MIN, A_MAX)
    assert a.opening[0] == b.opening[0]


# ---------------------------------------------------------------- indicators

def test_indicators_match_the_clemmens_definitions():
    ctrl = PI(kp=5.0, ki=0.002)
    res = run(IDEAL, IDEAL, ctrl, level0=POOL.target_depth + 0.03)
    ind = res.indicators(POOL.target_depth, DT)
    err = [abs(y - POOL.target_depth) for y in res.level]
    assert ind["MAE"] == pytest.approx(max(err) / POOL.target_depth)
    assert ind["IAE"] == pytest.approx(
        sum(err) / len(err) / POOL.target_depth, rel=1e-12)
    assert ind["MAE"] >= ind["IAE"], "a maximum cannot be below a mean"
    assert ind["IAQ"] >= 0 and ind["IAW"] >= 0


def test_ste_takes_the_worst_of_the_two_twelve_hour_windows():
    """[C98] eq. (4), Model/02 section 6.

    An offset that is present in the first period and gone by the end of the
    second must still be reported. Reading only the tail of the record hides it;
    that is what an earlier version of indicators() did.
    """
    target = 2.1
    n = int(24 * 3600 / DT)                       # 96 steps
    half = n // 2
    level = [target + 0.10] * half + [target] * half
    res = Result(times=[i * DT for i in range(n)], level=level,
                 opening=[1.0] * n, discharge=[10.0] * n,
                 saturated=[False] * n, n_steps=n)
    ind = res.indicators(target, DT)
    assert ind["StE"] == pytest.approx(0.10 / target), \
        "the first-period offset must not be averaged away by a quiet second half"


def test_a_window_of_a_run_is_a_run():
    ctrl = PI(kp=6.0, ki=0.003)
    res = run(IDEAL, IDEAL, ctrl, level0=POOL.target_depth + 0.04)
    half = len(res.level) // 2
    first, second = res.window(0, half), res.window(half, len(res.level))
    assert len(first.level) == len(second.level) == half
    assert first.saturated_steps + second.saturated_steps == res.saturated_steps
    whole = res.indicators(POOL.target_depth, DT)
    assert first.indicators(POOL.target_depth, DT)["MAE"] <= whole["MAE"]


def test_iaq_and_iaw_are_different_indicators():
    """[C98] (5) is discharge, (6) is gate position. Conflating them was a real
    error in this project's early drafts."""
    ctrl = PI(kp=6.0, ki=0.003)
    res = run(IDEAL, IDEAL, ctrl, level0=POOL.target_depth + 0.04)
    ind = res.indicators(POOL.target_depth, DT)
    assert ind["IAQ"] != ind["IAW"]


# ---------------------------------------------------------------- mismatch

def test_a_mismatched_gate_law_changes_the_delivered_discharge():
    """The experiment's premise. If this fails, H2 measures nothing."""
    fitted = GateLaw(25.5580, 1.0005, 0.5086).matched_to(IDEAL, 1.3007, 0.2)
    dh = 1.2                                    # away from the matching point
    q_wanted = 9.0
    a = IDEAL.opening_for(q_wanted, dh)         # controller believes the ideal law
    delivered = fitted.discharge(a, dh)         # the plant does something else
    assert abs(delivered / q_wanted - 1) > 1e-4


def test_matched_and_mismatched_runs_differ():
    fitted = GateLaw(25.5580, 1.0005, 0.5086).matched_to(IDEAL, 1.3007, 0.2)
    matched = run(fitted, fitted, PI(6.0, 0.003), level0=POOL.target_depth + 0.05)
    crossed = run(fitted, IDEAL, PI(6.0, 0.003), level0=POOL.target_depth + 0.05)
    assert matched.level != crossed.level


def test_saturation_is_counted_not_hidden():
    """An impossible demand must be reported as saturation, not silently clipped."""
    ctrl = PI(kp=500.0, ki=0.5)
    res = run(IDEAL, IDEAL, ctrl, level0=POOL.target_depth + 0.5)
    assert res.saturated_steps > 0
    assert res.indicators(POOL.target_depth, DT)["saturated_fraction"] > 0


def test_a_minimum_gate_step_suppresses_small_movements():
    """[C98] p. 24: the smallest movement is 0.5% of the gate height.

    With the deadband on, the gate must take fewer distinct positions and never
    move by less than the step -- and the run must still be a control run, not a
    frozen gate.
    """
    ctrl = PI(kp=6.0, ki=0.003)
    free = run(IDEAL, IDEAL, ctrl, level0=POOL.target_depth + 0.05)
    step = 0.005 * 2.3
    held = simulate(POOL, IDEAL, IDEAL, PI(kp=6.0, ki=0.003),
                    const(11.0), const(1.0), 24 * 3600.0, DT,
                    POOL.target_depth, POOL.target_depth + 0.05,
                    0.0, random.Random(0), A_MIN, A_MAX, step)
    moves = [abs(b - a) for a, b in zip(held.opening, held.opening[1:]) if b != a]
    assert all(m >= step - 1e-12 for m in moves), "no movement below the step"
    assert len(set(held.opening)) < len(set(free.opening))
    assert len(set(held.opening)) > 1, "the gate must still be controlling"


def test_the_controller_never_sees_the_plants_capacity():
    """The saturation cap must come from the controller's OWN gate law.

    Two plants of very different size behind the same model: at the first step,
    before any plant behaviour can reach the level, the demanded opening must be
    identical. It is not if the cap leaks from the plant -- which is what an
    earlier version of simulate() did.
    """
    small = GateLaw(IDEAL.gamma * 0.5, 1.0, 0.5, "half")
    large = GateLaw(IDEAL.gamma * 2.0, 1.0, 0.5, "double")
    hungry = PI(kp=1000.0, ki=0.0)          # always asks for everything
    a = run(small, IDEAL, hungry, level0=POOL.target_depth + 0.3)
    hungry2 = PI(kp=1000.0, ki=0.0)
    b = run(large, IDEAL, hungry2, level0=POOL.target_depth + 0.3)
    assert a.opening[0] == b.opening[0] == A_MAX


# ---------------------------------------------------------------- determinism

def test_the_same_seed_gives_the_same_run():
    a = run(IDEAL, IDEAL, PI(6.0, 0.003), noise=0.0015, seed=42)
    b = run(IDEAL, IDEAL, PI(6.0, 0.003), noise=0.0015, seed=42)
    assert a.level == b.level and a.opening == b.opening


def test_different_seeds_give_different_runs():
    a = run(IDEAL, IDEAL, PI(6.0, 0.003), noise=0.0015, seed=1)
    b = run(IDEAL, IDEAL, PI(6.0, 0.003), noise=0.0015, seed=2)
    assert a.level != b.level


# ---------------------------------------------------------------- mpc

def test_mpc_moves_the_command_towards_removing_the_error():
    mpc = MPC(q_weight=1.0, r_weight=1e-4, horizon=4, control_horizon=1,
              area=POOL.storage_area, dt=DT)
    up = mpc.command(+0.05, DT, feedforward=10.0, lo=0.0, hi=30.0)
    down = mpc.command(-0.05, DT, feedforward=10.0, lo=0.0, hi=30.0)
    assert up > 10.0 > down, "too high must open, too low must close"


def test_a_heavier_movement_penalty_makes_mpc_gentler():
    soft = MPC(1.0, 1e-6, 4, 1, POOL.storage_area, DT)
    firm = MPC(1.0, 1e2, 4, 1, POOL.storage_area, DT)
    assert (soft.command(0.05, DT, 10.0, 0.0, 30.0) - 10.0
            > firm.command(0.05, DT, 10.0, 0.0, 30.0) - 10.0)


def test_mpc_respects_the_bounds_it_is_given():
    mpc = MPC(1.0, 1e-9, 8, 1, POOL.storage_area, DT)
    assert mpc.command(10.0, DT, 10.0, 0.0, 12.0) == 12.0
    assert mpc.command(-10.0, DT, 10.0, 0.0, 12.0) == 0.0
