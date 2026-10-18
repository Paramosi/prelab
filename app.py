"""English UI: select datasets, observe deformation, then compare the curves."""

from dataclasses import asdict
from pathlib import Path

import streamlit as st

from data_io import CATALOG_FILES, catalog_zip, export_results, load_catalog, read_catalog_zip
from domain import ValidationError
from simulation import Playback, playback_indices, run_selected
from visualization import comparison_figure, playback_status_html, specimen_panel_html, specimen_svg


ROOT = Path(__file__).resolve().parent
TICK_SECONDS = 0.12

st.set_page_config(page_title="Tensile Lab | Material behavior", page_icon="🔬", layout="wide")
st.markdown("""<style>
.block-container {max-width:1380px;padding-top:4rem;padding-bottom:3rem}
h1 {letter-spacing:-1.3px;font-weight:750!important}
h2,h3 {letter-spacing:-.4px}
[data-testid="stMetric"] {background:white;border:1px solid #e1e7ed;border-radius:10px;padding:14px 18px}
[data-testid="stMetricLabel"] {color:#6c7b8d}
.eyebrow {font-size:12px;letter-spacing:2.2px;font-weight:700;color:#cf5c29;margin-bottom:6px}
.lead {font-size:17px;color:#67768a;margin-top:-8px;margin-bottom:26px}
.step {padding:12px 0;color:#8a96a5;border-bottom:3px solid #dde4eb;font-size:13px;letter-spacing:.4px}
.step.active {color:#172b45;border-color:#cf5c29;font-weight:700}
.source-note {font-size:12px;color:#65758a;line-height:1.6}
.test-status {background:#fff5ed;border-left:4px solid #cf5c29;padding:10px 16px;border-radius:8px;color:#172b45}
.test-status strong {font-size:18px}
.test-status div {font-size:13px;margin-top:3px}
.live-dot {display:inline-block;width:10px;height:10px;border-radius:50%;background:#cf5c29;margin-right:9px;animation:live-pulse 1s infinite}
.live-dot.paused {animation:none;background:#8793a1}
@keyframes live-pulse {50% {opacity:.3}}
@media (prefers-reduced-motion:reduce) {.live-dot {animation:none}}
.test-queue {display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.queue-item {font-size:12px;border:1px solid #dce3e9;border-radius:6px;padding:5px 9px;color:#69788b;background:#fff}
.queue-item.testing,.queue-item.finishing {border-color:#cf5c29;color:#a74316;background:#fff5ed}
.queue-item.completed {border-color:#98bca3;color:#326345;background:#f0f8f2}
.specimen-live img {display:block;width:100%;max-height:310px;object-fit:contain;background:#fff;border-radius:14px}
button {border-radius:7px!important}
</style>""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def cached_catalog(files):
    return load_catalog(files)


def clear_run():
    for key in ("results", "playback", "curve_csv", "result_zip", "run_fingerprint"):
        st.session_state.pop(key, None)
    st.session_state.phase = "select"


def choose(ids):
    clear_run()
    st.session_state.selection = ids


st.session_state.setdefault("phase", "select")
running = st.session_state.phase == "playback"

with st.sidebar:
    st.markdown('<div class="eyebrow">MECHANICS OF MATERIALS</div>', unsafe_allow_html=True)
    st.title("Tensile Lab")
    st.caption("Prelab 02 / 03 / 04")
    uploaded = st.file_uploader("Custom catalog", type=["zip"], disabled=running,
                                help="Optional ZIP with materials.csv, curve_points.csv, and provenance.csv. The lecture catalog loads automatically.")

try:
    if uploaded is not None:
        catalog = read_catalog_zip(uploaded.getvalue())
    else:
        catalog = cached_catalog({name: (ROOT / "data" / name).read_bytes() for name in CATALOG_FILES})
except (ValidationError, OSError) as exc:
    st.error(f"Catalog could not be loaded: {exc}")
    st.stop()

if st.session_state.get("catalog_fingerprint") != catalog.fingerprint:
    clear_run()
    st.session_state.catalog_fingerprint = catalog.fingerprint
    st.session_state.selection = [key for key, m in catalog.materials.items()
                                  if m.q2 and key != "yellow_brass_cold_rolled"]
    if not st.session_state.selection:
        st.session_state.selection = [next(iter(catalog.materials))]

with st.sidebar:
    st.caption(f"{len(catalog.materials)} independent datasets · fixed MPa units")
    brass_options = [key for key, m in catalog.materials.items() if m.material_name == "Yellow Brass"]
    brass = st.selectbox("Brass condition for Q2", brass_options, disabled=running,
                         format_func=lambda key: catalog.materials[key].condition) if brass_options else None
    c1, c2, c3 = st.columns(3)
    q2 = [key for key, m in catalog.materials.items() if m.q2 and (key not in brass_options or key == brass)]
    c1.button("Q2", width="stretch", disabled=running, on_click=choose, args=(q2,))
    c2.button("Q3", width="stretch", disabled=running, on_click=choose,
              args=([key for key, m in catalog.materials.items() if m.q3],))
    c3.button("Q4", width="stretch", disabled=running, on_click=choose,
              args=([key for key, m in catalog.materials.items() if m.q4],))
    st.button("Select all datasets", width="stretch", disabled=running,
              on_click=choose, args=(list(catalog.materials),))
    st.multiselect("Materials to test", list(catalog.materials), key="selection",
                   format_func=lambda key: catalog.materials[key].label, disabled=running, on_change=clear_run)
    seconds = st.slider("Playback seconds per specimen", 3, 10, 6, disabled=running,
                        help="Presentation speed only. This is not a physical strain rate.")
    st.caption("Q2 uses one Brass condition. Both conditions remain available as independent datasets.")
    st.divider()
    st.download_button("Download catalog template", catalog_zip(catalog), "tensile_catalog.zip", "application/zip",
                       width="stretch", disabled=running)
    with st.expander("Source & interpretation"):
        st.markdown("**Lecture:** Yonsei University, Mechanics of Materials, PDF page 8 (slide 8).")
        st.markdown("The lecture reproduces **Beer, Mechanics of Materials, 5th edition, Appendix B**. The original textbook was not independently checked.")
        st.caption("Proof strength: table footnote 3, 0.2% offset. Elongation: 50 mm gauge. All missing shape parameters are labeled assumptions.")
        lecture = ROOT.parent / "고체 Module#1 이론.pdf"
        if lecture.exists():
            st.download_button("Download source lecture", lecture.read_bytes(), "mechanics_lecture.pdf", "application/pdf", disabled=running)
        st.markdown("[Model definitions: MIT](https://ocw.mit.edu/courses/3-11-mechanics-of-materials-fall-1999/d4ea545640f151bb66e6d8bc0ba55ed4_MIT3_11F99_ss.pdf)")

st.markdown('<div class="eyebrow">VIRTUAL MATERIALS LABORATORY</div>', unsafe_allow_html=True)
if running:
    st.subheader("Live tensile test")
else:
    st.title("Watch the material. Then read the curve.")
    st.markdown('<div class="lead">A source-traceable tensile test, from your selected specimen to a shared stress–strain plot.</div>', unsafe_allow_html=True)
phase = st.session_state.phase
for col, title, state in zip(st.columns(3), ("01  SELECT MATERIALS", "02  OBSERVE DEFORMATION", "03  COMPARE & EXPORT"),
                             ("select", "playback", "results")):
    col.markdown(f'<div class="step {"active" if phase == state else ""}">{title}</div>', unsafe_allow_html=True)
st.write("")

selected = st.session_state.selection
if phase == "select":
    top = st.columns([3, 1])
    with top[0]:
        st.subheader("Your test series")
        st.write("Select a prelab group or combine individual datasets. Each specimen plays first; the comparison graph follows the complete series.")
    with top[1]:
        run = st.button("Run tensile tests", type="primary", width="stretch", disabled=not selected)
    if not selected:
        st.info("Select at least one material in the sidebar.")
    else:
        rows = []
        for key in selected:
            m = catalog.materials[key]
            rows.append({"Material": m.material_name, "Condition": m.condition, "E (GPa)": m.E_MPa / 1000,
                         "0.2% proof (MPa)": m.yield_MPa, "UTS (MPa)": m.uts_MPa,
                         "Listed elongation (%)": m.elongation_fraction * 100})
        st.dataframe(rows, width="stretch", hide_index=True)
        st.info("Lecture values constrain the curves. Hardening shape, localization, and fracture stress include explicit assumptions; the curves are not measured test records.")
        with st.expander("Review assumptions and field-level sources"):
            inspect_id = st.selectbox("Dataset to review", selected, format_func=lambda key: catalog.materials[key].label)
            m = catalog.materials[inspect_id]
            st.write(m.assumption_note)
            st.caption(f"Model: {m.model_id} · exponent: {m.exponent:g} · assumed UTS strain: {m.strain_at_uts:.6g} · assumed fracture stress: {m.fracture_stress_MPa:g} MPa")
            st.dataframe([asdict(p) for p in catalog.provenance if p.variant_id == inspect_id], hide_index=True, width="stretch")
    if run:
        try:
            with st.spinner("Validating and computing selected curves…"):
                results = run_selected(catalog, selected)
                curves, package = export_results(results, catalog)
            st.session_state.results = results
            st.session_state.curve_csv, st.session_state.result_zip = curves, package
            st.session_state.run_fingerprint = catalog.fingerprint
            frame_count = round(seconds / TICK_SECONDS)
            st.session_state.playback = Playback(tuple(selected), {key: playback_indices(r, frame_count) for key, r in results.items()})
            st.session_state.phase = "playback"
            st.rerun()
        except ValidationError as exc:
            st.error(f"Cannot run this selection: {exc}")

elif phase == "playback":
    timer = None if st.session_state.playback.paused else TICK_SECONDS

    @st.fragment(run_every=timer)
    def playback_panel():
        pb = st.session_state.playback
        if pb.complete:
            st.session_state.phase = "results"
            st.rerun()
        result = st.session_state.results[pb.current_id]
        index = pb.sample_index
        e, s = float(result.strain[index]), float(result.stress_MPa[index])
        fractured = index == len(result.strain) - 1 and pb.final_visible
        st.html(playback_status_html(pb, st.session_state.results))
        fraction = pb.frame / max(1, len(pb.frames[pb.current_id]) - 1)
        st.progress(fraction, text=f"Specimen {pb.specimen + 1} of {len(pb.selected)} · {result.material.label} · {fraction:.0%} · Frame {pb.frame + 1}/{len(pb.frames[pb.current_id])}")
        st.caption(f"{pb.specimen} completed · {len(pb.selected) - pb.specimen - 1} waiting · "
                   + ("Paused" if pb.paused else "Separating specimen" if fractured else str(result.stages[index])))
        st.html(specimen_panel_html(result, e, fractured))
        if result.material.fracture_strain < 0.03:
            st.caption("Small-strain material: the true-scale extension is subtle. Watch the strain readout and the final separation.")
        a, b, c, d = st.columns(4)
        a.metric("Engineering strain", f"{100 * e:.4f}%")
        b.metric("Engineering stress", f"{s:.2f} MPa")
        c.metric("Gauge length ratio", f"{1 + e:.5f}")
        d.metric("State", "Separated" if fractured else str(result.stages[index]))
        done = sum(len(pb.frames[key]) for key in pb.selected[:pb.specimen]) + pb.frame + 1
        total = sum(len(v) for v in pb.frames.values())
        st.progress(done / total, text=f"Series progress · {result.material.label}")
        st.caption("Axial length follows the computed engineering strain. Transverse shape and separation are conceptual; elapsed playback time is not test time. Stress shown at separation is the last intact value.")
        a, b, c = st.columns([1, 1, 3])
        if a.button("Resume" if pb.paused else "Pause", width="stretch"):
            pb.paused = not pb.paused
            st.rerun()
        if b.button("Restart specimen", width="stretch"):
            pb.frame, pb.final_visible = 0, False
            st.session_state.pop(f"seek_{pb.current_id}_{pb.specimen}", None)
            st.rerun()
        if c.button("Cancel and change selection"):
            clear_run()
            st.rerun()
        if pb.paused:
            seek_key = f"seek_{pb.current_id}_{pb.specimen}"
            chosen = st.slider("Inspect a computed frame", 0, len(pb.frames[pb.current_id]) - 1,
                               pb.frame, key=seek_key)
            if chosen != pb.frame:
                pb.frame, pb.final_visible = chosen, False
                st.rerun()
        pb.advance()

    playback_panel()

else:
    results = st.session_state.results
    st.subheader("Test series complete")
    st.caption(f"{len(results)} selected datasets · geometry playback completed · engineering stress based on original area")
    a, b, c = st.columns([1, 1, 2])
    percent = a.toggle("Strain in percent", value=True)
    markers = b.toggle("Show proof / UTS / fracture", value=True)
    if c.button("Replay this series", width="stretch"):
        st.session_state.playback = Playback(tuple(results), {key: playback_indices(r, round(seconds / TICK_SECONDS)) for key, r in results.items()})
        st.session_state.phase = "playback"
        st.rerun()
    fig = comparison_figure(results, percent, markers)
    st.plotly_chart(fig, width="stretch",
                    config={"displaylogo": False, "toImageButtonOptions": {"format": "png", "filename": "tensile_comparison", "width": 1600, "height": 1000, "scale": 2}})
    st.caption("Open circle: 0.2% proof · diamond: UTS · cross: last intact fracture point. Drag to zoom; double-click to reset. Use the camera icon to save a PNG.")
    summary = [{"Material": r.material.label, "Initial E (GPa)": r.material.E_MPa / 1000,
                "Proof (MPa)": r.material.yield_MPa, "UTS (MPa)": r.material.uts_MPa,
                "Endpoint strain (%)": r.material.fracture_strain * 100,
                "Modeled work (MJ/m³)": round(r.work_density_MJ_m3, 3)} for r in results.values()]
    st.dataframe(summary, hide_index=True, width="stretch")
    st.caption("Modeled work is the area under this assumed engineering curve per initial volume. It is not fracture toughness or a measured material property.")
    left, right = st.columns(2)
    left.download_button("Download selected curves (CSV)", st.session_state.curve_csv, "selected_curves.csv", "text/csv", width="stretch")
    right.download_button("Download curves + sources (ZIP)", st.session_state.result_zip, "tensile_results.zip", "application/zip", width="stretch")
    with st.expander("Inspect a specimen and its modeling assumptions"):
        key = st.selectbox("Result dataset", list(results), format_func=lambda key: results[key].material.label)
        r = results[key]
        idx = st.slider("Computed state", 0, len(r.strain) - 1, 0, key=f"result_index_{key}")
        st.image(specimen_svg(r, float(r.strain[idx])), width="stretch")
        st.write(f"Engineering strain: {100 * r.strain[idx]:.5g}% · Engineering stress: {r.stress_MPa[idx]:.5g} MPa")
        st.write(r.material.assumption_note)
        st.dataframe([asdict(p) for p in catalog.provenance if p.variant_id == key], hide_index=True, width="stretch")

st.divider()
st.markdown('<div class="source-note">TENSILE LAB · Lecture-sourced properties, explicit model assumptions. '
            'Local computation · No AI or external API is used during simulation.</div>', unsafe_allow_html=True)
