import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChartFrame, RangeSelector } from "./routeShared";

describe("shared UI route adapters", () => {
  it("keeps range state in the app while using shared pressed-button semantics", () => {
    const onChange = vi.fn();
    render(<RangeSelector value="1M" onChange={onChange} />);

    const selected = screen.getByRole("button", { name: "1M" });
    const next = screen.getByRole("button", { name: "1Y" });
    expect(selected).toHaveAttribute("aria-pressed", "true");
    expect(next).toHaveAttribute("aria-pressed", "false");

    fireEvent.keyDown(selected, { key: "ArrowRight" });
    expect(onChange).toHaveBeenCalledWith("1Y");
  });

  it("adapts dashboard headings, controls, content, and footnotes to ChartFrame", () => {
    render(
      <ChartFrame
        eyebrow="Performance"
        title="Portfolio return"
        detail="As of close"
        tools={<button type="button">Change range</button>}
      >
        <div>Chart content</div>
      </ChartFrame>,
    );

    expect(screen.getByText("Performance")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Portfolio return" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change range" })).toBeInTheDocument();
    expect(screen.getByText("Chart content")).toBeInTheDocument();
    expect(screen.getByText("As of close")).toBeInTheDocument();
  });
});
