import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AssetDetailPage } from "./assetRoute";

const apiMock = vi.hoisted(() => ({
  asset: vi.fn(),
  prices: vi.fn(),
  assetAnalytics: vi.fn(),
  assetActivity: vi.fn(),
}));

vi.mock("../api", () => ({ api: apiMock }));

vi.mock("recharts", () => {
  const passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: passthrough,
    BarChart: passthrough,
    Bar: passthrough,
    LineChart: passthrough,
    Line: passthrough,
    Tooltip: passthrough,
    XAxis: passthrough,
    YAxis: passthrough,
  };
});

function renderAsset(route = "/assets/NVDA") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/assets/:assetId" element={<AssetDetailPage notify={vi.fn()} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AssetDetailPage", () => {
  it("renders asset identity and stored price chart", async () => {
    apiMock.asset.mockResolvedValue({
      asset_id: "NVDA",
      symbol: "NVDA",
      name: "NVIDIA",
      sector: "Technology",
      latest_price: 120,
      currency: "USD",
    });
    apiMock.prices.mockResolvedValue([
      { date: "2026-06-18", close: 118 },
      { date: "2026-06-19", close: 120 },
    ]);
    apiMock.assetAnalytics.mockResolvedValue({});
    apiMock.assetActivity.mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 });

    renderAsset();

    expect(await screen.findByRole("heading", { level: 1, name: /NVDA/i })).toBeInTheDocument();
    expect(screen.getByText("Technology")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "NVDA price" })).toBeInTheDocument();
    expect(apiMock.prices).toHaveBeenCalledWith("NVDA", { range: "1Y" });
    expect(screen.getByRole("link", { name: /Compare/i })).toHaveAttribute("href", "/compare?symbols=NVDA");
  });
});
