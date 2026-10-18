"""Deterministic precomputation and independent playback state."""

from dataclasses import dataclass
import numpy as np

from domain import Catalog, MODEL_VERSION, ValidationError
from models import CompiledModel, compile_model


@dataclass
class SimulationResult:
    model: CompiledModel
    strain: np.ndarray
    stress_MPa: np.ndarray
    stages: np.ndarray
    work_density_MJ_m3: float

    @property
    def material(self):
        return self.model.material


def stage_at(model: CompiledModel, strain: float) -> str:
    m = model.material
    if strain >= m.fracture_strain:
        return "Fracture threshold"
    if m.family == "brittle":
        return "Pre-fracture response"
    if strain <= model.prefix_end:
        return "Elastic / proof transition"
    if m.geometry_mode == "drawing_conceptual":
        if "Drawing end" in model.events and strain < model.events["Drawing end"][0]:
            return "Drawing (conceptual)"
        return "Re-hardening (assumed)"
    if strain < m.strain_at_uts:
        return "Strain hardening"
    return "Post-UTS localization"


def simulate(model: CompiledModel, samples: int = 700) -> SimulationResult:
    if samples < 50 or samples > 20000:
        raise ValidationError("Use 50 to 20,000 curve samples per material.")
    end = model.material.fracture_strain
    # Resolve the small proof region even for very ductile materials.
    prefix = np.linspace(0, model.prefix_end, samples if model.tail is None else max(25, samples // 4))
    rest = np.array([]) if model.tail is None else np.linspace(model.prefix_end, end, max(25, samples - samples // 4))
    anchors = [v[0] for v in model.events.values()]
    if model.tail is not None:
        anchors.extend(model.tail.x.tolist())
    strain = np.unique(np.concatenate((prefix, rest, anchors)))
    strain = strain[(strain >= 0) & (strain <= end)]
    stress = model.stress(strain)
    stages = np.array([stage_at(model, float(e)) for e in strain])
    work = float(np.trapezoid(stress, strain))  # MPa = MJ/m^3, per initial volume.
    return SimulationResult(model, strain, stress, stages, work)


def run_selected(catalog: Catalog, selected: list[str], samples: int = 700) -> dict[str, SimulationResult]:
    if not selected or len(selected) != len(set(selected)):
        raise ValidationError("Select at least one unique material dataset.")
    if any(key not in catalog.materials for key in selected):
        raise ValidationError("The selection contains a dataset that is not in this catalog.")
    return {key: simulate(compile_model(catalog.materials[key], catalog.points.get(key, ())), samples)
            for key in selected}


def playback_indices(result: SimulationResult, frames: int = 36) -> list[int]:
    """Advance uniformly in strain, not through the dense proof-region samples."""
    targets = np.linspace(0, result.strain[-1], frames)
    idx = list(np.searchsorted(result.strain, targets))
    idx.extend(int(np.argmin(abs(result.strain - event[0]))) for event in result.model.events.values())
    return sorted(set(idx))


@dataclass
class Playback:
    selected: tuple[str, ...]
    frames: dict[str, list[int]]
    specimen: int = 0
    frame: int = 0
    paused: bool = False
    complete: bool = False
    final_visible: bool = False
    separation_ticks: int = 0

    @property
    def current_id(self) -> str:
        return self.selected[self.specimen]

    @property
    def sample_index(self) -> int:
        return self.frames[self.current_id][self.frame]

    def advance(self) -> None:
        if self.paused or self.complete:
            return
        if self.frame < len(self.frames[self.current_id]) - 1:
            self.frame += 1
            return
        if not self.final_visible:
            self.final_visible = True
            self.separation_ticks = 4
            return
        if self.separation_ticks > 0:
            self.separation_ticks -= 1
            return
        if self.specimen < len(self.selected) - 1:
            self.specimen += 1
            self.frame = 0
            self.final_visible = False
        else:
            self.complete = True

