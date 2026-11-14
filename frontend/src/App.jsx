import { useEffect, useRef, useState } from "react";
import "./App.css";
import { diffWords } from "./diff.js";

// Where the backend lives. Set VITE_API_BASE (see .env.example) when you deploy.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

// Pull a readable message out of a failed response.
async function readError(res) {
  const body = await res.json().catch(() => ({}));
  if (typeof body.detail === "string") return body.detail;
  // Validation errors (422) come back as a list of {msg: "..."} objects.
  if (Array.isArray(body.detail) && body.detail.length > 0) {
    return body.detail.map((d) => d.msg).join("; ");
  }
  return `Request failed (${res.status})`;
}

// Returns a copy of an object without one key (state must never be edited in place).
function omit(obj, key) {
  const next = { ...obj };
  delete next[key];
  return next;
}

// Renders text split into segments, highlighting the ones that changed.
function DiffText({ segments, kind }) {
  // Merge neighbors with the same status, so a run of changed words becomes ONE
  // highlight instead of a row of separate pills with notches between them.
  const groups = [];
  for (const seg of segments) {
    const last = groups[groups.length - 1];
    if (last && last.changed === seg.changed) {
      last.text += seg.text;
    } else {
      groups.push({ text: seg.text, changed: seg.changed });
    }
  }
  return (
    <>
      {groups.map((group, i) => (
        <span key={i} className={group.changed ? `diff-${kind}` : undefined}>
          {group.text}
        </span>
      ))}
    </>
  );
}

export default function App() {
  const [resume, setResume] = useState("");
  const [jobDescription, setJobDescription] = useState("");

  // True when the backend is running in demo mode (placeholder rewrites, no AI).
  const [demoMode, setDemoMode] = useState(false);

  // PDF upload state
  const fileRef = useRef(null);
  const [readingPdf, setReadingPdf] = useState(false);
  const [pdfNote, setPdfNote] = useState("");
  const [pdfError, setPdfError] = useState("");
  const [rewrites, setRewrites] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // The job description used for the current results. Regenerating a bullet must use
  // this one, even if the user edits the text box afterward.
  const [lastJobDescription, setLastJobDescription] = useState("");

  // Per-card state is keyed by each rewrite's stable id, not its list position.
  const [decisions, setDecisions] = useState({}); // id -> "accepted" | "rejected"
  const [answers, setAnswers] = useState({}); // id -> text typed in the answer box
  const [updating, setUpdating] = useState({}); // id -> true while regenerating
  const [cardErrors, setCardErrors] = useState({}); // id -> error message
  const [edits, setEdits] = useState({}); // id -> the user's hand-edited After text
  const [editingId, setEditingId] = useState(null); // which card's editor is open
  const [copied, setCopied] = useState(false);

  // Ask the backend once whether it is in demo mode, so we never pass off placeholder
  // text as real AI output.
  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => res.json())
      .then((data) => setDemoMode(Boolean(data.mock)))
      .catch(() => {}); // if the backend is down, the first request will show an error
  }, []);

  const canSubmit = resume.trim() && jobDescription.trim() && !loading;

  // The text a card currently shows: the user's edit if there is one, else the AI's.
  function currentText(r) {
    return edits[r.id] ?? r.rewritten;
  }

  // Derived from state, so it is always in sync and never stored separately.
  const acceptedBullets = rewrites
    .filter((r) => decisions[r.id] === "accepted")
    .map(currentText);

  // Send the chosen PDF to the backend, which returns its text for the user to review.
  async function handlePdf(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // lets the user pick the same file again later
    if (!file) return;

    setPdfNote("");
    setPdfError("");
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setPdfError("Please choose a PDF file.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setPdfError("That PDF is over 5 MB.");
      return;
    }

    setReadingPdf(true);
    try {
      const form = new FormData();
      form.append("file", file);
      // No Content-Type header here: the browser sets it, including the form boundary.
      const res = await fetch(`${API_BASE}/extract-pdf`, { method: "POST", body: form });
      if (!res.ok) throw new Error(await readError(res));
      const data = await res.json();
      setResume(data.text);
      setPdfNote(
        `Loaded ${file.name} (${data.pages} page${data.pages === 1 ? "" : "s"}). ` +
          "Check the text below and fix anything that looks off before rewriting."
      );
    } catch (err) {
      setPdfError(err.message);
    } finally {
      setReadingPdf(false);
    }
  }

  async function handleSubmit() {
    setLoading(true);
    setError("");
    setRewrites([]);
    setDecisions({});
    setAnswers({});
    setUpdating({});
    setCardErrors({});
    setEdits({});
    setEditingId(null);
    try {
      const res = await fetch(`${API_BASE}/rewrite`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: resume,
          job_description: jobDescription,
        }),
      });
      if (!res.ok) throw new Error(await readError(res));
      const data = await res.json();
      const batch = Date.now();
      // Give every rewrite a stable id so we can update one card safely later.
      setRewrites(data.rewrites.map((r, i) => ({ ...r, id: `${batch}-${i}` })));
      setLastJobDescription(jobDescription);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function regenerate(r) {
    const detail = (answers[r.id] || "").trim();
    if (!detail || updating[r.id]) return;

    setUpdating((prev) => ({ ...prev, [r.id]: true }));
    setCardErrors((prev) => ({ ...prev, [r.id]: "" }));
    try {
      const res = await fetch(`${API_BASE}/regenerate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          original: r.original,
          user_detail: detail,
          job_description: lastJobDescription,
        }),
      });
      if (!res.ok) throw new Error(await readError(res));
      const updated = await res.json();

      // Replace only this card, keeping its id and marking it as updated.
      setRewrites((prev) =>
        prev.map((x) => (x.id === r.id ? { ...updated, id: r.id, updated: true } : x))
      );
      setAnswers((prev) => omit(prev, r.id));
      // The text changed, so earlier accept/reject and hand edits no longer apply.
      setDecisions((prev) => omit(prev, r.id));
      setEdits((prev) => omit(prev, r.id));
      setEditingId((cur) => (cur === r.id ? null : cur));
    } catch (e) {
      setCardErrors((prev) => ({ ...prev, [r.id]: e.message }));
    } finally {
      setUpdating((prev) => ({ ...prev, [r.id]: false }));
    }
  }

  // Clicking the same button again undoes the decision.
  function decide(id, value) {
    setDecisions((prev) =>
      prev[id] === value ? omit(prev, id) : { ...prev, [id]: value }
    );
  }

  function acceptAll() {
    const all = {};
    rewrites.forEach((r) => {
      all[r.id] = "accepted";
    });
    setDecisions(all);
  }

  function startEditing(r) {
    setEdits((prev) => {
      const next = { ...prev };
      // Only one editor is open at a time, so close the previous one first, with the
      // same clean-up as Done: an empty or unchanged edit falls back to the AI version.
      if (editingId && editingId !== r.id) {
        const other = rewrites.find((x) => x.id === editingId);
        const text = (next[editingId] || "").trim();
        if (!other || !text || text === other.rewritten) {
          delete next[editingId];
        } else {
          next[editingId] = text;
        }
      }
      // Open this editor starting from the text the card currently shows.
      next[r.id] = prev[r.id] ?? r.rewritten;
      return next;
    });
    setEditingId(r.id);
  }

  function finishEditing(r) {
    // An empty edit isn't useful, so fall back to the AI's version.
    const text = (edits[r.id] || "").trim();
    setEdits((prev) => (text && text !== r.rewritten ? { ...prev, [r.id]: text } : omit(prev, r.id)));
    setEditingId(null);
  }

  function undoEdit(r) {
    setEdits((prev) => omit(prev, r.id));
    setEditingId((cur) => (cur === r.id ? null : cur));
  }

  async function copyAccepted() {
    const text = acceptedBullets.map((b) => `- ${b}`).join("\n");
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <main className="app">
      <header className="hero">
        <h1>
          <span>Sharper bullets.</span>
          <span>Nothing made up.</span>
        </h1>
        <p className="subtitle">
          Paste your resume and a job posting. You get rewrites that stick to what you
          wrote, and questions wherever a real detail would help.
        </p>
      </header>

      {demoMode && (
        <p className="demo-banner" role="status">
          Demo mode: the rewrites below are placeholders, not real AI output.
        </p>
      )}

      <div className="inputs">
        <div className="field">
          <div className="field-head">
            <label htmlFor="resume">Resume</label>
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf,.pdf"
              hidden
              onChange={handlePdf}
            />
            <button
              type="button"
              className="small"
              onClick={() => fileRef.current?.click()}
              disabled={readingPdf}
            >
              {readingPdf ? "Reading PDF..." : "Upload PDF"}
            </button>
          </div>
          <textarea
            id="resume"
            maxLength={30000}
            value={resume}
            onChange={(e) => {
              setResume(e.target.value);
              setPdfNote(""); // the "Loaded ...pdf" note no longer describes the text
            }}
            placeholder="Paste your resume text or bullets here, or upload a PDF"
            rows={12}
          />
          {pdfNote && (
            <p className="note" role="status">
              {pdfNote}
            </p>
          )}
          {pdfError && (
            <p className="field-error" role="alert">
              {pdfError}
            </p>
          )}
        </div>

        <div className="field">
          <div className="field-head">
            <label htmlFor="job">Job description</label>
          </div>
          <textarea
            id="job"
            maxLength={15000}
            value={jobDescription}
            onChange={(e) => setJobDescription(e.target.value)}
            placeholder="Paste the job posting here"
            rows={12}
          />
        </div>
      </div>

      <button className="cta" onClick={handleSubmit} disabled={!canSubmit}>
        {loading ? "Rewriting..." : "Rewrite my resume"}
      </button>

      {error && <p className="error">{error}</p>}

      {rewrites.length > 0 && (
        <section className="results">
          <div className="results-head">
            <h2>Suggested rewrites</h2>
            <p className="legend">
              <span className="diff-removed">Red</span> words were removed from your
              original. <span className="diff-added">Green</span> words were added. Click
              Edit to change a rewrite yourself.
            </p>
          </div>

          {rewrites.map((r) => {
            const status = decisions[r.id];
            const isUpdating = updating[r.id];
            const isEditing = editingId === r.id;
            const current = currentText(r);
            const isEdited = current !== r.rewritten;
            const diff = diffWords(r.original, current);
            return (
              <article className={`item ${status || ""}`} key={r.id}>
                <div className="line before-line">
                  <span className="label">Before</span>
                  <p>
                    <DiffText segments={diff.before} kind="removed" />
                  </p>
                </div>
                <div className="line after-line">
                  <span className="label">After</span>
                  {isEditing ? (
                    <textarea
                      className="edit-area"
                      value={edits[r.id] ?? ""}
                      rows={2}
                      autoFocus
                      onChange={(e) =>
                        setEdits((prev) => ({ ...prev, [r.id]: e.target.value }))
                      }
                    />
                  ) : (
                    <p>
                      <DiffText segments={diff.after} kind="added" />
                      {r.updated && (
                        <span className="updated-tag">Updated with your detail</span>
                      )}
                      {isEdited && <span className="edited-tag">Edited by you</span>}
                    </p>
                  )}
                </div>
                <p className="reason">{r.reason}</p>

                {r.missing_info && (
                  <div className="missing">
                    <p>Add detail: {r.missing_info}</p>
                    <div className="answer">
                      <input
                        type="text"
                        maxLength={500}
                        value={answers[r.id] || ""}
                        onChange={(e) =>
                          setAnswers((prev) => ({ ...prev, [r.id]: e.target.value }))
                        }
                        onKeyDown={(e) => e.key === "Enter" && regenerate(r)}
                        placeholder="Type your answer, e.g. a real number or detail"
                        disabled={isUpdating}
                      />
                      <button
                        className="small primary"
                        onClick={() => regenerate(r)}
                        disabled={isUpdating || !(answers[r.id] || "").trim()}
                      >
                        {isUpdating ? "Updating..." : "Update bullet"}
                      </button>
                    </div>
                    {cardErrors[r.id] && <p className="card-error">{cardErrors[r.id]}</p>}
                  </div>
                )}

                <div className="decision">
                  <button
                    className={`small accept ${status === "accepted" ? "on" : ""}`}
                    onClick={() => decide(r.id, "accepted")}
                  >
                    {status === "accepted" ? "Accepted ✓" : "Accept"}
                  </button>
                  <button
                    className={`small reject ${status === "rejected" ? "on" : ""}`}
                    onClick={() => decide(r.id, "rejected")}
                  >
                    {status === "rejected" ? "Rejected ✕" : "Reject"}
                  </button>
                  <button
                    className="small"
                    onClick={() => (isEditing ? finishEditing(r) : startEditing(r))}
                  >
                    {isEditing ? "Done" : "Edit"}
                  </button>
                  {isEdited && !isEditing && (
                    <button className="small" onClick={() => undoEdit(r)}>
                      Undo edit
                    </button>
                  )}
                </div>
              </article>
            );
          })}

          <div className="dock">
            <span className="count">
              {acceptedBullets.length} of {rewrites.length} accepted
            </span>
            <div className="dock-actions">
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
        </section>
      )}
    </main>
  );
}
