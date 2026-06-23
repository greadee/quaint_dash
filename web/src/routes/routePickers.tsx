import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type AssetSearchResult, type BenchmarkAssociation, type BenchmarkDefaultResponse } from "../api";

export function TickerPicker({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [search, setSearch] = useState("");
  const query = search.trim() || value.trim();
  const assets = useQuery({
    queryKey: ["asset-picker", query],
    queryFn: () => api.assets(query, 8),
    enabled: Boolean(query),
  });
  const selectAsset = (asset: AssetSearchResult) => {
    onChange(asset.asset_id);
    setSearch("");
  };
  return <div className="ticker-picker">
    <label>{label}<input value={value} onChange={(event) => onChange(event.target.value.toUpperCase())} placeholder="NVDA" /></label>
    <label>Find ticker<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search assets" /></label>
    {assets.data?.length ? <div className="ticker-picker-results">
      {assets.data.slice(0, 5).map((item) => (
        <button type="button" key={item.asset_id} onClick={() => selectAsset(item)}>
          <strong>{item.symbol}</strong>
          <span>{[item.name, item.sector, item.industry].filter(Boolean).join(" - ")}</span>
        </button>
      ))}
    </div> : null}
  </div>;
}

export function BenchmarkPicker({
  value,
  onChange,
  defaultBenchmark,
  associations,
}: {
  value: string;
  onChange: (value: string) => void;
  defaultBenchmark?: BenchmarkDefaultResponse;
  associations?: BenchmarkAssociation[];
}) {
  const [search, setSearch] = useState("");
  const benchmarks = useQuery({
    queryKey: ["benchmark-picker", search],
    queryFn: () => api.benchmarks({ q: search.trim() || undefined, limit: 8 }),
  });
  return <div className="benchmark-picker">
    <label>Benchmark<input value={value} onChange={(event) => onChange(event.target.value.toUpperCase())} placeholder={defaultBenchmark?.benchmark_index_id ?? "SP500"} /></label>
    <label>Find index<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search indexes" /></label>
    <div className="benchmark-picker-actions">
      {defaultBenchmark?.benchmark_index_id ? <button type="button" onClick={() => onChange(defaultBenchmark.benchmark_index_id ?? "")}>Use default</button> : null}
      {value ? <button type="button" onClick={() => onChange("")}>Clear</button> : null}
    </div>
    {associations?.length ? <div className="benchmark-associations">
      {associations.map((item) => (
        <button
          type="button"
          key={`${item.role}-${item.benchmark_index_id}`}
          className={value === item.benchmark_index_id ? "selected-row" : ""}
          onClick={() => onChange(item.benchmark_index_id)}
        >
          <strong>{item.role}</strong>
          <span>{item.benchmark_index_id}</span>
        </button>
      ))}
    </div> : null}
    {benchmarks.data?.length ? <div className="benchmark-picker-results">
      {benchmarks.data.slice(0, 5).map((item) => <button type="button" key={item.index_id} onClick={() => onChange(item.index_id)}><strong>{item.index_id}</strong><span>{item.index_name} - {item.currency}</span></button>)}
    </div> : null}
  </div>;
}
