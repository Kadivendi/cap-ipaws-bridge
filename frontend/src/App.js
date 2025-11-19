import React from "react";

import Composer from "./Composer";
import Dashboard from "./Dashboard";

/**
 * Top-level router. Hand-rolled (no react-router dependency) so the bundle
 * stays light. The available routes match the URLs documented in
 * `README.md`:
 *
 *   /            → dashboard (default landing page)
 *   /dashboard   → dashboard
 *   /composer    → CAP 1.2 composer UI
 *
 * Nginx (see `frontend/nginx.conf`) falls back to `index.html` for unknown
 * paths so a full-page reload on any of these works.
 */
function Nav({ path }) {
  const link = (target, label) => {
    const active = path === target || (target === "/dashboard" && path === "/");
    return (
      <a
        href={target}
        style={{
          marginRight: "1rem",
          fontWeight: active ? "bold" : "normal",
          textDecoration: active ? "underline" : "none",
        }}
      >
        {label}
      </a>
    );
  };
  return (
    <nav
      style={{
        borderBottom: "1px solid #ddd",
        padding: "0.75rem 2rem",
        fontFamily: "Arial, sans-serif",
        background: "#fafafa",
      }}
    >
      <strong style={{ marginRight: "1.5rem" }}>CAP-IPAWS Bridge</strong>
      {link("/dashboard", "Dashboard")}
      {link("/composer", "Composer")}
    </nav>
  );
}

function App() {
  // window.location.pathname is set by the time React mounts in the browser.
  const path =
    typeof window !== "undefined" && window.location
      ? window.location.pathname.replace(/\/+$/, "") || "/"
      : "/";

  let view;
  if (path === "/composer") {
    view = <Composer />;
  } else {
    // Default ("/") and /dashboard both render the dashboard.
    view = <Dashboard />;
  }

  return (
    <div>
      <Nav path={path} />
      {view}
    </div>
  );
}

export default App;
