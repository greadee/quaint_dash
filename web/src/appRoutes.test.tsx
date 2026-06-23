import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RouteErrorBoundary, SettingsPage, type AppSettings } from "./appRoutes";

const settings: AppSettings = {
  theme: "light",
  moverDefault: "8",
  density: "comfortable",
  featureColor: true,
};

function ThrowingRoute(): React.ReactElement {
  throw new Error("Route exploded");
}

describe("route modules", () => {
  it("renders SettingsPage without the App shell", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(<SettingsPage settings={settings} onChange={onChange} />);

    expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText(/Default holdings shown/i), "all");

    expect(onChange).toHaveBeenCalledWith({ moverDefault: "all" });
  });

  it("exports the route error boundary for isolated route tests", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(
      <RouteErrorBoundary>
        <ThrowingRoute />
      </RouteErrorBoundary>,
    );

    expect(screen.getByText("Unable to load data")).toBeInTheDocument();
    expect(screen.getByText("Route exploded")).toBeInTheDocument();
  });
});
