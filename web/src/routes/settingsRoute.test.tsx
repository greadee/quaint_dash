import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SettingsPage } from "./settingsRoute";
import type { AppSettings } from "./routeTypes";

const settings: AppSettings = {
  theme: "light",
  moverDefault: "8",
  density: "comfortable",
  featureColor: true,
};

describe("SettingsPage", () => {
  it("emits focused preference updates", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(<SettingsPage settings={settings} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Compact" }));
    await user.selectOptions(screen.getByLabelText(/Default holdings shown/i), "all");

    expect(onChange).toHaveBeenCalledWith({ density: "compact" });
    expect(onChange).toHaveBeenCalledWith({ moverDefault: "all" });
  });
});
