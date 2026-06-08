/**
 * CustomerProfile - the single-customer view a branch employee opens.
 *
 * Everything here is real: the durable Identity Passport (`/api/passport/{id}`)
 * and the customer's recent activity (`/api/user/{id}/timeline`). No synthetic
 * events are generated — the view simply reflects what TrustIQ has actually
 * observed for this identity from the Bank of Baroda simulator.
 */
function CustomerProfile({ customerId, onBack }) {
  const { api, Icon, useCountUp, timeAgo, eventLabel } = window.TrustIQ;
  const R = window.Roster;

  const [loading, setLoading] = React.useState(true);
  const [passport, setPassport] = React.useState(null);
  const [timeline, setTimeline] = React.useState([]);
  const [advanced, setAdvanced] = React.useState(false);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    if (!customerId) { setLoading(false); return; }
    let active = true;
    (async () => {
      setLoading(true); setError(null);
      try {
        const [p, t] = await Promise.all([
          api.get(`/api/passport/${encodeURIComponent(customerId)}`),
          api.get(`/api/user/${encodeURIComponent(customerId)}/timeline`),
        ]);
        if (!active) return;
        setPassport(p.data);
        setTimeline((t.data || []).slice().reverse());
      } catch (e) {
        if (active) setError("Couldn't load this customer. They may not have any activity yet.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [customerId]);

  const name = R.customerName(customerId);

  const actionInfo = (a) => ({
    silent_pass: { label: "Allowed automatically", key: "safe", icon: "check-circle" },
    push_notification: { label: "Confirm on trusted phone", key: "mid", icon: "smartphone" },
    step_up_otp: { label: "Asked for OTP / face check", key: "high", icon: "key-round" },
    block: { label: "Blocked & frozen", key: "critical", icon: "ban" },
  }[a] || { label: (a || "—").replace(/_/g, " "), key: "neutral", icon: "circle" });

  if (loading) {
    return (
      <React.Fragment>
        <div className="profile-bar">
          <button className="btn" onClick={onBack}><Icon name="arrow-left" size={15} /> All customers</button>
        </div>
        <div className="section"><div className="panel"><SkeletonLines /></div></div>
      </React.Fragment>
    );
  }

  if (!passport) {
    return (
      <React.Fragment>
        <div className="profile-bar">
          <button className="btn" onClick={onBack}><Icon name="arrow-left" size={15} /> All customers</button>
        </div>
        <div className="section"><div className="empty">
          <Icon name="user-x" size={34} className="empty-icon" />
          <div className="empty-title">{name}</div>
          <div className="empty-text">{error || "No activity recorded for this customer yet."}</div>
        </div></div>
      </React.Fragment>
    );
  }

  const status = R.passportStatus(passport);
  const si = R.statusInfo(status);
  const tb = R.trustBandInfo(passport.trust_score);
  const tr = R.trendInfo(passport.trust_trend);
  const devices = (passport.trusted_devices || []).map((d) => d.split("|")[0]);
  const locations = passport.trusted_locations || [];

  // Plain-English summary derived from the real passport (no AI call needed).
  const summary =
    status === "blocked"
      ? `${name}'s trust has collapsed to ${Math.round(passport.trust_score)}/100. Recent activity diverges sharply from their known pattern — treat as a likely account takeover.`
      : status === "suspicious"
      ? `${name}'s trust is low (${Math.round(passport.trust_score)}/100) and ${tr.label.toLowerCase()}. Several signals don't match their usual devices, places or behaviour.`
      : status === "verify"
      ? `${name} is mostly consistent but shows some inconsistency (trust ${Math.round(passport.trust_score)}/100). Confirm identity before high-value actions.`
      : `${name} looks like themselves — trust ${Math.round(passport.trust_score)}/100, ${tr.label.toLowerCase()}, acting from ${devices.length} known device${devices.length === 1 ? "" : "s"}.`;

  return (
    <React.Fragment>
      <div className="profile-bar">
        <button className="btn" onClick={onBack}><Icon name="arrow-left" size={15} /> All customers</button>
        <span className={`status-pill status-pill--${si.key}`}><span className="status-dot" /> {si.label}</span>
      </div>

      <div className="section">
        <div className="profile-head">
          <div className="profile-identity">
            <span className={`acct-avatar acct-avatar--${si.key}`} style={{ height: 56, width: 56, fontSize: "1.25rem" }}>
              {R.initials(name)}
            </span>
            <div>
              <div className="profile-name">{name}</div>
              <div className="profile-meta">
                <span className="mono">{passport.masked_user_id}</span>
                <span className="dotsep">•</span>
                <span><Icon name="activity" size={13} /> {passport.event_count} activities</span>
                {passport.last_seen && <React.Fragment><span className="dotsep">•</span>
                  <span><Icon name="clock" size={13} /> {timeAgo(passport.last_seen)}</span></React.Fragment>}
              </div>
            </div>
          </div>
          <ProfileTrust trust={passport.trust_score} band={tb} trend={tr} />
        </div>
      </div>

      <div className="section">
        <div className={`action-banner action-banner--${si.key}`}>
          <span className={`action-banner-icon tile-icon--${si.key}`}><Icon name={si.icon} size={22} /></span>
          <div>
            <div className="action-banner-label">Recommended action</div>
            <div className="action-banner-value">{si.label}</div>
            <div className="action-banner-advice">{si.advice}</div>
          </div>
          <div className="match-badge">
            <div className={`match-num match-num--${tb.key}`}>{Math.round(passport.trust_score)}</div>
            <div className="match-label">Trust score</div>
          </div>
        </div>
      </div>

      <div className="section">
        <div className="profile-grid">
          <div className="panel">
            <div className="panel-head"><div className="panel-title"><Icon name="message-square" size={18} color="var(--accent)" /> What we see</div></div>
            <p className="verdict-text">{summary}</p>
          </div>

          <div className="panel">
            <div className="panel-head"><div className="panel-title"><Icon name="smartphone" size={18} color="var(--accent)" /> Known to us</div></div>
            <div className="known-block">
              <div className="known-label">Trusted devices</div>
              <div className="chip-row">
                {devices.length ? devices.map((d, i) => <span key={i} className="chip chip--safe"><Icon name="smartphone" size={12} /> {d}</span>)
                  : <span className="chip chip--neutral">None learned yet</span>}
              </div>
            </div>
            <div className="known-block">
              <div className="known-label">Usual locations</div>
              <div className="chip-row">
                {locations.length ? locations.map((l, i) => <span key={i} className="chip chip--accent"><Icon name="map-pin" size={12} /> {l}</span>)
                  : <span className="chip chip--neutral">None learned yet</span>}
              </div>
            </div>
            <div className="known-stats">
              <span><b>{passport.event_count}</b> activities seen</span>
              <span><b>{passport.recovery_attempts}</b> recovery attempts</span>
            </div>
          </div>
        </div>
      </div>

      <div className="section">
        <div className="panel">
          <div className="panel-head"><div className="panel-title"><Icon name="history" size={18} color="var(--accent)" /> Recent activity</div></div>
          {timeline.length === 0 ? (
            <div className="empty" style={{ height: 120 }}><Icon name="history" size={28} className="empty-icon" />
              <div className="empty-text">No recent activity recorded.</div></div>
          ) : (
            <div className="activity-list">
              {timeline.slice(0, 10).map((a, i) => {
                const aInfo = actionInfo(a.response_taken);
                return (
                  <div key={i} className="activity-row">
                    <span className={`activity-dot activity-dot--${aInfo.key}`} />
                    <span className="activity-what">{eventLabel(a.action)}</span>
                    <span className="activity-where">{a.city}</span>
                    <span className={`risk-tag risk-tag--${aInfo.key}`}>{aInfo.label}</span>
                    <span className="activity-when">{timeAgo(a.timestamp)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {passport.trust_history && passport.trust_history.length > 1 && (
        <div className="section">
          <button className="advanced-toggle" onClick={() => setAdvanced((v) => !v)}>
            <Icon name={advanced ? "chevron-down" : "chevron-right"} size={16} /> Trust history (for analysts)
          </button>
          {advanced && (
            <div className="panel advanced-panel">
              <div className="adv-factors">
                {passport.trust_history.slice(-10).reverse().map((h, i) => (
                  <div key={i} className="adv-factor">
                    <span className="adv-factor-name">{(h.trigger || "event").replace(/_/g, " ")} · {h.channel || "—"}</span>
                    <span className="adv-factor-score">{Math.round(h.trust_score)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </React.Fragment>
  );

  function ProfileTrust({ trust, band, trend }) {
    const n = useCountUp(trust);
    const pct = Math.max(0, Math.min(100, trust));
    const R2 = 70, C = Math.PI * R2, off = C * (1 - pct / 100);
    return (
      <div className="profile-trust">
        <div className="gauge">
          <svg width="180" height="110" viewBox="0 0 180 110">
            <path d="M20 100 A70 70 0 0 1 160 100" fill="none" stroke="var(--bg-sunken)" strokeWidth="14" strokeLinecap="round" />
            <path d="M20 100 A70 70 0 0 1 160 100" fill="none" stroke={`var(--${band.key})`} strokeWidth="14"
                  strokeLinecap="round" strokeDasharray={C} strokeDashoffset={off}
                  style={{ transition: "stroke-dashoffset 1s ease" }} />
          </svg>
          <div className="gauge-center">
            <div className="gauge-num">{Math.round(n)}</div>
            <div className="gauge-outof">Trust Score</div>
          </div>
        </div>
        <div className="profile-trust-tags">
          <span className={`pill pill--${band.key}`}><span className={`pill-dot dot--${band.key}`} />{band.label}</span>
          <span className={`acct-trend acct-trend--${trend.key}`}>{trend.arrow} {trend.label}</span>
        </div>
      </div>
    );
  }

  function SkeletonLines() {
    return <div><div className="skeleton" style={{ height: 14, margin: "6px 0", borderRadius: 6 }} />
      <div className="skeleton" style={{ height: 14, margin: "6px 0", width: "80%", borderRadius: 6 }} /></div>;
  }
}

window.CustomerProfile = CustomerProfile;
