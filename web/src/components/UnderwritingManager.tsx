"use client";

import { useState, useRef } from "react";
import {
  parseUnderwritingTemplate,
  extractUnderwritingValues,
  downloadFilledTemplate,
  type ParsedTemplate,
} from "@/lib/api";

function colToLetter(col: number): string {
  let s = "";
  let c = col;
  while (c > 0) {
    c--;
    s = String.fromCharCode(65 + (c % 26)) + s;
    c = Math.floor(c / 26);
  }
  return s;
}

export default function UnderwritingManager() {
  const [template, setTemplate] = useState<ParsedTemplate | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [edits, setEdits] = useState<Record<string, Record<string, string | number>>>({});
  const [aiCells, setAiCells] = useState<Record<string, Set<string>>>({});
  const [uploading, setUploading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const parsed = await parseUnderwritingTemplate(file);
      setTemplate(parsed);
      setEdits({});
      setAiCells({});
      setActiveTab(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  function getCellRef(row: number, col: number): string {
    return `${colToLetter(col)}${row}`;
  }

  function handleCellChange(sheetName: string, row: number, col: number, raw: string) {
    const ref = getCellRef(row, col);
    const val: string | number = raw === "" ? "" : isNaN(Number(raw)) ? raw : Number(raw);
    setEdits((prev) => ({
      ...prev,
      [sheetName]: { ...(prev[sheetName] || {}), [ref]: val },
    }));
  }

  async function handleExtract() {
    setExtracting(true);
    setError("");
    try {
      const result = await extractUnderwritingValues();
      if (result.message) {
        setError(result.message);
        return;
      }
      const newAi: Record<string, Set<string>> = {};
      setEdits((prev) => {
        const merged = { ...prev };
        for (const [sheet, cells] of Object.entries(result.updates)) {
          merged[sheet] = { ...(merged[sheet] || {}), ...cells };
          newAi[sheet] = new Set(Object.keys(cells));
        }
        return merged;
      });
      setAiCells(newAi);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed");
    } finally {
      setExtracting(false);
    }
  }

  async function handleDownload() {
    setError("");
    try {
      const blob = await downloadFilledTemplate(edits);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = template?.filename?.replace(/\.xlsx?$/i, "_filled.xlsx") || "filled.xlsx";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    }
  }

  /* ── No template uploaded yet ── */
  if (!template) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 16,
          padding: 40,
          color: "var(--foreground)",
        }}
      >
        <div style={{ fontSize: 48, opacity: 0.3 }}>📊</div>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: "var(--blue-accent)" }}>
          Underwriting Template
        </h2>
        <p
          style={{
            margin: 0,
            fontSize: 13,
            color: "var(--brand-granite-gray)",
            textAlign: "center",
            maxWidth: 420,
            lineHeight: 1.5,
          }}
        >
          Upload a UAP underwriting Excel template to parse its structure, then
          use <strong>Auto-Fill</strong> to extract values from your uploaded
          documents via RAG.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".xlsx,.xls"
          onChange={handleUpload}
          style={{ display: "none" }}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          style={{
            padding: "10px 24px",
            background: "var(--blue)",
            border: "1px solid var(--border-color)",
            color: "var(--foreground)",
            cursor: uploading ? "not-allowed" : "pointer",
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          {uploading ? "Parsing…" : "Upload Excel Template"}
        </button>
        {error && <p style={{ fontSize: 12, color: "#e55" }}>{error}</p>}
      </div>
    );
  }

  /* ── Template loaded — tabbed grid view ── */
  const sheet = template.sheets[activeTab];
  const sheetEdits = edits[sheet.name] || {};
  const sheetAi = aiCells[sheet.name] || new Set<string>();

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
      {/* Action bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 16px",
          borderBottom: "1px solid var(--border-color)",
          background: "var(--bg-dark)",
          flexShrink: 0,
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontSize: 13, color: "var(--brand-granite-gray)" }}>
          📊 {template.filename}
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xls"
            onChange={handleUpload}
            style={{ display: "none" }}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            style={{
              padding: "6px 12px",
              background: "none",
              border: "1px solid var(--border-color)",
              color: "var(--foreground)",
              cursor: "pointer",
              fontSize: 12,
            }}
          >
            Re-upload
          </button>
          <button
            onClick={handleExtract}
            disabled={extracting}
            style={{
              padding: "6px 14px",
              background: extracting ? "var(--bg-elevated)" : "rgba(59,130,246,0.2)",
              border: "1px solid rgba(59,130,246,0.4)",
              color: "var(--blue-light)",
              cursor: extracting ? "not-allowed" : "pointer",
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            {extracting ? "Extracting…" : "⚡ Auto-Fill from Docs"}
          </button>
          <button
            onClick={handleDownload}
            style={{
              padding: "6px 14px",
              background: "rgba(34,197,94,0.15)",
              border: "1px solid rgba(34,197,94,0.4)",
              color: "#4ade80",
              cursor: "pointer",
              fontSize: 12,
              fontWeight: 600,
            }}
          >
            ⬇ Download .xlsx
          </button>
        </div>
      </div>

      {/* Sheet tabs */}
      <div
        style={{
          display: "flex",
          gap: 0,
          borderBottom: "1px solid var(--border-color)",
          background: "var(--bg-dark)",
          overflowX: "auto",
          flexShrink: 0,
        }}
      >
        {template.sheets.map((s, i) => (
          <button
            key={i}
            onClick={() => setActiveTab(i)}
            style={{
              padding: "8px 14px",
              background: i === activeTab ? "var(--bg-main)" : "transparent",
              border: "none",
              borderBottom:
                i === activeTab
                  ? "2px solid var(--blue-accent)"
                  : "2px solid transparent",
              color:
                i === activeTab
                  ? "var(--blue-accent)"
                  : "var(--brand-granite-gray)",
              cursor: "pointer",
              fontSize: 12,
              fontWeight: i === activeTab ? 600 : 400,
              whiteSpace: "nowrap",
            }}
          >
            {s.name.length > 22 ? s.name.slice(0, 22) + "…" : s.name}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            padding: "8px 16px",
            fontSize: 12,
            color: "#e55",
            background: "rgba(238,85,85,0.1)",
            borderBottom: "1px solid rgba(238,85,85,0.2)",
          }}
        >
          {error}
        </div>
      )}

      {/* Spreadsheet grid */}
      <div style={{ flex: 1, overflow: "auto", padding: 0 }}>
        <table
          style={{
            borderCollapse: "collapse",
            fontSize: 12,
            minWidth: "100%",
          }}
        >
          <tbody>
            {sheet.data.map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => {
                  if (cell === null) {
                    return (
                      <td
                        key={ci}
                        style={{
                          padding: "4px 8px",
                          border: "1px solid var(--glass-border)",
                          minWidth: 40,
                        }}
                      />
                    );
                  }

                  const ref = getCellRef(cell.r, cell.c);
                  const isFormula = !!cell.f;
                  const edit = sheetEdits[ref];
                  const isAi = sheetAi.has(ref);
                  const displayVal = edit !== undefined ? edit : cell.v;
                  const isLabel =
                    typeof cell.v === "string" && isNaN(Number(cell.v));

                  let bg = "transparent";
                  if (isFormula) bg = "rgba(255,255,255,0.03)";
                  else if (isAi && edit !== undefined) bg = "rgba(59,130,246,0.1)";
                  else if (edit !== undefined) bg = "rgba(34,197,94,0.08)";

                  return (
                    <td
                      key={ci}
                      style={{
                        padding: 0,
                        border: "1px solid var(--glass-border)",
                        background: bg,
                        minWidth: isLabel ? 140 : 80,
                        maxWidth: 220,
                      }}
                    >
                      {isFormula ? (
                        <span
                          style={{
                            display: "block",
                            padding: "4px 8px",
                            color: "var(--brand-granite-gray)",
                            fontSize: 11,
                            textAlign:
                              typeof displayVal === "number" ? "right" : "left",
                          }}
                        >
                          {typeof displayVal === "number"
                            ? displayVal.toLocaleString(undefined, {
                                maximumFractionDigits: 2,
                              })
                            : String(displayVal ?? "")}
                        </span>
                      ) : (
                        <input
                          value={String(displayVal ?? "")}
                          onChange={(e) =>
                            handleCellChange(
                              sheet.name,
                              cell.r,
                              cell.c,
                              e.target.value,
                            )
                          }
                          style={{
                            width: "100%",
                            background: "transparent",
                            border: "none",
                            color: isLabel
                              ? "var(--foreground)"
                              : "var(--blue-light)",
                            padding: "4px 8px",
                            fontSize: 12,
                            fontWeight: isLabel ? 600 : 400,
                            textAlign:
                              typeof displayVal === "number" ? "right" : "left",
                            outline: "none",
                            boxSizing: "border-box",
                          }}
                        />
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer stats */}
      <div
        style={{
          padding: "8px 16px",
          borderTop: "1px solid var(--border-color)",
          background: "var(--bg-dark)",
          display: "flex",
          gap: 16,
          fontSize: 11,
          color: "var(--brand-granite-gray)",
          flexShrink: 0,
        }}
      >
        <span>
          {sheet.maxRow} rows × {sheet.maxCol} cols
        </span>
        <span>{Object.keys(sheetEdits).length} edits</span>
        {sheetAi.size > 0 && <span>{sheetAi.size} AI-filled</span>}
      </div>
    </div>
  );
}
