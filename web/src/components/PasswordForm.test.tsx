import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PasswordForm } from "./PasswordForm";

// The Field hint is part of the label's accessible name, so match the start only.
const currentField = () => screen.getByLabelText(/^Current password/);
const nextField = () => screen.getByLabelText(/^New password/);
const confirmField = () => screen.getByLabelText(/^Confirm new password/);

function fill(values: { current?: string; next?: string; confirm?: string }) {
  fireEvent.change(currentField(), { target: { value: values.current ?? "OldPassword123" } });
  fireEvent.change(nextField(), { target: { value: values.next ?? "NewPassword456" } });
  fireEvent.change(confirmField(), { target: { value: values.confirm ?? "NewPassword456" } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
}

describe("PasswordForm", () => {
  it("refuses to submit when the two new entries differ", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<PasswordForm onSubmit={onSubmit} />);

    fill({ confirm: "SomethingElse789" });
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent("do not match");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("sends the current and new password, then clears the fields", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<PasswordForm onSubmit={onSubmit} />);

    fill({});
    submit();

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith("OldPassword123", "NewPassword456")
    );
    expect(await screen.findByText(/Other devices were signed out/)).toBeInTheDocument();
    // A secret must not linger in the DOM after a successful change.
    expect(currentField()).toHaveValue("");
    expect(nextField()).toHaveValue("");
    expect(confirmField()).toHaveValue("");
  });

  it("shows the server's reason when the current password is wrong", async () => {
    const onSubmit = vi
      .fn()
      .mockRejectedValue(new Error("Current password is incorrect."));
    render(<PasswordForm onSubmit={onSubmit} />);

    fill({});
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Current password is incorrect."
    );
    // The typed values survive a rejection, so the user does not retype everything.
    expect(currentField()).toHaveValue("OldPassword123");
  });

  it("keeps the button disabled until all three fields are filled", () => {
    render(<PasswordForm onSubmit={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Change password" })).toBeDisabled();

    fill({ confirm: "" });
    expect(screen.getByRole("button", { name: "Change password" })).toBeDisabled();

    fireEvent.change(confirmField(), { target: { value: "NewPassword456" } });
    expect(screen.getByRole("button", { name: "Change password" })).toBeEnabled();
  });
});
