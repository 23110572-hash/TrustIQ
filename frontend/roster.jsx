/**
 * roster - plain-language helpers for the operations console.
 *
 * There is NO hardcoded customer data here. Every customer the dashboard shows
 * is a real Identity Passport returned by TrustIQ (`/api/passports`), created
 * the moment that customer acts in the Bank of Baroda simulator. This module
 * only translates a passport's numbers into the words a branch employee thinks
 * in: Safe / Needs Verification / Suspicious / Blocked / Inactive.
 */
(function () {
  // An identity is "active" if it has acted within this window.
  const ACTIVE_WINDOW_MS = 5 * 60 * 1000;

  // Humanise any backend user_id into a display name. The simulator's account
  // ids (e.g. "krishna_agrawal") map cleanly to "Krishna Agrawal".
  function customerName(id) {
    if (!id) return "Unknown customer";
    return String(id).replace(/^demo_/, "").replace(/_/g, " ")
      .replace(/\b\w/g, (m) => m.toUpperCase());
  }

  function initials(name) {
    return (name || "?").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  }

  function isActive(lastSeen) {
    if (!lastSeen) return false;
    return (Date.now() - new Date(lastSeen).getTime()) < ACTIVE_WINDOW_MS;
  }

  // Turn a passport (or a passport-shaped object) into one of five business
  // statuses. Persistent trust bands: 80+ verified, 60+ established,
  // 40+ guarded, 20+ untrusted, else compromised.
  function passportStatus(p) {
    const t = p.trust_score != null ? p.trust_score : p.trust;
    if (t < 20) return "blocked";        // compromised — likely takeover
    if (t < 40) return "suspicious";     // untrusted
    if (!isActive(p.last_seen)) return "inactive";
    if (t < 60) return "verify";         // guarded
    return "safe";                       // established / verified
  }

  function statusInfo(status) {
    return ({
      safe:       { label: "Safe", key: "safe", icon: "shield-check",
                    advice: "No action needed — activity looks normal for this customer." },
      verify:     { label: "Needs Verification", key: "mid", icon: "alert-circle",
                    advice: "Some inconsistency — confirm identity before high-value actions." },
      suspicious: { label: "Suspicious", key: "high", icon: "alert-triangle",
                    advice: "Significant divergence — review now and contact the customer." },
      blocked:    { label: "Compromised", key: "critical", icon: "shield-alert",
                    advice: "Trust has collapsed — likely takeover. Freeze and verify in person." },
      inactive:   { label: "Inactive", key: "neutral", icon: "moon",
                    advice: "Dormant — no recent activity." },
    })[status] || { label: status, key: "neutral", icon: "circle", advice: "" };
  }

  // Colour key for the headline trust number (higher trust = safer colour).
  function trustColorKey(score) {
    if (score >= 60) return "safe";
    if (score >= 40) return "mid";
    if (score >= 20) return "high";
    return "critical";
  }

  function trustBandInfo(score) {
    if (score >= 80) return { label: "Verified", key: "safe" };
    if (score >= 60) return { label: "Established", key: "safe" };
    if (score >= 40) return { label: "Guarded", key: "mid" };
    if (score >= 20) return { label: "Untrusted", key: "high" };
    return { label: "Compromised", key: "critical" };
  }

  // TrustIQ trust_trend is "rising" | "falling" | "stable".
  function trendInfo(trend) {
    return ({
      rising:  { icon: "trending-up",   label: "Improving", key: "safe", arrow: "↑" },
      falling: { icon: "trending-down", label: "Declining", key: "high", arrow: "↓" },
      stable:  { icon: "minus",         label: "Stable",    key: "neutral", arrow: "→" },
      up:      { icon: "trending-up",   label: "Improving", key: "safe", arrow: "↑" },
      down:    { icon: "trending-down", label: "Declining", key: "high", arrow: "↓" },
    })[trend] || { icon: "minus", label: "Stable", key: "neutral", arrow: "→" };
  }

  window.Roster = {
    ACTIVE_WINDOW_MS, customerName, initials, isActive,
    passportStatus, statusInfo, trustColorKey, trustBandInfo, trendInfo,
  };
})();
