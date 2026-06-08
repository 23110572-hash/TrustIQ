/**
 * TrustScore - explains *how* TrustIQ calculates an identity's Trust Score and
 * shows the live, evolving score of every account in real time.
 *
 * There is NO hardcoded score here. Every number is pulled live from the
 * backend `/api/passports` endpoint (the persistent Identity Trust Engine) and
 * refreshes on a timer + instantly over the alert WebSocket. Each account's
 * score rises and falls as that customer acts, exactly as the engine evolves it
 * (slow to earn, fast to lose).
 *
 * The page has two parts:
 *   1. A block diagram of the calculation pipeline (event -> sub-scores ->
 *      weighted identity-trust blend -> trust-aware decision), with the real
 *      factor weights used by the engine.
 *   2. A live board of every account and its current Trust Score.
 */
function TrustScore({ onOpenCustomer }) {
  const { api, Icon, useCountUp, timeAgo, API_BASE } = window.TrustIQ;
  const R = window.Roster;

  const [accounts, setAccounts] = React.useState([]);
  const [loaded, setLoaded] = React.useState(false);
  const [flash, setFlash] = React.useState({});

  // The real per-factor weights the Identity Trust Engine blends
  // (backend/identity_trust.py :: _factors). Kept in sync for transparency.
  const FACTORS = [
    { name: "Identity match", weight: 0.30, key: "safe",
      detail: "Does the device, location & behaviour match this person's passport?" },
    { name: "Transaction pattern", weight: 0.20, key: "safe",
      detail: "Is the activity normal vs. the live ML risk score (100 − risk)?" },
    { name: "Trusted device", weight: 0.18, key: "mid",
      detail: "Is this a device we've seen and trusted before?" },
    { name: "Behavioural consistency", weight: 0.17, key: "mid",
      detail: "Typing, navigation & timing vs. the customer's baseline." },
    { name: "Fraud-ring links", weight: 0.10, key: "high",
      detail: "Shared devices / IPs / payees that link this account to mules." },
    { name: "Session trust", weight: 0.05, key: "neutral",
      detail: "Live trust that rises and falls within the current session." },
  ];

  const load = React.useCallback(async () => {
    try {
      const r = await api.get("/api/passports");
      setAccounts(r.data || []);
    } catch (e) { /* backend not up yet */ }
    finally { setLoaded(true); }
  }, []);

  // Poll every 4s + refresh instantly on every streamed decision.
  React.useEffect(() => {
    load();
    const poll = setInterval(load, 4000);
    let ws;
    try {
      ws = new WebSocket(API_BASE.replace(/^http/, "ws") + "/ws/alerts");
      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data);
          const id = m.customer || m.user_id;
          if (id) setFlash((f) => ({ ...f, [id]: Date.now() }));
          load();
        } catch (err) {}
      };
    } catch (e) {}
    return () => { clearInterval(poll); if (ws) ws.close(); };
  }, [load]);

  const sorted = [...accounts].sort((a, b) => a.trust_score - b.trust_score);

  return (
    <React.Fragment>
      <div className="explainer">
        <span className="explainer-icon"><Icon name="gauge" size={20} /></span>
        <span className="explainer-text">
          Every account carries a living <b>Trust Score</b> from 0–100. It is not fixed —
          the engine recalculates it on <b>every action</b> the customer takes, blending the
          signals below. Trust is <b>slow to earn and fast to lose</b>, just like a human analyst's confidence.
        </span>
      </div>

      {/* ---- Block diagram: how the score is built ---- */}
      <div className="section">
        <div className="section-head">
          <h2 className="section-title"><Icon name="workflow" size={20} color="var(--accent)" /> How the Trust Score is calculated</h2>
          <span className="section-hint">live pipeline · every event re-scores the identity</span>
        </div>

        <div className="trust-flow">
          <FlowBlock icon="activity" tone="accent" title="1 · Event captured"
            lines={["Channel + device", "Behaviour + context", "Beneficiary (transfers)"]} />
          <FlowArrow />
          <FlowBlock icon="cpu" tone="high" title="2 · Real-time risk"
            lines={["Behavioural anomaly 30%", "Device trust 30%", "Txn anomaly 40%", "+ fraud-ring escalator"]} />
          <FlowArrow />
          <FlowBlock icon="fingerprint" tone="safe" title="3 · Identity match"
            lines={["Device / location match", "Behaviour vs. baseline", "Digital Identity Passport"]} />
          <FlowArrow />
          <FlowBlock icon="scale" tone="mid" title="4 · Weighted blend"
            lines={["6 factors combined", "Target trust computed", "(see weights below)"]} />
          <FlowArrow />
          <FlowBlock icon="gauge" tone="safe" title="5 · Trust Score"
            lines={["Asymmetric inertia", "↑ slow (0.25)  ↓ fast (0.60)", "Persistent 0–100"]} />
          <FlowArrow />
          <FlowBlock icon="shield-check" tone="critical" title="6 · Decision"
            lines={["Allow / Confirm", "OTP / Face check", "or Block"]} />
        </div>

        <div className="trust-formula">
          <div className="trust-formula-head">
            <Icon name="sigma" size={16} color="var(--accent)" />
            <span>Identity Trust = weighted sum of these factors</span>
          </div>
          <div className="trust-weights">
            {FACTORS.map((f) => (
              <div className="weight-row" key={f.name}>
                <div className="weight-top">
                  <span className="weight-name">{f.name}</span>
                  <span className="weight-pct mono">{Math.round(f.weight * 100)}%</span>
                </div>
                <div className="weight-bar">
                  <div className={`weight-fill weight-fill--${f.key}`} style={{ width: `${f.weight * 100 * 3}%` }} />
                </div>
                <div className="weight-detail">{f.detail}</div>
              </div>
            ))}
          </div>
          <div className="trust-note">
            <Icon name="info" size={14} color="var(--text-secondary)" />
            <span>
              A critical event (risk ≥ 80) or a fraud-ring link applies an extra hard penalty so a clear
              takeover collapses trust immediately. High trust then softens friction for genuine customers;
              low trust hardens it.
            </span>
          </div>
        </div>
      </div>

      {/* ---- Live per-account scores ---- */}
      <div className="section">
        <div className="section-head">
          <h2 className="section-title"><Icon name="users" size={20} color="var(--accent)" /> Live Trust Score · every account</h2>
          <span className="section-hint">{accounts.length} account{accounts.length === 1 ? "" : "s"} · lowest trust first · updates in real time</span>
        </div>

        {loaded && accounts.length === 0 ? (
          <div className="empty">
            <Icon name="gauge" size={34} className="empty-icon" />
            <div className="empty-title">No scored accounts yet</div>
            <div className="empty-text">An account is scored the moment it performs its first action on any channel.</div>
          </div>
        ) : (
          <div className="trust-board">
            {sorted.map((p) => (
              <TrustRow key={p.user_id} passport={p}
                flashed={flash[p.user_id] && (Date.now() - flash[p.user_id] < 2500)}
                onOpen={() => onOpenCustomer && onOpenCustomer(p.user_id)} />
            ))}
          </div>
        )}
      </div>
    </React.Fragment>
  );

  function FlowBlock({ icon, tone, title, lines }) {
    return (
      <div className={`flow-block flow-block--${tone}`}>
        <div className="flow-block-head">
          <span className={`flow-block-icon tile-icon--${tone}`}><Icon name={icon} size={16} /></span>
          <span className="flow-block-title">{title}</span>
        </div>
        <ul className="flow-block-lines">
          {lines.map((l, i) => <li key={i}>{l}</li>)}
        </ul>
      </div>
    );
  }

  function FlowArrow() {
    return <span className="flow-arrow"><Icon name="chevron-right" size={18} color="var(--text-secondary)" /></span>;
  }
}

/** One account row on the live Trust Score board, with a history sparkline. */
function TrustRow({ passport: p, onOpen, flashed }) {
  const { Icon, useCountUp, timeAgo } = window.TrustIQ;
  const R = window.Roster;
  const name = R.customerName(p.user_id);
  const score = Math.round(p.trust_score);
  const tb = R.trustBandInfo(score);
  const tr = R.trendInfo(p.trust_trend);
  const n = useCountUp(score);
  const history = (p.trust_history || []).slice(-24);

  // Build a tiny dependency-free sparkline of recent trust history.
  const spark = React.useMemo(() => {
    if (history.length < 2) return null;
    const W = 120, H = 34, pad = 3;
    const pts = history.map((h, i) => {
      const x = pad + (i / (history.length - 1)) * (W - 2 * pad);
      const y = H - pad - (Math.max(0, Math.min(100, h.trust_score)) / 100) * (H - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    return { W, H, path: pts.join(" ") };
  }, [history]);

  return (
    <button className={`trust-row trust-row--${tb.key} ${flashed ? "trust-row--flash" : ""}`} onClick={onOpen}>
      <div className="trust-row-id">
        <span className={`acct-avatar acct-avatar--${tb.key}`}>{R.initials(name)}</span>
        <div>
          <div className="trust-row-name">{name}</div>
          <div className="trust-row-meta mono">{p.event_count} event{p.event_count === 1 ? "" : "s"} · {p.last_seen ? timeAgo(p.last_seen) : "no activity"}</div>
        </div>
      </div>

      <div className="trust-row-spark">
        {spark ? (
          <svg viewBox={`0 0 ${spark.W} ${spark.H}`} width="120" height="34" preserveAspectRatio="none">
            <polyline points={spark.path} fill="none" className={`spark-line spark-line--${tb.key}`} strokeWidth="2" />
          </svg>
        ) : <span className="trust-row-nohist">building history…</span>}
      </div>

      <div className="trust-row-score">
        <span className={`trust-row-num trust-row-num--${tb.key}`}>{Math.round(n)}</span>
        <span className="trust-row-band">
          {tb.label}
          <span className={`acct-trend acct-trend--${tr.key}`}> · {tr.arrow} {tr.label}</span>
        </span>
      </div>

      <div className={`trust-row-bar`}>
        <div className={`trust-row-fill trust-row-fill--${tb.key}`} style={{ width: `${score}%` }} />
      </div>
    </button>
  );
}

window.TrustScore = TrustScore;
window.TrustRow = TrustRow;
