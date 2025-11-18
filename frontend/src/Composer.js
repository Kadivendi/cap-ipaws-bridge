import React, { useState } from "react";

const SEVERITIES = ["Extreme", "Severe", "Moderate", "Minor", "Unknown"];
const URGENCIES = ["Immediate", "Expected", "Future", "Past", "Unknown"];
const CERTAINTIES = ["Observed", "Likely", "Possible", "Unlikely", "Unknown"];

/**
 * CAP Message Composer — minimal authoring UI that posts to the
 * `/api/v1/compose` endpoint exposed by the FastAPI backend.
 *
 * Designed as a thin React surface over the same composer pipeline used by
 * the embedded `cap_composer_module/` Django app. The dropdowns mirror the
 * enums enforced by modules/ipaws/validator.py so anything submitted from
 * this UI already passes schema validation.
 */
function Composer() {
  const [form, setForm] = useState({
    event_id: "",
    severity: "Severe",
    urgency: "Immediate",
    certainty: "Observed",
    sender: "rapid_alert_platform@kadivendi.com",
    headline: "",
    description: "",
    instruction: "",
    target_areas: "",
  });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const setField = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const payload = {
        event_id: form.event_id || `evt-${Date.now()}`,
        severity: form.severity,
        headline: form.headline,
        description: form.description,
        instruction: form.instruction,
        target_areas: form.target_areas
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      };
      const res = await fetch("/api/v1/compose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(JSON.stringify(data));
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ fontFamily: "Arial, sans-serif", padding: "2rem", maxWidth: 880 }}>
      <h1>CAP 1.2 Composer</h1>
      <p>
        Author a CAP 1.2 alert and submit it through{" "}
        <code>POST /api/v1/compose</code>. The backend validates against the
        OASIS schema, dedups, audits, and forwards to IPAWS-OPEN.
      </p>

      <form onSubmit={submit} style={{ display: "grid", gap: "0.75rem" }}>
        <label>
          Event ID
          <input
            style={{ width: "100%" }}
            value={form.event_id}
            onChange={setField("event_id")}
            placeholder="evt-001 (auto if blank)"
          />
        </label>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem" }}>
          <label>
            Severity
            <select value={form.severity} onChange={setField("severity")}>
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label>
            Urgency
            <select value={form.urgency} onChange={setField("urgency")}>
              {URGENCIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label>
            Certainty
            <select value={form.certainty} onChange={setField("certainty")}>
              {CERTAINTIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label>
          Headline
          <input
            style={{ width: "100%" }}
            value={form.headline}
            onChange={setField("headline")}
            required
          />
        </label>

        <label>
          Description
          <textarea
            style={{ width: "100%" }}
            rows={4}
            value={form.description}
            onChange={setField("description")}
            required
          />
        </label>

        <label>
          Instruction
          <textarea
            style={{ width: "100%" }}
            rows={2}
            value={form.instruction}
            onChange={setField("instruction")}
          />
        </label>

        <label>
          Target areas (one per line)
          <textarea
            style={{ width: "100%" }}
            rows={3}
            value={form.target_areas}
            onChange={setField("target_areas")}
            placeholder={"Los Angeles County, CA\nOrange County, CA"}
          />
        </label>

        <button
          type="submit"
          disabled={submitting || !form.headline || !form.description}
          style={{ padding: "0.6rem", width: "12rem" }}
        >
          {submitting ? "Composing…" : "Compose & dispatch"}
        </button>
      </form>

      {error && (
        <pre style={{ background: "#fee", color: "crimson", padding: "1rem", marginTop: "1rem" }}>
          {error}
        </pre>
      )}

      {result && (
        <div style={{ marginTop: "1.5rem" }}>
          <h2>Result</h2>
          <p>
            <strong>Status:</strong> {result.status} ·{" "}
            <strong>IPAWS:</strong> {result.ipaws_status}
          </p>
          {result.cap_xml && (
            <details>
              <summary>Generated CAP 1.2 XML</summary>
              <pre style={{ background: "#f6f6f6", padding: "1rem", overflowX: "auto" }}>
                {result.cap_xml}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

export default Composer;
