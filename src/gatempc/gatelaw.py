"""Identification of a gate discharge relation from real canal observations.

The relation, as a generalised power law (Model/01_plant_model.md, 4.3):

    Q = G * a**alpha * dh**beta,      dh = (H1 - z0) - max(H2 - z0, a)

The ideal submerged-orifice law used in the ASCE benchmark is the special case
``alpha = 1, beta = 0.5``, with ``G = Cd * W * sqrt(2 g)``.

Why the exponents and not the coefficient
-----------------------------------------
``G`` lumps the discharge coefficient with the effective gate width, and the two
gates at USGS 09522700 have no published width. A difference in ``G`` between
this structure and the benchmark could mean the physics differs or simply that
the gates are a different size, and nothing in the archive separates those. The
exponents are dimensionless and width-free: no gate width can change them. They
are therefore the honest comparable, which is what requirements/hypotheses.md H1
pre-registers.

Why z0 is searched on a grid
----------------------------
``z0`` enters only through the ``max(H2 - z0, a)`` switch between submerged and
free flow. In fully submerged flow ``dh = H1 - H2`` and ``z0`` cancels exactly,
so the objective is flat in ``z0`` over any region where no sample is free, and
kinked where samples cross the switch. A gradient method would settle in the
nearest flat spot and report it as an optimum. The grid search is task V6 in
Model/01_plant_model.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

FT = 0.3048                     # exact, by definition
FT3 = FT ** 3                   # exact
G_ACCEL = 9.80665               # standard gravity, m/s^2

IDEAL_ALPHA = 1.0
IDEAL_BETA = 0.5


@dataclass(frozen=True)
class Sample:
    """One simultaneous observation, in SI units."""
    time: str
    a: float                    # gate opening, m
    h1: float                   # headwater stage, m (gauge datum)
    h2: float                   # tailwater stage, m (gauge datum)
    q: float                    # discharge, m3/s
    year: int


@dataclass
class Fit:
    """A fitted power law and the diagnostics needed to judge it."""
    z0: float                   # m, gauge datum
    log_gamma: float
    alpha: float
    beta: float
    sse: float                  # in log space
    n: int
    se_alpha: float = float("nan")
    se_beta: float = float("nan")
    free_fraction: float = float("nan")
    extras: dict = field(default_factory=dict)

    @property
    def gamma(self) -> float:
        return math.exp(self.log_gamma)

    def predict(self, s: Sample) -> float:
        dh = head_difference(s, self.z0)
        if s.a <= 0 or dh <= 0:
            return 0.0
        return self.gamma * s.a ** self.alpha * dh ** self.beta


def head_difference(s: Sample, z0: float) -> float:
    """Effective head across the gate for a given sill elevation.

    Submerged when the tailwater depth exceeds the opening, free otherwise; the
    switch is the only place z0 is observable at all.
    """
    h1 = s.h1 - z0
    h2 = s.h2 - z0
    return h1 - max(h2, s.a)


def is_free(s: Sample, z0: float) -> bool:
    return (s.h2 - z0) <= s.a


def usable(s: Sample, z0: float) -> bool:
    """Samples the law can be fitted on: gate open, positive head."""
    return s.a > 0.0 and s.q > 0.0 and head_difference(s, z0) > 0.0


# ---------------------------------------------------------------- inner solve

def fit_loglinear(samples: list[Sample], z0: float,
                  fix_alpha: float | None = None,
                  fix_beta: float | None = None) -> Fit | None:
    """Least squares for ln Q = ln G + alpha ln a + beta ln dh, at fixed z0.

    Solved in closed form through the normal equations of a two-regressor
    regression; ``fix_alpha``/``fix_beta`` constrain the model to the ideal law,
    which is what the synthetic baseline uses.
    """
    xs, ys, zs = [], [], []
    n_free = 0
    for s in samples:
        if not usable(s, z0):
            continue
        dh = head_difference(s, z0)
        xs.append(math.log(s.a))
        ys.append(math.log(dh))
        zs.append(math.log(s.q))
        if is_free(s, z0):
            n_free += 1
    n = len(zs)
    if n < 10:
        return None

    if fix_alpha is not None and fix_beta is not None:
        resid = [zs[i] - fix_alpha * xs[i] - fix_beta * ys[i] for i in range(n)]
        log_gamma = sum(resid) / n
        sse = sum((r - log_gamma) ** 2 for r in resid)
        return Fit(z0, log_gamma, fix_alpha, fix_beta, sse, n,
                   free_fraction=n_free / n)

    mx = sum(xs) / n
    my = sum(ys) / n
    mz = sum(zs) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    sxz = sum((xs[i] - mx) * (zs[i] - mz) for i in range(n))
    syz = sum((ys[i] - my) * (zs[i] - mz) for i in range(n))

    det = sxx * syy - sxy * sxy
    if abs(det) < 1e-12 * max(1.0, sxx * syy):
        return None                        # regressors collinear at this z0
    alpha = (syy * sxz - sxy * syz) / det
    beta = (sxx * syz - sxy * sxz) / det
    log_gamma = mz - alpha * mx - beta * my

    sse = 0.0
    for i in range(n):
        r = zs[i] - (log_gamma + alpha * xs[i] + beta * ys[i])
        sse += r * r
    dof = n - 3
    se_alpha = se_beta = float("nan")
    if dof > 0 and det != 0:
        s2 = sse / dof
        se_alpha = math.sqrt(max(s2 * syy / det, 0.0))
        se_beta = math.sqrt(max(s2 * sxx / det, 0.0))
    return Fit(z0, log_gamma, alpha, beta, sse, n, se_alpha, se_beta,
               free_fraction=n_free / n)


# ---------------------------------------------------------------- outer search

def profile_z0(samples: list[Sample], z0_grid: list[float],
               fix_alpha: float | None = None,
               fix_beta: float | None = None) -> list[Fit]:
    """Fit at every sill elevation on the grid. Nothing is discarded here.

    The whole profile is returned rather than only its minimum, because its
    shape is the evidence for or against z0 being identifiable at all
    (hypotheses.md H0c-2, second condition).
    """
    out = []
    for z0 in z0_grid:
        fit = fit_loglinear(samples, z0, fix_alpha, fix_beta)
        if fit is not None:
            out.append(fit)
    return out


def best(fits: list[Fit]) -> Fit:
    """Lowest mean squared error, not lowest SSE.

    The number of usable samples changes with z0 — a sample with dh <= 0 drops
    out — so comparing raw SSE across the grid would reward sill elevations that
    simply discard more data.
    """
    return min(fits, key=lambda f: f.sse / f.n)


def rmse_linear(fit: Fit, samples: list[Sample]) -> tuple[float, int]:
    """Root mean squared error in m3/s on the samples the fit can predict."""
    total, n = 0.0, 0
    for s in samples:
        if not usable(s, fit.z0):
            continue
        r = s.q - fit.predict(s)
        total += r * r
        n += 1
    return (math.sqrt(total / n) if n else float("nan")), n


# ---------------------------------------------------------------- vectorised

def profile_z0_fast(samples: list[Sample], z0_grid: list[float]):
    """Vectorised equivalent of :func:`profile_z0`, for grids of any size.

    The pure-Python path above stays the reference implementation: it is short
    enough to read line by line and is tested against laws with known parameters.
    This one exists only because the real profile needs a few hundred sill
    elevations over a quarter of a million samples, which pure Python does in
    minutes rather than seconds.

    ``tests/test_gatelaw.py`` asserts the two agree to floating-point tolerance.
    If they ever diverge, that test fails rather than the faster one silently
    becoming the truth.
    """
    import numpy as np

    a = np.array([s.a for s in samples], dtype=float)
    h1 = np.array([s.h1 for s in samples], dtype=float)
    h2 = np.array([s.h2 for s in samples], dtype=float)
    q = np.array([s.q for s in samples], dtype=float)
    ln_a_all = np.log(np.where(a > 0, a, 1.0))
    ln_q_all = np.log(np.where(q > 0, q, 1.0))
    positive = (a > 0) & (q > 0)

    out = []
    for z0 in z0_grid:
        dh = (h1 - z0) - np.maximum(h2 - z0, a)
        keep = positive & (dh > 0)
        n = int(keep.sum())
        if n < 10:
            continue
        x = ln_a_all[keep]
        y = np.log(dh[keep])
        z = ln_q_all[keep]
        mx, my, mz = x.mean(), y.mean(), z.mean()
        dx, dy, dz = x - mx, y - my, z - mz
        sxx = float(dx @ dx)
        syy = float(dy @ dy)
        sxy = float(dx @ dy)
        sxz = float(dx @ dz)
        syz = float(dy @ dz)
        det = sxx * syy - sxy * sxy
        if abs(det) < 1e-12 * max(1.0, sxx * syy):
            continue
        alpha = (syy * sxz - sxy * syz) / det
        beta = (sxx * syz - sxy * sxz) / det
        log_gamma = mz - alpha * mx - beta * my
        resid = z - (log_gamma + alpha * x + beta * y)
        sse = float(resid @ resid)
        dof = n - 3
        se_alpha = se_beta = float("nan")
        if dof > 0:
            s2 = sse / dof
            se_alpha = math.sqrt(max(s2 * syy / det, 0.0))
            se_beta = math.sqrt(max(s2 * sxx / det, 0.0))
        n_free = int(((h2[keep] - z0) <= a[keep]).sum())
        out.append(Fit(z0, log_gamma, alpha, beta, sse, n, se_alpha, se_beta,
                       free_fraction=n_free / n))
    return out
