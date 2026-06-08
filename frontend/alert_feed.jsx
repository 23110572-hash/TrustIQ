/**
 * AlertFeed - the live alert stream a fraud analyst watches.
 *
 * Each alert is written as a banking incident, not a technical event:
 *   WHO  (customer name)
 *   HOW BAD (severity)
 *   WHY  (plain-English reason)
 *   WHAT TO DO (recommended action)
 * Live via WebSocket with a polling fallback. Click an alert to open the
 * customer. Designed to be readable in a glance.
 */
function AlertFeed({ onOpenCustomer, compact }) {
  const { api, Icon, timeAgo, API_BASE } = window.TrustIQ;
  const R = window.Roster;
  const [alerts, setAlerts] = React.useState([]);
  const [filter, setFilter] = React.useState("all");

  // Alert type (category) → banking label + icon.
  const typeInfo = (cat) => ({
    account_takeover:  { label: "Account Takeover Attempt", icon: "user-x" },
    impossible_travel: { label: "Impossible Travel", icon: "plane" },
    mule_network:      { label: "Mule Network", icon: "share-2" },
    recovery:          { label: "Recovery / Deepfake Attempt", icon: "scan-face" },
    identity_trust:    { label: "Suspicious Activity", icon: "shield-alert" },
  }[cat] || { label: "Suspicious Activity", icon: "shield-alert" });

  const sevInfo = (a) => {
    let s = a.severity;
    if (!s) s = a.risk_score >= 80 ? "critical" : a.risk_score >= 60 ? "high" : a.risk_score >= 30 ? "elevated" : "safe";
    return ({
      critical: { label: "Critical", key: "critical" },
      high:     { label: "High", key: "high" },
      elevated: { label: "Medium", key: "mid" },
      safe:     { label: "Low", key: "safe" },
    })[s] || { label: "Medium", key: "mid" };
  };

  const recommended = (a) => a.recommended_action || ({
    block: "Block the account and call the customer on a verified number.",
    step_up_otp: "Ask the customer for an OTP or face check.",
    push_notification: "Send a confirmation to the customer's trusted phone.",
  }[a.response_taken] || "Review this activity.");

  const reasonText = (a) => {
    if (a.reason) return a.reason.length > 180 ? a.reason.slice(0, 177) + "…" : a.reason;
    return "Unusual activity detected for this account.";
  };

  React.useEffect(() => {
    let active = true;
    const load = async () => {
      try { const r = await api.get("/api/alerts"); if (active) setAlerts(r.data || []); } catch (e) {}
    };
    load();
    const id = setInterval(load, 3000);
    return () => { active = false; clearInterval(id); };
  }, []);

  React.useEffect(() => {
    let ws;
    try {
      ws = new WebSocket(API_BASE.replace(/^http/, "ws") + "/ws/alerts");
      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data);
          if (m.type === "snapshot") setAlerts(m.alerts || []);
          else if (m.alert_id && m.category) setAlerts((p) => [m, ...p.filter((x) => x.alert_id !== m.alert_id)].slice(0, 60));
        } catch (err) {}
      };
    } catch (e) {}
    return () => { if (ws) ws.close(); };
  }, []);

  const FILTERS = [
    { key: "all", label: "All alerts" },
    { key: "account_takeover", label: "Takeovers" },
    { key: "impossible_travel", label: "Travel" },
    { key: "mule_network", label: "Mule" },
    { key: "recovery", label: "Recovery" },
  ];
  const shown = alerts.filter((a) => filter === "all" || a.category === filter);
  const isNew = (iso) => (Date.now() - new Date(iso).getTime()) < 8000;

  return (
    <div className="feed">
      <div className="feed-head">
        <div className="feed-title"><Icon name="siren" size={18} color="#DC2626" /> Live alerts</div>
        <div className="feed-subtitle">Newest first. Click an alert to open the customer.</div>
        {!compact && (
          <div className="feed-filters">
            {FILTERS.map((c) => (
              <button key={c.key} onClick={() => setFilter(c.key)}
                className={`filter-chip ${filter === c.key ? "active" : ""}`}>{c.label}</button>
            ))}
          </div>
        )}
      </div>

      <div className="feed-body scroll-thin">
        {shown.length === 0 && (
          <div className="empty"><Icon name="shield-check" size={34} className="empty-icon" />
            <div className="empty-title">All clear</div>
            <div className="empty-text">No alerts right now. Live banking activity will populate this feed as it happens.</div></div>
        )}
        {shown.map((a) => {
          const ti = typeInfo(a.category);
          const sv = sevInfo(a);
          const name = R.customerName(a.customer || a.masked_user_id);
          const clickable = !!a.customer;
          return (
            <div key={a.alert_id}
                 className={`alert-card alert-card--${sv.key} ${clickable ? "alert-card--click" : ""}`}
                 onClick={() => clickable && onOpenCustomer && onOpenCustomer(a.customer)}>
              <div className="alert-card-top">
                <span className={`alert-card-icon tile-icon--${sv.key === "critical" ? "critical" : sv.key}`}><Icon name={ti.icon} size={18} /></span>
                <div className="alert-card-id">
                  <div className="alert-card-type">{ti.label}{isNew(a.timestamp) && <span className="new-tag">New</span>}</div>
                  <div className="alert-card-name">{name}</div>
                </div>
                <span className={`status-pill status-pill--${sv.key}`}><span className="status-dot" /> {sv.label}</span>
              </div>
              <div className="alert-card-reason">{reasonText(a)}</div>
              <div className="alert-card-action">
                <Icon name="arrow-right-circle" size={14} color="#2563EB" />
                <span><b>Action:</b> {recommended(a)}</span>
                <span className="alert-card-time">{timeAgo(a.timestamp)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

window.AlertFeed = AlertFeed;
