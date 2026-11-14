import { useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000/rewrite";

export default function App() {
  const [resume, setResume] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [rewrites, setRewrites] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // decisions maps a rewrite's index to "accepted" or "rejected".
  // No entry means the user hasn't decided yet.
  const [decisions, setDecisions] = useState({});
  const [copied, setCopied] = useState(false);

  const canSubmit = resume.trim() && jobDescription.trim() && !loading;

  // Derived from state, so it is always in sync and never stored separately.
  const acceptedBullets = rewrites
    .filter((_, i) => decisions[i] === "accepted")
    .map((r) => r.rewritten);

  async function handleSubmit() {
    setLoading(true);
    setError("");
    setRewrites([]);
    setDecisions({});
    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: resume,
          job_description: jobDescription,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail =
          typeof body.detail === "string"
            ? body.detail
            : `Request failed (${res.status})`;
        throw new Error(detail);
      }
      const data = await res.json();
      setRewrites(data.rewrites);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  // Clicking the same button again undoes the decision.
  function decide(index, value) {
    setDecisions((prev) => {
      const next = { ...prev };
      if (next[index] === value) {
        delete next[index];
      } else {
        next[index] = value;
      }
      return next;
    });
  }

  function acceptAll() {
    const all = {};
    rewrites.forEach((_, i) => {
      all[i] = "accepted";
    });
    setDecisions(all);
  }

  async function copyAccepted() {
    const text = acceptedBullets.map((b) => `- ${b}`).join("\n");
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <main className="app">
      <h1>AI Resume Rewriter</h1>
      <p className="subtitle">
        Paste your resume bullets and a job description to get tailored rewrites.
      </p>

      <div className="inputs">
        <label>
          Resume
          <textarea
            value={resume}
            onChange={(e) => setResume(e.target.value)}
            placeholder="Paste your resume text or bullets here"
            rows={12}
          />
        </label>
        <label>
          Job description
          <textarea
            value={jobDescription}
            onChange={(e) => setJobDescription(e.target.value)}
            placeholder="Paste the job posting here"
            rows={12}
          />
        </label>
      </div>

      <button onClick={handleSubmit} disabled={!canSubmit}>
        {loading ? "Rewriting..." : "Rewrite my resume"}
      </button>

      {error && <p className="error">{error}</p>}

      {rewrites.length > 0 && (
        <section className="results">
          <div className="results-header">
            <h2>Suggested rewrites</h2>
            <div className="toolbar">
              <span className="count">
                {acceptedBullets.length} of {rewrites.length} accepted
              </span>
              <button className="small" onClick={acceptAll}>
                Accept all
              </button>
              <button
                className="small primary"
                onClick={copyAccepted}
                disabled={acceptedBullets.length === 0}
              >
                {copied ? "Copied!" : "Copy accepted"}
              </button>
            </div>
          </div>

          {rewrites.map((r, i) => {
            const status = decisions[i];
            return (
              <article className={`card ${status || ""}`} key={i}>
                <div className="row">
                  <span className="tag before">Before</span>
                  <p>{r.original}</p>
                </div>
                <div className="row">
                  <span className="tag after">After</span>
                  <p>{r.rewritten}</p>
                </div>
                <p className="reason">{r.reason}</p>
                {r.missing_info && (
                  <p className="missing">Add detail: {r.missing_info}</p>
                )}
                <div className="decision">
                  <button
                    className={`small accept ${status === "accepted" ? "on" : ""}`}
                    onClick={() => decide(i, "accepted")}
                  >
                    {status === "accepted" ? "Accepted ✓" : "Accept"}
                  </button>
                  <button
                    className={`small reject ${status === "rejected" ? "on" : ""}`}
                    onClick={() => decide(i, "rejected")}
                  >
                    {status === "rejected" ? "Rejected ✕" : "Reject"}
                  </button>
                </div>
              </article>
            );
          })}
        </section>
      )}
    </main>
  );
}
