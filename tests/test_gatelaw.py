"""Tests for the gate-law identification.

Two kinds of test here. The recovery tests build data from a law with known
parameters and check that the fit returns them: an estimator that cannot recover
a law it generated itself is worthless on real data. The structural tests pin
down the properties the pre-registration depends on — above all that ``z0`` is
invisible in fully submerged flow, which is the whole reason H0c-2 exists.

No network, no data package required.
"""
import math

import pytest

from gatempc.gatelaw import (
    IDEAL_ALPHA, IDEAL_BETA, Fit, Sample, best, fit_loglinear,
    head_difference, is_free, profile_z0, rmse_linear, usable,
)


def make(a, h1, h2, gamma, alpha, beta, z0, year=2020, t="t"):
    """A sample whose discharge obeys the law exactly."""
    s = Sample(t, a, h1, h2, 0.0, year)
    dh = head_difference(s, z0)
    q = gamma * a ** alpha * dh ** beta
    return Sample(t, a, h1, h2, q, year)


def synthetic(gamma=4.27, alpha=1.0, beta=0.5, z0=1.0, n=400, free=False):
    """A spread of openings and heads, all submerged unless ``free``."""
    out = []
    for i in range(n):
        a = 0.3 + 1.4 * ((i * 7) % n) / n
        h1 = 3.0 + 1.2 * ((i * 13) % n) / n
        h2 = (z0 + a * 0.5) if free else h1 - 0.4 - 0.8 * ((i * 11) % n) / n
        s = make(a, h1, h2, gamma, alpha, beta, z0, t=f"t{i}")
        if s.q > 0 and head_difference(s, z0) > 0:
            out.append(s)
    return out


# ---------------------------------------------------------------- recovery

def test_recovers_the_ideal_law_it_generated():
    truth = dict(gamma=4.27, alpha=1.0, beta=0.5, z0=1.0)
    fit = fit_loglinear(synthetic(**truth), z0=1.0)
    assert fit is not None
    assert fit.alpha == pytest.approx(1.0, abs=1e-9)
    assert fit.beta == pytest.approx(0.5, abs=1e-9)
    assert fit.gamma == pytest.approx(4.27, rel=1e-9)


def test_recovers_a_law_whose_exponents_are_not_ideal():
    """The case H1 is about: a real gate that does not follow the textbook law."""
    truth = dict(gamma=6.1, alpha=0.83, beta=0.62, z0=1.0)
    fit = fit_loglinear(synthetic(**truth), z0=1.0)
    assert fit is not None
    assert fit.alpha == pytest.approx(0.83, abs=1e-9)
    assert fit.beta == pytest.approx(0.62, abs=1e-9)
    assert fit.gamma == pytest.approx(6.1, rel=1e-9)


def test_constrained_fit_returns_the_ideal_exponents_and_only_scales_gamma():
    samples = synthetic(gamma=4.27, alpha=1.0, beta=0.5, z0=1.0)
    fit = fit_loglinear(samples, z0=1.0, fix_alpha=IDEAL_ALPHA, fix_beta=IDEAL_BETA)
    assert fit is not None
    assert (fit.alpha, fit.beta) == (IDEAL_ALPHA, IDEAL_BETA)
    assert fit.gamma == pytest.approx(4.27, rel=1e-9)


def test_perfect_data_leaves_no_residual():
    fit = fit_loglinear(synthetic(), z0=1.0)
    assert fit is not None and fit.sse < 1e-18
    rmse, n = rmse_linear(fit, synthetic())
    assert n > 0 and rmse < 1e-9


# ---------------------------------------------------------------- structure

def test_z0_cancels_exactly_in_fully_submerged_flow():
    """The finding behind H0c-2: submerged samples carry no information on z0.

    dh = (H1 - z0) - (H2 - z0) = H1 - H2. If this ever stops holding, the whole
    argument for the pre-registered sill window collapses.
    """
    s = Sample("t", a=0.5, h1=3.0, h2=2.4, q=1.0, year=2020)
    # h2 - z0 > a for every one of these, so the gate stays submerged throughout
    submerged = (-5.0, 0.0, 1.0, 1.8)
    values = {round(head_difference(s, z0), 12) for z0 in submerged}
    assert values == {round(3.0 - 2.4, 12)}
    assert all(not is_free(s, z0) for z0 in submerged)


def test_the_submerged_free_switch_is_exactly_where_tailwater_depth_meets_the_opening():
    """The boundary itself, which is the only place z0 becomes observable."""
    s = Sample("t", a=0.5, h1=3.0, h2=2.4, q=1.0, year=2020)
    z_switch = s.h2 - s.a                     # 1.9: h2 - z0 == a
    assert is_free(s, z_switch)               # the switch counts as free
    assert not is_free(s, z_switch - 1e-9)
    # past the switch the head starts depending on z0, which is the point
    assert head_difference(s, z_switch + 0.1) != pytest.approx(0.6)


def test_the_fit_is_flat_in_z0_when_every_sample_is_submerged():
    """A flat profile is exactly what "not identifiable" looks like."""
    samples = synthetic(z0=1.0)
    # Stay strictly below the switch for every sample, or some become free and
    # the profile is *supposed* to move.
    ceiling = min(s.h2 - s.a for s in samples)
    grid = [ceiling - d for d in (3.0, 2.0, 1.0, 0.01)]
    fits = profile_z0(samples, grid)
    assert len(fits) == len(grid)
    per_sample = {round(f.sse / f.n, 15) for f in fits}
    assert len(per_sample) == 1, "z0 must not move the fit in submerged flow"
    assert {round(f.alpha, 12) for f in fits} == {round(fits[0].alpha, 12)}


def test_free_flow_samples_make_z0_visible():
    """With free-flow samples present the profile must stop being flat."""
    samples = synthetic(z0=1.0) + synthetic(z0=1.0, n=200, free=True)
    fits = profile_z0(samples, [0.0, 0.5, 1.0, 1.5])
    per_sample = {round(f.sse / f.n, 12) for f in fits}
    assert len(per_sample) > 1
    assert best(fits).z0 == pytest.approx(1.0, abs=0.51)


def test_best_uses_mean_error_not_total_error():
    """Total SSE would reward a z0 that simply discards more samples."""
    cheap = Fit(z0=0.0, log_gamma=0.0, alpha=1.0, beta=0.5, sse=1.0, n=10)
    honest = Fit(z0=1.0, log_gamma=0.0, alpha=1.0, beta=0.5, sse=5.0, n=1000)
    assert best([cheap, honest]) is honest


# ---------------------------------------------------------------- guards

def test_samples_without_head_or_with_a_shut_gate_are_not_usable():
    shut = Sample("t", a=0.0, h1=3.0, h2=2.0, q=0.0, year=2020)
    reversed_head = Sample("t", a=0.5, h1=2.0, h2=3.0, q=1.0, year=2020)
    assert not usable(shut, 1.0)
    assert not usable(reversed_head, 1.0)


def test_too_few_samples_returns_none_rather_than_a_confident_answer():
    assert fit_loglinear(synthetic(n=8), z0=1.0) is None


def test_exactly_collinear_regressors_return_none():
    """If dh is proportional to a, alpha and beta cannot be separated at all.

    Constructed so that dh = 2a exactly, hence ln dh = ln 2 + ln a. The normal
    equations are then singular and the fit must refuse rather than return an
    arbitrary split of the exponent between the two terms.
    """
    import random
    rng = random.Random(1)
    samples = []
    for i in range(60):
        a = 0.4 + 0.02 * i
        # z0 = 0 and h2 = 0 keeps the gate free, so dh = h1 - a; h1 = 3a gives dh = 2a
        q = 5.0 * a ** 1.5 * math.exp(rng.gauss(0, 0.02))
        samples.append(Sample(f"t{i}", a=a, h1=3.0 * a, h2=0.0, q=q, year=2020))
    dh = [head_difference(s, 0.0) for s in samples]
    assert all(abs(d - 2 * s.a) < 1e-12 for d, s in zip(dh, samples))
    assert fit_loglinear(samples, z0=0.0) is None


def test_prediction_is_zero_where_the_law_cannot_produce_flow():
    fit = Fit(z0=1.0, log_gamma=math.log(4.27), alpha=1.0, beta=0.5, sse=0.0, n=100)
    assert fit.predict(Sample("t", 0.0, 3.0, 2.0, 0.0, 2020)) == 0.0
    assert fit.predict(Sample("t", 0.5, 2.0, 3.0, 0.0, 2020)) == 0.0


def test_standard_errors_shrink_as_samples_are_added():
    small = fit_loglinear(synthetic(n=60), z0=1.0)
    large = fit_loglinear(synthetic(n=2000), z0=1.0)
    assert small is not None and large is not None
    # noiseless data gives ~0 SE either way; add noise to make the test bite
    import random
    rng = random.Random(0)

    def noisy(n):
        out = []
        for s in synthetic(n=n):
            out.append(Sample(s.time, s.a, s.h1, s.h2,
                              s.q * math.exp(rng.gauss(0, 0.05)), s.year))
        return out

    a = fit_loglinear(noisy(60), z0=1.0)
    b = fit_loglinear(noisy(2000), z0=1.0)
    assert a is not None and b is not None
    assert b.se_alpha < a.se_alpha


def test_the_fast_profile_agrees_with_the_reference_implementation():
    """Two independent implementations must give the same answer.

    The vectorised path exists for speed only. Pinning it to the readable one
    means a mistake in either shows up here instead of quietly becoming the
    published number.
    """
    np = pytest.importorskip("numpy")
    samples = synthetic(gamma=5.5, alpha=0.9, beta=0.55, z0=1.0)
    samples += synthetic(gamma=5.5, alpha=0.9, beta=0.55, z0=1.0, n=200, free=True)
    grid = [0.2 * i for i in range(9)]

    from gatempc.gatelaw import profile_z0_fast
    slow = {round(f.z0, 9): f for f in profile_z0(samples, grid)}
    fast = {round(f.z0, 9): f for f in profile_z0_fast(samples, grid)}
    assert set(slow) == set(fast), "the two paths kept different grid points"
    for z0 in slow:
        a, b = slow[z0], fast[z0]
        assert a.n == b.n
        assert a.alpha == pytest.approx(b.alpha, rel=1e-10, abs=1e-12)
        assert a.beta == pytest.approx(b.beta, rel=1e-10, abs=1e-12)
        assert a.log_gamma == pytest.approx(b.log_gamma, rel=1e-10, abs=1e-12)
        assert a.sse == pytest.approx(b.sse, rel=1e-9, abs=1e-14)
        assert a.free_fraction == pytest.approx(b.free_fraction, abs=1e-12)
