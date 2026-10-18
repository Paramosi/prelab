# Tensile Lab

An English-language tensile-test simulator for prelab Q2, Q3, and Q4. Select material datasets, watch each specimen deform, and then compare only the selected engineering stress–strain curves.

## Run

For sharing, use `dist/TensileLab-Windows.zip` when provided. Extract the entire `TensileLab` folder before running the launcher. Keep all six Python files (`app.py`, `domain.py`, `models.py`, `simulation.py`, `data_io.py`, `visualization.py`), the `data` directory, `requirements.txt`, and the launcher together. The CSV files are inputs, not the application. Do not copy `.venv` between computers; the launcher creates it on the destination. Startup failures are recorded in `startup.log` with missing-file checks. Windows with Python 3.12+ and the `py` launcher is required; the first dependency installation needs internet access.

The distribution contains the transcribed catalog and its provenance records. Original course PDF/DOCX files are not bundled. The optional source-lecture download is available only when that PDF is present beside the original project folder; simulation does not depend on it.

On this Windows computer, double-click **Start-TensileLab.cmd**. The launcher uses the local `.venv`, opens Streamlit in your browser, and keeps the server running in its terminal. Close the terminal or press Ctrl+C to stop it. If an instance is already running, use its browser tab instead of launching another instance.

Manual launch from this folder:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

For a fresh installation, install Python 3.12 or newer, create a virtual environment, and install `requirements.txt`. `requirements.lock.txt` records the complete tested environment, including development dependencies. Core simulation runs locally; it does not call an AI service, API, or remote material database. A first dependency installation requires internet access. [Streamlit launch documentation](https://docs.streamlit.io/develop/api-reference/cli/run)

## Use

1. Choose **Q2**, **Q3**, **Q4**, or individual datasets in the sidebar.
2. For Q2, choose the Brass condition, then click **Q2** to apply that five-material preset.
3. Review the property table and the expandable source/assumption records.
4. Click **Run tensile tests**. Each selected specimen plays in sequence. Pause, resume, restart the current specimen, or cancel to change the selection.
5. After all specimens finish, the comparison plot appears. Drag to zoom, double-click to reset, and use the camera icon to save a PNG.
6. Download selected curve samples as CSV or a ZIP containing curves, input values, modeling assumptions, and field-level provenance. Replay or inspect individual specimens from the result screen.

The initial Q2 preset uses Annealed Yellow Brass. This is a UI default, not a claim that the assignment specifies that condition. Both Brass states are independently selectable. Selecting both results in six Q2-related datasets, not the five-material Q2 preset.

## Verified lecture data

The supplied lecture PDF is **`../고체 Module#1 이론.pdf`**, PDF page 8 / printed slide 8. Its embedded table is attributed to Ferdinand P. Beer, *Mechanics of Materials*, 5th edition, Appendix B. These values were transcribed from a rendered image of that slide; the original textbook was not independently accessed. The table's yield heading refers to footnote 3, “Offset of 0.2 percent.” Elongation is listed for a 50 mm gauge. See [SOURCES.md](SOURCES.md) for locators and definitions.

| Dataset | E (GPa) | Tensile proof strength (MPa) | Tensile UTS (MPa) | Listed elongation (%) |
|---|---:|---:|---:|---:|
| Aluminum Alloy 2024-T4 | 73 | 325 | 470 | 19 |
| Yellow Brass, Annealed | 105 | 100 | 320 | 65 |
| Yellow Brass, Cold-rolled | 105 | 410 | 510 | 8 |
| Polycarbonate | 2.4 | 35 | 65 | 110 |
| Gray Cast Iron, 4.5% C, ASTM A-48 | 69 | Not provided | 170 | 0.5 |
| Polystyrene | 3.1 | 55 | 55 | 2 |
| Hypothetical Aluminum (Q3) | 109.5 | 422.5 | 470* | 19* |
| Monel Alloy 400, Annealed | 180 | 220 | 550 | 46 |
| Monel Alloy 400, Cold-worked | 180 | 585 | 675 | 22 |

**Source:** lecture slide 8 for all real-material rows; lecture PDF page 30 / printed slide 33, Q3, for the hypothetical multipliers. `*` Keeping baseline UTS and elongation is an explicit comparison assumption. The virtual dataset retains the baseline shape settings as well. The 352 MPa aluminum example on slide 13 is a generic offset-method illustration; it is not substituted for the 325 MPa Al 2024-T4 table value.

There are **nine datasets because the lecture provides two Yellow Brass conditions**, not because the same baseline Al is duplicated between Q2 and Q3. Both Q2 and Q3 reference the same `al2024_t4` row. The earlier planning count of eight assumed a single unspecified Brass state; the source table resolves that ambiguity.

## Model assumptions

The table constrains E, proof strength, UTS, and listed elongation. It does **not** uniquely determine an entire curve. All shipped datasets are lecture-constrained **illustrative reconstructions**, not calibrated experimental records. The prelab says simulator accuracy is not evaluated; the implementation nevertheless checks its mathematical constraints.

| Quantity or choice | Implementation | Attribution |
|---|---|---|
| Initial modulus | Exactly the supplied E | Lecture table, converted GPa → MPa |
| Proof point | Strain = proof/E + 0.002 | Offset definition and lecture footnote 3 |
| Pre-proof response | `strain = stress/E + offset*(stress/proof)^n` | Offset-normalized Ramberg–Osgood form; exponent is assumed |
| Exponent n | 6 for proof-based metals/PS; 4 for PC | Project assumptions, not lecture measurements |
| Metal UTS strain | 0.6 × listed elongation fraction | Project assumption |
| Metal fracture engineering stress | 0.8 × UTS | Project assumption |
| Fracture strain | Listed elongation fraction used as total loaded endpoint | Project assumption; no elastic-recovery correction |
| PC drawing anchors | (0.08, 28 MPa), (0.45, 30 MPa), then (1.10, 65 MPa) | Project assumptions; UTS value is lecture-sourced |
| PS endpoint | Proof at 55 MPa, then a short plateau to strain 0.02 | Project assumption preserving the listed proof/UTS/elongation |
| Gray Cast Iron | `strain = stress/E + a*(stress/UTS)^3`, with `a = endpoint - UTS/E` | Project nonlinear brittle envelope; no invented yield strength |
| Post-proof tail | Shape-checked cubic Hermite segments | PCHIP-derived tangents except explicitly supplied tangents |
| Proof-to-tail join | Continuous stress (C0); generally a tangent change | Explicit modeling choice, not an assertion of C1 smoothness |
| Transverse geometry | Conceptual localization/drawing or uncomputed width | No measured Poisson ratio or local strain field |

The nonlinear brittle envelope is an empirical interpolation of E and the endpoint, not a damage or microcrack evolution model. Polystyrene remains labeled brittle even though its source table includes a proof-strength value; the app does not invent a long plastic regime.

**Why the implementation adds a proof prefix:** the plan initially favored two basic curve kernels. The actual lecture table includes a low proof/E ratio for annealed Brass. Forcing the origin tangent E and the proof point into one short cubic segment can conflict with shape preservation. A small analytic proof prefix preserves both definitions without changing measured values. The application therefore implements three recipes (`linear`, `proof_anchored`, `nonlinear_brittle`), with one shared prefix inverter and one shared Hermite tail. This is a documented implementation refinement, not a newly measured property. The bundled catalog does not need the optional linear recipe.

The prefix is inverted with 56 vectorized bisection steps during precomputation. This is bounded O(MNI), with fixed I = 56, rather than an unqualified claim that every model is closed-form O(MN). Tail construction/evaluation and storage are O(M(N+P)). Frames read precomputed states and construct O(K) geometry for one specimen. No constitutive recalculation occurs during playback.

The polynomial tail is checked at internal stationary points for bounds/overshoot and at derivative extrema for monotonicity. Proof intersections are independently checked. General unrestricted Hermite interpolation does not provide those guarantees on its own. See [SciPy CubicHermiteSpline](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.CubicHermiteSpline.html) and [PCHIP](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.PchipInterpolator.html).

## Geometry and time

Axial length always satisfies `L/L0 = 1 + engineering_strain`. The gauge is normalized; the app does not predict force, specimen diameter, actual fracture time, or fracture-face details. A constant screen scale is used for each specimen throughout its run.

In conceptual metal/drawing modes, a normalized positive stretch field integrates to the prescribed length; its displayed section uses reciprocal stretch. This conserves volume **within that assumed display model**. The PC shape is an illustrative spreading deformation zone, not a simulation of polymer crazing or an assertion that all polymers are incompressible. In axial-only mode, width is merely held fixed and no area-change prediction is made. Gaps after fracture are a display effect; they do not enter the calculated strain. The displayed stress in the separated frame is explicitly the last intact stress.

The UI uses an approximate 120 ms refresh interval. Playback duration is a presentation setting, not a physical test rate or a frame-rate guarantee. All specimens must complete before the comparison graph is displayed. Page refresh resets session state; export the results before closing the app.

Playback advances approximately uniformly in strain, retaining proof/UTS/fracture event frames. The six-second default plus event frames and a short separation hold is a presentation choice. A status panel above the specimen identifies Testing, Waiting, Completed, and Paused materials, with a changing frame counter and progress bar. SVG frames are embedded as data images to avoid a separate media request for each frame. Small-strain specimens retain their actual axial scale; their extension can be subtle. These are project UI decisions in response to the user's playback feedback, not additional material properties. Rendering uses [Streamlit HTML](https://docs.streamlit.io/develop/api-reference/text/st.html) and the [fragment timer](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment).

## Catalog files

- `data/materials.csv`: one row per independent material/condition; fixed MPa and fractional strain. `q2`, `q3`, `q4` are boolean group memberships.
- `data/curve_points.csv`: extra post-proof anchors only. The proof point is derived and is not duplicated here. Anchors must be strictly ordered within each dataset.
- `data/provenance.csv`: field or point, reported/derived/assumed classification, source document and locator, original units, and transformation/assumption. Blank is not zero.

The CSV files are inputs, not hardcoded material branches in the numerical engine. Edit a copy, ZIP exactly these three files at the ZIP root, and upload it through **Custom catalog**. Download the bundled ZIP as a template first. Material names need not match the shipped materials; unique `variant_id` values identify the records. Do not rename headers or silently substitute units. Unknown IDs, incompatible models, nonfinite inputs, extra/missing columns, duplicate keys, missing provenance, and curve inconsistencies are rejected.

If you use a different source table, preserve its meaning in the source records. A new source with a different condition is a new dataset. The ZIP result contains only selected input/provenance records; it also records the full catalog hash for traceability. The exported work density is an integral of the modeled engineering curve per initial volume (MPa = MJ/m³); it is not the crack-resistance quantity K_IC.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests cover lecture transcription, Q3 derivation, initial slope, offset intersection, UTS, finite values, no extrapolation, subinterval overshoot, sampling convergence, geometry length/conditional volume, selected-only export, malformed catalogs, playback completion, and the Streamlit Q2/Q3/Q4 workflow. These are implementation checks, not experimental validation. Development test dependency: `pytest==9.1.1`.

## Files

`app.py` owns the UI and session state. `domain.py` defines records and input checks. `models.py` defines envelopes. `simulation.py` precomputes arrays and advances playback. `visualization.py` renders the specimen and comparison. `data_io.py` loads and exports traceable data. `SOURCES.md` separates lecture evidence, public references, and project assumptions.
