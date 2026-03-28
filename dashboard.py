"""
Dashboard Generator for IOTBSM Simulation
Produces a self-contained HTML file with embedded Chart.js visualizations.
"""

import json
import math
from simulation import IOTBSMSimulation


def generate_dashboard(sim: IOTBSMSimulation, output_path: str):
    """Generate the full interactive HTML dashboard."""

    cycles = sim.history["cycle"]
    ia_pct = sim.history["ia_pct"]
    sm_pct = sim.history["sm_pct"]
    breaches = sim.history["security_breaches"]
    bs_counts = sim.history["bs_count"]
    total_shared = sim.history["total_facts_shared"]

    trust_matrix = sim.get_org_trust_matrix()
    network = sim.get_network_graph()
    provenance = sim.get_provenance_sample(8)

    # Select a sample of inter-org trust pairs to chart (top 8 by variance)
    trust_series = sim.history["inter_org_trust"]
    sorted_pairs = sorted(
        trust_series.items(),
        key=lambda kv: (max(kv[1]) - min(kv[1])) if kv[1] else 0,
        reverse=True
    )[:8]
    trust_labels = [k for k, _ in sorted_pairs]
    trust_data = [v for _, v in sorted_pairs]

    # Color palette
    COLORS = [
        "#6366f1", "#22d3ee", "#f59e0b", "#10b981",
        "#f43f5e", "#a78bfa", "#34d399", "#fb923c"
    ]

    # Build trust matrix heatmap cells
    matrix_html = ""
    labels = trust_matrix["labels"]
    matrix = trust_matrix["matrix"]
    for i, row in enumerate(matrix):
        for j, val in enumerate(row):
            color = _trust_color(val, i == j)
            matrix_html += f'<div class="cell" style="background:{color}" title="{labels[i]} → {labels[j]}: {val:.2f}"><span>{val:.2f}</span></div>\n'

    # Build network nodes for SVG
    num_nodes = len(network["nodes"])
    cx, cy, r = 300, 220, 160
    node_positions = {}
    svg_elements = []

    for idx, node in enumerate(network["nodes"]):
        angle = (2 * math.pi * idx / num_nodes) - math.pi / 2
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        node_positions[node["id"]] = (x, y)

    # Draw edges first
    drawn_edges = set()
    for edge in network["edges"]:
        src = edge["source"]
        tgt = edge["target"]
        key = tuple(sorted([src, tgt]))
        if key in drawn_edges:
            continue
        drawn_edges.add(key)
        if src in node_positions and tgt in node_positions:
            x1, y1 = node_positions[src]
            x2, y2 = node_positions[tgt]
            trust = edge["trust"]
            opacity = max(0.15, trust)
            width = 1 + trust * 3
            color = _trust_color_hex(trust)
            svg_elements.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="{color}" stroke-width="{width:.1f}" stroke-opacity="{opacity:.2f}"/>'
            )

    # Draw nodes
    for idx, node in enumerate(network["nodes"]):
        x, y = node_positions[node["id"]]
        color = COLORS[idx % len(COLORS)]
        bs = node["bs_count"]
        svg_elements.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="22" fill="{color}" '
            f'stroke="#1e293b" stroke-width="2" opacity="0.9"/>'
        )
        svg_elements.append(
            f'<text x="{x:.1f}" y="{y-6:.1f}" text-anchor="middle" '
            f'fill="white" font-size="7" font-weight="bold">{node["label"]}</text>'
        )
        svg_elements.append(
            f'<text x="{x:.1f}" y="{y+5:.1f}" text-anchor="middle" '
            f'fill="white" font-size="6">BS:{bs}</text>'
        )

    svg_content = "\n".join(svg_elements)

    # Provenance table rows
    prov_rows = ""
    for p in provenance:
        path_str = " → ".join([e["entity"][:6] for e in p["pedigree"]])
        status = "🔴 Breach" if p["unintended"] > 0 else "✅ Clean"
        prov_rows += f"""
        <tr>
            <td><code>{p['fact_id']}</code></td>
            <td><span class="badge">{p['content']}</span></td>
            <td>{p['org'][:12]}</td>
            <td class="path-cell">{path_str}</td>
            <td>{p['intended']}</td>
            <td>{p['unintended']}</td>
            <td>{status}</td>
        </tr>"""

    # Final metrics
    final_ia = ia_pct[-1] if ia_pct else 0
    final_sm = sm_pct[-1] if sm_pct else 0
    total_breaches = sum(breaches)
    final_bs = bs_counts[-1] if bs_counts else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IOTBSM — Trust-Based Security Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0f172a;
    --surface: #1e293b;
    --surface2: #253347;
    --border: #334155;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --accent: #6366f1;
    --green: #10b981;
    --red: #f43f5e;
    --amber: #f59e0b;
    --cyan: #22d3ee;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 13px;
    min-height: 100vh;
  }}
  header {{
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border-bottom: 1px solid var(--border);
    padding: 20px 32px;
  }}
  header h1 {{
    font-size: 20px;
    font-weight: 700;
    color: var(--cyan);
    letter-spacing: 0.3px;
  }}
  header p {{
    color: var(--muted);
    font-size: 12px;
    margin-top: 4px;
  }}
  .citation {{
    font-size: 11px;
    color: #6366f1;
    margin-top: 6px;
    font-style: italic;
  }}
  main {{
    padding: 24px 32px;
    max-width: 1600px;
    margin: 0 auto;
  }}
  .kpi-row {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
  }}
  .kpi {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px 20px;
  }}
  .kpi-label {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .kpi-value {{ font-size: 32px; font-weight: 800; margin-top: 6px; }}
  .kpi-sub {{ font-size: 11px; color: var(--muted); margin-top: 4px; }}
  .green {{ color: var(--green); }}
  .red {{ color: var(--red); }}
  .cyan {{ color: var(--cyan); }}
  .amber {{ color: var(--amber); }}
  .grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 20px;
  }}
  .grid-3 {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 20px;
    margin-bottom: 20px;
  }}
  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
  }}
  .card h2 {{
    font-size: 13px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 16px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }}
  .card h2 span {{
    color: var(--accent);
    font-size: 10px;
    margin-left: 8px;
    font-weight: 400;
    text-transform: none;
  }}
  canvas {{ max-height: 260px; }}
  /* Trust matrix */
  .matrix-wrap {{
    overflow-x: auto;
  }}
  .matrix-grid {{
    display: grid;
    grid-template-columns: repeat({len(labels)}, 1fr);
    gap: 3px;
  }}
  .cell {{
    aspect-ratio: 1;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 9px;
    font-weight: 600;
    cursor: default;
    transition: transform 0.1s;
  }}
  .cell:hover {{ transform: scale(1.1); z-index: 2; }}
  .cell span {{ color: rgba(255,255,255,0.9); text-shadow: 0 1px 2px rgba(0,0,0,0.5); }}
  /* Network SVG */
  .network-svg {{
    width: 100%;
    height: 300px;
    background: var(--surface2);
    border-radius: 8px;
  }}
  /* Matrix labels */
  .matrix-labels {{
    display: grid;
    grid-template-columns: repeat({len(labels)}, 1fr);
    gap: 3px;
    margin-bottom: 4px;
  }}
  .matrix-labels span {{
    font-size: 8px;
    color: var(--muted);
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  /* Provenance table */
  .prov-wrap {{ overflow-x: auto; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
  }}
  th {{
    color: var(--muted);
    text-align: left;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    font-weight: 600;
    text-transform: uppercase;
    font-size: 10px;
    letter-spacing: 0.4px;
  }}
  td {{
    padding: 8px 10px;
    border-bottom: 1px solid rgba(51,65,85,0.5);
    vertical-align: top;
  }}
  tr:hover td {{ background: var(--surface2); }}
  .path-cell {{
    font-family: monospace;
    font-size: 10px;
    color: var(--cyan);
    max-width: 260px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .badge {{
    background: rgba(99,102,241,0.2);
    color: var(--accent);
    border: 1px solid rgba(99,102,241,0.3);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 10px;
  }}
  code {{
    background: var(--surface2);
    border-radius: 3px;
    padding: 1px 5px;
    font-size: 10px;
    color: var(--amber);
  }}
  .legend-row {{
    display: flex;
    gap: 16px;
    margin-top: 10px;
    flex-wrap: wrap;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--muted);
  }}
  .legend-dot {{
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }}
  .tpm-info {{
    background: rgba(99,102,241,0.1);
    border: 1px solid rgba(99,102,241,0.2);
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 16px;
    font-size: 11px;
    color: var(--muted);
  }}
  .tpm-info strong {{ color: var(--accent); }}
  footer {{
    text-align: center;
    padding: 20px;
    color: var(--muted);
    font-size: 11px;
    border-top: 1px solid var(--border);
    margin-top: 24px;
  }}
</style>
</head>
<body>
<header>
  <h1>⚡ IOTBSM — Inter-Organizational Trust-Based Security Model</h1>
  <p>Agentic AI Enterprise Data Sharing Simulation · {sim.num_orgs} Organizations · {sim.num_orgs * sim.agents_per_org} Agents · {len(cycles)} Cycles</p>
  <div class="citation">Based on: Hexmoor, Wilson &amp; Bhattaram (2006). "A Theoretical Inter-organizational Trust-based Security Model." <em>The Knowledge Engineering Review</em>, 21(2), 127–161.</div>
</header>

<main>

<!-- KPI Row -->
<div class="kpi-row">
  <div class="kpi">
    <div class="kpi-label">Information Availability</div>
    <div class="kpi-value green">{final_ia:.1f}%</div>
    <div class="kpi-sub">Target: 100% · Definition 27</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Security Measure</div>
    <div class="kpi-value {'green' if final_sm < 10 else 'red'}">{final_sm:.1f}%</div>
    <div class="kpi-sub">Target: 0% · Definition 29</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Total Security Breaches</div>
    <div class="kpi-value {'amber' if total_breaches > 0 else 'green'}">{total_breaches}</div>
    <div class="kpi-sub">Unintended receivers detected · TPM{sim.tpm_mode} applied</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Active Boundary Spanners</div>
    <div class="kpi-value cyan">{final_bs}</div>
    <div class="kpi-sub">Orchestrator agents · Section 4.7</div>
  </div>
</div>

<!-- IA / SM + Trust Growth -->
<div class="grid-2">
  <div class="card">
    <h2>Information Availability &amp; Security Measure <span>Definitions 27–30</span></h2>
    <canvas id="iasmChart"></canvas>
    <div class="legend-row">
      <div class="legend-item"><div class="legend-dot" style="background:#10b981"></div>IA % (maximize)</div>
      <div class="legend-item"><div class="legend-dot" style="background:#f43f5e"></div>SM % (minimize)</div>
    </div>
  </div>
  <div class="card">
    <h2>Inter-Organizational Trust Growth <span>Equation 5 — Logistic</span></h2>
    <canvas id="trustGrowthChart"></canvas>
    <div class="legend-row">
      {" ".join(f'<div class="legend-item"><div class="legend-dot" style="background:{COLORS[i % len(COLORS)]}"></div>{lbl}</div>' for i, lbl in enumerate(trust_labels))}
    </div>
  </div>
</div>

<!-- Trust Matrix + Network + Breaches -->
<div class="grid-3">
  <div class="card">
    <h2>Inter-Org Trust Matrix <span>Current State</span></h2>
    <div class="matrix-wrap">
      <div class="matrix-labels">
        {"".join(f'<span>{l}</span>' for l in labels)}
      </div>
      <div class="matrix-grid">
        {matrix_html}
      </div>
    </div>
    <div style="margin-top:10px; font-size:10px; color:var(--muted)">
      🟩 High trust (≥0.7) &nbsp; 🟨 Medium (0.4–0.7) &nbsp; 🟥 Low (&lt;0.4)
    </div>
  </div>

  <div class="card">
    <h2>Boundary Spanner Network <span>Cross-org BS trust topology</span></h2>
    <svg class="network-svg" viewBox="0 0 600 440">
      {svg_content}
    </svg>
    <div style="margin-top:8px; font-size:10px; color:var(--muted)">
      Edge thickness &amp; color = inter-BS trust strength · BS = Boundary Spanner
    </div>
  </div>

  <div class="card">
    <h2>Security Breaches Per Cycle <span>Unintended receivers</span></h2>
    <canvas id="breachChart"></canvas>
    <div class="tpm-info" style="margin-top:12px; margin-bottom:0">
      <strong>TPM{sim.tpm_mode} Active</strong> — 
      {"Exponential decay along fact path (proportional responsibility)" if sim.tpm_mode == 1 else
       "Uniform trust decrement across all fact path edges" if sim.tpm_mode == 2 else
       "Initiator cuts trust to all entities in breach path"}
      · Decrement δ = {sim.decrement}
    </div>
  </div>
</div>

<!-- Fact Pedigree / Provenance -->
<div class="card" style="margin-bottom:20px">
  <h2>Fact Provenance Log — Active Facts <span>Definition 19 — Fact Pedigree</span></h2>
  <div class="prov-wrap">
    <table>
      <thead>
        <tr>
          <th>Fact ID</th>
          <th>Content / Topic</th>
          <th>Origin Org</th>
          <th>Agent Pedigree Path</th>
          <th>Intended</th>
          <th>Unintended</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>{prov_rows}</tbody>
    </table>
  </div>
</div>

<!-- BS Count + Total Shared -->
<div class="grid-2">
  <div class="card">
    <h2>Boundary Spanner Count Over Time <span>Regulatory process §4.7</span></h2>
    <canvas id="bsChart"></canvas>
  </div>
  <div class="card">
    <h2>Total Facts Shared Per Cycle <span>Definition 26</span></h2>
    <canvas id="factsChart"></canvas>
  </div>
</div>

</main>

<footer>
  IOTBSM Proof of Concept · Python Simulation · Trust α={sim.alpha} · TPM{sim.tpm_mode} · 
  {sim.num_orgs} Orgs × {sim.agents_per_org} Agents · {len(cycles)} Cycles
</footer>

<script>
const CYCLES = {json.dumps(cycles)};
const IA = {json.dumps([round(x,2) for x in ia_pct])};
const SM = {json.dumps([round(x,2) for x in sm_pct])};
const BREACHES = {json.dumps(breaches)};
const BS_COUNTS = {json.dumps(bs_counts)};
const TOTAL_SHARED = {json.dumps(total_shared)};
const TRUST_LABELS = {json.dumps(trust_labels)};
const TRUST_DATA = {json.dumps([[round(v,3) for v in series] for series in trust_data])};
const COLORS = {json.dumps(COLORS)};

const chartDefaults = {{
  responsive: true,
  maintainAspectRatio: true,
  plugins: {{ legend: {{ display: false }}, tooltip: {{ mode: 'index', intersect: false }} }},
  scales: {{
    x: {{ ticks: {{ color: '#64748b', maxTicksLimit: 10 }}, grid: {{ color: 'rgba(51,65,85,0.5)' }} }},
    y: {{ ticks: {{ color: '#64748b' }}, grid: {{ color: 'rgba(51,65,85,0.5)' }} }}
  }}
}};

// IA / SM Chart
new Chart(document.getElementById('iasmChart'), {{
  type: 'line',
  data: {{
    labels: CYCLES,
    datasets: [
      {{ label: 'IA %', data: IA, borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.1)', fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2 }},
      {{ label: 'SM %', data: SM, borderColor: '#f43f5e', backgroundColor: 'rgba(244,63,94,0.1)', fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2 }}
    ]
  }},
  options: {{ ...chartDefaults, scales: {{ ...chartDefaults.scales, y: {{ ...chartDefaults.scales.y, min: 0, max: 100 }} }} }}
}});

// Trust growth chart
new Chart(document.getElementById('trustGrowthChart'), {{
  type: 'line',
  data: {{
    labels: CYCLES,
    datasets: TRUST_LABELS.map((lbl, i) => ({{
      label: lbl,
      data: TRUST_DATA[i],
      borderColor: COLORS[i % COLORS.length],
      tension: 0.4,
      pointRadius: 0,
      borderWidth: 1.5
    }}))
  }},
  options: {{ ...chartDefaults, scales: {{ ...chartDefaults.scales, y: {{ ...chartDefaults.scales.y, min: 0, max: 1 }} }} }}
}});

// Breach chart
new Chart(document.getElementById('breachChart'), {{
  type: 'bar',
  data: {{
    labels: CYCLES,
    datasets: [{{
      label: 'Breaches',
      data: BREACHES,
      backgroundColor: 'rgba(244,63,94,0.6)',
      borderColor: '#f43f5e',
      borderWidth: 1
    }}]
  }},
  options: chartDefaults
}});

// BS count chart
new Chart(document.getElementById('bsChart'), {{
  type: 'line',
  data: {{
    labels: CYCLES,
    datasets: [{{
      label: 'BS Count',
      data: BS_COUNTS,
      borderColor: '#22d3ee',
      backgroundColor: 'rgba(34,211,238,0.1)',
      fill: true,
      stepped: true,
      pointRadius: 0,
      borderWidth: 2
    }}]
  }},
  options: chartDefaults
}});

// Facts shared chart
new Chart(document.getElementById('factsChart'), {{
  type: 'line',
  data: {{
    labels: CYCLES,
    datasets: [{{
      label: 'Facts Shared',
      data: TOTAL_SHARED,
      borderColor: '#a78bfa',
      backgroundColor: 'rgba(167,139,250,0.1)',
      fill: true,
      tension: 0.3,
      pointRadius: 0,
      borderWidth: 2
    }}]
  }},
  options: chartDefaults
}});
</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)
    print(f"Dashboard written to {output_path}")


def _trust_color(val: float, is_self: bool) -> str:
    if is_self:
        return "#1e40af"
    if val >= 0.7:
        r, g, b = 16, 185, 129   # green
    elif val >= 0.4:
        r, g, b = 245, 158, 11   # amber
    else:
        r, g, b = 244, 63, 94    # red
    alpha = 0.3 + val * 0.7
    return f"rgba({r},{g},{b},{alpha:.2f})"


def _trust_color_hex(val: float) -> str:
    if val >= 0.7:
        return "#10b981"
    elif val >= 0.4:
        return "#f59e0b"
    return "#f43f5e"
