/**
 * app_core - shared configuration, API client and plain-language helpers.
 *
 * Design goal: a bank fraud officer (not an engineer) must understand every
 * screen at a glance. So this file centralises the translation of technical
 * values (risk bands, response actions, event types, categories) into clear,
 * human sentences and labels used across the whole UI.
 *
 * Loaded first in the compiled bundle; everything hangs off window.TrustIQ.
 */

// Base URL for the TrustIQ API. Override by setting window.TRUSTIQ_API.
const API_BASE = window.TRUSTIQ_API || "https://trustiq-67h0.onrender.com";
const api = axios.create({ baseURL: API_BASE, timeout: 8000 });

// --------------------------------------------------------------------------
// RISK BANDS — what a score means + what the officer should think/do
// --------------------------------------------------------------------------
function scoreBand(score) {
  if (score <= 30) return "safe";
  if (score <= 60) return "elevated";
  if (score <= 80) return "high";
  return "critical";
}

// Full descriptor for a band: colour key, short label, plain meaning, advice.
function bandInfo(band) {
  switch (band) {
    case "safe":
      return {
        key: "safe", label: "Trusted", icon: "check-circle",
        meaning: "Looks normal for this customer.",
        advice: "No action needed — allowed automatically.",
      };
    case "elevated":
      return {
        key: "mid", label: "Slightly unusual", icon: "alert-circle",
        meaning: "A little different from usual, but not alarming.",
        advice: "We sent a quick confirmation to their trusted phone.",
      };
    case "high":
      return {
        key: "high", label: "Risky", icon: "alert-triangle",
        meaning: "Several things don't match this customer's normal pattern.",
        advice: "We asked for an OTP or face check before allowing it.",
      };
    case "critical":
      return {
        key: "critical", label: "Dangerous", icon: "shield-alert",
        meaning: "Strong signs of fraud or account takeover.",
        advice: "We blocked it and flagged it for you to review now.",
      };
    default:
      return { key: "neutral", label: "Unknown", icon: "help-circle", meaning: "", advice: "" };
  }
}

// Convenience: band colour key straight from a numeric score.
function bandKey(band) { return bandInfo(band).key; }

// --------------------------------------------------------------------------
// RESPONSE ACTIONS — what the system actually did, in plain words
// --------------------------------------------------------------------------
function actionInfo(action) {
  return ({
    silent_pass:       { label: "Allowed",       icon: "check",        key: "safe" },
    push_notification: { label: "Phone confirm", icon: "smartphone",   key: "mid" },
    step_up_otp:       { label: "Asked for OTP", icon: "key-round",    key: "high" },
    block:             { label: "Blocked",       icon: "ban",          key: "critical" },
  })[action] || { label: action, icon: "circle", key: "neutral" };
}

// --------------------------------------------------------------------------
// EVENT TYPES & CATEGORIES — friendly names
// --------------------------------------------------------------------------
function eventLabel(type) {
  return ({
    login: "Sign-in",
    transfer: "Money transfer",
    otp: "OTP request",
    profile_change: "Profile change",
    account_recovery: "Account recovery",
    beneficiary_add: "New payee added",
    device_change: "Device change",
    settings_change: "Settings change",
  })[type] || (type || "").replace(/_/g, " ");
}

function categoryInfo(category) {
  return ({
    account_takeover:  { label: "Account takeover",  icon: "user-x" },
    identity_trust:    { label: "Identity trust",     icon: "fingerprint" },
    impossible_travel: { label: "Impossible travel",  icon: "plane" },
    mule_network:      { label: "Mule network",       icon: "share-2" },
    recovery:          { label: "Password reset",     icon: "key-round" },
  })[category] || { label: (category || "").replace(/_/g, " "), icon: "shield" };
}

// --------------------------------------------------------------------------
// IDENTITY TRUST BANDS — meaning of a persistent 0-100 trust score
// --------------------------------------------------------------------------
function trustBand(score) {
  if (score >= 80) return "verified";
  if (score >= 60) return "established";
  if (score >= 40) return "guarded";
  if (score >= 20) return "untrusted";
  return "compromised";
}

// Descriptor for a trust band: colour key (reuses risk palette inverted),
// label and plain meaning. Higher trust = safer = "safe" colour.
function trustBandInfo(band) {
  return ({
    verified:    { key: "safe",     label: "Verified",    meaning: "Strongly trusted identity — consistent across devices, places and behaviour." },
    established: { key: "safe",     label: "Established",  meaning: "Known, consistent identity with a solid history." },
    guarded:     { key: "mid",      label: "Guarded",     meaning: "Some inconsistency — worth keeping an eye on." },
    untrusted:   { key: "high",     label: "Untrusted",   meaning: "Significant divergence from the real person's pattern." },
    compromised: { key: "critical", label: "Compromised", meaning: "Likely takeover or fraud — trust has collapsed." },
  })[band] || { key: "neutral", label: "Unknown", meaning: "" };
}

// Trend → arrow + colour.
function trendInfo(trend) {
  return ({
    rising:  { icon: "trending-up",   label: "Trust rising",  key: "safe" },
    falling: { icon: "trending-down", label: "Trust falling", key: "critical" },
    stable:  { icon: "minus",         label: "Trust steady",  key: "neutral" },
  })[trend] || { icon: "minus", label: "—", key: "neutral" };
}

// --------------------------------------------------------------------------
// CHANNELS — the banking surfaces the trust layer protects
// --------------------------------------------------------------------------
function channelInfo(channel) {
  return ({
    mobile_banking:   { label: "Mobile Banking",   icon: "smartphone" },
    internet_banking: { label: "Internet Banking", icon: "monitor" },
    upi:              { label: "UPI",              icon: "qr-code" },
    branch:           { label: "Branch Banking",   icon: "building-2" },
    call_center:      { label: "Call Center",      icon: "phone" },
    atm:              { label: "ATM",              icon: "landmark" },
  })[channel] || { label: (channel || "").replace(/_/g, " "), icon: "globe" };
}

// Build a one-line plain-English story for an alert feed item.
function alertStory(alert) {
  const ev = eventLabel(alert.event_type).toLowerCase();
  const act = actionInfo(alert.response_taken).label.toLowerCase();
  return `${eventLabel(alert.event_type)} attempt — we ${act} it.`;
}

// --------------------------------------------------------------------------
// TIME
// --------------------------------------------------------------------------
function timeAgo(iso) {
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 10) return "just now";
  if (secs < 60) return `${secs} sec ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hr ago`;
  return new Date(iso).toLocaleDateString();
}

function clockTime(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// --------------------------------------------------------------------------
// ICON (Lucide) — renders an <svg>; missing names render nothing gracefully
// --------------------------------------------------------------------------
function Icon({ name, size = 18, strokeWidth = 1.75, className = "", color }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!ref.current || !window.lucide) return;
    ref.current.innerHTML = `<i data-lucide="${name}"></i>`;
    try { window.lucide.createIcons(); } catch (e) { /* ignore */ }
    const svg = ref.current.querySelector("svg");
    if (svg) {
      svg.setAttribute("width", size);
      svg.setAttribute("height", size);
      svg.setAttribute("stroke-width", strokeWidth);
      if (color) svg.setAttribute("stroke", color);
    }
  }, [name, size, strokeWidth, color]);
  return <span ref={ref} className={className} style={{ display: "inline-flex" }} />;
}

// --------------------------------------------------------------------------
// Count-up animation hook (0 -> value, quadratic ease)
// --------------------------------------------------------------------------
function useCountUp(value, duration = 800) {
  const [display, setDisplay] = React.useState(0);
  React.useEffect(() => {
    let raf;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - t) * (1 - t);
      setDisplay(value * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else setDisplay(value);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);
  return display;
}

// Small reusable status pill: coloured dot + word (never colour alone).
function StatusPill({ band }) {
  const info = bandInfo(band);
  return (
    <span className={`pill pill--${info.key}`}>
      <span className={`pill-dot dot--${info.key}`} />
      {info.label}
    </span>
  );
}

window.TrustIQ = {
  api, API_BASE,
  scoreBand, bandInfo, bandKey, actionInfo, eventLabel, categoryInfo, alertStory,
  trustBand, trustBandInfo, trendInfo, channelInfo,
  timeAgo, clockTime, Icon, useCountUp, StatusPill,
};
