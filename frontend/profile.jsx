/**
 * Profile - the signed-in fraud analyst's own profile page.
 *
 * Editable: the operator can update their identity fields inline; changes are
 * persisted to localStorage so they survive reloads (there is no analyst-user
 * backend in this build). Live workload numbers come from the platform.
 */
const OPERATOR_KEY = "trustiq.operator.v1";

const DEFAULT_OPERATOR = {
  name: "Krishna Agrawal",
  role: "Senior Fraud & Identity-Trust Analyst",
  team: "Identity Trust SOC",
  employeeId: "BOB-SOC-2026",
  email: "Krishnaagrawal0706@gmail.com",
  phone: "+91 7447020046",
  location: "Mumbai · BKC Operations Hub",
  shift: "Day shift · 09:00 – 18:00 IST",
  clearance: "Tier 3 · Fraud Operations",
};

function loadOperator() {
  try {
    const raw = localStorage.getItem(OPERATOR_KEY);
    if (raw) return { ...DEFAULT_OPERATOR, ...JSON.parse(raw) };
  } catch (e) {}
  return { ...DEFAULT_OPERATOR };
}

function Profile() {
  const { api, Icon, useCountUp } = window.TrustIQ;

  const [operator, setOperator] = React.useState(loadOperator);
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(operator);
  const [saved, setSaved] = React.useState(false);

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

  const startEdit = () => { setDraft(operator); setEditing(true); setSaved(false); };
  const cancelEdit = () => { setEditing(false); setDraft(operator); };
  const change = (k) => (e) => setDraft((d) => ({ ...d, [k]: e.target.value }));
  const save = () => {
    const next = { ...draft, name: (draft.name || "").trim() || "Fraud Analyst" };
    setOperator(next);
    try { localStorage.setItem(OPERATOR_KEY, JSON.stringify(next)); } catch (e) {}
    setEditing(false); setSaved(true);
    setTimeout(() => setSaved(false), 2600);
  };

  // Live workload numbers derived from whatever the platform reports.
  const monitored = passports.length;
  const needsReview = passports.filter((p) => p.trust_score < 60).length;
  const decisions = stats ? (stats.total_events || stats.total_decisions || stats.events_today || 0) : 0;
  const alerts = stats ? (stats.active_alerts || stats.alerts || stats.total_alerts || 0) : 0;

  const tiles = [
    { icon: "users",          tone: "accent",   value: monitored,   label: "Accounts monitored", desc: "Identities under watch" },
    { icon: "alert-triangle", tone: "high",     value: needsReview, label: "Need review",        desc: "Trust below 60" },
    { icon: "scroll-text",    tone: "safe",      value: decisions,   label: "Decisions seen",     desc: "Scored this session" },
    { icon: "siren",          tone: "critical",  value: alerts,      label: "Open alerts",        desc: "Awaiting triage" },
  ];

  const fields = [
    { key: "name",       icon: "user",          label: "Full name" },
    { key: "role",       icon: "briefcase",     label: "Role" },
    { key: "employeeId", icon: "id-card",       label: "Employee ID" },
    { key: "email",      icon: "mail",          label: "Email" },
    { key: "phone",      icon: "phone",         label: "Phone" },
    { key: "team",       icon: "users",         label: "Team" },
    { key: "location",   icon: "map-pin",       label: "Location" },
    { key: "shift",      icon: "clock",         label: "Shift" },
    { key: "clearance",  icon: "shield-check",  label: "Clearance" },
  ];

  const permissions = [
    { name: "View customer passports", detail: "Read identity trust scores, history and verdicts.", on: true },
    { name: "Review & triage alerts",  detail: "Open, acknowledge and action live fraud alerts.", on: true },
    { name: "Export audit log",        detail: "Download the immutable decision record (JWT-protected).", on: true },
    { name: "Inspect fraud rings",     detail: "View linked-account and mule-network maps.", on: true },
    { name: "Modify trust policy",     detail: "Change scoring weights and thresholds.", on: false },
  ];

  const initials = (operator.name || "?").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();

  return (
    <React.Fragment>
      <div className="ops-banner">
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <span className="profile-avatar">{initials}</span>
          <div className="profile-head-text">
            <div className="ops-banner-title">{operator.name}</div>
            <div className="ops-banner-sub">{operator.role} · {operator.team}</div>
          </div>
        </div>
        <div className="panel-actions">
          {saved && <span className="pill pill--safe"><span className="pill-dot dot--safe" /> Saved</span>}
          {!editing
            ? <button className="btn btn--primary" onClick={startEdit}><Icon name="pencil" size={15} /> Edit profile</button>
            : <span className="pill pill--accent"><span className="pill-dot dot--neutral" style={{ background: "var(--accent)" }} /> Editing</span>}
        </div>
      </div>

      <div className="section">
        <div className="grid grid-4">
          {tiles.map((t, i) => <ProfileTile key={t.label} {...t} delay={i * 60} />)}
        </div>
      </div>

      <div className="section">
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title"><Icon name="user" size={18} color="var(--accent)" /> Operator details</div>
            {editing && (
              <div className="panel-actions">
                <button className="btn" onClick={cancelEdit}><Icon name="x" size={15} /> Cancel</button>
                <button className="btn btn--primary" onClick={save}><Icon name="check" size={15} /> Save changes</button>
              </div>
            )}
          </div>

          {editing ? (
            <React.Fragment>
              <div className="profile-form">
                {fields.map((f) => (
                  <div key={f.key} className="form-field">
                    <label>{f.label}</label>
                    <input className="input" value={draft[f.key] || ""} onChange={change(f.key)}
                      placeholder={DEFAULT_OPERATOR[f.key]} />
                  </div>
                ))}
              </div>
              <div className="form-actions">
                <button className="btn btn--primary" onClick={save}><Icon name="check" size={15} /> Save changes</button>
                <button className="btn" onClick={cancelEdit}><Icon name="x" size={15} /> Cancel</button>
              </div>
            </React.Fragment>
          ) : (
            <div className="control-list">
              {fields.map((f) => (
                <div key={f.key} className="control-row">
                  <span className="control-status control-status--safe"><Icon name={f.icon} size={16} /></span>
                  <div className="control-body">
                    <div className="control-name">{f.label}</div>
                    <div className="control-detail">{operator[f.key] || "—"}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="section">
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title"><Icon name="lock" size={18} color="var(--accent)" /> Access &amp; permissions</div>
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
