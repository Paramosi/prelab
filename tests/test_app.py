"""Streamlit integration: rendering order, selection snapshots, and Q2-Q4 presets."""
from pathlib import Path
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def button(at, label):
    return next(item for item in at.button if item.label == label)


def test_full_series_then_results_then_new_selection():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert len(at.session_state.selection) == 5
    assert len(at.get("plotly_chart")) == 0
    button(at, "Run tensile tests").click().run()
    assert not at.exception
    assert at.session_state.phase == "playback"
    assert len(at.get("plotly_chart")) == 0
    results = at.session_state.results
    pb = at.session_state.playback
    while not pb.complete:
        pb.advance()
    at.run()
    assert not at.exception
    assert at.session_state.phase == "results"
    assert len(at.get("plotly_chart")) == 1
    assert list(at.session_state.results) == list(results)
    at.multiselect[0].set_value(["gray_cast_iron"]).run()
    assert not at.exception
    assert at.session_state.phase == "select"
    assert "results" not in at.session_state
    assert len(at.get("plotly_chart")) == 0


def test_presets_use_distinct_datasets():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    button(at, "Q3").click().run()
    assert at.session_state.selection == ["al2024_t4", "al2024_virtual"]
    button(at, "Q4").click().run()
    assert at.session_state.selection == ["monel400_annealed", "monel400_cold_worked"]
    next(item for item in at.selectbox if item.label == "Brass condition for Q2").set_value("yellow_brass_cold_rolled").run()
    button(at, "Q2").click().run()
    assert len(at.session_state.selection) == 5
    assert "yellow_brass_cold_rolled" in at.session_state.selection
    assert "yellow_brass_annealed" not in at.session_state.selection
    button(at, "Select all datasets").click().run()
    assert len(at.session_state.selection) == 9
    assert not at.exception


def test_restart_while_paused_resets_frame_inspector():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    button(at, "Q3").click().run()
    button(at, "Run tensile tests").click().run()
    button(at, "Pause").click().run()
    inspector = next(item for item in at.slider if item.label == "Inspect a computed frame")
    inspector.set_value(12).run()
    assert at.session_state.playback.frame == 12
    button(at, "Restart specimen").click().run()
    assert not at.exception
    assert at.session_state.playback.paused
    assert at.session_state.playback.frame == 0
    assert next(item for item in at.slider if item.label == "Inspect a computed frame").value == 0
