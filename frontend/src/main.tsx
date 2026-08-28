import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const questions = [
  ["country", "Which country do you live in?", "Single choice"],
  ["fl_journey", "Where are you now in your FL journey?", "Single choice"],
  ["treatment_access", "Have you experienced a treatment access delay?", "Single choice"],
];

function App() {
  return <main>
    <header><span className="eyebrow">PROlog</span><h1>Patient-reported outcomes</h1>
      <p>Design governed surveys and run them securely against PRomop.</p></header>
    <section className="grid">
      <article><span className="eyebrow">Survey designer</span><h2>FLF Global Patient Survey 2026</h2>
        <p className="muted">Draft · English · 6 sections</p>
        {questions.map(([key, label, type]) => <div className="question" key={key}>
          <strong>{label}</strong><small>{type} · {key}</small></div>)}
        <button>Open designer</button>
      </article>
      <article><span className="eyebrow">Survey runner</span><h2>About you and your FL journey</h2>
        <label>Which country do you live in?<select defaultValue=""><option value="" disabled>Select a country</option><option>United Kingdom</option><option>United States</option><option>Other</option></select></label>
        <label>Where are you now in your FL journey?<select defaultValue=""><option value="" disabled>Select an answer</option><option>Watch and wait</option><option>Currently receiving treatment</option><option>In remission</option></select></label>
        <button>Save and continue</button>
      </article>
    </section>
  </main>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
