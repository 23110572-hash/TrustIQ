/**
 * CommandCenter - the bank's operations home screen.
 *
 * Shows every real customer TrustIQ knows about, pulled live from
 * `/api/passports`. Each customer here is a genuine Identity Passport created
 * when that account acted in the Bank of Baroda simulator — there is no demo or
 * placeholder data. The board refreshes on a timer and instantly whenever a new
 * decision streams in over the alert WebSocket.
 */
function CommandCenter({ onOpenCustomer }) {
  const { api, Icon, useCountUp, timeAgo, API_BASE } = window.TrustIQ;
  const R = window.Roster;

  const [customers, setCustomers] = React.useState([]);
  const [loaded, setLoaded] = React.useState(false);
  const [flash, setFlash] = React.useState({});

  // Map a TrustIQ passport into the card model the board renders.
  const toCard = React.useCallback((p) => ({
    id: p.user_id,
    name: R.customerName(p.user_id),
    trust: Math.round(p.trust_score),
    trend: p.trust_trend,
    lastActivity: p.last_seen,
    events: p.event_count,
    devices: p.trusted_devices ? p.trusted_devices.length : 0,
  }), []);

  const loadPassports = React.useCallback(async () => {
    try {
      const r = await api.get("/api/passports");
      setCustomers((r.data || []).map(toCard));
    } catch (e) { /* backend not up yet */ }
    finally { setLoaded(true); }
  }, [toCard]);

  // Poll + live refresh on every streamed decision.
  React.useEffect(() => {
    loadPassports();
    const poll = setInterval(loadPassports, 5000);
    let ws;
    try {
      ws = new WebSocket(API_BASE.replace(/^http/, "ws") + "/ws/alerts");
      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data);
          const id = m.customer || m.user_id;
          if (id) setFlash((f) => ({ ...f, [id]: Date.now() }));
          loadPassports();
        } catch (err) {}
      };
    } catch (e) {}
    return () => { clearInterval(poll); if (ws) ws.close(); };
  }, [loadPassports]);

  // ---- metrics ----
  const stat = (status) => customers.filter((c) => R.passportStatus(c) === status).length;
  const metrics = [
    { label: "Customers", value: customers.length, icon: "users", tone: "accent" },
    { label: "Active now", value: customers.filter((c) => R.isActive(c.lastActivity)).length, icon: "activity", tone: "safe" },
    { label: "Need verification", value: stat("verify"), icon: "alert-circle", tone: "mid" },
    { label: "Suspicious", value: stat("suspicious"), icon: "alert-triangle", tone: "high" },
    { label: "Compromised", value: stat("blocked"), icon: "shield-alert", tone: "critical" },
  ];

  const order = { blocked: 0, suspicious: 1, verify: 2, safe: 3, inactive: 4 };
  const sortByConcern = (a, b) =>
    order[R.passportStatus(a)] - order[R.passportStatus(b)] || b.trust - a.trust;
  const active = customers.filter((c) => R.isActive(c.lastActivity)).sort(sortByConcern);
  const dormant = customers.filter((c) => !R.isActive(c.lastActivity)).sort((a, b) => b.trust - a.trust);

  return (
    <React.Fragment>
      <div className="ops-banner">
        <div className="ops-banner-text">
          <div className="ops-banner-title">Account Command Center</div>
          <div className="ops-banner-sub">
            Every customer TrustIQ is protecting, live. Accounts in red and black need attention first.
          </div>
        </div>
        <div className="live-indicator"><span className="live-dot" /><span className="live-text">Real-time</span></div>
      </div>

      <div className="section">
        <div className="metric-row">
          {metrics.map((m, i) => <Metric key={m.label} {...m} delay={i * 60} />)}
        </div>
      </div>

      {loaded && customers.length === 0 ? (
        <div className="section"><div className="empty">
          <Icon name="users" size={36} className="empty-icon" />
          <div className="empty-title">No customer activity yet</div>
          <div className="empty-text">
            Each customer appears here the moment they perform an action on any
            banking channel. Live activity will populate this board automatically.
          </div>
        </div></div>
      ) : (
        <React.Fragment>
          <Section title="Active customers" hint="acted in the last few minutes" icon="activity"
                   items={active} onOpenCustomer={onOpenCustomer} flash={flash} empty="No active customers right now." />
          <Section title="Everyone else" hint="no recent activity" icon="moon"
                   items={dormant} onOpenCustomer={onOpenCustomer} flash={flash} empty="" />
        </React.Fragment>
      )}
    </React.Fragment>
  );

  function Metric({ icon, tone, value, label, delay }) {
    const n = useCountUp(value);
    return (
      <div className="metric" style={{ animationDelay: `${delay}ms` }}>
        <span className={`metric-icon tile-icon--${tone}`}><Icon name={icon} size={20} /></span>
        <div className="metric-body">
          <div className="metric-value">{Math.round(n)}</div>
          <div className="metric-label">{label}</div>
        </div>
      </div>
    );
  }

  function Section({ title, hint, icon, items, empty }) {
    if (!items.length && !empty) return null;
    return (
      <div className="section">
        <div className="section-head">
          <h2 className="section-title"><Icon name={icon} size={20} color="var(--accent)" /> {title}</h2>
          <span className="section-hint">{items.length} customer{items.length === 1 ? "" : "s"} · {hint}</span>
        </div>
        {items.length === 0 ? (
          <div className="empty"><Icon name="inbox" size={30} className="empty-icon" /><div className="empty-text">{empty}</div></div>
        ) : (
          <div className="card-grid">
            {items.map((c) => (
              <CustomerCard key={c.id} customer={c} flashed={flash[c.id] && (Date.now() - flash[c.id] < 2500)}
                            onOpen={() => onOpenCustomer && onOpenCustomer(c.id)} />
            ))}
          </div>
        )}
      </div>
    );
  }
}

/** A single customer account card — driven entirely by a real passport. */
function CustomerCard({ customer: c, onOpen, flashed }) {
  const { Icon, useCountUp, timeAgo } = window.TrustIQ;
  const R = window.Roster;
  const status = R.passportStatus(c);
  const si = R.statusInfo(status);
  const tb = R.trustBandInfo(c.trust);
  const tr = R.trendInfo(c.trend);
  const n = useCountUp(c.trust);

  return (
    <button className={`acct acct--${si.key} ${flashed ? "acct--flash" : ""}`} onClick={onOpen}>
      <div className="acct-top">
        <span className={`acct-avatar acct-avatar--${si.key}`}>{R.initials(c.name)}</span>
        <div className="acct-id">
          <div className="acct-name">{c.name}</div>
          <div className="acct-acc mono">{c.events} activit{c.events === 1 ? "y" : "ies"}</div>
        </div>
        <span className={`status-pill status-pill--${si.key}`}>
          <span className="status-dot" /> {si.label}
        </span>
      </div>

      <div className="acct-trust">
        <div className={`acct-trust-num acct-trust-num--${tb.key}`}>{Math.round(n)}</div>
        <div className="acct-trust-meta">
          <span className="acct-trust-label">Trust Score · {tb.label}</span>
          <span className={`acct-trend acct-trend--${tr.key}`}>{tr.arrow} {tr.label}</span>
        </div>
      </div>

      <div className="acct-foot">
        <span><Icon name="smartphone" size={13} /> {c.devices} trusted device{c.devices === 1 ? "" : "s"}</span>
        <span className="dotsep">•</span>
        <span><Icon name="clock" size={13} /> {c.lastActivity ? timeAgo(c.lastActivity) : "—"}</span>
      </div>
    </button>
  );
}

window.CommandCenter = CommandCenter;
window.CustomerCard = CustomerCard;
