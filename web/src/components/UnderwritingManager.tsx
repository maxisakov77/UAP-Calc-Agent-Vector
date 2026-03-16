"use client";

import { useEffect, useRef, useState } from "react";
import {
  downloadFilledTemplate,
  extractUnderwritingValues,
  parseUnderwritingTemplate,
  type ParsedTemplate,
  type TemplateCell,
  type TemplateSheet,
} from "@/lib/api";

type CellValue = string | number | boolean | null;

type ActiveCell = {
  sheetName: string;
  row: number;
  col: number;
  ref: string;
};

const ROW_HEADER_WIDTH = 56;
const NUMERIC_COLUMN_WIDTH = 112;
const DEFAULT_COLUMN_WIDTH = 140;
const TEXT_HEAVY_COLUMN_WIDTH = 220;

const moneySignalPattern =
  /(?:\$|\b(?:rent|cost|expense|revenue|income|tax|fee|loan|equity|debt|price|sale|purchase|budget|noi|value)\b)/i;
const percentSignalPattern =
  /(?:%|\b(?:percent|rate|yield|margin|irr|ltv|cap)\b)/i;

const numberFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 2,
});

const currencyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const percentFormatter = new Intl.NumberFormat(undefined, {
  style: "percent",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
});

function colToLetter(col: number): string {
  let value = col;
  let label = "";

  while (value > 0) {
    value -= 1;
    label = String.fromCharCode(65 + (value % 26)) + label;
    value = Math.floor(value / 26);
  }

  return label;
}

function getCellRef(row: number, col: number): string {
  return `${colToLetter(col)}${row}`;
}

function normalizeInputValue(value: string): string | number {
  const trimmed = value.trim();
  if (trimmed === "") return "";
  return Number.isNaN(Number(trimmed)) ? value : Number(trimmed);
}

function getResolvedCellValue(
  cell: TemplateCell | null,
  sheetEdits: Record<string, string | number>,
): CellValue {
  if (!cell) return null;
  const ref = getCellRef(cell.r, cell.c);
  return sheetEdits[ref] !== undefined ? sheetEdits[ref] : cell.v;
}

function toInputValue(value: CellValue): string {
  return value === null ? "" : String(value);
}

function isNumericString(value: string): boolean {
  const trimmed = value.trim();
  return trimmed !== "" && !Number.isNaN(Number(trimmed));
}

function isDateLikeString(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed || /^\d+$/.test(trimmed)) {
    return false;
  }
  if (!(/[/-]/.test(trimmed) || /[A-Za-z]{3,}/.test(trimmed))) {
    return false;
  }
  return !Number.isNaN(Date.parse(trimmed));
}

function isLabelValue(value: CellValue): value is string {
  return (
    typeof value === "string" &&
    value.trim() !== "" &&
    !isNumericString(value) &&
    !isDateLikeString(value)
  );
}

function buildRowSignalText(
  row: (TemplateCell | null)[],
  sheetEdits: Record<string, string | number>,
): string {
  return row
    .map((cell) => {
      const value = getResolvedCellValue(cell, sheetEdits);
      if (typeof value !== "string") return "";

      const trimmed = value.trim();
      if (!trimmed) return "";
      if (!isLabelValue(trimmed) && !/[%$]/.test(trimmed)) return "";

      return trimmed.toLowerCase();
    })
    .filter(Boolean)
    .join(" ");
}

function getCellSignalText(
  row: (TemplateCell | null)[],
  colIndex: number,
  rowSignal: string,
  sheetEdits: Record<string, string | number>,
): string {
  for (let index = colIndex - 1; index >= 0; index--) {
    const candidate = getResolvedCellValue(row[index] ?? null, sheetEdits);
    if (typeof candidate !== "string") {
      continue;
    }

    const trimmed = candidate.trim();
    if (!trimmed) {
      continue;
    }

    if (isLabelValue(trimmed) || /[%$]/.test(trimmed)) {
      return trimmed.toLowerCase();
    }
  }

  return rowSignal;
}

function formatPercentValue(value: number): string {
  const normalized = Math.abs(value) <= 1 ? value : value / 100;
  return percentFormatter.format(normalized);
}

function formatDisplayValue(value: CellValue, rowSignal: string): string {
  if (value === null) return "";
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";

  if (typeof value === "number") {
    if (percentSignalPattern.test(rowSignal)) {
      return formatPercentValue(value);
    }
    if (moneySignalPattern.test(rowSignal)) {
      return currencyFormatter.format(value);
    }
    return numberFormatter.format(value);
  }

  if (isDateLikeString(value)) {
    return dateFormatter.format(new Date(value));
  }

  return value;
}

function getColumnWidth(
  sheet: TemplateSheet,
  sheetEdits: Record<string, string | number>,
  colIndex: number,
): number {
  let numericCount = 0;
  let nonEmptyCount = 0;
  let maxLabelLength = 0;

  for (let rowIndex = 0; rowIndex < sheet.maxRow; rowIndex++) {
    const cell = sheet.data[rowIndex]?.[colIndex] ?? null;
    const value = getResolvedCellValue(cell, sheetEdits);

    if (value === null || value === "") {
      continue;
    }

    nonEmptyCount += 1;

    if (typeof value === "number") {
      numericCount += 1;
      continue;
    }

    if (typeof value === "string") {
      if (isNumericString(value)) {
        numericCount += 1;
        continue;
      }

      if (isLabelValue(value)) {
        maxLabelLength = Math.max(maxLabelLength, value.trim().length);
      }
    }
  }

  if (maxLabelLength >= 24) {
    return TEXT_HEAVY_COLUMN_WIDTH;
  }

  if (
    nonEmptyCount > 0 &&
    numericCount / nonEmptyCount >= 0.6 &&
    maxLabelLength < 16
  ) {
    return NUMERIC_COLUMN_WIDTH;
  }

  return DEFAULT_COLUMN_WIDTH;
}

function findAdjacentEditableCell(
  sheet: TemplateSheet,
  activeCell: ActiveCell,
  direction: 1 | -1,
): ActiveCell | null {
  if (direction === 1) {
    for (let row = activeCell.row; row <= sheet.maxRow; row++) {
      const startCol = row === activeCell.row ? activeCell.col + 1 : 1;
      for (let col = startCol; col <= sheet.maxCol; col++) {
        const candidate = sheet.data[row - 1]?.[col - 1] ?? null;
        if (candidate && !candidate.f) {
          return { sheetName: sheet.name, row, col, ref: getCellRef(row, col) };
        }
      }
    }
    return null;
  }

  for (let row = activeCell.row; row >= 1; row--) {
    const startCol = row === activeCell.row ? activeCell.col - 1 : sheet.maxCol;
    for (let col = startCol; col >= 1; col--) {
      const candidate = sheet.data[row - 1]?.[col - 1] ?? null;
      if (candidate && !candidate.f) {
        return { sheetName: sheet.name, row, col, ref: getCellRef(row, col) };
      }
    }
  }

  return null;
}

export default function UnderwritingManager() {
  const [template, setTemplate] = useState<ParsedTemplate | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [edits, setEdits] = useState<Record<string, Record<string, string | number>>>({});
  const [aiCells, setAiCells] = useState<Record<string, Set<string>>>({});
  const [uploading, setUploading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState("");
  const [activeCell, setActiveCell] = useState<ActiveCell | null>(null);
  const [draftValue, setDraftValue] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const activeInputRef = useRef<HTMLInputElement>(null);
  const skipBlurCommitRef = useRef(false);

  useEffect(() => {
    if (!activeCell) return;
    activeInputRef.current?.focus();
    activeInputRef.current?.select();
  }, [activeCell]);

  function clearActiveCell() {
    setActiveCell(null);
    setDraftValue("");
  }

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setError("");
    clearActiveCell();

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

  function handleCellChange(sheetName: string, row: number, col: number, raw: string) {
    const ref = getCellRef(row, col);
    const value = normalizeInputValue(raw);

    setEdits((prev) => ({
      ...prev,
      [sheetName]: { ...(prev[sheetName] || {}), [ref]: value },
    }));
  }

  async function handleExtract() {
    setExtracting(true);
    setError("");
    clearActiveCell();

    try {
      const result = await extractUnderwritingValues();
      if (result.message) {
        setError(result.message);
        return;
      }

      const newAi: Record<string, Set<string>> = {};
      setEdits((prev) => {
        const merged = { ...prev };
        for (const [sheetName, cells] of Object.entries(result.updates)) {
          merged[sheetName] = { ...(merged[sheetName] || {}), ...cells };
          newAi[sheetName] = new Set(Object.keys(cells));
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
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download =
        template?.filename?.replace(/\.xlsx?$/i, "_filled.xlsx") || "filled.xlsx";
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    }
  }

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
        <h2
          style={{
            margin: 0,
            fontSize: 18,
            fontWeight: 600,
            color: "var(--blue-accent)",
          }}
        >
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
          Upload a UAP underwriting Excel template to parse its structure, then use{" "}
          <strong>Auto-Fill</strong> to extract values from your uploaded
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

  const sheet = template.sheets[activeTab];
  const sheetEdits = edits[sheet.name] || {};
  const sheetAi = aiCells[sheet.name] || new Set<string>();
  const rowSignals = sheet.data.map((row) => buildRowSignalText(row, sheetEdits));
  const columnWidths = Array.from({ length: sheet.maxCol }, (_, index) =>
    getColumnWidth(sheet, sheetEdits, index),
  );

  function getResolvedValueForCell(cell: TemplateCell | null): CellValue {
    return getResolvedCellValue(cell, sheetEdits);
  }

  function activateCell(cell: TemplateCell) {
    if (cell.f) return;

    const ref = getCellRef(cell.r, cell.c);
    const value = getResolvedValueForCell(cell);
    setActiveCell({ sheetName: sheet.name, row: cell.r, col: cell.c, ref });
    setDraftValue(toInputValue(value));
  }

  function openCellByPosition(nextCell: ActiveCell | null) {
    if (!nextCell) {
      clearActiveCell();
      return;
    }

    const nextTemplateCell = sheet.data[nextCell.row - 1]?.[nextCell.col - 1] ?? null;
    if (!nextTemplateCell) {
      clearActiveCell();
      return;
    }

    const value = getResolvedValueForCell(nextTemplateCell);
    setActiveCell(nextCell);
    setDraftValue(toInputValue(value));
  }

  function commitActiveCell(nextCell: ActiveCell | null = null) {
    if (!activeCell || activeCell.sheetName !== sheet.name) {
      clearActiveCell();
      return;
    }

    handleCellChange(activeCell.sheetName, activeCell.row, activeCell.col, draftValue);
    openCellByPosition(nextCell);
  }

  function handleActiveInputBlur() {
    if (skipBlurCommitRef.current) {
      skipBlurCommitRef.current = false;
      return;
    }

    commitActiveCell();
  }

  function handleActiveInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!activeCell) return;

    if (event.key === "Escape") {
      event.preventDefault();
      skipBlurCommitRef.current = true;
      clearActiveCell();
      return;
    }

    if (event.key === "Enter") {
      event.preventDefault();
      skipBlurCommitRef.current = true;
      commitActiveCell();
      return;
    }

    if (event.key === "Tab") {
      event.preventDefault();
      skipBlurCommitRef.current = true;
      const nextCell = findAdjacentEditableCell(
        sheet,
        activeCell,
        event.shiftKey ? -1 : 1,
      );
      commitActiveCell(nextCell);
    }
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
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
        {template.sheets.map((tabSheet, index) => (
          <button
            key={tabSheet.name}
            onClick={() => {
              clearActiveCell();
              setActiveTab(index);
            }}
            style={{
              padding: "8px 14px",
              background: index === activeTab ? "var(--bg-main)" : "transparent",
              border: "none",
              borderBottom:
                index === activeTab
                  ? "2px solid var(--blue-accent)"
                  : "2px solid transparent",
              color:
                index === activeTab
                  ? "var(--blue-accent)"
                  : "var(--brand-granite-gray)",
              cursor: "pointer",
              fontSize: 12,
              fontWeight: index === activeTab ? 600 : 400,
              whiteSpace: "nowrap",
            }}
          >
            {tabSheet.name.length > 22 ? `${tabSheet.name.slice(0, 22)}…` : tabSheet.name}
          </button>
        ))}
      </div>

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

      <div className="underwriting-grid-shell">
        <div className="underwriting-grid-scroll">
          <table className="underwriting-grid-table">
            <colgroup>
              <col style={{ width: ROW_HEADER_WIDTH }} />
              {columnWidths.map((width, index) => (
                <col key={colToLetter(index + 1)} style={{ width }} />
              ))}
            </colgroup>
            <thead>
              <tr>
                <th className="underwriting-grid-corner" />
                {columnWidths.map((_, index) => (
                  <th
                    key={colToLetter(index + 1)}
                    scope="col"
                    className="underwriting-grid-column-header"
                  >
                    {colToLetter(index + 1)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sheet.data.map((row, rowIndex) => {
                const rowSignal = rowSignals[rowIndex];

                return (
                  <tr key={rowIndex + 1}>
                    <th scope="row" className="underwriting-grid-row-header">
                      {rowIndex + 1}
                    </th>
                    {Array.from({ length: sheet.maxCol }, (_, colIndex) => {
                      const cell = row[colIndex] ?? null;

                      if (!cell) {
                        return (
                          <td
                            key={`${rowIndex + 1}-${colIndex + 1}`}
                            className="underwriting-grid-cell underwriting-grid-cell-empty"
                          >
                            <div className="underwriting-grid-cell-view" />
                          </td>
                        );
                      }

                      const ref = getCellRef(cell.r, cell.c);
                      const resolvedValue = getResolvedValueForCell(cell);
                      const isFormula = !!cell.f;
                      const hasEdit = sheetEdits[ref] !== undefined;
                      const isAi = sheetAi.has(ref);
                      const isActive =
                        activeCell?.sheetName === sheet.name &&
                        activeCell.row === cell.r &&
                        activeCell.col === cell.c;
                      const isLabel = isLabelValue(resolvedValue);
                      const isNumeric = typeof resolvedValue === "number";
                      const cellSignal = getCellSignalText(
                        row,
                        colIndex,
                        rowSignal,
                        sheetEdits,
                      );
                      const displayValue = formatDisplayValue(resolvedValue, cellSignal);
                      const className = [
                        "underwriting-grid-cell",
                        isFormula ? "underwriting-grid-cell-formula" : "",
                        isLabel ? "underwriting-grid-cell-label" : "",
                        isNumeric ? "underwriting-grid-cell-value" : "",
                        hasEdit ? "underwriting-grid-cell-edited" : "",
                        isAi ? "underwriting-grid-cell-ai" : "",
                        isActive ? "underwriting-grid-cell-active" : "",
                      ]
                        .filter(Boolean)
                        .join(" ");
                      const displayTitle =
                        typeof resolvedValue === "string"
                          ? resolvedValue
                          : displayValue || ref;

                      return (
                        <td key={ref} className={className}>
                          {isActive ? (
                            <input
                              ref={activeInputRef}
                              value={draftValue}
                              onChange={(event) => setDraftValue(event.target.value)}
                              onBlur={handleActiveInputBlur}
                              onKeyDown={handleActiveInputKeyDown}
                              className="underwriting-grid-input"
                              aria-label={`Edit cell ${ref}`}
                            />
                          ) : isFormula ? (
                            <div className="underwriting-grid-cell-view" title={displayTitle}>
                              {displayValue}
                            </div>
                          ) : (
                            <button
                              type="button"
                              className="underwriting-grid-button"
                              onClick={() => activateCell(cell)}
                              title={displayTitle}
                              aria-label={`Edit cell ${ref}`}
                            >
                              {displayValue}
                            </button>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

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
        {activeCell?.sheetName === sheet.name && <span>Active: {activeCell.ref}</span>}
      </div>
    </div>
  );
}
