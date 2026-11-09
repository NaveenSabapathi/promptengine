import { useState } from "react";
import type {
  GenerationResponse,
  TargetModel,
} from "@promptengine/shared-types";
export const targets: TargetModel[] = [
  "chatgpt-4o",
  "openai-reasoning",
  "claude-3-7-sonnet",
  "gemini-2-5-pro",
  "perplexity-search",
  "midjourney-v7",
  "video-gen",
];
export function PrecisionControls({
  target,
  setTarget,
  context,
  setContext,
}: {
  target: TargetModel;
  setTarget: (v: TargetModel) => void;
  context: string;
  setContext: (v: string) => void;
}) {
  return (
    <fieldset className="precision">
      <legend>Prompt precision</legend>
      <label>
        Target model
        <select
          value={target}
          onChange={(e) => setTarget(e.target.value as TargetModel)}
        >
          {targets.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
      </label>
      <label>
        Domain constraints
        <textarea
          value={context}
          maxLength={4000}
          onChange={(e) => setContext(e.target.value)}
          placeholder="Audience, boundaries, required output…"
        />
      </label>
    </fieldset>
  );
}
export function PrecisionResult({
  result,
  busy,
  apply,
}: {
  result: GenerationResponse;
  busy: boolean;
  apply: (
    answers: Record<string, string>,
    variables: Record<string, string>,
  ) => Promise<void>;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [variables, setVariables] = useState<Record<string, string>>({});
  return (
    <section className="precision" aria-label="Prompt precision diagnostics">
      {result.quality_score !== undefined && (
        <>
          <label>
            Prompt Precision: {result.quality_score}/100
            <progress max={100} value={result.quality_score} />
          </label>
          <p>
            Raw input: {result.raw_quality_score ?? "—"}/100. Structural
            heuristic; not a factual accuracy rating.
          </p>
        </>
      )}
      {!!result.redacted_entities_count && (
        <p>
          {result.redacted_entities_count} sensitive entities redacted before AI
          transmission.
        </p>
      )}
      {!!result.clarification_questions.length && <h3>Worth clarifying</h3>}
      {result.clarification_questions.map((q, i) => {
        const id = typeof q === "string" ? `question_${i}` : q.id;
        return (
          <fieldset key={id}>
            <legend>{typeof q === "string" ? q : q.question}</legend>
            {typeof q !== "string" &&
              q.suggested_options.map((option) => (
                <button
                  type="button"
                  key={option}
                  aria-pressed={answers[id] === option}
                  onClick={() => setAnswers((a) => ({ ...a, [id]: option }))}
                >
                  {option}
                </button>
              ))}
            <input
              aria-label={typeof q === "string" ? q : q.question}
              value={answers[id] || ""}
              maxLength={4000}
              onChange={(e) =>
                setAnswers((a) => ({ ...a, [id]: e.target.value }))
              }
            />
          </fieldset>
        );
      })}
      {(result.detected_variables || []).map((name) => (
        <label key={name}>
          {name}
          <input
            value={variables[name] || ""}
            maxLength={4000}
            onChange={(e) =>
              setVariables((v) => ({ ...v, [name]: e.target.value }))
            }
          />
        </label>
      ))}
      <button
        type="button"
        disabled={busy}
        onClick={() => void apply(answers, variables)}
      >
        {busy ? "Sharpening…" : "Apply & Sharpen"}
      </button>
    </section>
  );
}

export function VariableInputs({
  text,
  values,
  setValues,
}: {
  text: string;
  values: Record<string, string>;
  setValues: (values: Record<string, string>) => void;
}) {
  const names = [
    ...new Set(
      [
        ...text.matchAll(/\{\{([A-Za-z_][A-Za-z0-9_]{0,63})(?::[^{}]*)?\}\}/g),
      ].map((m) => m[1]),
    ),
  ];
  if (!names.length) return null;
  return (
    <fieldset className="precision">
      <legend>Template variables</legend>
      {names.map((name) => (
        <label key={name}>
          {name}
          <input
            value={values[name] || ""}
            maxLength={4000}
            onChange={(e) => setValues({ ...values, [name]: e.target.value })}
          />
        </label>
      ))}
    </fieldset>
  );
}
