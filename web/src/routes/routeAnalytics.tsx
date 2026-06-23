import type { ReactNode } from "react";
import { type BenchmarkAssociation, type BenchmarkDefaultResponse } from "../api";
import { money, num, number, percent } from "./routeFormatters";
import { BenchmarkPicker } from "./routePickers";
import { HelpDisclosure, Loading, MetricLine, Signal } from "./routeShared";
import type { HelpItem } from "./routeTypes";

const portfolioAnalyticsHelp: HelpItem[] = [
  { term: "Modified Dietz", detail: "A portfolio return estimate that adjusts for deposits and withdrawals, so cash movement does not distort performance as much." },
  { term: "Sharpe and Sortino", detail: "Risk-adjusted return scores. Higher is generally better; Sortino focuses more on harmful downside moves." },
  { term: "Max drawdown", detail: "The largest peak-to-trough loss in the period. It is a plain stress measure: how deep the worst slump was." },
  { term: "Monte Carlo", detail: "A probability simulation that creates many possible paths using expected return and volatility. Treat it as a range of outcomes, not a prediction." },
  { term: "Margin of safety", detail: "How far estimated fair value sits above the current price. Bigger positive margins imply more valuation cushion." },
];

const assetAnalyticsHelp: HelpItem[] = [
  { term: "Beta", detail: "How sensitive the stock is to the benchmark. A beta above 1 usually moves more than the market; below 1 usually moves less." },
  { term: "DCF", detail: "Discounted cash flow. It estimates fair value from future cash the company may produce, discounted back to today." },
  { term: "DDM", detail: "Dividend discount model. It estimates fair value from future dividends, so it matters most for dividend-paying companies." },
  { term: "Forecast band", detail: "A range of simulated outcomes. The 10th percentile is a rough bear case, the 90th percentile a rough bull case." },
  { term: "Quality", detail: "Profitability and balance-sheet clues, such as margins, return on equity, and debt/equity." },
];

const dataReadinessHelp: HelpItem[] = [
  { term: "Ready", detail: "The model has enough inputs to produce that section's analytics." },
  { term: "Missing inputs", detail: "Data the model wanted but could not find, such as price history, fundamentals, cash flow, or dividend data." },
  { term: "Weak", detail: "Some useful data exists, but the output may be thinner or less reliable than a fully populated model." },
];

export function DataIssueList({ items }: { items: string[] }) {
  return <div className="data-issues" role="status">{items.slice(0, 8).map((item) => <p key={item}>{item}</p>)}</div>;
}

export function AnalyticsPanel({
  payload,
  isLoading,
}: {
  payload?: Record<string, unknown>;
  isLoading: boolean;
}) {
  const report = payload?.report as AnyRecord | undefined;
  const performance = record(report?.performance);
  const risk = record(report?.risk);
  const decomposition = record(report?.risk_decomposition);
  const valuation = record(report?.valuation);
  const forecast = record(report?.forecast);
  const simulation = record(forecast?.simulation);
  const aiContext = record(payload?.ai_context);
  const anomalies = arrayOfRecords(aiContext?.anomalies);
  const volatilityContributions = arrayOfRecords(decomposition?.volatility_contributions).slice(0, 4);
  const valuationContributions = arrayOfRecords(valuation?.position_contributions).slice(0, 6);
  const healthItems: DataHealthItem[] = [
    {
      label: "DCF rollup",
      detail: "Holding intrinsic value and margin of safety",
      missing: missingList(valuation?.missing_inputs),
      ready: num(valuation?.weighted_margin_of_safety) != null || num(valuation?.weighted_pe_ratio) != null,
    },
    {
      label: "Monte Carlo",
      detail: "Projected value band and expected CAGR",
      missing: missingList(forecast?.missing_inputs),
      ready: num(simulation?.expected_value) != null,
    },
    {
      label: "Valuation models",
      detail: "Multiples, dividend yield, and holding-level forecasts",
      missing: uniqueStrings([
        ...missingList(valuation?.missing_inputs),
        ...missingList(forecast?.missing_inputs),
        ...missingList(performance?.missing_inputs),
      ]),
      ready: num(valuation?.weighted_expected_cagr) != null || num(valuation?.weighted_price_to_free_cash_flow) != null,
    },
  ];
  return <section className="card">
    <div className="card-heading">
      <div><p className="eyebrow">Phase 3 analytics</p><h2>Portfolio signals</h2></div>
      <div className="card-tools">
        <HelpDisclosure title="Portfolio analytics" items={portfolioAnalyticsHelp} note="These metrics are best used together. A high return with poor drawdown or weak data should still be treated cautiously." />
        <span>{payload?.schema_version as string ?? "loading"}</span>
      </div>
    </div>
    {isLoading ? <Loading compact /> : (
      <div className="analytics-stack">
        <div className="signal-grid deep">
          <Signal label="Modified Dietz" value={percent(num(performance?.modified_dietz_return))} />
          <Signal label="CAGR" value={percent(num(risk?.cagr))} />
          <Signal label="Volatility" value={percent(num(risk?.annualized_volatility))} />
          <Signal label="Sharpe" value={number(num(risk?.sharpe_ratio))} />
          <Signal label="Sortino" value={number(num(risk?.sortino_ratio))} />
          <Signal label="Max drawdown" value={percent(num(risk?.max_drawdown))} />
          <Signal label="Expected CAGR" value={percent(num(valuation?.weighted_expected_cagr))} />
          <Signal label="Dividend yield" value={percent(num(valuation?.weighted_dividend_yield))} />
        </div>
        <div className="analytics-detail-grid">
          <AnalyticsBlock title="Concentration">
            <MetricLine label="Largest holding" value={percent(num(decomposition?.largest_position_weight))} />
            <MetricLine label="Effective assets" value={number(num(decomposition?.effective_asset_count), 1)} />
            <MetricLine label="Diversification" value={number(num(decomposition?.diversification_score), 1)} />
            <MetricLine label="Average correlation" value={number(num(decomposition?.average_pairwise_correlation), 2)} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Exposure">
            <ExposureBars values={record(decomposition?.sector_exposure)} />
            <ExposureBars values={record(decomposition?.country_exposure)} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Risk contributors">
            {volatilityContributions.length ? volatilityContributions.map((item) => <MetricLine key={String(item.asset_id)} label={String(item.asset_id)} value={percent(num(item.percent_of_portfolio_volatility))} />) : <span className="muted-copy">No volatility contribution data yet.</span>}
          </AnalyticsBlock>
          <AnalyticsBlock title="Forecast">
            <MetricLine label="5y median" value={money(num(simulation?.p50_value))} />
            <MetricLine label="10th percentile" value={money(num(simulation?.p10_value))} />
            <MetricLine label="90th percentile" value={money(num(simulation?.p90_value))} />
            <MetricLine label="Blended CAGR" value={percent(num(forecast?.blended_expected_cagr))} />
          </AnalyticsBlock>
        </div>
        <div className="model-grid">
          <AnalyticsBlock title="Monte Carlo projection">
            <MetricLine label="Expected value" value={money(num(simulation?.expected_value))} />
            <MetricLine label="Expected CAGR" value={percent(num(simulation?.expected_cagr))} />
            <MetricLine label="Bear CAGR" value={percent(num(simulation?.p10_cagr))} />
            <MetricLine label="Bull CAGR" value={percent(num(simulation?.p90_cagr))} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Valuation rollup">
            <MetricLine label="Expected CAGR" value={percent(num(valuation?.weighted_expected_cagr))} />
            <MetricLine label="Dividend yield" value={percent(num(valuation?.weighted_dividend_yield))} />
            <MetricLine label="Margin of safety" value={num(valuation?.weighted_margin_of_safety) == null ? "Needs DCF inputs" : percent(num(valuation?.weighted_margin_of_safety))} />
            <MetricLine label="Valuation mix" value={valuationMixLabel(valuation)} />
          </AnalyticsBlock>
        </div>
        <DataHealthPanel items={healthItems} />
        {valuationContributions.length ? <div className="model-table"><table><thead><tr><th>Holding</th><th>Weight</th><th>Expected CAGR</th><th>Margin</th><th>P/E</th><th>P/FCF</th></tr></thead><tbody>{valuationContributions.map((item) => <tr key={String(item.asset_id)}><td>{String(item.asset_id)}</td><td>{percent(num(item.weight))}</td><td>{percent(num(item.expected_cagr))}</td><td>{percent(num(item.margin_of_safety))}</td><td>{number(num(item.pe_ratio))}</td><td>{number(num(item.price_to_free_cash_flow))}</td></tr>)}</tbody></table></div> : null}
        {anomalies.length ? <InsightList items={anomalies.map((item) => `${String(item.severity).toUpperCase()}: ${String(item.message)}`)} /> : null}
      </div>
    )}
  </section>;
}
export function AssetAnalyticsPanel({
  payload,
  isLoading,
  benchmark,
  onBenchmarkChange,
  defaultBenchmark,
  associations,
}: {
  payload?: Record<string, unknown>;
  isLoading: boolean;
  benchmark: string;
  onBenchmarkChange: (value: string) => void;
  defaultBenchmark?: BenchmarkDefaultResponse;
  associations?: BenchmarkAssociation[];
}) {
  const report = payload?.report as AnyRecord | undefined;
  const risk = record(report?.risk);
  const relative = record(report?.relative);
  const valuation = record(report?.valuation_depth);
  const dividend = record(report?.dividend_discount);
  const dcf = record(report?.discounted_cash_flow);
  const forecast = record(report?.forecast);
  const simulation = record(forecast?.simulation);
  const dcfInputs = record(dcf?.inputs_used);
  const dividendInputs = record(dividend?.inputs_used);
  const dcfScenarios = arrayOfRecords(valuation?.dcf_scenarios);
  const aiContext = record(payload?.ai_context);
  const anomalies = arrayOfRecords(aiContext?.anomalies);
  const healthItems: DataHealthItem[] = [
    {
      label: "DCF",
      detail: "Intrinsic value per share and margin of safety",
      missing: missingList(dcf?.missing_inputs),
      ready: num(dcf?.intrinsic_value_per_share) != null,
    },
    {
      label: "Monte Carlo",
      detail: "Forecast range from expected return and volatility",
      missing: missingList(forecast?.missing_inputs),
      ready: num(simulation?.expected_value) != null,
    },
    {
      label: "Valuation models",
      detail: "Fundamental ratios, DCF scenarios, and growth assumptions",
      missing: uniqueStrings([
        ...missingList(valuation?.missing_inputs),
        ...missingList(forecast?.missing_inputs),
        ...missingList(dividend?.missing_inputs),
      ]),
      ready: num(valuation?.pe_ratio) != null || dcfScenarios.some((item) => num(item.intrinsic_value_per_share) != null),
    },
  ];
  return <section className="card asset-analytics-card">
    <div className="card-heading">
      <div><p className="eyebrow">Phase 3 analytics</p><h2>Asset signals</h2></div>
      <div className="card-tools">
        <HelpDisclosure title="Asset analytics" items={assetAnalyticsHelp} note="Fair value models are sensitive to assumptions. Treat them as structured estimates, then compare against the business story and risk." />
        <BenchmarkPicker value={benchmark} onChange={onBenchmarkChange} defaultBenchmark={defaultBenchmark} associations={associations} />
        <span>{payload?.schema_version as string ?? "loading"}</span>
      </div>
    </div>
    {isLoading ? <Loading compact /> : (
      <div className="analytics-stack">
        <div className="signal-grid deep">
          <Signal label="Historical CAGR" value={percent(num(risk?.cagr))} />
          <Signal label="Volatility" value={percent(num(risk?.annualized_volatility))} />
          <Signal label="Sharpe" value={number(num(risk?.sharpe_ratio))} />
          <Signal label="Sortino" value={number(num(risk?.sortino_ratio))} />
          <Signal label="Max drawdown" value={percent(num(risk?.max_drawdown))} />
          <Signal label="Beta" value={number(num(relative?.beta))} />
          <Signal label="P/E" value={number(num(valuation?.pe_ratio))} />
          <Signal label="Blended CAGR" value={percent(num(forecast?.blended_expected_cagr))} />
        </div>
        <div className="analytics-detail-grid">
          <AnalyticsBlock title="Risk profile">
            <MetricLine label="Best day" value={percent(num(risk?.best_daily_return))} />
            <MetricLine label="Worst day" value={percent(num(risk?.worst_daily_return))} />
            <MetricLine label="Alpha" value={percent(num(relative?.alpha_annualized))} />
            <MetricLine label="Correlation" value={number(num(relative?.correlation), 2)} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Valuation">
            <MetricLine label="DCF fair value" value={money(num(dcf?.intrinsic_value_per_share))} />
            <MetricLine label="DCF safety" value={percent(num(dcf?.margin_of_safety))} />
            <MetricLine label="DDM fair value" value={money(num(dividend?.intrinsic_value_per_share))} />
            <MetricLine label="P/FCF" value={number(num(valuation?.price_to_free_cash_flow))} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Quality">
            <MetricLine label="Gross margin" value={percent(num(valuation?.gross_margin))} />
            <MetricLine label="Net margin" value={percent(num(valuation?.net_margin))} />
            <MetricLine label="ROE" value={percent(num(valuation?.return_on_equity))} />
            <MetricLine label="Debt/equity" value={number(num(valuation?.debt_to_equity))} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Forecast band">
            <MetricLine label="5y median" value={money(num(simulation?.p50_value))} />
            <MetricLine label="10th percentile" value={money(num(simulation?.p10_value))} />
            <MetricLine label="90th percentile" value={money(num(simulation?.p90_value))} />
            <MetricLine label="Expected value" value={money(num(simulation?.expected_value))} />
          </AnalyticsBlock>
        </div>
        <div className="model-grid">
          <AnalyticsBlock title="DCF model">
            <MetricLine label="Cash flow/share" value={money(num(dcfInputs?.cashflow_per_share))} />
            <MetricLine label="Discount rate" value={percent(num(dcfInputs?.discount_rate))} />
            <MetricLine label="Growth rate" value={percent(num(dcfInputs?.growth_rate))} />
            <MetricLine label="Terminal growth" value={percent(num(dcfInputs?.terminal_growth_rate))} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Dividend model">
            <MetricLine label="DDM fair value" value={money(num(dividend?.intrinsic_value_per_share))} />
            <MetricLine label="Annual dividend" value={money(num(dividendInputs?.annual_dividend))} />
            <MetricLine label="Implied growth" value={percent(num(dividend?.implied_growth_rate))} />
            <MetricLine label="Dividend growth" value={percent(num(forecast?.dividend_growth_projection))} />
          </AnalyticsBlock>
          <AnalyticsBlock title="Monte Carlo projection">
            <MetricLine label="Expected CAGR" value={percent(num(simulation?.expected_cagr))} />
            <MetricLine label="Bear CAGR" value={percent(num(simulation?.p10_cagr))} />
            <MetricLine label="Median CAGR" value={percent(num(simulation?.p50_cagr))} />
            <MetricLine label="Bull CAGR" value={percent(num(simulation?.p90_cagr))} />
          </AnalyticsBlock>
        </div>
        <DataHealthPanel items={healthItems} />
        {dcfScenarios.length ? <div className="model-table"><table><thead><tr><th>DCF scenario</th><th>Fair value</th><th>Margin</th><th>Growth</th><th>Discount</th><th>Terminal</th></tr></thead><tbody>{dcfScenarios.map((item) => <tr key={String(item.scenario_name)}><td>{String(item.scenario_name)}</td><td>{money(num(item.intrinsic_value_per_share))}</td><td>{percent(num(item.margin_of_safety))}</td><td>{percent(num(item.growth_rate))}</td><td>{percent(num(item.discount_rate))}</td><td>{percent(num(item.terminal_growth_rate))}</td></tr>)}</tbody></table></div> : null}
        {anomalies.length ? <InsightList items={anomalies.map((item) => `${String(item.severity).toUpperCase()}: ${String(item.message)}`)} /> : null}
      </div>
    )}
  </section>;
}
type AnyRecord = Record<string, unknown>;
type DataHealthItem = {
  label: string;
  detail: string;
  missing: string[];
  ready: boolean;
};
const valuationMixLabel = (valuation: AnyRecord) => {
  const undervalued = num(valuation?.undervalued_weight);
  const fair = num(valuation?.fair_value_weight);
  const overvalued = num(valuation?.overvalued_weight);
  const total = (undervalued ?? 0) + (fair ?? 0) + (overvalued ?? 0);
  if (!total) return "Needs DCF inputs";
  return `${percent(undervalued)} under / ${percent(fair)} fair / ${percent(overvalued)} over`;
};
function record(value: unknown): AnyRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as AnyRecord : {};
}
function arrayOfRecords(value: unknown): AnyRecord[] {
  return Array.isArray(value) ? value.filter((item): item is AnyRecord => Boolean(item) && typeof item === "object" && !Array.isArray(item)) : [];
}
function missingList(value: unknown): string[] {
  return Array.isArray(value) ? uniqueStrings(value.map((item) => String(item)).filter(Boolean)) : [];
}
function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.map((item) => item.trim()).filter(Boolean)));
}
function DataHealthPanel({ items }: { items: DataHealthItem[] }) {
  return <div className="data-health-panel">
    <div className="data-health-heading">
      <div><p className="eyebrow">Analytics data health</p><strong>Model input readiness</strong></div>
      <div className="card-tools"><HelpDisclosure title="Model input readiness" items={dataReadinessHelp} /><span>{items.filter((item) => item.missing.length === 0 && item.ready).length}/{items.length} ready</span></div>
    </div>
    <div className="data-health-grid">
      {items.map((item) => {
        const status = item.missing.length ? "missing" : item.ready ? "ready" : "weak";
        return <article className={`data-health-card ${status}`} key={item.label}>
          <div><strong>{item.label}</strong><span className={`pill ${status === "ready" ? "done" : status === "missing" ? "failed" : "running"}`}>{status}</span></div>
          <p>{item.detail}</p>
          {item.missing.length ? <ul>{item.missing.map((missing) => <li key={missing}>{missing}</li>)}</ul> : <em>{item.ready ? "Required inputs are present." : "No explicit missing inputs, but output is still unavailable."}</em>}
        </article>;
      })}
    </div>
  </div>;
}
export function AnalyticsBlock({ title, children }: { title: string; children: ReactNode }) {
  return <div className="analytics-block"><strong>{title}</strong><div>{children}</div></div>;
}
export function ExposureBars({ values }: { values: AnyRecord }) {
  const entries = Object.entries(values)
    .map(([label, value]) => ({ label, value: num(value) ?? 0 }))
    .filter((item) => item.value > 0)
    .sort((left, right) => right.value - left.value)
    .slice(0, 4);
  if (!entries.length) return <span className="muted-copy">No exposure data yet.</span>;
  return <div className="exposure-bars">{entries.map((item) => <div key={item.label}><p><span>{item.label}</span><b>{percent(item.value)}</b></p><div className="bar"><span style={{ width: `${Math.max(item.value * 100, 2)}%` }} /></div></div>)}</div>;
}
function InsightList({ items }: { items: string[] }) {
  return <div className="analytics-insights">{items.slice(0, 3).map((item) => <p key={item}>{item}</p>)}</div>;
}
