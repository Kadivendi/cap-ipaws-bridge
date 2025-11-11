import React, { useEffect, useState } from "react";

/**
 * Alert Dashboard — lists recently ingested CAP alerts and their delivery
 * status. The backend is reached through nginx's /api/ proxy, so the
 * fetch URL is same-origin and works whether the app is loaded from
 * http://localhost:8080/dashboard or behind a real reverse proxy.
 */
function Dashboard() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let aborted = false;
    const tick = () =>
      fetch("/api/v1/alerts")
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then((data) => {
          if (aborted) return;
          setAlerts(data.alerts || []);
          setLoading(false);
        })
        .catch((err) => {
          if (aborted) return;
          setError(err.message);
          setLoading(false);
        });

    tick();
    const id = setInterval(tick, 10000); // 10s refresh
    return () => {
      aborted = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div style={{ fontFamily: "Arial, sans-serif", padding: "2rem" }}>
      <h1>CAP-IPAWS Routing Dashboard</h1>
      <p>
        Bridge module translating internal Rapid Alert Platform events into CAP
        1.2 and dispatching to FEMA IPAWS-OPEN.
      </p>

      <div
        style={{ border: "1px solid #ccc", padding: "1rem", marginTop: "2rem" }}
      >
        <h2>Recent Dispatches</h2>
        {loading && <p>Loading…</p>}
        {error && (
          <p style={{ color: "crimson" }}>Failed to fetch alerts: {error}</p>
        )}
        {!loading && !error && alerts.length === 0 ? (
          <p>No recent alerts dispatched.</p>
        ) : (
          <ul>
            {alerts.map((alert) => (
              <li key={alert.alert_id || alert.event_id}>
                <strong>{alert.alert_id || alert.event_id}</strong>
                {alert.headline ? ` - ${alert.headline}` : ""}{" "}
                [{alert.severity || alert.status || "?"}]
                {alert.timestamp ? ` at ${alert.timestamp}` : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default Dashboard;
