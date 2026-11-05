import { useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import type { Account, ImportJob, ImportPreview, UploadResponse } from "../lib/types";
import { formatMoney } from "../lib/format";
import { Badge, Button, Field, Select } from "./ui";

const MAPPING_FIELDS: { key: string; label: string; hint?: string }[] = [
  { key: "date", label: "Date", hint: "Required" },
  { key: "description", label: "Description", hint: "Required" },
  { key: "amount", label: "Amount", hint: "Signed where possible" },
  { key: "debit", label: "Debit (money out)" },
  { key: "credit", label: "Credit (money in)" },
  { key: "merchant", label: "Merchant" },
  { key: "type", label: "Type" },
  { key: "category", label: "Category name" },
  { key: "external_id", label: "External ID" },
];

type Step = "upload" | "map" | "done";

export function ImportWizard({
  accounts,
  history,
  onClose,
  onImported,
}: {
  accounts: Account[];
  history: ImportJob[];
  onClose: () => void;
  onImported: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? "");
  const [step, setStep] = useState<Step>("upload");
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [result, setResult] = useState<{
    imported: number;
    duplicates: number;
    rejected: number;
    matched_bills?: number;
  } | null>(null);

  const headers = upload?.headers ?? preview?.headers ?? [];
  const canPreview = mapping.date && mapping.description && (mapping.amount || mapping.debit || mapping.credit);

  const summary = preview?.summary;
  const activeAccounts = useMemo(() => accounts.filter((a) => !a.is_archived), [accounts]);

  const handleFile = async (file: File) => {
    if (!accountId) {
      setError("Choose the account this CSV belongs to first.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const response = await api.imports.upload(file, accountId);
      setUpload(response);
      setMapping(response.suggested_mapping);
      setPreview(response.preview);
      setStep("map");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to read that file.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const refreshPreview = async () => {
    if (!upload) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.imports.preview(upload.import.id, mapping);
      setPreview(next);
    } catch (err) {
      setPreview(null);
      setError(err instanceof Error ? err.message : "Unable to preview with this mapping.");
    } finally {
      setBusy(false);
    }
  };

  const commit = async () => {
    if (!upload) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.imports.commit(upload.import.id, mapping);
      setResult(next);
      setStep("done");
      onImported();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed. Nothing was committed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-stack">
      {step === "upload" ? (
        <>
          <Field label="Import into account" htmlFor="import-account">
            <Select
              id="import-account"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            >
              {activeAccounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </Select>
          </Field>

          <label
            className="dropzone"
            onDragOver={(event) => {
              event.preventDefault();
              event.currentTarget.classList.add("is-dragging");
            }}
            onDragLeave={(event) => event.currentTarget.classList.remove("is-dragging")}
            onDrop={(event) => {
              event.preventDefault();
              event.currentTarget.classList.remove("is-dragging");
              const file = event.dataTransfer.files?.[0];
              if (file) void handleFile(file);
            }}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleFile(file);
              }}
            />
            <strong>{uploading ? "Reading file…" : "Choose a CSV or drop it here"}</strong>
            <p className="small muted" style={{ marginTop: "0.3rem" }}>
              Up to 5 MB / 5,000 rows. You will always see a preview before anything is saved.
            </p>
          </label>

          {history.length ? (
            <div>
              <p className="eyebrow">Recent imports</p>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Status</th>
                      <th className="is-right">Imported</th>
                      <th className="is-right">Skipped</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.slice(0, 5).map((job) => (
                      <tr key={job.id}>
                        <td>
                          <div className="cell-title">
                            <strong>{job.filename}</strong>
                            <span>
                              {new Date(job.created_at).toLocaleString("en-US", {
                                dateStyle: "medium",
                                timeStyle: "short",
                              })}
                            </span>
                          </div>
                        </td>
                        <td>
                          <Badge tone={job.status === "committed" ? "positive" : "neutral"}>
                            {job.status}
                          </Badge>
                        </td>
                        <td className="is-right mono">{job.imported_count}</td>
                        <td className="is-right mono">
                          {job.duplicate_count + job.rejected_count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </>
      ) : null}

      {step === "map" && upload ? (
        <>
          <div className="summary-strip">
            <span>
              File <strong>{upload.import.filename}</strong>
            </span>
            <span>
              Rows <strong>{summary?.total_rows ?? upload.import.row_count}</strong>
            </span>
            {summary ? (
              <>
                <span>
                  Ready <strong>{summary.ready}</strong>
                </span>
                <span>
                  Duplicates <strong>{summary.duplicates}</strong>
                </span>
                <span>
                  Invalid <strong>{summary.rejected}</strong>
                </span>
                <span>
                  Value <strong>{formatMoney(summary.ready_total)}</strong>
                </span>
              </>
            ) : null}
          </div>

          <div>
            <div className="section-heading">
              <h3 style={{ fontSize: "0.95rem" }}>Map your columns</h3>
              <Button size="sm" variant="secondary" onClick={() => void refreshPreview()} loading={busy}>
                Update preview
              </Button>
            </div>
            <div className="mapping-grid">
              {MAPPING_FIELDS.map((field) => (
                <Field key={field.key} label={field.label} hint={field.hint} htmlFor={`map-${field.key}`}>
                  <Select
                    id={`map-${field.key}`}
                    value={mapping[field.key] ?? ""}
                    onChange={(event) =>
                      setMapping({ ...mapping, [field.key]: event.target.value || null })
                    }
                  >
                    <option value="">Not mapped</option>
                    {headers.map((header) => (
                      <option key={header} value={header}>
                        {header}
                      </option>
                    ))}
                  </Select>
                </Field>
              ))}
            </div>
          </div>

          {!canPreview ? (
            <p className="small muted">
              Map a date, a description and an amount (or debit/credit columns) to continue.
            </p>
          ) : null}

          {preview ? (
            <div className="preview-table">
              <table className="data">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Date</th>
                    <th>Description</th>
                    <th>Type</th>
                    <th className="is-right">Amount</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.slice(0, 60).map((row) => (
                    <tr key={row.row_number}>
                      <td className="mono tiny muted">{row.row_number}</td>
                      <td className="mono tiny">{row.date ?? "—"}</td>
                      <td>
                        <div className="cell-title">
                          <strong>{row.description || "(empty)"}</strong>
                          <span>{row.merchant}</span>
                        </div>
                      </td>
                      <td className="tiny">{row.suggested_type}</td>
                      <td className="is-right mono">{row.amount ?? "—"}</td>
                      <td>
                        <Badge
                          tone={
                            row.status === "ok"
                              ? "positive"
                              : row.status === "duplicate"
                                ? "warning"
                                : "danger"
                          }
                        >
                          {row.status}
                        </Badge>
                        {row.reason ? (
                          <span className="tiny muted" style={{ display: "block", maxWidth: 210 }}>
                            {row.reason}
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {preview?.truncated ? (
            <p className="tiny muted">Showing the first 60 of {preview.summary.total_rows} rows.</p>
          ) : null}

          <div className="form-actions" style={{ justifyContent: "space-between" }}>
            <Button variant="ghost" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void commit()}
              loading={busy}
              disabled={!preview || !preview.summary.ready}
            >
              Import {preview?.summary.ready ?? 0} transactions
            </Button>
          </div>
        </>
      ) : null}

      {step === "done" && result ? (
        <div className="page-stack">
          <div className="card card--hero">
            <p className="eyebrow">Import complete</p>
            <p className="sts-amount">{result.imported}</p>
            <p className="sts-caption">transactions added to your ledger</p>
            <div className="sts-breakdown">
              <span>
                Duplicates skipped <strong>{result.duplicates}</strong>
              </span>
              <span>
                Invalid rows <strong>{result.rejected}</strong>
              </span>
              <span>
                Bills matched <strong>{result.matched_bills ?? 0}</strong>
              </span>
            </div>
          </div>
          <p className="small muted">
            Duplicates are detected by account, date, amount and description, so importing the same
            file twice is safe. Review suggested bill matches under Bills.
          </p>
          <div className="form-actions">
            <Button type="button" onClick={onClose}>
              Done
            </Button>
          </div>
        </div>
      ) : null}

      {error ? <div className="form-error" role="alert">{error}</div> : null}
    </div>
  );
}
