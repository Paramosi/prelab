"""Physical axial length, explicitly conceptual transverse shape, and comparison plots."""

from html import escape
from base64 import b64encode
import numpy as np
import plotly.graph_objects as go

from simulation import Playback, SimulationResult


COLORS = ["#cf5c29", "#2978a0", "#699341", "#9a62a3", "#d7a02d", "#287d71", "#b34965", "#5869b1", "#687987"]


def specimen_panel_html(result: SimulationResult, strain: float, fractured: bool) -> str:
    # Embed the SVG bytes so each frame does not require another media request.
    encoded = b64encode(specimen_svg(result, strain, fractured).encode("utf-8")).decode("ascii")
    return (f'<div class="specimen-live"><img alt="Tensile specimen: {escape(result.material.label)}" '
            f'src="data:image/svg+xml;base64,{encoded}" /></div>')


def playback_status_html(pb: Playback, results: dict[str, SimulationResult]) -> str:
    """Presentation statuses follow the actual playback state; labels are escaped."""
    rows = []
    for i, key in enumerate(pb.selected):
        state = ("Completed" if pb.complete or i < pb.specimen else
                 "Waiting" if i > pb.specimen else
                 "Paused" if pb.paused else "Finishing" if pb.final_visible else "Testing")
        rows.append(f'<span class="queue-item {state.lower()}"><b>{i+1}. {escape(results[key].material.label)}</b> · {state}</span>')
    live = "Paused" if pb.paused else "Test in progress"
    detail = ("Press Resume to continue." if pb.paused else
              "Watch the specimen stretch. Results open automatically after every material finishes.")
    return (f'<div class="test-status"><strong><span class="live-dot {"paused" if pb.paused else ""}"></span>{live}</strong>'
            f'<div>{detail}</div></div><div class="test-queue">{"".join(rows)}</div>')


def geometry_state(result: SimulationResult, strain: float, points: int = 101):
    """Unit initial gauge length. Localized incompressibility is a display assumption."""
    if not 0 <= strain <= result.material.fracture_strain or points < 3:
        raise ValueError("Invalid geometry state.")
    m = result.material
    X = np.linspace(0.0, 1.0, points)
    if m.geometry_mode == "axial_only":
        stretch = np.full_like(X, 1 + strain)
        area = np.ones_like(X)  # Transverse response intentionally not computed.
    else:
        onset = m.localization_strain
        q = np.clip((strain - onset) / (m.fracture_strain - onset), 0, 1)
        q = q * q * (3 - 2 * q)
        # Drawing spreads the deformed region; metal localization narrows it.
        width = 0.065 + 0.30 * q if m.geometry_mode == "drawing_conceptual" else 0.13 - 0.055 * q
        shape = np.exp(-0.5 * ((X - 0.5) / width) ** 2)
        shape /= np.trapezoid(shape, X)
        w = (1 - 0.75 * q) + 0.75 * q * shape
        stretch = 1 + strain * w
        area = 1 / stretch
    dx = (stretch[:-1] + stretch[1:]) / 2 * np.diff(X)
    x = np.concatenate(([0.0], np.cumsum(dx)))
    return {"X": X, "x": x, "stretch": stretch, "area": area,
            "length_ratio": float(x[-1]), "volume_ratio": float(np.trapezoid(area * stretch, X))}


def specimen_svg(result: SimulationResult, strain: float, fractured: bool = False) -> str:
    m = result.material
    g = geometry_state(result, strain)
    # Fixed scale for a given specimen throughout playback, including its final state.
    scale = 570 / (1 + m.fracture_strain)
    left, mid = 160.0, 175.0
    x = left + g["x"] * scale
    half = 26 * np.sqrt(g["area"])
    initial_right = left + scale
    right = float(x[-1])
    def polygon(xs, hs, shift=0):
        top = " ".join(f"{v+shift:.2f},{mid-h:.2f}" for v, h in zip(xs, hs))
        bottom = " ".join(f"{v+shift:.2f},{mid+h:.2f}" for v, h in zip(xs[::-1], hs[::-1]))
        return f'<polygon points="{top} {bottom}" fill="url(#metal)" stroke="#1e587d" stroke-width="1.5"/>'
    body = polygon(x, half)
    gap = 0
    if fractured:
        center = len(x) // 2
        gap = 12
        body = polygon(x[:center+1], half[:center+1], -gap/2) + polygon(x[center:], half[center:], gap/2)
    end_right = right + gap / 2
    end_left = left - gap / 2
    title = escape(m.label)
    state = "SEPARATION IS A DISPLAY EFFECT" if fractured else "ENGINEERING STRAIN DRIVES GAUGE LENGTH"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 340" role="img" aria-label="Tensile specimen: {title}">
    <defs><linearGradient id="metal" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#8abbd4"/><stop offset="0.5" stop-color="#d9ebf4"/><stop offset="1" stop-color="#4b87a8"/></linearGradient></defs>
    <rect width="900" height="340" rx="14" fill="#fff"/>
    <text x="34" y="40" font-family="Arial,sans-serif" font-size="13" fill="#6c7b8d" letter-spacing="2">VIRTUAL TENSILE TEST</text>
    <text x="34" y="69" font-family="Arial,sans-serif" font-size="19" fill="#172b45">{title}</text>
    <line x1="50" y1="175" x2="850" y2="175" stroke="#d9e1e8" stroke-dasharray="5 5"/>
    <rect x="{left}" y="149" width="{scale}" height="52" fill="none" stroke="#aab8c5" stroke-dasharray="5 4"/>
    {body}
    <path d="M {end_left-42} 130 L {end_left-12} 130 L {end_left} 149 L {end_left} 201 L {end_left-12} 220 L {end_left-42} 220 Z" fill="#92b7cc" stroke="#1e587d"/>
    <path d="M {end_right} 149 L {end_right+12} 130 L {end_right+42} 130 L {end_right+42} 220 L {end_right+12} 220 L {end_right} 201 Z" fill="#92b7cc" stroke="#1e587d"/>
    <rect x="{end_left-65}" y="116" width="40" height="118" rx="5" fill="#172b45"/>
    <rect x="{end_right+25}" y="116" width="40" height="118" rx="5" fill="#172b45"/>
    <line x1="{left}" y1="257" x2="{right}" y2="257" stroke="#cf5c29" stroke-width="2"/>
    <path d="M {left} 251 v 12 M {right} 251 v 12" stroke="#cf5c29" stroke-width="2"/>
    <text x="{(left+right)/2}" y="281" text-anchor="middle" font-family="Arial,sans-serif" font-size="15" fill="#172b45">L / L₀ = {1+strain:.5f}</text>
    <text x="34" y="318" font-family="Arial,sans-serif" font-size="11" fill="#6c7b8d" letter-spacing="1">{state}</text>
    <text x="866" y="318" text-anchor="end" font-family="Arial,sans-serif" font-size="11" fill="#6c7b8d">Normalized gauge · conceptual section</text></svg>'''


def comparison_figure(results: dict[str, SimulationResult], percent: bool = True, markers: bool = True):
    fig = go.Figure()
    scale = 100 if percent else 1
    for i, (key, r) in enumerate(results.items()):
        color = COLORS[i % len(COLORS)]
        label = r.material.label
        fig.add_trace(go.Scatter(x=r.strain * scale, y=r.stress_MPa, name=label,
                                 legendgroup=key, mode="lines", line=dict(color=color, width=2.7),
                                 customdata=np.column_stack((r.strain, r.stages)),
                                 hovertemplate="Strain: %{x:.5g}<br>Stress: %{y:.5g} MPa<br>%{customdata[1]}<extra>%{fullData.name}</extra>"))
        if markers:
            for event in ("Proof", "UTS", "Fracture"):
                if event in r.model.events:
                    e, s = r.model.events[event]
                    symbol = {"Proof": "circle-open", "UTS": "diamond", "Fracture": "x"}[event]
                    fig.add_trace(go.Scatter(x=[e * scale], y=[s], mode="markers", name=f"{label}: {event}",
                                             legendgroup=key, showlegend=False,
                                             marker=dict(color=color, size=9, symbol=symbol),
                                             hovertemplate=f"{escape(event)}<br>Strain: %{{x:.6g}}<br>Stress: %{{y:.6g}} MPa<extra>{escape(label)}</extra>"))
    fig.update_layout(template="plotly_white", height=600,
                      title=dict(text="Engineering stress–strain comparison", font=dict(size=22)),
                      xaxis_title="Engineering strain (%)" if percent else "Engineering strain (mm/mm)",
                      yaxis_title="Engineering stress (MPa)", hovermode="closest",
                      margin=dict(l=65, r=30, t=85, b=160),
                      legend=dict(orientation="h", yanchor="top", y=-0.2, x=0, font=dict(size=11)),
                      font=dict(family="Arial, sans-serif", color="#172b45"),
                      annotations=[dict(text="Lecture properties + explicit shape assumptions. Full curves are modeled, not measured.",
                                        x=0, y=1.04, xref="paper", yref="paper", showarrow=False,
                                        xanchor="left", font=dict(size=11, color="#6b7280"))])
    fig.update_xaxes(rangemode="tozero", gridcolor="#edf1f5")
    fig.update_yaxes(rangemode="tozero", gridcolor="#edf1f5")
    return fig
