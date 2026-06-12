/**
 * Profile - the signed-in fraud analyst's own profile page.
 *
 * Shows who is operating the console (identity, team, shift, clearance) plus a
 * few live workload numbers pulled from the platform so the page reflects the
 * real state of the floor rather than static placeholders.
 */
function Profile() {
  const { api, Icon, useCountUp, timeAgo } = window.TrustIQ;

  // The operator currently signed in to the SOC console.
  const operator = {
    name: "Fraud Analyst",
    role: "Senior Fraud & Identity-Trust Analyst",
    team: "Identity Trust SOC",
    employeeId: "BOB-SOC-2026",
    email: "fraud.soc@bankofbaroda.in",
    location: "Mumbai · BKC Operations Hub",
    shift: "Day shift · 09:00 – 18:00 IST",
    clearance: "Tier 3 · Fraud Operations",
  };

  const [stats, setStats] = React.useState(null);
  const [passports, setPassports] = React.useState([]);

  React.useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [s, p] = await Promise.all([
          api.get("/api/dashboard/stats").catch(() => ({ data: null })),
          api.get("/api/passports").catch(() => ({ data: [] })),
        ]);
        if (!active) return;
        setStats(s.data);
        setPassports(p.data || []);
      } catch (e) {}
    };
    load();
    const id = setInterval(load, 6000);
    return () => { active = false; clearInterval(id); };
  }, []);

  // Derive live workload numbers from whatever the platform reports.
  const monitored = passports.length;
  const needsReview = passports.filter((p) => p.trust_score < 60).length;
  const decisions = stats
    ? (stats.total_events || stats.total_decisions || stats.events_today || 0)
    : 0;
  const alerts = stats
    ? (stats.active_alerts || stats.alerts || stats.total_alerts || 0)
    : 0;

  const tiles = [
    { icon: "users",          tone: "accent",   value: monitored,   label: "Accounts monitored", desc: "Identities under watch" },
    { icon: "alert-triangle", tone: "high",     value: needsReview, label: "Need review",        desc: "Trust below 60" },
    { icon: "scroll-text",    tone: "safe",      value: decisions,   label: "Decisions seen",     desc: "Scored this session" },
    { icon: "siren",          tone: "critical",  value: alerts,      label: "Open alerts",        desc: "Awaiting triage" },
  ];

  const details = [
    { icon: "id-card",    name: "Employee ID",   value: operator.employeeId },
    { icon: "mail",       name: "Email",         value: operator.email },
    { icon: "users",      name: "Team",          value: operator.team },
    { icon: "map-pin",    name: "Location",      value: operator.location },
    { icon: "clock",      name: "Shift",         value: operator.shift },
    { icon: "shield-check", name: "Clearance",   value: operator.clearance },
  ];

  const permissions = [
    { name: "View customer passports", detail: "Read identity trust scores, history and verdicts.", on: true },
    { name: "Review & triage alerts",  detail: "Open, acknowledge and action live fraud alerts.", on: true },
    { name: "Export audit log",        detail: "Download the immutable decision record (JWT-protected).", on: true },
    { name: "Inspect fraud rings",     detail: "View linked-account and mule-network maps.", on: true },
    { name: "Modify trust policy",     detail: "Change scoring weights and thresholds.", on: false },
  ];

  const initials = operator.name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();

  return (
    <React.Fragment>
      <div className="ops-banner">
        <div className="profile-head">
          <span className="profile-avatar">{initials}</span>
          <div className="profile-head-text">
            <div className="ops-banner-title">{operator.name}</div>
            <div className="ops-banner-sub">{operator.role} · {operator.team}</div>
          </div>
        </div>
        <span className="pill pill--safe"><span className="pill-dot dot--safe" /> On shift</span>
      </div>

      <div className="section">
        <div className="grid grid-4">
          {tiles.map((t, i) => <ProfileTile key={t.label} {...t} delay={i * 60} />)}
        </div>
      </div>

      <div className="section">
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title"><Icon name="user" size={18} color="#2563EB" /> Operator details</div>
          </div>
          <div className="control-list">
            {details.map((d) => (
              <div key={d.name} className="control-row">
                <span className="control-status control-status--safe"><Icon name={d.icon} size={16} /></span>
                <div className="control-body">
                  <div className="control-name">{d.name}</div>
                  <div className="control-detail">{d.value}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="section">
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title"><Icon name="lock" size={18} color="#2563EB" /> Access &amp; permissions</div>
            <span className="panel-hint" style={{ marginTop: 0 }}>{operator.clearance}</span>
          </div>
          <div className="control-list">
            {permissions.map((p) => (
              <div key={p.name} className="control-row">
                <span className={`control-status control-status--${p.on ? "safe" : "neutral"}`}>
                  <Icon name={p.on ? "check-circle" : "minus-circle"} size={16} />
                </span>
                <div className="control-body">
                  <div className="control-name">{p.name}</div>
                  <div className="control-detail">{p.detail}</div>
                </div>
                <span className={`pill pill--${p.on ? "safe" : "neutral"}`}>
                  <span className={`pill-dot dot--${p.on ? "safe" : "neutral"}`} />
                  {p.on ? "Granted" : "Restricted"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </React.Fragment>
  );

  function ProfileTile({ icon, tone, value, label, desc, delay }) {
    const n = useCountUp(value);
    return (
      <div className="tile" style={{ animationDelay: `${delay}ms` }}>
        <div className="tile-top">
          <span className={`tile-icon tile-icon--${tone}`}><Icon name={icon} size={20} /></span>
          <span className="tile-value">{Math.round(n)}</span>
        </div>
        <div className="tile-label">{label}</div>
        <div className="tile-desc">{desc}</div>
      </div>
    );
  }
}

window.Profile = Profile;
