import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const questions = [
  ["country", "Which country do you live in?", "Dropdown"],
  ["wellbeing", "How would you rate your overall wellbeing this week?", "Scale 1–5"],
  ["symptoms", "Which of the following have you experienced?", "Multi-select"],
];

function App() {
  return <main>
    <header><span className="eyebrow">PROlog</span><h1>Patient-reported outcomes</h1>
      <p>Design governed surveys and run them securely against PRomop.</p></header>
    <section className="grid">
      <article><span className="eyebrow">Survey designer</span><h2>Sample wellbeing survey</h2>
        <p className="muted">Draft · English · 3 sections</p>
        {questions.map(([key, label, type]) => <div className="question" key={key}>
          <strong>{label}</strong><small>{type} · {key}</small></div>)}
        <button>Open designer</button>
      </article>
      <article><span className="eyebrow">Survey runner</span><h2>About you</h2>
        <label>Which country do you live in?<select defaultValue=""><option value="" disabled>Select a country</option><option>United Kingdom</option><option>United States</option><option>Other</option></select></label>
        <label>How would you rate your overall wellbeing this week?<select defaultValue=""><option value="" disabled>Select an answer</option><option>1 – Very poor</option><option>3 – Fair</option><option>5 – Very good</option></select></label>
        <button>Save and continue</button>
      </article>
    </section>
  </main>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
