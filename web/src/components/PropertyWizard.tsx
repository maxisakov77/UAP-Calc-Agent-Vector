"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  clearPropertyContext,
  getBlockLots,
  getPropertyContext,
  searchPropertyAddress,
  setPropertyContext,
  validatePropertyLot,
  type BlockLotInfo,
  type PropertyContext,
  type PropertySearchResult,
} from "@/lib/api";

function parseBbl(bbl: string) {
  const digits = String(bbl || "").replace(/\D/g, "");
  if (digits.length !== 10) return null;
  return {
    borough: Number.parseInt(digits[0], 10),
    block: Number.parseInt(digits.slice(1, 6), 10),
    lot: Number.parseInt(digits.slice(6), 10),
    prefix: digits.slice(0, 6),
  };
}

function fmtCurrency(value: number | null | undefined) {
  if (!value) return "N/A";
  return `$${value.toLocaleString()}`;
}

export default function PropertyWizard({
  refreshKey,
  onPropertyChange,
}: {
  refreshKey?: number;
  onPropertyChange?: (context: PropertyContext | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PropertySearchResult[]>([]);
  const [activeContext, setActiveContextState] = useState<PropertyContext | null>(null);
  const [availableLots, setAvailableLots] = useState<BlockLotInfo[]>([]);
  const [lotInput, setLotInput] = useState("");
  const [searching, setSearching] = useState(false);
  const [loadingContext, setLoadingContext] = useState(true);
  const [loadingLots, setLoadingLots] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState("");
  const [autoFilled, setAutoFilled] = useState<{ address: string; bbl: string } | null>(null);
  const debounceRef = useRef<number | null>(null);
  const autoFillTimerRef = useRef<number | null>(null);

  function setActiveContext(next: PropertyContext | null) {
    setActiveContextState(next);
    onPropertyChange?.(next);
  }

  async function loadActiveContext() {
    setLoadingContext(true);
    try {
      const context = await getPropertyContext();
      setActiveContext(context);
      setError("");
    } catch (err) {
      setActiveContext(null);
      setError(err instanceof Error ? err.message : "Failed to load property context");
    } finally {
      setLoadingContext(false);
    }
  }

  useEffect(() => {
    setQuery("");
    setResults([]);
    setLotInput("");
    setError("");
    void loadActiveContext();
  }, [refreshKey]);

  useEffect(() => {
    if (!activeContext) {
      setAvailableLots([]);
      return;
    }
    const parsed = parseBbl(activeContext.primary_bbl);
    if (!parsed) return;
    let cancelled = false;
    setLoadingLots(true);
    void getBlockLots(parsed.borough, parsed.block)
      .then((lots) => {
        if (!cancelled) setAvailableLots(lots);
      })
      .catch(() => {
        if (!cancelled) setAvailableLots([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingLots(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeContext]);

  async function runSearch(value: string) {
    const trimmed = value.trim();
    if (!trimmed) {
      setResults([]);
      return;
    }
    setSearching(true);
    try {
      const nextResults = await searchPropertyAddress(trimmed);
      setResults(nextResults);
      setError(nextResults.length === 0 ? "No results. Try a full NYC address or 10-digit BBL." : "");
      if (nextResults.length === 1) {
        await applyProperty(nextResults[0].bbl, []);
        setAutoFilled({ address: nextResults[0].address || "Unknown", bbl: nextResults[0].bbl });
        if (autoFillTimerRef.current) window.clearTimeout(autoFillTimerRef.current);
        autoFillTimerRef.current = window.setTimeout(() => setAutoFilled(null), 6000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Property search failed");
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    if (query.trim().length < 4) {
      setResults([]);
      return;
    }
    debounceRef.current = window.setTimeout(() => {
      void runSearch(query);
    }, 450);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [query]);

  async function applyProperty(primaryBbl: string, adjacentBbls: string[]) {
    setUpdating(true);
    try {
      const context = await setPropertyContext(primaryBbl, adjacentBbls);
      setActiveContext(context);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update property context");
    } finally {
      setUpdating(false);
    }
  }

  async function handleSelect(result: PropertySearchResult) {
    await applyProperty(result.bbl, []);
  }

  async function handleClear() {
    setUpdating(true);
    try {
      await clearPropertyContext();
      setActiveContext(null);
      setResults([]);
      setQuery("");
      setLotInput("");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear property context");
    } finally {
      setUpdating(false);
    }
  }

  async function handleRefresh() {
    if (!activeContext) return;
    await applyProperty(activeContext.primary_bbl, activeContext.adjacent_bbls);
  }

  async function addAdjacentLotFromNumber(rawValue: string) {
    if (!activeContext) return;
    const parsed = parseBbl(activeContext.primary_bbl);
    if (!parsed) return;
    const cleaned = rawValue.replace(/\D/g, "");
    if (!cleaned) {
      setError("Enter a valid adjacent lot number.");
      return;
    }
    const fullBbl = `${parsed.prefix}${cleaned.padStart(4, "0")}`;
    try {
      await validatePropertyLot(fullBbl);
      if (fullBbl === activeContext.primary_bbl || activeContext.adjacent_bbls.includes(fullBbl)) {
        setError("That lot is already included.");
        return;
      }
      await applyProperty(activeContext.primary_bbl, [...activeContext.adjacent_bbls, fullBbl]);
      setLotInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Adjacent lot validation failed");
    }
  }

  async function addAdjacentLotFromSuggestion(info: BlockLotInfo) {
    if (!activeContext) return;
    const parsed = parseBbl(activeContext.primary_bbl);
    if (!parsed) return;
    const fullBbl = `${parsed.prefix}${String(info.lot).padStart(4, "0")}`;
    if (fullBbl === activeContext.primary_bbl || activeContext.adjacent_bbls.includes(fullBbl)) return;
    await applyProperty(activeContext.primary_bbl, [...activeContext.adjacent_bbls, fullBbl]);
  }

  async function removeAdjacentLot(bbl: string) {
    if (!activeContext) return;
    await applyProperty(
      activeContext.primary_bbl,
      activeContext.adjacent_bbls.filter((item) => item !== bbl),
    );
  }

  const suggestions = useMemo(() => {
    if (!activeContext) return [];
    const parsed = parseBbl(activeContext.primary_bbl);
    if (!parsed) return [];
    const selected = new Set(activeContext.selected_bbls);
    return availableLots.filter((item) => {
      const fullBbl = `${parsed.prefix}${String(item.lot).padStart(4, "0")}`;
      return !selected.has(fullBbl);
    });
  }, [activeContext, availableLots]);

  const candidateScenarios = activeContext?.scenarios ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div>
        <h2
          style={{
            margin: 0,
            fontSize: 14,
            fontWeight: 600,
            color: "var(--blue-accent)",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          Property
        </h2>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--brand-granite-gray)" }}>
          Search NYC address or BBL, add same-block lots, and feed live site data into the agents.
        </p>
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void runSearch(query);
            }
          }}
          placeholder="Search address or BBL"
          style={{
            flex: 1,
            padding: "8px 10px",
            background: "var(--bg-elevated)",
            border: "1px solid var(--border-color)",
            color: "var(--foreground)",
            fontSize: 13,
            outline: "none",
          }}
        />
        <button
          onClick={() => void runSearch(query)}
          disabled={searching || !query.trim()}
          style={{
            padding: "8px 12px",
            background: searching ? "var(--bg-elevated)" : "var(--blue)",
            border: "1px solid var(--border-color)",
            color: "var(--foreground)",
            cursor: searching ? "not-allowed" : "pointer",
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          {searching ? "..." : "Search"}
        </button>
      </div>

      {autoFilled && (
        <div
          style={{
            margin: 0,
            fontSize: 12,
            color: "#34d399",
            padding: "6px 8px",
            background: "rgba(52,211,153,0.1)",
            border: "1px solid rgba(52,211,153,0.25)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
          }}
        >
          <span>Auto-filled: <strong>{autoFilled.address}</strong> (BBL {autoFilled.bbl})</span>
          <button
            onClick={() => setAutoFilled(null)}
            style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", padding: 0, fontSize: 14, lineHeight: 1 }}
          >
            ×
          </button>
        </div>
      )}

      {error && (
        <p
          style={{
            margin: 0,
            fontSize: 12,
            color: "#e55",
            padding: "6px 8px",
            background: "rgba(238,85,85,0.1)",
            border: "1px solid rgba(238,85,85,0.2)",
          }}
        >
          {error}
        </p>
      )}

      {results.length > 1 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 180, overflowY: "auto" }}>
          {results.map((result) => (
            <button
              key={result.bbl}
              onClick={() => void handleSelect(result)}
              style={{
                textAlign: "left",
                padding: "8px 10px",
                background: "var(--bg-card)",
                border: "1px solid var(--glass-border)",
                color: "var(--foreground)",
                cursor: "pointer",
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 600 }}>{result.address || "Unknown"}, {result.borough}</div>
              <div style={{ fontSize: 11, color: "var(--brand-granite-gray)" }}>
                BBL {result.bbl} · {result.zone || "No zone"} · {result.lotArea.toLocaleString()} SF
              </div>
            </button>
          ))}
        </div>
      )}

      {loadingContext ? (
        <p style={{ margin: 0, fontSize: 12, color: "var(--brand-granite-gray)" }}>Loading active property context...</p>
      ) : activeContext ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: 10, background: "var(--bg-card)", border: "1px solid var(--glass-border)" }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--foreground)" }}>
              {activeContext.address || "Unknown address"}
            </div>
            <div style={{ fontSize: 11, color: "var(--brand-granite-gray)", lineHeight: 1.5 }}>
              {activeContext.borough} · BBL {activeContext.primary_bbl} · Zone {activeContext.zoning_district || "N/A"} · {activeContext.lot_area.toLocaleString()} SF lot area
              <span style={{ display: "inline-block", marginLeft: 4, width: 7, height: 7, borderRadius: "50%", background: "#14b8a6", verticalAlign: "middle" }} title="PLUTO" />
            </div>
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, fontSize: 10, color: "var(--brand-granite-gray)" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "#14b8a6", display: "inline-block" }} /> PLUTO</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "#f59e0b", display: "inline-block" }} /> DOF</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "#a78bfa", display: "inline-block" }} /> Zoning Ref</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "#3b82f6", display: "inline-block" }} /> Calculated</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "#ef4444", display: "inline-block" }} /> ACRIS</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><span style={{ width: 7, height: 7, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} /> Documents</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 11 }}>
            <Metric label="Standard FAR" value={activeContext.standard_far?.toFixed(2) ?? "N/A"} source="zoning" />
            <Metric label="UAP / QAH FAR" value={activeContext.qah_far?.toFixed(2) ?? "N/A"} source="zoning" />
            <Metric label="Mkt Value" value={fmtCurrency(activeContext.market_value)} source="dof" />
            <Metric label="Taxable" value={fmtCurrency(activeContext.dof_taxable)} source="dof" />
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {activeContext.selected_bbls.map((bbl) => {
              const isPrimary = bbl === activeContext.primary_bbl;
              return (
                <span
                  key={bbl}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "4px 8px",
                    background: isPrimary ? "rgba(59,130,246,0.12)" : "var(--bg-elevated)",
                    border: isPrimary ? "1px solid rgba(59,130,246,0.25)" : "1px solid var(--border-color)",
                    fontSize: 11,
                    color: isPrimary ? "var(--blue-light)" : "var(--foreground)",
                  }}
                >
                  {isPrimary ? "Primary" : "Adj."} {bbl}
                  {!isPrimary && (
                    <button
                      onClick={() => void removeAdjacentLot(bbl)}
                      style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", padding: 0 }}
                    >
                      x
                    </button>
                  )}
                </span>
              );
            })}
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="text"
              value={lotInput}
              onChange={(e) => setLotInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void addAdjacentLotFromNumber(lotInput);
                }
              }}
              placeholder="Add same-block lot #"
              style={{
                flex: 1,
                padding: "8px 10px",
                background: "var(--bg-elevated)",
                border: "1px solid var(--border-color)",
                color: "var(--foreground)",
                fontSize: 12,
                outline: "none",
              }}
            />
            <button
              onClick={() => void addAdjacentLotFromNumber(lotInput)}
              disabled={updating || !lotInput.trim()}
              style={{
                padding: "8px 12px",
                background: updating ? "var(--bg-elevated)" : "transparent",
                border: "1px solid var(--border-color)",
                color: "var(--foreground)",
                cursor: updating ? "not-allowed" : "pointer",
                fontSize: 12,
              }}
            >
              Add Lot
            </button>
          </div>

          {loadingLots ? (
            <p style={{ margin: 0, fontSize: 11, color: "var(--brand-granite-gray)" }}>Loading lots on this block...</p>
          ) : suggestions.length > 0 ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {suggestions.slice(0, 10).map((item) => (
                <button
                  key={item.lot}
                  onClick={() => void addAdjacentLotFromSuggestion(item)}
                  style={{
                    padding: "4px 8px",
                    background: "transparent",
                    border: "1px solid var(--border-color)",
                    color: "var(--brand-granite-gray)",
                    cursor: "pointer",
                    fontSize: 11,
                  }}
                  title={`${item.address || "No address"} · ${item.zone || "No zone"} · ${item.lotArea.toLocaleString()} SF`}
                >
                  + Lot {String(item.lot).padStart(4, "0")}
                </button>
              ))}
            </div>
          ) : null}

          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={() => void handleRefresh()}
              disabled={updating}
              style={{
                flex: 1,
                padding: "8px 10px",
                background: updating ? "var(--bg-elevated)" : "var(--blue)",
                border: "1px solid var(--border-color)",
                color: "var(--foreground)",
                cursor: updating ? "not-allowed" : "pointer",
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              {updating ? "Updating..." : "Refresh Property Data"}
            </button>
            <button
              onClick={() => void handleClear()}
              disabled={updating}
              style={{
                padding: "8px 10px",
                background: "transparent",
                border: "1px solid var(--border-color)",
                color: "var(--brand-granite-gray)",
                cursor: updating ? "not-allowed" : "pointer",
                fontSize: 12,
              }}
            >
              Clear
            </button>
          </div>

          {candidateScenarios.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 600, color: "var(--blue-accent)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                Scenario Candidates
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#3b82f6", display: "inline-block" }} title="Calculated" />
              </div>
              {candidateScenarios.map((scenario) => (
                <div
                  key={scenario.code}
                  style={{
                    padding: "8px 10px",
                    background: "var(--bg-elevated)",
                    border: "1px solid var(--border-color)",
                    fontSize: 11,
                    color: "var(--foreground)",
                  }}
                >
                  <div style={{ fontWeight: 600 }}>{scenario.label}</div>
                  <div style={{ color: "var(--brand-granite-gray)", lineHeight: 1.5 }}>
                    {scenario.max_res_floor_area.toLocaleString()} SF · {scenario.max_number_of_units} units · {scenario.affordable_units_total} affordable · {scenario.market_rate_units} market
                  </div>
                </div>
              ))}
            </div>
          )}

          {activeContext.acris_summary && activeContext.acris_summary.documents.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 600, color: "#ef4444", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                ACRIS Transactions
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#ef4444", display: "inline-block" }} title="ACRIS" />
              </div>
              {activeContext.acris_summary.last_deed_date && (
                <div style={{ padding: "8px 10px", background: "var(--bg-elevated)", border: "1px solid var(--border-color)", borderLeft: "3px solid #ef4444", fontSize: 11 }}>
                  <div style={{ fontWeight: 600, color: "var(--foreground)" }}>Last Deed</div>
                  <div style={{ color: "var(--brand-granite-gray)", lineHeight: 1.5 }}>
                    {activeContext.acris_summary.last_deed_date?.slice(0, 10)}
                    {activeContext.acris_summary.last_deed_amount ? ` · ${fmtCurrency(activeContext.acris_summary.last_deed_amount)}` : ""}
                  </div>
                  {activeContext.acris_summary.last_deed_seller && (
                    <div style={{ color: "var(--brand-granite-gray)", lineHeight: 1.5 }}>
                      {activeContext.acris_summary.last_deed_seller} → {activeContext.acris_summary.last_deed_buyer}
                    </div>
                  )}
                </div>
              )}
              {activeContext.acris_summary.total_mortgage_amount ? (
                <Metric label="Total Mortgages" value={fmtCurrency(activeContext.acris_summary.total_mortgage_amount)} source="acris" />
              ) : null}
              <div style={{ fontSize: 10, color: "var(--brand-granite-gray)" }}>
                {activeContext.acris_summary.documents.length} document{activeContext.acris_summary.documents.length !== 1 ? "s" : ""} from ACRIS
              </div>
            </div>
          )}
        </div>
      ) : (
        <p style={{ margin: 0, fontSize: 12, color: "var(--brand-granite-gray)" }}>
          No active property context yet. Search an NYC address or BBL to feed live site data into the agent.
        </p>
      )}
    </div>
  );
}

const SOURCE_COLORS: Record<string, string> = {
  pluto: "#14b8a6",
  dof: "#f59e0b",
  zoning: "#a78bfa",
  calc: "#3b82f6",
  acris: "#ef4444",
};

function Metric({ label, value, source }: { label: string; value: string; source?: keyof typeof SOURCE_COLORS }) {
  const dotColor = source ? SOURCE_COLORS[source] : undefined;
  return (
    <div style={{ padding: "6px 8px", background: "var(--bg-elevated)", border: "1px solid var(--border-color)", borderLeft: dotColor ? `3px solid ${dotColor}` : undefined }}>
      <div style={{ color: "var(--brand-granite-gray)", marginBottom: 2 }}>{label}</div>
      <div style={{ color: "var(--foreground)", fontWeight: 600 }}>{value}</div>
    </div>
  );
}
