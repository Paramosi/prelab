"""Typed catalog records and model-level input checks. Units: MPa, mm, fraction."""

from dataclasses import dataclass
import math


MODEL_VERSION = "1.0.0"


class ValidationError(ValueError):
    """An input cannot be interpreted without changing its meaning."""


@dataclass(frozen=True)
class Material:
    variant_id: str
    material_name: str
    condition: str
    family: str
    q2: bool
    q3: bool
    q4: bool
    E_MPa: float
    yield_MPa: float | None
    uts_MPa: float
    elongation_fraction: float
    elongation_definition: str
    model_id: str
    offset_strain: float
    exponent: float
    fracture_strain: float
    fracture_stress_MPa: float
    strain_at_uts: float
    geometry_mode: str
    localization_strain: float | None
    source_id: str
    assumption_note: str
    parent_variant_id: str

    @property
    def label(self) -> str:
        return f"{self.material_name} | {self.condition}"

    @property
    def proof_strain(self) -> float | None:
        if self.yield_MPa is None:
            return None
        return self.yield_MPa / self.E_MPa + self.offset_strain


@dataclass(frozen=True)
class Point:
    variant_id: str
    point_id: str
    event: str
    strain: float
    stress_MPa: float
    tangent_MPa: float | None


@dataclass(frozen=True)
class Provenance:
    variant_id: str
    field: str
    kind: str
    source_title: str
    source_locator: str
    source_url: str
    original_value: str
    original_unit: str
    derivation: str


@dataclass
class Catalog:
    materials: dict[str, Material]
    points: dict[str, tuple[Point, ...]]
    provenance: tuple[Provenance, ...]
    fingerprint: str
    files: dict[str, bytes]


def validate_material(m: Material) -> None:
    """Reject incompatible inputs; never repair data silently."""
    if not m.variant_id or not m.material_name or not m.condition:
        raise ValidationError("ID, material name, and condition must be supplied.")
    if m.family not in {"metal", "polymer", "brittle"}:
        raise ValidationError(f"{m.variant_id}: unknown material family.")
    if m.model_id not in {"linear", "proof_anchored", "nonlinear_brittle"}:
        raise ValidationError(f"{m.variant_id}: unknown model ID.")
    if m.geometry_mode not in {"axial_only", "necking_conceptual", "drawing_conceptual"}:
        raise ValidationError(f"{m.variant_id}: unknown geometry mode.")
    numeric = [m.E_MPa, m.uts_MPa, m.elongation_fraction, m.offset_strain,
               m.exponent, m.fracture_strain, m.fracture_stress_MPa, m.strain_at_uts]
    numeric += [v for v in (m.yield_MPa, m.localization_strain) if v is not None]
    if not all(math.isfinite(v) for v in numeric):
        raise ValidationError(f"{m.variant_id}: every numeric value must be finite.")
    if min(m.E_MPa, m.uts_MPa, m.elongation_fraction, m.fracture_strain) <= 0:
        raise ValidationError(f"{m.variant_id}: modulus, strength, and elongation must be positive.")
    if not 0 < m.fracture_stress_MPa <= m.uts_MPa:
        raise ValidationError(f"{m.variant_id}: fracture stress must be positive and no greater than UTS.")
    if not 0 < m.strain_at_uts <= m.fracture_strain:
        raise ValidationError(f"{m.variant_id}: UTS strain must lie within the simulation range.")
    if m.yield_MPa is not None and not 0 < m.yield_MPa <= m.uts_MPa:
        raise ValidationError(f"{m.variant_id}: proof strength cannot exceed UTS.")
    if m.localization_strain is not None and not 0 < m.localization_strain < m.fracture_strain:
        raise ValidationError(f"{m.variant_id}: localization must start before fracture.")
    if m.geometry_mode != "axial_only" and m.localization_strain is None:
        raise ValidationError(f"{m.variant_id}: conceptual localization requires a start strain.")
    if m.model_id == "proof_anchored":
        if m.yield_MPa is None or m.offset_strain <= 0 or m.exponent <= 1:
            raise ValidationError(f"{m.variant_id}: proof model requires yield, offset > 0, and exponent > 1.")
        if m.proof_strain >= m.fracture_strain:
            raise ValidationError(f"{m.variant_id}: fracture must follow the proof point.")
    if m.model_id == "nonlinear_brittle":
        if m.yield_MPa is not None:
            raise ValidationError(f"{m.variant_id}: this brittle model does not define a proof strength.")
        if m.exponent <= 1 or m.fracture_strain < m.uts_MPa / m.E_MPa:
            raise ValidationError(f"{m.variant_id}: nonlinear brittle endpoint is incompatible with E.")
        if not math.isclose(m.fracture_stress_MPa, m.uts_MPa, rel_tol=1e-10):
            raise ValidationError(f"{m.variant_id}: nonlinear brittle UTS must occur at fracture.")
        if not math.isclose(m.strain_at_uts, m.fracture_strain, rel_tol=1e-10):
            raise ValidationError(f"{m.variant_id}: nonlinear brittle UTS strain must equal fracture strain.")
    if m.model_id == "linear":
        expected = m.E_MPa * m.fracture_strain
        if m.yield_MPa is not None or not math.isclose(expected, m.uts_MPa, rel_tol=1e-8):
            raise ValidationError(f"{m.variant_id}: linear fracture must satisfy stress = E * strain; yield must be empty.")
        if not math.isclose(expected, m.fracture_stress_MPa, rel_tol=1e-8):
            raise ValidationError(f"{m.variant_id}: inconsistent linear fracture stress.")
        if not math.isclose(m.strain_at_uts, m.fracture_strain, rel_tol=1e-8):
            raise ValidationError(f"{m.variant_id}: linear UTS must occur at fracture.")
    if not m.source_id or not m.assumption_note or not m.elongation_definition:
        raise ValidationError(f"{m.variant_id}: source, elongation definition, and modeling notes are required.")

