/**
 * RiskTimeline - one customer's recent activity, in plain language.
 *
 * Shows the risk level of each recent action as a line. Threshold guide-lines
 * (orange/red) make it obvious when TrustIQ stepped in. Hovering a point shows
 * a plain-English summary. API/data unchanged.
 */
function RiskTimeline({ userId }) {
  const { api, eventLabel, actionInfo, bandInfo, scoreBand, Icon } = window.TrustIQ;
  const {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, ReferenceLine,
  } = window.Recharts;

  const [points, setPoints] = React.useState([]);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!userId) return;
    let active = true;
    const load = async () => {
      setLoading(true);
      try {
        const res = await api.get(`/api/user/${encodeURIComponent(userId)}/timeline`);
        if (active) setPoints(res.data || []);
      } catch (e) {
        if (active) setPoints([]);
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    const id = setInterval(load, 3000);
    return () => { active = false; clearInterval(id); };
  }, [userId]);

  // Plain-English tooltip.
  const CustomTooltip = ({ active, payload }) => {
    if (!active || !payload || !payload.length) return null;
    const p = payload[0].payload;
    const info = bandInfo(scoreBand(p.risk_score));
    const act = actionInfo(p.response_taken);
    return (
      <div className="rc-tooltip">
        <div className="rc-tooltip-title">{eventLabel(p.action)} · {info.label}</div>
        <div className="rc-tooltip-row">Risk score: <span className="mono">{p.risk_score}</span> / 100</div>
        <div className="rc-tooltip-row">What we did: {act.label}</div>
        <div className="rc-tooltip-row">Place: {p.city}</div>
      </div>
    );
  };

  // Bigger red dot where we stepped in.
  const renderDot = (props) => {
    const stepped = props.payload.response_taken &&
      props.payload.response_taken !== "silent_pass";
    return (
      <circle key={props.index} cx={props.cx} cy={props.cy}
        r={stepped ? 6 : 4}
        fill={stepped ? "#DC2626" : "#2563EB"}
        stroke="#FFFFFF" strokeWidth={2} />
    );
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <div className="panel-title">
          <Icon name="activity" size={18} color="#2563EB" />
          {userId ? `${userId}'s activity` : "Customer activity"}
        </div>
        {loading && <span className="panel-hint" style={{ marginTop: 0 }}>updating…</span>}
      </div>

      {points.length === 0 ? (
        <div className="empty" style={{ height: 260 }}>
          <Icon name="line-chart" size={34} className="empty-icon" />
          <div className="empty-title">No activity yet</div>
          <div className="empty-text">When this customer signs in or transfers money, it will show here.</div>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={points} margin={{ top: 10, right: 16, bottom: 4, left: -12 }}>
            <CartesianGrid horizontal vertical={false} stroke="#E2DDD4" strokeDasharray="4 4" />
            <XAxis dataKey="sequence" tick={{ fill: "#A39F97", fontSize: 12, fontFamily: "DM Sans" }}
                   axisLine={false} tickLine={false} />
            <YAxis domain={[0, 100]} tick={{ fill: "#A39F97", fontSize: 12, fontFamily: "DM Sans" }}
                   axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} cursor={{ stroke: "#CCC8BC", strokeWidth: 1 }} />
            <ReferenceLine y={60} stroke="#B45309" strokeDasharray="5 4" strokeWidth={1}
              label={{ value: "we step in", position: "insideTopRight", fill: "#B45309", fontSize: 11, fontFamily: "DM Sans" }} />
            <ReferenceLine y={80} stroke="#DC2626" strokeDasharray="5 4" strokeWidth={1}
              label={{ value: "we block", position: "insideTopRight", fill: "#DC2626", fontSize: 11, fontFamily: "DM Sans" }} />
            <Line type="monotone" dataKey="risk_score" stroke="#2563EB" strokeWidth={2.5}
              dot={renderDot} activeDot={{ r: 5, fill: "#2563EB", stroke: "#FFFFFF", strokeWidth: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      )}
      <p className="panel-hint">Higher line = riskier action. Red dots are where we asked for extra proof or blocked it.</p>
    </div>
  );
}

window.RiskTimeline = RiskTimeline;
