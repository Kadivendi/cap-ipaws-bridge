import React, { useEffect, useState } from 'react';

function App() {
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    fetch('http://localhost:8000/api/v1/alerts')
      .then((res) => res.json())
      .then((data) => setAlerts(data.alerts || []))
      .catch((err) => console.error("Failed to fetch alerts", err));
  }, []);

  return (
    <div style={{ fontFamily: 'Arial, sans-serif', padding: '2rem' }}>
      <h1>CAP-IPAWS Routing Dashboard</h1>
      <p>Bridge module translating internal Rapid Alert Platform events into CAP 1.2 and dispatching to FEMA IPAWS-OPEN.</p>
      
      <div style={{ border: '1px solid #ccc', padding: '1rem', marginTop: '2rem' }}>
        <h2>Recent Dispatches</h2>
        {alerts.length === 0 ? (
          <p>No recent alerts dispatched.</p>
        ) : (
          <ul>
            {alerts.map((alert, i) => (
              <li key={i}>
                <strong>{alert.event_id}</strong> - {alert.headline} [{alert.status}] at {alert.timestamp}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default App;
