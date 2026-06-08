/**
 * CompliancePanel - DPDP & RBI compliance center.
 *
 * Proves, at a glance and for auditors, that every automated decision the
 * Identity Trust Platform makes is consented, explained, versioned and logged.
 * Reads /api/compliance (posture + controls) and /api/compliance/consent.
 */
function CompliancePanel() {
  const { api, Icon, useCountUp, timeAgo } = window.TrustIQ;
  const [report, setReport] = React.useState(null);
  const [consent, setConsent] = React.useState([]);

  React.useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [r, c] = await Promise.all([
          api.get("/api/compliance"),
          api.get("/api/compliance/consent"),
        ]);
        if (!active) return;
        setReport(r.data); setConsent(c.data || []);
      } catch (e) {}
    };
    load();
    const id = setInterval(load, 5000);
    return () => { active = false; clearInterval(id); };
  }, []);

  const statusChip = (s) => ({
    pass:    { label: "Compliant", key: "safe", icon: "check-circle" },
    partial: { label: "In progress", key: "mid", icon: "clock" },
    fail:    { label: "Action needed", key: "high", icon: "alert-triangle" },
  }[s] || { label: s, key: "neutral", icon: "circle" });

  const r = report;
  const explainPct = r && r.total_decisions
    ? Math.round((r.explainable_decisions / Math.max(r.total_decisions, r.explainable_decisions)) * 100)
    : 100;
  const decisions = useCountUp(r ? r.total_decisions : 0);

  return (
    <React.Fragment>
      <div className="explainer">
        <span className="explainer-icon"><Icon name="scale" size={20} /></span>
        <span className="explainer-text">
          Banking AI in India must satisfy the <b>DPDP Act 2023</b> and <b>RBI</b> directions.
          This center shows TrustIQ's live compliance posture: personal data is masked, decisions
          are explainable and version-stamped, consent is tracked, and the audit trail can never
          be altered.
        </span>
      </div>

      {!r ? (
        <div className="section"><div className="empty"><Icon name="scale" size={34} className="empty-icon" />
          <div className="empty-title">Loading posture…</div></div></div>
      ) : (
        <React.Fragment>
          <div className="section">
            <div className="grid grid-4">
              <div className="tile">
                <div className="tile-top">
                  <span className={`tile-icon tile-icon--${r.dpdp_compliant ? "safe" : "high"}`}><Icon name="shield-check" size={20} /></span>
                  <span className="tile-value" style={{ fontSize: "1.3rem" }}>{r.dpdp_compliant ? "DPDP ✓" : "DPDP ✗"}</span>
                </div>
                <div className="tile-label">DPDP 2023</div>
                <div className="tile-desc">Data protection compliant</div>
              </div>
              <div className="tile">
                <div className="tile-top">
                  <span className={`tile-icon tile-icon--${r.rbi_audit_ready ? "safe" : "high"}`}><Icon name="landmark" size={20} /></span>
                  <span className="tile-value" style={{ fontSize: "1.3rem" }}>{r.rbi_audit_ready ? "RBI ✓" : "RBI ✗"}</span>
                </div>
                <div className="tile-label">RBI ready</div>
                <div className="tile-desc">Audit & model governance</div>
              </div>
              <div className="tile">
                <div className="tile-top">
                  <span className="tile-icon tile-icon--accent"><Icon name="scroll-text" size={20} /></span>
                  <span className="tile-value">{Math.round(decisions)}</span>
                </div>
                <div className="tile-label">Logged decisions</div>
                <div className="tile-desc">Immutable audit records</div>
              </div>
              <div className="tile">
                <div className="tile-top">
                  <span className="tile-icon tile-icon--safe"><Icon name="sparkles" size={20} /></span>
                  <span className="tile-value">{explainPct}%</span>
                </div>
                <div className="tile-label">Explainable</div>
                <div className="tile-desc">Decisions with AI rationale</div>
              </div>
            </div>
          </div>

          <div className="section">
            <div className="panel">
              <div className="panel-head"><div className="panel-title"><Icon name="list-checks" size={18} color="#2563EB" /> Control checklist</div>
                <span className="panel-hint" style={{ marginTop: 0 }}>model {r.model_version} · retention {r.data_retention_days} days</span></div>
              <div className="control-list">
                {r.controls.map((c) => {
                  const s = statusChip(c.status);
                  return (
                    <div key={c.id} className="control-row">
                      <span className={`control-status control-status--${s.key}`}><Icon name={s.icon} size={16} /></span>
                      <div className="control-body">
                        <div className="control-name">{c.name} <span className="control-reg">{c.regulation}</span></div>
                        <div className="control-detail">{c.detail}</div>
                      </div>
                      <span className={`pill pill--${s.key}`}><span className={`pill-dot dot--${s.key}`} />{s.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="section">
            <div className="panel">
              <div className="panel-head"><div className="panel-title"><Icon name="file-check" size={18} color="#2563EB" /> Consent register (DPDP)</div></div>
              {consent.length === 0 ? (
                <div className="empty" style={{ height: 140 }}><Icon name="file-check" size={30} className="empty-icon" />
                  <div className="empty-text">Consent is recorded the first time an identity is evaluated.</div></div>
              ) : (
                <div className="table-scroll">
                  <table className="tbl">
                    <thead><tr><th>Identity</th><th>Purpose</th><th>Status</th><th>Recorded</th></tr></thead>
                    <tbody>
                      {consent.map((c, i) => (
                        <tr key={i}>
                          <td><span className="mono">{c.masked_user_id}</span></td>
                          <td>{c.purpose.replace(/_/g, " ")}</td>
                          <td>{c.granted
                            ? <span className="chip chip--safe">granted</span>
                            : <span className="chip chip--high">withdrawn</span>}</td>
                          <td><span className="cell-sub">{timeAgo(c.granted_at)}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </React.Fragment>
      )}
    </React.Fragment>
  );
}

window.CompliancePanel = CompliancePanel;
