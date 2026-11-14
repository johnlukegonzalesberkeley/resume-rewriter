import { useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000/rewrite";

export default function App() {
  const [resume, setResume] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [rewrites, setRewrites] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const canSubmit = resume.trim() && jobDescription.trim() && !loading;

  async function handleSubmit() {
    setLoading(true);
    setError("");
    setRewrites([]);
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

  function copy(text) {
    navigator.clipboard.writeText(text);
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
          <h2>Suggested rewrites</h2>
          {rewrites.map((r, i) => (
            <article className="card" key={i}>
              <div className="row">
                <span className="tag before">Before</span>
                <p>{r.original}</p>
              </div>
              <div className="row">
                <span className="tag after">After</span>
                <p>{r.rewritten}</p>
                <button className="small" onClick={() => copy(r.rewritten)}>
                  Copy
                </button>
              </div>
              <p className="reason">{r.reason}</p>
              {r.missing_info && (
                <p className="missing">Add detail: {r.missing_info}</p>
              )}
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
