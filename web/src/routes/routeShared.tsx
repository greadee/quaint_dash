import { AlertTriangle, ArrowLeft, ArrowRight, BarChart3, Info, LineChart, RefreshCw, SearchX } from "lucide-react";
import type { ReactNode } from "react";
import type { HelpItem } from "./routeTypes";

export function HelpDisclosure({ title, items, note }: { title: string; items: HelpItem[]; note?: string }) {
  return (
    <details className="info-popover">
      <summary aria-label={`${"Explain " + title}`}>
        <Info size={15} />
      </summary>
      <div className="info-panel">
        <strong>{title}</strong>
        <dl>
          {items.map((item) => (
            <div key={item.term}>
              <dt>{item.term}</dt>
              <dd>{item.detail}</dd>
            </div>
          ))}
        </dl>
        {note ? <p>{note}</p> : null}
      </div>
    </details>
  );
}

export function Metric({ icon, label, value, detail, positive }: { icon: ReactNode; label: string; value: string; detail?: string; positive?: boolean }) {
  const tone = positive == null ? "" : positive ? " positive" : " negative";
  return <article className={`metric card${tone}`}><div className="metric-icon">{icon}</div><p>{label}</p><strong>{value}</strong>{detail && <span>{detail}</span>}</article>;
}

export function Loading({ compact = false }: { compact?: boolean }) {
  return <div className={compact ? "loading compact" : "loading"} role="status" aria-live="polite"><RefreshCw /><span>Loading dashboard data</span></div>;
}

export function ErrorPanel({ error }: { error: Error }) {
  return <div className="error-panel" role="alert"><AlertTriangle size={20} /><strong>Unable to load data</strong><span>{error.message}</span></div>;
}

export function EmptyRow({ text }: { text: string }) {
  return <div className="empty-row"><SearchX size={18} /><span>{text}</span></div>;
}

export function MetricLine({ label, value }: { label: string; value: string }) {
  return <p className="metric-line"><span>{label}</span><b>{value}</b></p>;
}

export function Signal({ label, value }: { label: string; value: string }) {
  return <div className="signal"><span>{label}</span><strong>{value}</strong></div>;
}

export function TabBar<T extends string>({ tabs, selected, onSelect, label }: { tabs: { value: T; label: string }[]; selected: T; onSelect: (value: T) => void; label: string }) {
  return <div className="tab-bar" role="tablist" aria-label={label}>{tabs.map((tab) => <button role="tab" aria-selected={selected === tab.value} className={selected === tab.value ? "active" : ""} onClick={() => onSelect(tab.value)} key={tab.value}>{tab.label}</button>)}</div>;
}

export function RangeSelector({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <div className="segmented-control" aria-label="Performance range">{["1D", "1W", "1M", "1Y", "YTD", "5Y"].map((item) => <button key={item} className={value.toUpperCase() === item ? "active" : ""} onClick={() => onChange(item)}>{item}</button>)}</div>;
}

export function ChartTypeToggle({ value, onChange }: { value: "line" | "bar"; onChange: (value: "line" | "bar") => void }) {
  return <div className="segmented-control compact" aria-label="Chart type">
    <button className={value === "line" ? "active" : ""} onClick={() => onChange("line")} title="Line chart"><LineChart size={14} /><span>Line</span></button>
    <button className={value === "bar" ? "active" : ""} onClick={() => onChange("bar")} title="Bar chart"><BarChart3 size={14} /><span>Bar</span></button>
  </div>;
}

export function Pager({ total, limit, offset, onChange }: { total: number; limit: number; offset: number; onChange: (offset: number) => void }) {
  const nextOffset = offset + limit;
  const previousOffset = Math.max(offset - limit, 0);
  const start = total ? offset + 1 : 0;
  const end = Math.min(offset + limit, total);
  return <div className="pager">
    <span>{start}-{end} of {total}</span>
    <div className="actions">
      <button onClick={() => onChange(previousOffset)} disabled={offset <= 0}><ArrowLeft size={14} />Previous</button>
      <button onClick={() => onChange(nextOffset)} disabled={nextOffset >= total}>Next<ArrowRight size={14} /></button>
    </div>
  </div>;
}
