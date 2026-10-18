"""Scientific invariants, source integrity, catalog errors, and playback contracts."""

from dataclasses import asdict, fields, replace
import csv
import io
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
from scipy.optimize import brentq

from data_io import catalog_zip, csv_bytes, export_results, load_catalog, read_catalog, read_catalog_zip
from domain import Material, Point, ValidationError
from models import compile_model
from simulation import Playback, playback_indices, run_selected, simulate
from visualization import comparison_figure, geometry_state, playback_status_html, specimen_svg


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def catalog():
    return read_catalog(ROOT / "data")


@pytest.fixture(scope="module")
def results(catalog):
    return run_selected(catalog, list(catalog.materials))


def test_lecture_transcription(catalog):
    # Independent expected values, visually transcribed from lecture PDF p.8.
    expected = {
        "al2024_t4": (73000, 325, 470, .19),
        "yellow_brass_annealed": (105000, 100, 320, .65),
        "yellow_brass_cold_rolled": (105000, 410, 510, .08),
        "polycarbonate": (2400, 35, 65, 1.10),
        "gray_cast_iron": (69000, None, 170, .005),
        "polystyrene": (3100, 55, 55, .02),
        "monel400_annealed": (180000, 220, 550, .46),
        "monel400_cold_worked": (180000, 585, 675, .22),
    }
    assert len(catalog.materials) == 9
    for key, values in expected.items():
        m = catalog.materials[key]
        assert (m.E_MPa, m.yield_MPa, m.uts_MPa, m.elongation_fraction) == values


def test_q3_has_only_the_requested_property_changes(catalog):
    a, b = catalog.materials["al2024_t4"], catalog.materials["al2024_virtual"]
    assert b.parent_variant_id == a.variant_id
    assert b.E_MPa == 1.5 * a.E_MPa
    assert b.yield_MPa == 1.3 * a.yield_MPa
    for field in ("uts_MPa", "elongation_fraction", "fracture_strain", "fracture_stress_MPa", "strain_at_uts", "exponent"):
        assert getattr(a, field) == getattr(b, field)


@pytest.mark.parametrize("key", ["al2024_t4", "yellow_brass_annealed", "yellow_brass_cold_rolled", "polycarbonate",
                                "gray_cast_iron", "polystyrene", "al2024_virtual", "monel400_annealed", "monel400_cold_worked"])
def test_curve_invariants(results, key):
    r = results[key]
    m = r.material
    assert np.all(np.isfinite(r.stress_MPa))
    assert np.all(np.diff(r.strain) > 0)
    assert r.strain[0] == 0 and r.stress_MPa[0] == 0
    assert r.model.tangent(0) == m.E_MPa
    h = min(1e-9, m.fracture_strain * 1e-7)
    assert float(r.model.stress(h)) / h == pytest.approx(m.E_MPa, rel=1e-6)
    assert min(r.stress_MPa) >= 0
    assert max(r.stress_MPa) == pytest.approx(m.uts_MPa, abs=1e-7)
    assert r.strain[-1] == m.fracture_strain
    assert r.stress_MPa[-1] == pytest.approx(m.fracture_stress_MPa, abs=1e-7)
    with pytest.raises(ValidationError):
        r.model.stress(m.fracture_strain + .000001)
    if m.yield_MPa is not None:
        root = brentq(lambda x: float(r.model.stress(x)) - m.E_MPa * (x - m.offset_strain), 0, m.fracture_strain)
        assert float(r.model.stress(root)) == pytest.approx(m.yield_MPa, rel=1e-7)
        assert root == pytest.approx(m.yield_MPa / m.E_MPa + m.offset_strain, abs=1e-10)


def test_sampling_converges_without_moving_events(results):
    for r in results.values():
        fine = simulate(r.model, 1400)
        assert fine.model.events == r.model.events
        assert fine.work_density_MJ_m3 == pytest.approx(r.work_density_MJ_m3, rel=.001)
        np.testing.assert_allclose(r.model.stress(r.strain), r.stress_MPa, rtol=0, atol=0)


def test_selected_order_export_and_round_trip(catalog):
    selected = ["monel400_cold_worked", "monel400_annealed"]
    r = run_selected(catalog, selected)
    assert list(r) == selected
    curves, package = export_results(r, catalog)
    rows = list(csv.DictReader(io.StringIO(curves.decode("utf-8-sig"))))
    assert {row["variant_id"] for row in rows} == set(selected)
    with ZipFile(io.BytesIO(package)) as z:
        metadata = json.loads(z.read("metadata.json"))
        assert metadata["selected_ids"] == selected
        assert {p["variant_id"] for p in metadata["provenance"]} == set(selected)
        assert z.read("curves.csv") == curves
    c2 = read_catalog_zip(catalog_zip(catalog))
    assert c2.fingerprint == catalog.fingerprint
    assert c2.materials == catalog.materials


@pytest.mark.parametrize("bad", [[], ["missing"], ["al2024_t4", "al2024_t4"]])
def test_bad_selections(catalog, bad):
    with pytest.raises(ValidationError):
        run_selected(catalog, bad)


@pytest.mark.parametrize("field,value", [("E_MPa", float("nan")), ("E_MPa", -1), ("yield_MPa", 1000),
                                         ("exponent", 1), ("fracture_strain", .00001), ("offset_strain", 0),
                                         ("fracture_stress_MPa", 999)])
def test_invalid_physical_input(catalog, field, value):
    m = replace(catalog.materials["al2024_t4"], **{field: value})
    with pytest.raises(ValidationError):
        compile_model(m, catalog.points[m.variant_id])


def test_overshoot_is_rejected(catalog):
    m = catalog.materials["al2024_t4"]
    pts = list(catalog.points[m.variant_id])
    pts[0] = replace(pts[0], tangent_MPa=1e7)
    with pytest.raises(ValidationError, match="overshoot|reverses|bounds"):
        compile_model(m, tuple(pts))


def test_csv_errors_and_missing_provenance(catalog):
    headers = [f.name for f in fields(Material)]
    original = list(csv.DictReader(io.StringIO(catalog.files["materials.csv"].decode("utf-8-sig"))))
    files = dict(catalog.files)
    files["materials.csv"] = csv_bytes(original + [original[0]], headers)
    with pytest.raises(ValidationError, match="Duplicate material"):
        load_catalog(files)
    files = dict(catalog.files)
    files["materials.csv"] = catalog.files["materials.csv"].replace(b"E_MPa", b"E_GPa", 1)
    with pytest.raises(ValidationError, match="header"):
        load_catalog(files)
    files = dict(catalog.files)
    files["provenance.csv"] = catalog.files["provenance.csv"].splitlines(keepends=True)[0]
    with pytest.raises(ValidationError, match="missing provenance"):
        load_catalog(files)
    files = dict(catalog.files)
    files["materials.csv"] += b"broken,row\r\n"
    with pytest.raises(ValidationError, match="columns"):
        load_catalog(files)


def test_geometry_preserves_length_and_conditional_volume(results):
    for r in results.values():
        for e in [0, r.material.fracture_strain / 2, r.material.fracture_strain]:
            g = geometry_state(r, e)
            assert g["length_ratio"] == pytest.approx(1 + e, abs=1e-12)
            assert np.all(g["area"] > 0)
            if r.material.geometry_mode != "axial_only":
                assert g["volume_ratio"] == pytest.approx(1, abs=1e-12)
        svg = specimen_svg(r, r.material.fracture_strain, True)
        assert "SEPARATION IS A DISPLAY EFFECT" in svg


def test_playback_visits_each_specimen_and_does_not_advance_when_paused(results):
    selected = tuple(list(results)[:2])
    frames = {k: playback_indices(results[k], 8) for k in selected}
    pb = Playback(selected, frames)
    pb.paused = True
    pb.advance()
    assert pb.sample_index == 0
    pb.paused = False
    visited, separated = set(), set()
    for _ in range(100):
        visited.add(pb.current_id)
        if pb.final_visible:
            separated.add(pb.current_id)
        pb.advance()
        if pb.complete:
            break
    assert pb.complete
    assert visited == separated == set(selected)
    for key in selected:
        assert frames[key][0] == 0
        assert frames[key][-1] == len(results[key].strain) - 1


def test_playback_progress_is_visible_and_queue_follows_actual_state(results):
    selected = ("al2024_t4", "al2024_virtual")
    frames = {key: playback_indices(results[key], 50) for key in selected}
    r = results[selected[0]]
    # The first half of playback must traverse appreciable strain, despite dense proof samples.
    assert r.strain[frames[selected[0]][len(frames[selected[0]]) // 2]] > 0.4 * r.strain[-1]
    pb = Playback(selected, frames)
    html = playback_status_html(pb, results)
    assert "Testing" in html and "Waiting" in html and "Completed" not in html
    pb.paused = True
    assert "Press Resume" in playback_status_html(pb, results)
    pb.paused = False
    while not pb.final_visible:
        pb.advance()
    for _ in range(4):
        pb.advance()
        assert pb.specimen == 0 and pb.final_visible
    pb.advance()
    html = playback_status_html(pb, results)
    assert "Completed" in html and "Testing" in html and "Waiting" not in html
    while not pb.complete:
        pb.advance()
    assert playback_status_html(pb, results).count("· Completed") == 2


def test_percent_display_changes_units_not_physics(results):
    chosen = {"al2024_t4": results["al2024_t4"]}
    a = comparison_figure(chosen, percent=False)
    b = comparison_figure(chosen, percent=True)
    np.testing.assert_array_equal(np.array(a.data[0].x) * 100, b.data[0].x)
    np.testing.assert_array_equal(a.data[0].y, b.data[0].y)
    assert len([trace for trace in b.data if trace.showlegend is not False]) == 1

