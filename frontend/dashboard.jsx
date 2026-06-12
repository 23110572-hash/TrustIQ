/**
 * Dashboard - the shell for the Bank of Baroda operations console.
 *
 * Plain banking navigation (Accounts, Alerts, Simulations, etc.), a clean
 * top bar, and content routing — including the drill-in Customer Profile.
 * Everything is written for a branch / fraud-ops employee, not an engineer.
 */
function Dashboard() {
  const { api, Icon, eventLabel, timeAgo } = window.TrustIQ;
  const {
    CommandCenter, CustomerProfile, AlertFeed,
    FraudRing, CompliancePanel, TrustScore, Profile,
  } = window;

  const [nav, setNav] = React.useState("overview");
  const [selectedCustomer, setSelectedCustomer] = React.useState(null);
  const [audit, setAudit] = React.useState([]);
  const [token, setToken] = React.useState(null);
  const [collapsed, setCollapsed] = React.useState(false);

  const NAV = [
    { key: "overview",   label: "Accounts", desc: "Command center", icon: "layout-dashboard" },
    { key: "trust",      label: "Trust Score", desc: "How trust is calculated", icon: "gauge" },
    { key: "alerts",     label: "Alerts", desc: "Live fraud alerts", icon: "siren" },
    { key: "rings",      label: "Linked Accounts", desc: "Mule networks", icon: "share-2" },
    { key: "compliance", label: "Compliance", desc: "DPDP & RBI", icon: "scale" },
    { key: "audit",      label: "History", desc: "Every decision", icon: "scroll-text" },
    { key: "account",    label: "My Profile", desc: "Your SOC profile", icon: "user" },
  ];

  const openProfile = (id) => { setSelectedCustomer(id); setNav("profile"); };

  // Load audit log (with a demo JWT) when the History tab opens.
  React.useEffect(() => {
    if (nav !== "audit") return;
    let active = true;
    (async () => {
      try {
        let t = token;
        if (!t) { const res = await api.post("/api/token?username=analyst"); t = res.data.access_token; if (active) setToken(t); }
        const log = await api.get("/api/audit/log?limit=25", { headers: { Authorization: `Bearer ${t}` } });
        if (active) setAudit(log.data || []);
      } catch (e) { if (active) setAudit([]); }
    })();
    return () => { active = false; };
  }, [nav]);

  const page = nav === "profile"
    ? { label: "Customer Profile", desc: "Full account view" }
    : NAV.find((n) => n.key === nav);

  return (
    <div className={`app ${collapsed ? "nav-collapsed" : ""}`}>
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-mark"><img src="logo.jpeg" alt="Bank of Baroda" /></div>
        </div>

        <button className="sidebar-collapse" onClick={() => setCollapsed((c) => !c)}
          title={collapsed ? "Expand" : "Collapse"}>
          <Icon name={collapsed ? "chevrons-right" : "chevrons-left"} size={16} />
          <span>{collapsed ? "" : "Collapse"}</span>
        </button>

        <div className="nav-label">Menu</div>
        <nav className="nav">
          {NAV.map((item) => (
            <button key={item.key} onClick={() => setNav(item.key)}
              className={`nav-item ${nav === item.key || (nav === "profile" && item.key === "overview") ? "active" : ""}`}>
              <span className="nav-icon"><Icon name={item.icon} size={20} /></span>
              <span className="nav-text">
                <span className="nav-title">{item.label}</span>
                <span className="nav-desc">{item.desc}</span>
              </span>
            </button>
          ))}
        </nav>

        <div className="sidebar-spacer" />

        <div className="sidebar-user" onClick={() => setNav("account")}
             style={{ cursor: "pointer" }} role="button" tabIndex={0}>
          <div className="user-avatar">FA</div>
          <div>
            <div className="user-name">Fraud Analyst</div>
            <div className="user-role">Bank of Baroda · SOC</div>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <div className="topbar-title">{page.label}</div>
            <div className="topbar-sub">{page.desc}</div>
          </div>
          <div className="live-indicator"><span className="live-dot" /><span className="live-text">Live</span></div>
        </header>

        <div className="content">
          {nav === "overview" && <CommandCenter onOpenCustomer={openProfile} />}
          {nav === "trust" && <TrustScore onOpenCustomer={openProfile} />}
          {nav === "account" && <Profile />}
          {nav === "profile" && <CustomerProfile customerId={selectedCustomer} onBack={() => setNav("overview")} />}

          {nav === "alerts" && (
            <div className="section"><div className="alerts-full"><AlertFeed onOpenCustomer={openProfile} /></div></div>
          )}

          {nav === "rings" && <FraudRing />}
          {nav === "compliance" && <CompliancePanel />}

          {nav === "audit" && (
            <React.Fragment>
              <div className="section">
                <div className="table-wrap">
                  <div className="table-head">
                    <div className="table-head-text">
                      <div className="table-title"><Icon name="scroll-text" size={18} color="#2563EB" /> Decision history</div>
                      <div className="table-sub">Newest first · permanent, tamper-proof record</div>
                    </div>
                  </div>
                  {audit.length === 0 ? (
                    <div className="empty"><Icon name="scroll-text" size={34} className="empty-icon" />
                      <div className="empty-title">No records yet</div>
                      <div className="empty-text">Live account activity will appear here as decisions are made.</div></div>
                  ) : (
                    <div className="table-scroll">
                      <table className="tbl">
                        <thead><tr><th>When</th><th>Customer</th><th>Activity</th><th>Risk</th><th>Decision</th></tr></thead>
                        <tbody>
                          {audit.map((r) => (
                            <tr key={r.id}>
                              <td><span className="mono" style={{ color: "var(--text-secondary)" }}>{new Date(r.timestamp).toLocaleString()}</span></td>
                              <td><span className="mono">{r.user_id}</span></td>
                              <td>{eventLabel(r.action)}</td>
                              <td><span className="mono">{Math.round(r.risk_score)}</span></td>
                              <td>{(r.response_taken || "").replace(/_/g, " ")}</td>
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
        </div>
      </main>
    </div>
  );
}

window.Dashboard = Dashboard;
