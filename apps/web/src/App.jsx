import { useEffect, useRef, useState } from "react";

const PERSONAS = [
  { id: "dean_cs", label: "Dean, Computer Science" },
  { id: "university", label: "University" },
];

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  return { ok: response.ok, status: response.status, data };
}

export default function App() {
  const [persona, setPersona] = useState("university");
  const [threadId, setThreadId] = useState(null);
  const [groups, setGroups] = useState([]);
  const [health, setHealth] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [matches, setMatches] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [questionsOpen, setQuestionsOpen] = useState(false);
  const threadRef = useRef(null);
  const starters = groups.slice(0, 3).flatMap((group) => group.questions.slice(0, 1));

  useEffect(() => {
    fetch("/api/templates")
      .then((response) => response.json())
      .then((body) => setGroups(body.groups || []))
      .catch(() => setError("The question list is not available yet."));
    fetch("/api/health")
      .then((response) => response.json())
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    const query = draft.trim();
    if (query.length < 2) {
      setMatches([]);
      return undefined;
    }
    const handle = setTimeout(() => {
      fetch(`/api/suggest?q=${encodeURIComponent(query)}`)
        .then((response) => response.json())
        .then((body) => setMatches(body.groups || []))
        .catch(() => setMatches([]));
    }, 150);
    return () => clearTimeout(handle);
  }, [draft]);

  useEffect(() => {
    const node = threadRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, busy]);

  function switchPersona(next) {
    setPersona(next);
    setThreadId(null);
    setMessages([]);
    setError("");
  }

  async function ask(text, templateId = null, page = 1) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setQuestionsOpen(false);
    setBusy(true);
    setError("");
    try {
      const { data } = await postJson("/api/chat", {
        message: trimmed,
        persona,
        thread_id: threadId,
        page,
        template_id: templateId,
      });
      setThreadId(data.thread_id || threadId);
      setMessages((current) => [
        ...current,
        { role: "user", text: page > 1 ? `${trimmed} (page ${page})` : trimmed },
        { role: "assistant", data, request: { text: trimmed, templateId, page } },
      ]);
      setDraft("");
      setMatches([]);
    } catch {
      setError("The assistant did not respond.");
    } finally {
      setBusy(false);
    }
  }

  async function approveReview(id) {
    setBusy(true);
    try {
      const { data } = await postJson("/api/review/approve", { id, persona });
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          data: {
            route: "template",
            answer: data.ok
              ? "Approved. The next time this question is asked, the saved query runs and the model is not called."
              : (data.error || "The question was not approved."),
            how_i_got_this: { summary: "Owner review", filters: [`persona=${persona}`], period: "not applicable", exclusions: [], assumptions: [], sql_or_template_id: data.ok ? `approved:${id}` : null },
            suggestions: [],
          },
        },
      ]);
    } catch {
      setError("Approval did not complete.");
    } finally {
      setBusy(false);
    }
  }

  function keepProxy() {
    setMessages((current) => [
      ...current,
      {
        role: "assistant",
        data: {
          route: "template",
          answer: "Keeping the loaded window. It stays labelled as a proxy, and nothing was emailed.",
          data_as_of: health?.data_as_of,
          how_i_got_this: {
            summary: "The user kept the labelled proxy. SMTP was not contacted.",
            filters: [`persona=${persona}`],
            period: "loaded window, labelled proxy",
            exclusions: ["No email was sent."],
            assumptions: ["The earlier period is still not loaded."],
            data_as_of: health?.data_as_of,
            sql_or_template_id: null,
          },
          suggestions: [],
          clarifying_question: null,
        },
      },
    ]);
  }

  async function confirmEmail(confirm) {
    if (!threadId) return;
    setBusy(true);
    try {
      const { data } = await postJson("/api/chat/confirm-email", { thread_id: threadId, confirm });
      const sent = Boolean(confirm && data.ok);
      const answer = sent
        ? "The draft was sent."
        : confirm
          ? (data.error || "Nothing was sent.")
          : "Nothing was sent. The draft stays unsent.";
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          data: {
            route: "email",
            answer,
            data_as_of: health?.data_as_of,
            how_i_got_this: {
              summary: data.smtp_attempted
                ? "SMTP was contacted after confirmation."
                : "SMTP was not contacted.",
              filters: [`confirm=${confirm}`, `smtp_attempted=${data.smtp_attempted}`],
              period: "not applicable",
              exclusions: data.error ? [data.error] : [],
              assumptions: [],
              data_as_of: health?.data_as_of,
              sql_or_template_id: null,
            },
            table: null,
            suggestions: [],
            clarifying_question: null,
          },
        },
      ]);
    } catch {
      setError("The email action failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <a className="skip" href="#conversation">Skip to conversation</a>
      <div className="shell">
        {questionsOpen && (
          <button type="button" className="backdrop" aria-label="Close questions" onClick={() => setQuestionsOpen(false)} />
        )}
        <aside className={questionsOpen ? "rail open" : "rail"} id="questions">
          <div className="mark">
            <svg width="36" height="36" viewBox="0 0 36 36" aria-hidden="true">
              <rect width="36" height="36" rx="8" fill="#1E40AF" />
              <text x="18" y="23" textAnchor="middle" fill="#F8FAFC" fontFamily="Space Grotesk, sans-serif" fontSize="12" fontWeight="700">LIA</text>
            </svg>
            <div>
              <strong>LIA</strong>
              <span>Utilization assistant</span>
            </div>
          </div>
          <div className="persona" role="radiogroup" aria-label="Who is asking">
            <p>View</p>
            {PERSONAS.map((item) => (
              <label key={item.id} className={persona === item.id ? "on" : ""}>
                <input
                  type="radio"
                  name="persona"
                  value={item.id}
                  checked={persona === item.id}
                  onChange={() => switchPersona(item.id)}
                />
                {item.label}
              </label>
            ))}
          </div>
          <nav className="catalog" aria-label="Suggested questions">
            {groups.map((group, index) => (
              <details key={group.area} open={index === 0}>
                <summary>{group.area}</summary>
                {group.questions.map((question) => (
                  <button
                    key={question.label}
                    type="button"
                    className="prompt"
                    disabled={busy}
                    onClick={() => ask(question.label, question.template_id, 1)}
                  >
                    {question.label}
                  </button>
                ))}
              </details>
            ))}
          </nav>
          <p className="status">
            Read only. {health?.timetable_rows ?? "—"} timetable rows.
            {" "}Data as of {health?.data_as_of || "not loaded"}.
          </p>
        </aside>
        <section className="stage">
          <header className="stage-bar">
            <button
              type="button"
              className="menu-toggle"
              aria-expanded={questionsOpen}
              aria-controls="questions"
              onClick={() => setQuestionsOpen((open) => !open)}
            >
              {questionsOpen ? "Close" : "Questions"}
            </button>
            <div className="titles">
              <h1>Ask the week</h1>
              <p>Faculty load, rooms, and the timetable. Known questions stay exact.</p>
            </div>
            <span className="pill">{persona === "dean_cs" ? "Computer Science" : "All schools"}</span>
          </header>
          <div id="conversation" className="thread" ref={threadRef} aria-live="polite">
            {messages.length === 0 && (
              <div className="empty">
                <h2>What should the dean see first?</h2>
                <p>Pick a reviewed question, or type one. You can edit a name, a school, or a number before you ask.</p>
                <div className="starters">
                  {starters.map((question) => (
                    <button
                      key={question.label}
                      type="button"
                      disabled={busy}
                      onClick={() => ask(question.label, question.template_id, 1)}
                    >
                      {question.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((message, index) =>
              message.role === "user" ? (
                <p key={index} className="user">{message.text}</p>
              ) : (
                <Answer
                  key={index}
                  data={message.data}
                  busy={busy}
                  onNext={
                    message.request &&
                    message.data?.table &&
                    message.request.page * (message.data.table.page_size || 20) < message.data.table.total_count
                      ? () => ask(message.request.text, message.request.templateId, message.request.page + 1)
                      : null
                  }
                  onChip={(option) => {
                    if (option.id === "confirm-email") confirmEmail(true);
                    else if (option.id === "cancel-email") confirmEmail(false);
                    else if (option.id === "keep-proxy") keepProxy();
                    else if (option.id === "request-email") {
                      ask("Please email the data owner to upload the missing period", null, 1);
                    } else ask(option.label, null, 1);
                  }}
                  onSuggestion={(suggestion) => ask(suggestion.label, suggestion.template_id, 1)}
                  onApprove={persona === "university" ? approveReview : null}
                />
              ),
            )}
            {busy && <p className="working">Looking that up.</p>}
            {error && <p className="error" role="alert">{error}</p>}
          </div>
          <div className="dock">
            <form
              onSubmit={(event) => {
                event.preventDefault();
                ask(draft, null, 1);
              }}
            >
              <label htmlFor="question">Type a question</label>
              <div className="row">
                <input
                  id="question"
                  value={draft}
                  role="combobox"
                  aria-autocomplete="list"
                  aria-expanded={matches.length > 0}
                  aria-controls="template-matches"
                  placeholder="Try a name, a room, or a school"
                  onChange={(event) => setDraft(event.target.value)}
                  disabled={busy}
                />
                <button type="submit" className="cta" disabled={busy || !draft.trim()}>
                  {busy ? "Asking" : "Ask"}
                </button>
              </div>
              {matches.length > 0 && (
                <div id="template-matches" className="suggest" role="listbox" aria-label="Matching question templates">
                  {matches.map((group) => (
                    <div key={group.area}>
                      <p>{group.area}</p>
                      {group.questions.map((question) => (
                        <button
                          key={question.label}
                          type="button"
                          role="option"
                          onClick={() => {
                            setDraft(question.label);
                            setMatches([]);
                          }}
                        >
                          {question.label}
                        </button>
                      ))}
                    </div>
                  ))}
                  <p className="hint">Edit the name, school, or number, then Ask.</p>
                </div>
              )}
            </form>
          </div>
        </section>
      </div>
    </>
  );
}

function Answer({ data, onNext, onChip, onSuggestion, onApprove, busy }) {
  const how = data?.how_i_got_this || {};
  const table = data?.table;
  return (
    <article className="answer">
      <p className="badges">
        <span>Route {data?.route || "unknown"}</span>
        {data?.review?.label && <span>{data.review.label}</span>}
        <span>Data as of {data?.data_as_of || how.data_as_of || "unknown"}</span>
      </p>
      <p>{data?.answer}</p>
      <details>
        <summary>How I got this. {how.summary || "Closed until opened."}</summary>
        <dl>
          <dt>Filters</dt>
          <dd>{(how.filters || []).join("; ") || "none"}</dd>
          <dt>Period</dt>
          <dd>{how.period}</dd>
          <dt>Exclusions</dt>
          <dd>{(how.exclusions || []).join(" ") || "none"}</dd>
          <dt>Assumptions</dt>
          <dd>{(how.assumptions || []).join(" ") || "none"}</dd>
          <dt>Data as of</dt>
          <dd>{how.data_as_of || data?.data_as_of || "unknown"}</dd>
          <dt>SQL or template</dt>
          <dd><code>{how.sql_or_template_id || "none"}</code></dd>
        </dl>
      </details>
      {table && table.columns?.length > 0 && (
        <div className="table-wrap">
          <p>
            Showing {table.rows.length} of {table.total_count} · page {table.page}
          </p>
          <table>
            <thead>
              <tr>{table.columns.map((column) => <th key={column}>{column}</th>)}</tr>
            </thead>
            <tbody>
              {table.rows.map((row, index) => (
                <tr key={index}>
                  {table.columns.map((column) => <td key={column}>{String(row[column] ?? "")}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
          {onNext && (
            <button type="button" className="cta" disabled={busy} onClick={onNext}>Next page</button>
          )}
        </div>
      )}
      {data?.review?.status === "pending_owner_review" && onApprove && (
        <button type="button" className="cta" disabled={busy} onClick={() => onApprove(data.review.id)}>
          Approve as a template
        </button>
      )}
      {data?.clarifying_question && (
        <div className="chips" role="group" aria-label="Clarifying choices">
          {data.clarifying_question.options.map((option) => (
            <button key={option.id} type="button" disabled={busy} onClick={() => onChip(option)}>
              {option.label}
            </button>
          ))}
        </div>
      )}
      {!!data?.suggestions?.length && (
        <div className="chips related">
          {data.suggestions.map((suggestion) => (
            <button key={suggestion.label} type="button" disabled={busy} onClick={() => onSuggestion(suggestion)}>
              {suggestion.label}
            </button>
          ))}
        </div>
      )}
    </article>
  );
}
