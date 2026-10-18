"""Monotonic tensile envelopes, not general multiaxial constitutive laws.

The proof prefix uses epsilon = sigma/E + offset*(sigma/proof)**n.
Its origin tangent is exactly E and its proof intersection is exact.
The post-proof tail is an explicitly assumed, shape-checked Hermite curve.
See SOURCES.md and data/provenance.csv for data and assumption boundaries.
"""

from dataclasses import dataclass
import numpy as np
from scipy.interpolate import CubicHermiteSpline, PchipInterpolator
from scipy.optimize import brentq

from domain import Material, Point, ValidationError, validate_material


@dataclass
class CompiledModel:
    material: Material
    prefix_end: float
    prefix_stress: float
    nonlinear_strain: float
    tail: CubicHermiteSpline | None
    events: dict[str, tuple[float, float]]

    def stress(self, strain):
        """Evaluate only the unbroken envelope. Vectorized bracketed inversion."""
        x = np.asarray(strain, dtype=float)
        if np.any(~np.isfinite(x)) or np.any(x < 0) or np.any(x > self.material.fracture_strain):
            raise ValidationError("Requested strain lies outside the unbroken curve.")
        if self.material.model_id == "linear":
            return x * self.material.E_MPa
        flat = x.reshape(-1)
        y = np.empty_like(flat)
        prefix = flat <= self.prefix_end
        target = flat[prefix]
        low = np.zeros_like(target)
        high = np.full_like(target, self.prefix_stress)
        # Fixed iterations give deterministic bounded work and sub-float64 scale residuals.
        for _ in range(56):
            mid = (low + high) / 2
            e = mid / self.material.E_MPa + self.nonlinear_strain * (mid / self.prefix_stress) ** self.material.exponent
            low = np.where(e < target, mid, low)
            high = np.where(e >= target, mid, high)
        y[prefix] = (low + high) / 2
        y[flat == 0] = 0.0
        y[flat == self.prefix_end] = self.prefix_stress
        if np.any(~prefix):
            if self.tail is None:
                raise ValidationError("No post-prefix curve is defined.")
            y[~prefix] = self.tail(flat[~prefix])
        return y.reshape(x.shape)

    def tangent(self, strain: float) -> float:
        if strain == 0 or self.material.model_id == "linear":
            return self.material.E_MPa
        if strain <= self.prefix_end:
            s = float(self.stress(strain))
            derivative = (1 / self.material.E_MPa + self.nonlinear_strain * self.material.exponent
                          / self.prefix_stress * (s / self.prefix_stress) ** (self.material.exponent - 1))
            return 1 / derivative
        return float(self.tail.derivative()(strain))


def _check_tail(tail: CubicHermiteSpline, m: Material) -> None:
    """Check interior extrema analytically, not only sampled values."""
    tol = max(1.0, m.uts_MPa) * 1e-9
    for i, h in enumerate(np.diff(tail.x)):
        a, b, c, d = tail.c[:, i]
        candidates = [0.0, h]
        roots = np.roots(np.trim_zeros([3 * a, 2 * b, c], "f")) if any((a, b, c)) else []
        candidates.extend(float(r.real) for r in roots if abs(r.imag) < 1e-10 and 0 < r.real < h)
        values = [((a * t + b) * t + c) * t + d for t in candidates]
        y0, y1 = float(tail(tail.x[i])), float(tail(tail.x[i + 1]))
        if min(values) < min(y0, y1) - tol or max(values) > max(y0, y1) + tol:
            raise ValidationError(f"{m.variant_id}: a Hermite segment overshoots its anchors. Revise points or tangents.")
        if min(values) < -tol or max(values) > m.uts_MPa + tol:
            raise ValidationError(f"{m.variant_id}: curve exceeds physical stress bounds.")
        # A cubic can reverse direction without exceeding its endpoints.
        at = [0.0, h]
        if abs(a) > 1e-20 and 0 < -b / (3 * a) < h:
            at.append(-b / (3 * a))
        slopes = [(3 * a * t + 2 * b) * t + c for t in at]
        if (y1 > y0 and min(slopes) < -tol) or (y1 < y0 and max(slopes) > tol):
            raise ValidationError(f"{m.variant_id}: a segment reverses its declared direction.")
        if abs(y1 - y0) < tol and max(abs(s) for s in slopes) > tol:
            raise ValidationError(f"{m.variant_id}: a constant-stress segment must have zero tangents.")


def compile_model(m: Material, points: tuple[Point, ...] = ()) -> CompiledModel:
    validate_material(m)
    events = {"UTS": (m.strain_at_uts, m.uts_MPa),
              "Fracture": (m.fracture_strain, m.fracture_stress_MPa)}
    if m.model_id == "linear":
        if points:
            raise ValidationError(f"{m.variant_id}: linear model does not accept extra anchors.")
        return CompiledModel(m, m.fracture_strain, m.uts_MPa, 0.0, None, events)
    if m.model_id == "nonlinear_brittle":
        if points:
            raise ValidationError(f"{m.variant_id}: nonlinear brittle model does not accept extra anchors.")
        return CompiledModel(m, m.fracture_strain, m.uts_MPa,
                             m.fracture_strain - m.uts_MPa / m.E_MPa, None, events)
    start = m.proof_strain
    events["Proof"] = (start, m.yield_MPa)
    if not points:
        raise ValidationError(f"{m.variant_id}: post-proof anchors are required.")
    x = np.array([start, *[p.strain for p in points]])
    y = np.array([m.yield_MPa, *[p.stress_MPa for p in points]])
    if np.any(~np.isfinite(x)) or np.any(~np.isfinite(y)) or np.any(np.diff(x) <= 0):
        raise ValidationError(f"{m.variant_id}: finite, strictly increasing anchors are required.")
    if np.any(y < 0) or np.any(y > m.uts_MPa):
        raise ValidationError(f"{m.variant_id}: anchors must lie between zero and UTS.")
    if not np.isclose(x[-1], m.fracture_strain, rtol=1e-10, atol=1e-12) or not np.isclose(y[-1], m.fracture_stress_MPa):
        raise ValidationError(f"{m.variant_id}: last anchor must match the fracture point.")
    if not np.any(np.isclose(x, m.strain_at_uts, atol=1e-12, rtol=1e-10) & np.isclose(y, m.uts_MPa)):
        raise ValidationError(f"{m.variant_id}: UTS must have an explicit anchor.")
    slopes = PchipInterpolator(x, y).derivative()(x)
    for i, p in enumerate(points, start=1):
        if p.tangent_MPa is not None:
            if not np.isfinite(p.tangent_MPa):
                raise ValidationError(f"{m.variant_id}: anchor tangent must be finite.")
            slopes[i] = p.tangent_MPa
        if p.event and p.event not in {"UTS", "Fracture", "Proof"}:
            if p.event in events:
                raise ValidationError(f"{m.variant_id}: duplicate event label {p.event}.")
            events[p.event] = (p.strain, p.stress_MPa)
    tail = CubicHermiteSpline(x, y, slopes, extrapolate=False)
    _check_tail(tail, m)
    model = CompiledModel(m, start, m.yield_MPa, m.offset_strain, tail, events)
    # Ensure the post-proof tail cannot intersect the proof line again.
    for i, h in enumerate(np.diff(tail.x)):
        a, b, c, d = tail.c[:, i]
        q = [a, b, c - m.E_MPa, d - m.E_MPa * (tail.x[i] - m.offset_strain)]
        roots = np.roots(np.trim_zeros(q, "f"))
        for r in roots:
            if abs(r.imag) < 1e-9 and 1e-9 < tail.x[i] + r.real - start and 0 <= r.real <= h:
                raise ValidationError(f"{m.variant_id}: multiple proof-line intersections.")
    measured = brentq(lambda e: float(model.stress(e)) - m.E_MPa * (e - m.offset_strain),
                     0.0, m.fracture_strain, xtol=1e-14)
    if not np.isclose(measured, start, atol=1e-10, rtol=1e-9):
        raise ValidationError(f"{m.variant_id}: the offset proof intersection is inconsistent.")
    return model

