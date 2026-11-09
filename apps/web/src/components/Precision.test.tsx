import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { PrecisionResult, VariableInputs } from "./Precision";
import type { GenerationResponse } from "@promptengine/shared-types";

describe("precision workflow", () => {
  it("submits selected answers and unresolved variables without copying or inserting", async () => {
    const apply = vi.fn().mockResolvedValue(undefined);
    const result = {
      generation_id: "g",
      prompt: "Build {{name}}",
      quality_score: 70,
      raw_quality_score: 20,
      detected_variables: ["name"],
      clarification_questions: [
        { id: "stack", question: "Which stack?", suggested_options: ["Flask"] },
      ],
    } as GenerationResponse;
    render(<PrecisionResult result={result} busy={false} apply={apply} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Flask" }));
    await user.type(screen.getByLabelText("name"), "Portal");
    await user.click(screen.getByRole("button", { name: "Apply & Sharpen" }));
    expect(apply).toHaveBeenCalledWith({ stack: "Flask" }, { name: "Portal" });
    expect(screen.getByRole("progressbar")).toHaveAttribute("value", "70");
  });
  it("detects defaulted variables before generation", () => {
    render(
      <VariableInputs
        text="For {{audience:engineers}} and {{audience}}"
        values={{}}
        setValues={vi.fn()}
      />,
    );
    expect(screen.getAllByLabelText("audience")).toHaveLength(1);
  });
});
