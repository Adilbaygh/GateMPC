"""Closed-loop canal pool: an integrator-delay plant with a gate boundary.

Scope, and why it is drawn this narrowly
----------------------------------------
The question this serves is not "how does this canal behave" but "how much does
a controller lose by carrying the benchmark's gate law instead of the identified
one". That is a PAIRED difference: the pool is identical in both arms, so what
the pool model gets wrong largely cancels, while the gate law -- the only thing
that differs -- is a boundary condition and is represented exactly.

So the pool is an integrator with delay rather than a Saint-Venant reach. The
cost is real and is declared: wave dynamics are absent, so absolute IAE values
here are not realistic canal performance. Only the relative difference is
reported. See requirements/hypotheses.md, H2 stage-two protocol.

Where the model mismatch enters
-------------------------------
The controller computes a DISCHARGE command and inverts its own gate law to get
an opening; the plant then applies ITS gate law to that opening. This mirrors
how canal structures are actually operated -- a supervisory loop asks for a flow
and a local loop inverts the rating -- and it isolates the mismatch in exactly
the place being studied.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

G = 9.80665


@dataclass(frozen=True)
class GateLaw:
    """Q = gamma * a**alpha * dh**beta, and its inverse."""
    gamma: float
    alpha: float
    beta: float
    name: str = ""

    def discharge(self, a: float, dh: float) -> float:
        if a <= 0.0 or dh <= 0.0:
            return 0.0
        return self.gamma * a ** self.alpha * dh ** self.beta

    def opening_for(self, q: float, dh: float) -> float:
        """Opening this law thinks will deliver ``q``. The controller uses this."""
        if q <= 0.0 or dh <= 0.0:
            return 0.0
        return (q / (self.gamma * dh ** self.beta)) ** (1.0 / self.alpha)

    def matched_to(self, other: "GateLaw", a_ref: float, dh_ref: float) -> "GateLaw":
        """A copy rescaled to deliver the same discharge as ``other`` at a point.

        Without this the two plants would differ in capacity, and the experiment
        would mostly measure "these gates are a different size" -- which says
        nothing about anyone's model. hypotheses.md fixes the reference point.
        """
        target = other.discharge(a_ref, dh_ref)
        mine = self.discharge(a_ref, dh_ref)
        if mine <= 0:
            raise ValueError("cannot match a law that delivers nothing at the reference")
        return GateLaw(self.gamma * target / mine, self.alpha, self.beta,
                       self.name + "+matched")


@dataclass(frozen=True)
class Pool:
    """Integrator-delay pool, parameters derived from ASCE Test Case 2."""
    length: float          # m
    bottom_width: float    # m
    side_slope: float      # horizontal : vertical
    target_depth: float    # m
    tailwater_depth: float  # m, level below the gate, held fixed

    @property
    def top_width(self) -> float:
        return self.bottom_width + 2.0 * self.side_slope * self.target_depth

    @property
    def storage_area(self) -> float:
        return self.length * self.top_width

    @property
    def delay(self) -> float:
        """L / (v + c) with c = sqrt(g y). A standard first estimate."""
        area = (self.bottom_width + self.side_slope * self.target_depth) * self.target_depth
        velocity = 1.0  # m/s, order of magnitude for a main canal; see note below
        celerity = math.sqrt(G * self.target_depth)
        return self.length / (velocity + celerity) if area > 0 else 0.0


@dataclass
class Result:
    """One closed-loop run."""
    times: list[float] = field(default_factory=list)
    level: list[float] = field(default_factory=list)
    opening: list[float] = field(default_factory=list)
    discharge: list[float] = field(default_factory=list)
    saturated: list[bool] = field(default_factory=list)
    n_steps: int = 0

    @property
    def saturated_steps(self) -> int:
        return sum(1 for s in self.saturated if s)

    def window(self, start: int, stop: int) -> "Result":
        """A slice of the run, so indicators can be taken per 12-hour period.

        [C98] p. 26 asks for the indicators over each 12-hour period of the
        test, not only over the whole of it.
        """
        return Result(self.times[start:stop], self.level[start:stop],
                      self.opening[start:stop], self.discharge[start:stop],
                      self.saturated[start:stop], max(0, stop - start))

    def _steady_windows(self, dt: float) -> list[tuple[int, int]]:
        """The two-hour windows [C98] eq. (4) averages over.

        The test is divided into 12-hour periods and the steady-state error is
        measured over the LAST TWO HOURS OF EACH, then the worst is reported --
        for a 24-hour test that is 10-12 h and 22-24 h. An earlier version of
        this method used the tail of the record only, which silently dropped the
        first period and could not see an offset that had been corrected by the
        end.
        """
        n = len(self.level)
        period = max(1, int(round(12 * 3600 / dt)))
        width = max(1, int(round(2 * 3600 / dt)))
        ends = list(range(period, n + 1, period)) or [n]
        if ends[-1] != n:                      # a trailing partial period counts
            ends.append(n)
        return [(max(0, e - width), e) for e in ends]

    def indicators(self, target: float, dt: float) -> dict[str, float]:
        """ASCE indicators, [C98] equations (2)-(6); see Model/02 section 6.

        MAE, IAE and StE are normalised by the target level and dimensionless;
        IAQ is the integrated absolute change in DISCHARGE and IAW the same for
        gate POSITION. Those two are distinct indicators in [C98] and were
        conflated in an earlier draft of this project.
        """
        err = [abs(y - target) for y in self.level]
        n = len(self.level)
        mae = max(err) / target
        iae = (sum(err) / n) / target          # (dt/T) sum, with T = dt * n
        ste = max(abs(sum(self.level[a:b]) / (b - a) - target)
                  for a, b in self._steady_windows(dt)) / target
        iaq = (sum(abs(b - a) for a, b in zip(self.discharge, self.discharge[1:]))
               - abs(self.discharge[-1] - self.discharge[0]))
        iaw = (sum(abs(b - a) for a, b in zip(self.opening, self.opening[1:]))
               - abs(self.opening[-1] - self.opening[0]))
        return {"MAE": mae, "IAE": iae, "StE": ste, "IAQ": iaq, "IAW": iaw,
                "saturated_fraction": self.saturated_steps / max(n, 1)}


class PI:
    """Discrete PI on the level error, output in DISCHARGE, with anti-windup."""

    def __init__(self, kp: float, ki: float):
        self.kp, self.ki = kp, ki
        self.integral = 0.0

    def reset(self) -> None:
        self.integral = 0.0

    def command(self, error: float, dt: float, feedforward: float,
                lo: float, hi: float) -> float:
        trial = feedforward + self.kp * error + self.ki * (self.integral + error * dt)
        if lo < trial < hi:                      # anti-windup: hold on saturation
            self.integral += error * dt
        return min(max(trial, lo), hi)


class MPC:
    """Receding-horizon control of the integrator-delay pool, in DISCHARGE.

    The prediction model is the controller's own pool model. The optimum of the
    unconstrained quadratic problem is available in closed form; the command is
    then saturated, and how often that binds is reported rather than assumed
    harmless.
    """

    def __init__(self, q_weight: float, r_weight: float, horizon: int,
                 control_horizon: int, area: float, dt: float):
        self.q, self.r = q_weight, r_weight
        self.np_, self.nc = horizon, control_horizon
        self.area, self.dt = area, dt

    def reset(self) -> None:
        pass

    def command(self, error: float, dt: float, feedforward: float,
                lo: float, hi: float) -> float:
        """Level error is removed over the horizon by a change in outflow.

        With A dH/dt = Qin - Qout, holding a constant correction u over Np steps
        moves the level by -u Np dt / A. Minimising q (error - u Np dt / A)^2 +
        r u^2 gives the closed form below.
        """
        k = self.np_ * self.dt / self.area
        u = self.q * k * error / (self.q * k * k + self.r)
        return min(max(feedforward + u, lo), hi)


def simulate(pool: Pool, plant_law: GateLaw, model_law: GateLaw, controller,
             inflow, offtake, duration: float, dt: float,
             target: float, initial_level: float,
             level_noise: float, rng,
             a_min: float, a_max: float, min_step: float = 0.0) -> Result:
    """One closed-loop run.

    ``plant_law`` is what the structure does; ``model_law`` is what the
    controller believes. Passing the same object to both is the matched case.

    What the controller may see. [C98] p. 25 is explicit: the controller gets
    the water level at the downstream end of the pool at the regulation step,
    and the gate position -- nothing else. An earlier version of this function
    fed it the delayed inflow as a feedforward term, which made the feedforward
    exact, held the level perfectly still whatever the disturbance, and quietly
    removed the control problem altogether. A test that asserted an uncontrolled
    pool must drift caught it. The command is now built from the initial
    operating discharge plus feedback on the level error only.

    The same rule governs the saturation bound. The largest discharge the
    controller may ask for is the largest its OWN law says a fully open gate
    delivers -- not the plant's. An earlier version took that bound from
    ``plant_law``, which handed the mismatched controller the very capacity it
    is not supposed to know; the two caps differ by about the size of the effect
    H2 measures, so the leak was not harmless.

    ``min_step`` is the smallest gate movement the actuator can execute; a
    smaller demand leaves the gate where it is. [C98] p. 24 sets it at 0.5 per
    cent of the gate height and places NO limit on the largest movement or on
    gate speed. It defaults to zero here because the H2 stage-two protocol was
    registered without it; it is switched on as a declared sensitivity axis
    rather than folded into the headline after the fact.
    """
    res = Result()
    level = initial_level
    delay_steps = max(1, int(round(pool.delay / dt)))
    history = [inflow(0.0)] * delay_steps
    steps = int(round(duration / dt))
    # The operating point the structure starts from. The controller may know
    # this -- it is reading its own gate and its own level in steady flow -- but
    # it never learns the inflow again after t = 0.
    q_operating = max(inflow(0.0) - offtake(0.0), 0.0)
    # The gate starts where that operating point puts it, not shut: with a
    # ``min_step`` deadband a gate started at zero would have to earn its way
    # back to the operating opening, which is an artefact, not a plant property.
    opening = model_law.opening_for(
        q_operating, max(target - pool.tailwater_depth, 1e-6))

    for i in range(steps):
        t = i * dt
        dh = level - pool.tailwater_depth
        measured = level + rng.uniform(-level_noise, level_noise)
        error = measured - target          # positive: too high, open the gate

        lo, hi = 0.0, model_law.discharge(a_max, max(dh, 1e-6))
        q_cmd = controller.command(error, dt, q_operating, lo, hi)

        demand = model_law.opening_for(q_cmd, max(dh, 1e-6))
        limited = demand >= a_max or demand <= a_min
        demand = min(max(demand, a_min), a_max)
        opening = opening if abs(demand - opening) < min_step else demand

        q_out = plant_law.discharge(opening, max(dh, 0.0))
        q_in_delayed = history.pop(0)
        history.append(inflow(t))

        level += dt * (q_in_delayed - q_out - offtake(t)) / pool.storage_area

        res.times.append(t)
        res.level.append(level)
        res.opening.append(opening)
        res.discharge.append(q_out)
        res.saturated.append(limited)
    res.n_steps = steps
    return res
