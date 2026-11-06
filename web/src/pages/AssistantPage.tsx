import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { AssistantAnswer } from "../lib/types";
import {
  Badge,
  Button,
  Card,
  ErrorBanner,
  Input,
  PageHeader,
} from "../components/ui";

const EXAMPLES = [
  "How much can I safely spend?",
  "What bills are due this week?",
  "How much will I have after payday?",
  "Can I afford $150 on Clothing?",
  "Which subscriptions am I paying for?",
  "Where am I spending too much?",
];

export function AssistantPage() {
  const queryClient = useQueryClient();
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<AssistantAnswer[]>([]);
  const [error, setError] = useState<string | null>(null);

  const statusQuery = useQuery({ queryKey: ["assistant-status"], queryFn: api.assistant.status });

  const ask = useMutation({
    mutationFn: (q: string) => api.assistant.ask(q),
    onSuccess: (answer) => {
      setHistory((previous) => [answer, ...previous]);
      setError(null);
      setQuestion("");
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not answer that."),
  });

  const consent = useMutation({
    mutationFn: api.assistant.consent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assistant-status"] });
    },
  });

  const submit = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || ask.isPending) return;
    setError(null);
    ask.mutate(trimmed);
  };

  const status = statusQuery.data;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Assistant"
        title="Ask about your money"
        description="Answers come from the same deterministic engine that powers Safe-to-Spend and your bills. The assistant explains figures; it cannot move money or change your data."
      />

      {error ? <ErrorBanner message={error} onRetry={() => setError(null)} /> : null}

      {status ? (
        <Card>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <Badge tone={status.mode === "model" ? "info" : "neutral"}>
              {status.mode === "model" ? `Model: ${status.model}` : "Deterministic engine"}
            </Badge>
            <span className="tiny muted">{status.note}</span>
          </div>
          {status.consent_required ? (
            <div className="page-stack" style={{ gap: "0.5rem", marginTop: "0.75rem" }}>
              <p className="tiny">
                A language model is configured. Sending it your figures requires your consent —
                only the structured results of your financial tools are sent, never raw
                transaction history, and never your credentials.
              </p>
              <div>
                <Button
                  size="sm"
                  loading={consent.isPending}
                  onClick={() => consent.mutate(true)}
                >
                  Allow AI explanations
                </Button>
              </div>
            </div>
          ) : null}
          {status.ai_consent ? (
            <div style={{ marginTop: "0.75rem" }}>
              <Button size="sm" variant="ghost" onClick={() => consent.mutate(false)}>
                Revoke AI data sharing
              </Button>
            </div>
          ) : null}
        </Card>
      ) : null}

      <Card>
        <form
          className="list-row"
          style={{ gap: "0.5rem" }}
          onSubmit={(event) => {
            event.preventDefault();
            submit(question);
          }}
        >
          <Input
            value={question}
            maxLength={400}
            placeholder="e.g. Can I afford $150 on Clothing?"
            onChange={(event) => setQuestion(event.target.value)}
            aria-label="Your question"
          />
          <Button type="submit" loading={ask.isPending}>
            Ask
          </Button>
        </form>
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
          {EXAMPLES.map((example) => (
            <Button
              key={example}
              type="button"
              size="sm"
              variant="ghost"
              disabled={ask.isPending}
              onClick={() => submit(example)}
            >
              {example}
            </Button>
          ))}
        </div>
      </Card>

      {history.length === 0 ? (
        <Card>
          <p className="tiny muted">
            Ask a question above, or pick one of the examples. Every answer lists the tools it
            used so you can check the figures yourself.
          </p>
        </Card>
      ) : null}

      {history.map((answer, index) => (
        <Card key={`${answer.question}-${index}`}>
          <div className="tiny muted" style={{ marginBottom: "0.35rem" }}>
            You asked: “{answer.question}”
          </div>
          <p>{answer.answer}</p>
          {answer.note ? <p className="tiny muted">{answer.note}</p> : null}
          <div className="tiny muted mono" style={{ marginTop: "0.5rem" }}>
            {answer.mode} · tools: {answer.used_tools.join(", ") || "none"}
          </div>
          <p className="tiny muted" style={{ marginTop: "0.35rem" }}>
            {answer.disclaimer}
          </p>
        </Card>
      ))}
    </div>
  );
}
