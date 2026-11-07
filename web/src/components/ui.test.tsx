import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Modal } from "./ui";

/**
 * Mirrors how every page uses Modal: form state lives in the page that owns the
 * dialog and onClose is an inline arrow, so the handler identity changes on
 * every keystroke. That combination used to re-run the dialog's focus effect on
 * each render and pull the caret out of the field being typed into - which sent
 * the following keystroke to the browser's type-ahead Find bar.
 */
function Harness({ onClosed }: { onClosed?: () => void } = {}) {
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  return (
    <Modal open title="Add transaction" onClose={() => onClosed?.()}>
      <label htmlFor="txn-name">Name</label>
      <input id="txn-name" value={name} onChange={(event) => setName(event.target.value)} />
      <label htmlFor="txn-notes">Notes</label>
      <input id="txn-notes" value={notes} onChange={(event) => setNotes(event.target.value)} />
    </Modal>
  );
}

/** A dialog laid out like the real forms: a select first, then an unusable
 * input, then the first field a person could actually type in. */
function FormHarness() {
  return (
    <Modal open title="Record a transaction" onClose={() => {}}>
      <label htmlFor="f-type">Type</label>
      <select id="f-type" defaultValue="purchase">
        <option value="purchase">Purchase</option>
      </select>
      <label htmlFor="f-locked">Locked</label>
      <input id="f-locked" value="read only" readOnly />
      <label htmlFor="f-amount">Amount</label>
      <input id="f-amount" defaultValue="" />
      <label htmlFor="f-notes">Notes</label>
      <textarea id="f-notes" defaultValue="" />
    </Modal>
  );
}

/** An edit dialog opens with the saved record already in its fields. */
function EditHarness() {
  return (
    <Modal open title="Edit transaction" onClose={() => {}}>
      <label htmlFor="e-amount">Amount</label>
      <input id="e-amount" defaultValue="12.50" />
      <label htmlFor="e-description">Description</label>
      <input id="e-description" defaultValue="Coffee" />
    </Modal>
  );
}

function DateFirstHarness() {
  return (
    <Modal open title="Move the due date" onClose={() => {}}>
      <label htmlFor="d-date">Date</label>
      <input id="d-date" type="date" defaultValue="2026-11-07" />
    </Modal>
  );
}

function ConfirmHarness({ onClose }: { onClose: () => void }) {
  return (
    <Modal
      open
      title="Delete this transaction?"
      onClose={onClose}
      footer={
        <button type="button" onClick={onClose}>
          Delete transaction
        </button>
      }
    >
      <p>This cannot be undone.</p>
    </Modal>
  );
}

describe("Modal focus management", () => {
  it("focuses the first text field when a form dialog opens", () => {
    render(<Harness />);
    expect(screen.getByLabelText("Name")).toHaveFocus();
  });

  it("skips selects, read-only inputs and checkboxes to reach a usable field", () => {
    render(<FormHarness />);
    expect(screen.getByLabelText("Amount")).toHaveFocus();
  });

  it("selects the saved value of the first field so typing replaces it", () => {
    render(<EditHarness />);
    const amount = screen.getByLabelText("Amount") as HTMLInputElement;
    expect(amount).toHaveFocus();
    expect(amount.selectionStart).toBe(0);
    expect(amount.selectionEnd).toBe("12.50".length);
  });

  it("leaves a collapsed caret in an empty add dialog", () => {
    render(<Harness />);
    const name = screen.getByLabelText("Name") as HTMLInputElement;
    expect(name).toHaveFocus();
    expect(name.selectionStart).toBe(0);
    expect(name.selectionEnd).toBe(0);
  });

  it("focuses a date field without failing when it cannot be selected", () => {
    render(<DateFirstHarness />);
    const date = screen.getByLabelText("Date") as HTMLInputElement;
    expect(date).toHaveFocus();
    expect(date.value).toBe("2026-11-07");
  });

  it("keeps focus on the dialog itself when there is no text field", () => {
    render(<ConfirmHarness onClose={() => {}} />);
    expect(screen.getByRole("dialog")).toHaveFocus();
  });

  it("keeps focus in the input when the owning page re-renders", () => {
    render(<Harness />);
    const name = screen.getByLabelText("Name") as HTMLInputElement;

    name.focus();
    expect(name).toHaveFocus();

    fireEvent.change(name, { target: { value: "Coffee" } });
    expect(name).toHaveFocus();
  });

  it("keeps focus through every keystroke, including spaces, punctuation and /", () => {
    render(<Harness />);
    const notes = screen.getByLabelText("Notes") as HTMLInputElement;
    notes.focus();

    let typed = "";
    for (const char of "Coffee & tea / snacks 2.50") {
      typed += char;
      fireEvent.change(notes, { target: { value: typed } });
      expect(notes).toHaveFocus();
    }
    expect(notes.value).toBe("Coffee & tea / snacks 2.50");
  });

  it("keeps focus while text is edited with backspace and selection keys", () => {
    render(<Harness />);
    const name = screen.getByLabelText("Name") as HTMLInputElement;

    name.focus();
    fireEvent.change(name, { target: { value: "Groceries" } });
    fireEvent.keyDown(name, { key: "Backspace" });
    fireEvent.change(name, { target: { value: "Grocerie" } });
    fireEvent.keyDown(name, { key: "a", ctrlKey: true });
    fireEvent.keyDown(name, { key: "Home" });
    fireEvent.keyDown(name, { key: "End" });
    expect(name).toHaveFocus();
    expect(name.value).toBe("Grocerie");
  });

  it("does not swallow Ctrl+F or Cmd+F from an input", () => {
    render(<Harness />);
    const name = screen.getByLabelText("Name") as HTMLInputElement;
    name.focus();

    const ctrlF = fireEvent.keyDown(name, { key: "f", ctrlKey: true });
    const metaF = fireEvent.keyDown(name, { key: "f", metaKey: true });
    // fireEvent returns false when a handler called preventDefault().
    expect(ctrlF).toBe(true);
    expect(metaF).toBe(true);
    expect(name).toHaveFocus();
  });

  it("still closes on Escape", () => {
    const onClosed = vi.fn();
    render(<Harness onClosed={onClosed} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClosed).toHaveBeenCalledTimes(1);
  });

  it("does not call onClose when ordinary keys are pressed", () => {
    const onClosed = vi.fn();
    render(<Harness onClosed={onClosed} />);
    const notes = screen.getByLabelText("Notes") as HTMLInputElement;
    notes.focus();
    fireEvent.keyDown(notes, { key: "q" });
    fireEvent.keyDown(notes, { key: "/" });
    expect(onClosed).not.toHaveBeenCalled();
  });
});
