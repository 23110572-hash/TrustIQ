/**
 * FraudRing - mule-network & fraud-ring visualization.
 *
 * Reads the identity graph (/api/graph) and draws how identities are linked
 * through shared devices, IPs, beneficiaries and accounts. Clusters of 3+
 * linked users are highlighted as suspected fraud rings / mule networks. A
 * deterministic radial layout keeps it dependency-free (no physics engine).
 */
function FraudRing() {
  const { api, Icon, useCountUp } = window.TrustIQ;
  const [graph, setGraph] = React.useState({ nodes: [], edges: [], clusters: [], suspicious_clusters: 0 });
  const [hover, setHover] = React.useState(null);

  const load = async () => {
    try { const res = await api.get("/api/graph"); setGraph(res.data); } catch (e) {}
  };
  React.useEffect(() => {
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, []);

  const W = 760, H = 460;

  // Deterministic layout: group nodes into connected components, lay each
  // component out on its own circle, arrange components in a grid.
  const layout = React.useMemo(() => {
    const adj = {};
    graph.nodes.forEach((n) => (adj[n.id] = []));
    graph.edges.forEach((e) => {
      if (adj[e.source]) adj[e.source].push(e.target);
      if (adj[e.target]) adj[e.target].push(e.source);
    });
    const seen = new Set();
    const comps = [];
    graph.nodes.forEach((n) => {
      if (seen.has(n.id)) return;
      const stack = [n.id], comp = [];
      seen.add(n.id);
      while (stack.length) {
        const cur = stack.pop();
        comp.push(cur);
        (adj[cur] || []).forEach((m) => { if (!seen.has(m)) { seen.add(m); stack.push(m); } });
      }
      comps.push(comp);
    });
    comps.sort((a, b) => b.length - a.length);

    const pos = {};
    const cols = Math.ceil(Math.sqrt(comps.length)) || 1;
    const cellW = W / cols;
    const rows = Math.ceil(comps.length / cols) || 1;
    const cellH = H / rows;
    comps.forEach((comp, ci) => {
      const cx = (ci % cols) * cellW + cellW / 2;
      const cy = Math.floor(ci / cols) * cellH + cellH / 2;
      const r = Math.min(cellW, cellH) * 0.34;
      comp.forEach((id, i) => {
        if (comp.length === 1) { pos[id] = { x: cx, y: cy }; return; }
        const a = (2 * Math.PI * i) / comp.length;
        pos[id] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
      });
    });
    return { pos, comps };
  }, [graph]);

  const flagged = new Set(graph.clusters.flat());
  const nodeColor = (n) => {
    if (n.type === "user") {
      if (n.risk >= 50) return "var(--critical)";
      if (n.risk >= 25) return "var(--high)";
      return "var(--accent)";
    }
    return ({ device: "#7C3AED", ip: "#0891B2", account: "#B45309", phone: "#9333EA", email: "#0D9488" }[n.type]) || "#A39F97";
  };
  const rings = useCountUp(graph.suspicious_clusters);

  return (
    <React.Fragment>
      <div className="explainer">
        <span className="explainer-icon"><Icon name="share-2" size={20} /></span>
        <span className="explainer-text">
          Fraudsters rarely act alone. This map links identities through the <b>devices, IPs,
          phone numbers and payees</b> they share. When several accounts cluster around the same
          shared attributes, it usually means a <b>mule network or fraud ring</b> — shown in red.
        </span>
      </div>

      <div className="section">
        <div className="grid grid-4">
          <MiniStat icon="users" tone="accent" value={graph.nodes.filter((n) => n.type === "user").length} label="Identities" />
          <MiniStat icon="smartphone" tone="safe" value={graph.nodes.filter((n) => n.type === "device").length} label="Shared devices" />
          <MiniStat icon="link" tone="mid" value={graph.edges.length} label="Links" />
          <div className="tile">
            <div className="tile-top">
              <span className="tile-icon tile-icon--critical"><Icon name="share-2" size={20} /></span>
              <span className="tile-value">{Math.round(rings)}</span>
            </div>
            <div className="tile-label">Suspected rings</div>
            <div className="tile-desc">Clusters of 3+ linked accounts</div>
          </div>
        </div>
      </div>

      <div className="section">
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title"><Icon name="git-fork" size={18} color="#2563EB" /> Identity link map</div>
            <span className="panel-hint" style={{ marginTop: 0 }}>{hover ? hover : "hover a node for details"}</span>
          </div>
          {graph.nodes.length === 0 ? (
            <div className="empty" style={{ height: 300 }}>
              <Icon name="share-2" size={34} className="empty-icon" />
              <div className="empty-title">No links yet</div>
              <div className="empty-text">No linked accounts detected yet. Links appear automatically when accounts share a device, IP or payee — e.g. several accounts transferring to one beneficiary.</div>
            </div>
          ) : (
            <div className="graph-wrap">
              <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="graph-svg">
                {graph.edges.map((e, i) => {
                  const a = layout.pos[e.source], b = layout.pos[e.target];
                  if (!a || !b) return null;
                  return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                               stroke="#CCC8BC" strokeWidth="1.5" />;
                })}
                {graph.nodes.map((n) => {
                  const pt = layout.pos[n.id];
                  if (!pt) return null;
                  const isUser = n.type === "user";
                  const inRing = isUser && flagged.has(n.label) ;
                  const r = isUser ? 14 : 8;
                  return (
                    <g key={n.id} onMouseEnter={() => setHover(`${n.type}: ${n.label}${isUser ? ` · fraud-link ${Math.round(n.risk)}` : ""}`)}
                       onMouseLeave={() => setHover(null)} style={{ cursor: "pointer" }}>
                      {inRing && <circle cx={pt.x} cy={pt.y} r={r + 6} fill="none" stroke="var(--critical)" strokeWidth="2" strokeDasharray="3 3" />}
                      <circle cx={pt.x} cy={pt.y} r={r} fill={nodeColor(n)} stroke="#fff" strokeWidth="2" />
                      {isUser && <text x={pt.x} y={pt.y + r + 12} textAnchor="middle" className="graph-label">{n.label}</text>}
                    </g>
                  );
                })}
              </svg>
              <div className="graph-legend">
                <span><i className="leg-dot" style={{ background: "var(--accent)" }} /> Identity</span>
                <span><i className="leg-dot" style={{ background: "var(--critical)" }} /> Ring member</span>
                <span><i className="leg-dot" style={{ background: "#7C3AED" }} /> Device</span>
                <span><i className="leg-dot" style={{ background: "#0891B2" }} /> IP</span>
                <span><i className="leg-dot" style={{ background: "#B45309" }} /> Account / payee</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </React.Fragment>
  );

  function MiniStat({ icon, tone, value, label }) {
    const n = useCountUp(value);
    return (
      <div className="tile">
        <div className="tile-top">
          <span className={`tile-icon tile-icon--${tone}`}><Icon name={icon} size={20} /></span>
          <span className="tile-value">{Math.round(n)}</span>
        </div>
        <div className="tile-label">{label}</div>
      </div>
    );
  }
}

window.FraudRing = FraudRing;
