/**
 * A page that mounts the real `Modal` the way a page does, so Playwright can
 * drive it with real key events — jsdom cannot reproduce a browser's own
 * handling of selection and typing.
 *
 * It is served by the Vite dev server at `/e2e/harness/index.html` and is not
 * part of the production build: `vite build` only bundles `index.html`.
 *
 * Two details are deliberate, because they are what the regression needed:
 *  - `onClose` is an inline arrow, so its identity changes on every render, and
 *  - the inputs are controlled by state, so every keystroke re-renders `Modal`.
 *
 * Together they are the shape that used to re-run the dialog's setup effect and
 * yank the caret out of the field being typed into.
 */
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { Field, Input, Modal, Select, Textarea } from "../../src/components/ui";

type Mode = "edit" | "add" | "date";

function Harness() {
  const [mode, setMode] = useState<Mode | null>(null);
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [notes, setNotes] = useState("");

  function open(next: Mode) {
    setMode(next);
    if (next === "edit") {
      // An edit dialog opens with the record's saved values.
      setAmount("128.00");
      setDescription("Groceries");
      setNotes("Weekly shop");
    } else {
      // An add dialog opens empty.
      setAmount("");
      setDescription("");
      setNotes("");
    }
  }

  return (
    <div>
      <button id="open-edit" type="button" onClick={() => open("edit")}>
        Edit transaction
      </button>
      <button id="open-add" type="button" onClick={() => open("add")}>
        Add transaction
      </button>
      <button id="open-date" type="button" onClick={() => open("date")}>
        Change date
      </button>
      <p id="state">{mode ? `open:${mode}` : "closed"}</p>

      {mode === "date" ? (
        <Modal open title="Change the date" onClose={() => setMode(null)}>
          <Field label="Date" htmlFor="due-date">
            <Input id="due-date" type="date" defaultValue="2026-11-07" />
          </Field>
        </Modal>
      ) : (
        <Modal
          open={mode !== null}
          title={mode === "edit" ? "Edit transaction" : "Add transaction"}
          onClose={() => setMode(null)}
        >
          <div className="col">
            {/* A select leads, as in the real forms: focus must skip it. */}
            <Field label="Type" htmlFor="type">
              <Select id="type" value="purchase" onChange={() => {}}>
                <option value="purchase">Purchase</option>
                <option value="income">Income</option>
              </Select>
            </Field>
            <Field label="Amount" htmlFor="amount">
              <Input
                id="amount"
                inputMode="decimal"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              />
            </Field>
            <Field label="Description" htmlFor="description">
              <Input
                id="description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>
            <Field label="Notes" htmlFor="notes">
              <Textarea id="notes" value={notes} onChange={(event) => setNotes(event.target.value)} />
            </Field>
          </div>
        </Modal>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Harness />
  </StrictMode>,
);
