"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import * as SSF from "ssf";
import {
  downloadFilledTemplate,
  extractUnderwritingValues,
  listDocuments,
  parseUnderwritingTemplate,
  recalculateUnderwritingFormulaValues,
  type DocumentInfo,
  type ParsedTemplate,
  type TemplateCell,
  type TemplateSheet,
  type UnderwritingRecalculationWarning,
} from "@/lib/api";

type CellValue = string | number | boolean | null;
type EditsBySheet = Record<string, Record<string, string | number>>;
type FormulaValuesBySheet = Record<string, Record<string, CellValue>>;
type AiSourceMap = Record<string, Record<string, string>>;
type AiConfidenceMap = Record<string, Record<string, string>>;

type ActiveCell = {
  sheetName: string;
  row: number;
  col: number;
  ref: string;
};

type AutofillEntry = {
  key: string;
  sheetName: string;
  row: number;
  col: number;
  ref: string;
  sourceName: string;
  confidence: string;
  locationLabel: string;
  coordinatesLabel: string;
  displayValue: string;
  rawValue: string;
  rawDiffersFromDisplay: boolean;
};

const ROW_HEADER_WIDTH = 56;
const NUMERIC_COLUMN_WIDTH = 112;
const DEFAULT_COLUMN_WIDTH = 140;
const LONG_NUMERIC_COLUMN_WIDTH = 196;
const TEXT_HEAVY_COLUMN_WIDTH = 220;

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

function letterToCol(label: string): number {
  let value = 0;
  for (const char of label.toUpperCase()) {
    value = value * 26 + (char.charCodeAt(0) - 64);
  }
  return value;
}

function parseCellRef(ref: string): { row: number; col: number } | null {
  const match = /^([A-Z]+)(\d+)$/i.exec(ref.trim());
  if (!match) {
    return null;
  }

  return {
    col: letterToCol(match[1]),
    row: Number(match[2]),
  };
}

function getAutofillKey(sheetName: string, ref: string): string {
  return `${sheetName}::${ref.toUpperCase()}`;
}

function normalizeInputValue(value: string): string | number {
  const trimmed = value.trim();
  if (trimmed === "") return "";
  return Number.isNaN(Number(trimmed)) ? value : Number(trimmed);
}

function getResolvedCellValue(
  cell: TemplateCell | null,
  sheetEdits: Record<string, string | number>,
  sheetFormulaValues?: Record<string, CellValue>,
): CellValue {
  if (!cell) return null;
  const ref = getCellRef(cell.r, cell.c);
  if (
    cell.f &&
    sheetFormulaValues &&
    Object.prototype.hasOwnProperty.call(sheetFormulaValues, ref)
  ) {
    return sheetFormulaValues[ref];
  }
  return sheetEdits[ref] !== undefined ? sheetEdits[ref] : cell.v;
}

function toInputValue(value: CellValue): string {
  return value === null ? "" : String(value);
}

function isLabelValue(value: CellValue): value is string {
  return typeof value === "string" && value.trim() !== "";
}

function formatGeneralValue(value: CellValue): string {
  if (value === null) return "";
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  if (typeof value === "string") return value;

  try {
    return SSF.format("General", value);
  } catch {
    return String(value);
  }
}

function formatWorkbookDisplayValue(
  cell: TemplateCell | null,
  value: CellValue,
): string {
  if (!cell) return "";
  if (value === null) return "";
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  if (typeof value === "string") return value;

  const formatCode = cell.z?.trim();
  if (!formatCode) {
    return formatGeneralValue(value);
  }

  try {
    return SSF.format(formatCode, value);
  } catch {
    return formatGeneralValue(value);
  }
}

function buildSourceThemeMap(sourceNames: string[]): Record<string, string> {
  const uniqueNames = Array.from(new Set(sourceNames.filter(Boolean)));
  return Object.fromEntries(
    uniqueNames.map((sourceName, index) => [sourceName, `underwriting-source-theme-${index % 12}`]),
  );
}

function getColumnWidth(
  sheet: TemplateSheet,
  sheetEdits: Record<string, string | number>,
  colIndex: number,
  sheetFormulaValues?: Record<string, CellValue>,
): number {
  let nonEmptyCount = 0;
  let numericCount = 0;
  let maxDisplayLength = 0;
  let maxTextLength = 0;

  for (let rowIndex = 0; rowIndex < sheet.maxRow; rowIndex++) {
    const cell = sheet.data[rowIndex]?.[colIndex] ?? null;
    if (!cell) {
      continue;
    }

    const resolvedValue = getResolvedCellValue(cell, sheetEdits, sheetFormulaValues);
    const displayValue = formatWorkbookDisplayValue(cell, resolvedValue).trim();

    if (!displayValue) {
      continue;
    }

    nonEmptyCount += 1;
    maxDisplayLength = Math.max(maxDisplayLength, displayValue.length);

    if (typeof resolvedValue === "number") {
      numericCount += 1;
      continue;
    }

    if (typeof resolvedValue === "string") {
      maxTextLength = Math.max(maxTextLength, resolvedValue.trim().length);
    }
  }

  if (maxTextLength >= 28 || maxDisplayLength >= 30) {
    return TEXT_HEAVY_COLUMN_WIDTH;
  }

  if (nonEmptyCount > 0 && numericCount / nonEmptyCount >= 0.6) {
    if (maxDisplayLength >= 16) {
      return LONG_NUMERIC_COLUMN_WIDTH;
    }
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
  const [edits, setEdits] = useState<EditsBySheet>({});
  const [aiCells, setAiCells] = useState<Record<string, Set<string>>>({});
  const [aiSources, setAiSources] = useState<AiSourceMap>({});
  const [aiConfidence, setAiConfidence] = useState<AiConfidenceMap>({});
  const [autofillQuery, setAutofillQuery] = useState("");
  const [selectedAutofillKey, setSelectedAutofillKey] = useState<string | null>(null);
  const [showAutofillPanel, setShowAutofillPanel] = useState(false);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [formulaValues, setFormulaValues] = useState<FormulaValuesBySheet>({});
  const [formulaWarnings, setFormulaWarnings] = useState<UnderwritingRecalculationWarning[]>([]);
  const [uploading, setUploading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [activeCell, setActiveCell] = useState<ActiveCell | null>(null);
  const [draftValue, setDraftValue] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const activeInputRef = useRef<HTMLInputElement>(null);
  const skipBlurCommitRef = useRef(false);
  const recalcRequestIdRef = useRef(0);
  const editsRef = useRef<EditsBySheet>({});
  const cellElementRefs = useRef<Record<string, HTMLTableCellElement | null>>({});

  const refreshDocuments = useCallback(async () => {
    setLoadingDocuments(true);
    try {
      const response = await listDocuments();
      setDocuments(response.documents);
    } catch {
      setDocuments([]);
    } finally {
      setLoadingDocuments(false);
    }
  }, []);

  useEffect(() => {
    if (!activeCell) return;
    activeInputRef.current?.focus();
    activeInputRef.current?.select();
  }, [activeCell]);

  useEffect(() => {
    void refreshDocuments();
  }, [refreshDocuments]);

  function clearActiveCell() {
    setActiveCell(null);
    setDraftValue("");
  }

  const replaceEdits = useCallback((nextEdits: EditsBySheet) => {
    editsRef.current = nextEdits;
    setEdits(nextEdits);
  }, []);

  const updateEdits = useCallback(
    (updater: (current: EditsBySheet) => EditsBySheet) => {
      const nextEdits = updater(editsRef.current);
      replaceEdits(nextEdits);
      return nextEdits;
    },
    [replaceEdits],
  );

  const runRecalculation = useCallback(
    async (nextEdits: EditsBySheet) => {
      const requestId = ++recalcRequestIdRef.current;
      setRecalculating(true);

      try {
        const result = await recalculateUnderwritingFormulaValues(nextEdits);
        if (requestId !== recalcRequestIdRef.current) {
          return;
        }
        setFormulaValues(result.formulaValues || {});
        setFormulaWarnings(result.warnings || []);
        setError((previous) =>
          previous.startsWith("Formula recalculation failed") ? "" : previous,
        );
      } catch (err) {
        if (requestId !== recalcRequestIdRef.current) {
          return;
        }
        setFormulaWarnings([]);
        setError(
          err instanceof Error ? err.message : "Formula recalculation failed",
        );
      } finally {
        if (requestId === recalcRequestIdRef.current) {
          setRecalculating(false);
        }
      }
    },
    [],
  );

  function applyCellChange(
    sheetName: string,
    row: number,
    col: number,
    raw: string,
  ): EditsBySheet {
    const ref = getCellRef(row, col);
    const value = normalizeInputValue(raw);
    return updateEdits((current) => ({
      ...current,
      [sheetName]: { ...(current[sheetName] || {}), [ref]: value },
    }));
  }

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setError("");
    setStatusMessage("");
    clearActiveCell();

    try {
      const parsed = await parseUnderwritingTemplate(file);
      setTemplate(parsed);
      replaceEdits({});
      setAiCells({});
      setAiSources({});
      setAutofillQuery("");
      setSelectedAutofillKey(null);
      setShowAutofillPanel(false);
      setFormulaValues({});
      setFormulaWarnings([]);
      setActiveTab(0);
      setStatusMessage(`Loaded ${parsed.filename} with ${parsed.sheets.length} sheet${parsed.sheets.length === 1 ? "" : "s"}.`);
      void runRecalculation({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  function handleCellChange(sheetName: string, row: number, col: number, raw: string) {
    return applyCellChange(sheetName, row, col, raw);
  }

  async function handleExtract() {
    setExtracting(true);
    setError("");
    setStatusMessage("");
    clearActiveCell();

    try {
      const result = await extractUnderwritingValues();
      if (result.message) {
        setStatusMessage(result.message);
        return;
      }

      const newAi: Record<string, Set<string>> = {};
      const newAiSources: AiSourceMap = {};
      const newAiConfidence: AiConfidenceMap = {};
      const mergedEdits = updateEdits((current) => {
        const merged = { ...current };
        for (const [sheetName, cells] of Object.entries(result.updates)) {
          merged[sheetName] = { ...(merged[sheetName] || {}), ...cells };
          newAi[sheetName] = new Set(Object.keys(cells));
          const sheetSources = result.sources?.[sheetName] || {};
          if (Object.keys(sheetSources).length > 0) {
            newAiSources[sheetName] = { ...sheetSources };
          }
          const sheetConfidence = result.confidence?.[sheetName] || {};
          if (Object.keys(sheetConfidence).length > 0) {
            newAiConfidence[sheetName] = { ...sheetConfidence };
          }
        }
        return merged;
      });
      setAiCells(newAi);
      setAiSources(newAiSources);
      setAiConfidence(newAiConfidence);
      const updatedCount = Object.values(result.updates).reduce((sum, cells) => sum + Object.keys(cells).length, 0);
      const firstFilledSheet = Object.keys(result.updates)[0];
      const firstFilledRef = firstFilledSheet ? Object.keys(result.updates[firstFilledSheet] || {})[0] : null;
      setAutofillQuery("");
      setShowAutofillPanel(false);
      if (firstFilledSheet && firstFilledRef && template) {
        const nextTabIndex = template.sheets.findIndex((candidate) => candidate.name === firstFilledSheet);
        if (nextTabIndex >= 0) {
          setActiveTab(nextTabIndex);
        }
        setSelectedAutofillKey(getAutofillKey(firstFilledSheet, firstFilledRef));
      } else {
        setSelectedAutofillKey(null);
      }
      setStatusMessage(
        `Auto-filled ${updatedCount} cell${updatedCount === 1 ? "" : "s"} from uploaded documents. Use Show Matches to review locations.`,
      );
      void runRecalculation(mergedEdits);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed");
    } finally {
      setExtracting(false);
    }
  }

  async function handleDownload() {
    setError("");

    try {
      const blob = await downloadFilledTemplate(editsRef.current);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download =
        template?.filename?.replace(/\.xlsx?$/i, "_filled.xlsx") || "filled.xlsx";
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      setStatusMessage("Downloaded filled workbook.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    }
  }

  useEffect(() => {
    if (!template || !selectedAutofillKey) {
      return;
    }

    const selectedEntry = template.sheets
      .flatMap((templateSheet) => {
        const sheetAi = aiCells[templateSheet.name];
        if (!sheetAi || sheetAi.size === 0) {
          return [];
        }

        return Array.from(sheetAi, (ref) => ({
          key: getAutofillKey(templateSheet.name, ref),
          sheetName: templateSheet.name,
        }));
      })
      .find((entry) => entry.key === selectedAutofillKey);

    if (!selectedEntry || template.sheets[activeTab]?.name !== selectedEntry.sheetName) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      cellElementRefs.current[selectedAutofillKey]?.scrollIntoView({
        behavior: "smooth",
        block: "center",
        inline: "center",
      });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [activeTab, aiCells, selectedAutofillKey, template]);

  if (!template) {
    return (
      <div className="underwriting-empty-state">
        <div className="underwriting-empty-icon">📊</div>
        <h2 className="underwriting-empty-title">Underwriting Template</h2>
        <p className="underwriting-empty-copy">
          Upload a UAP underwriting Excel template to parse its structure, then use{" "}
          <strong>Auto-Fill</strong> to extract values from your uploaded
          documents via RAG.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".xlsx,.xls"
          onChange={handleUpload}
          aria-label="Upload underwriting template"
          title="Upload underwriting template"
          hidden
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className={`underwriting-button underwriting-button-primary${uploading ? " underwriting-button-disabled" : ""}`}
        >
          {uploading ? "Parsing…" : "Upload Excel Template"}
        </button>
        {statusMessage && (
          <p className="underwriting-status-copy">{statusMessage}</p>
        )}
        {error && <p className="underwriting-error-copy">{error}</p>}
      </div>
    );
  }

  const aiCountBySheet = Object.fromEntries(
    template.sheets.map((templateSheet) => [templateSheet.name, aiCells[templateSheet.name]?.size || 0]),
  );

  const sourceThemeMap = buildSourceThemeMap([
    ...documents.map((document) => document.filename),
    ...Object.values(aiSources).flatMap((sheetSources) => Object.values(sheetSources)),
  ]);

  function getSourceThemeClass(sourceName: string | undefined): string {
    if (!sourceName) {
      return "";
    }

    return sourceThemeMap[sourceName] || "underwriting-source-theme-0";
  }

  const autofillEntries: AutofillEntry[] = template.sheets.flatMap((templateSheet) => {
    const sheetAi = aiCells[templateSheet.name];
    if (!sheetAi || sheetAi.size === 0) {
      return [];
    }

    const sheetEdits = edits[templateSheet.name] || {};
    const sheetFormulaValues = formulaValues[templateSheet.name] || {};
    const sheetSources = aiSources[templateSheet.name] || {};
    const sheetConfidence = aiConfidence[templateSheet.name] || {};

    return Array.from(sheetAi)
      .map((ref) => {
        const position = parseCellRef(ref);
        if (!position) {
          return null;
        }

        const cell = templateSheet.data[position.row - 1]?.[position.col - 1] ?? null;
        const resolvedValue = getResolvedCellValue(cell, sheetEdits, sheetFormulaValues);
        const displayValue =
          formatWorkbookDisplayValue(cell, resolvedValue) ||
          toInputValue(resolvedValue) ||
          "(blank)";
        const rawValue = toInputValue(resolvedValue) || "(blank)";
        return {
          key: getAutofillKey(templateSheet.name, ref),
          sheetName: templateSheet.name,
          row: position.row,
          col: position.col,
          ref,
          sourceName: sheetSources[ref] || "Uploaded documents",
          confidence: sheetConfidence[ref] || "medium",
          locationLabel: `${templateSheet.name} · ${ref}`,
          coordinatesLabel: `Row ${position.row} · Column ${colToLetter(position.col)}`,
          displayValue,
          rawValue,
          rawDiffersFromDisplay: rawValue !== displayValue,
        } satisfies AutofillEntry;
      })
      .filter((entry): entry is AutofillEntry => entry !== null)
      .sort((left, right) => {
        if (left.row !== right.row) {
          return left.row - right.row;
        }
        return left.col - right.col;
      });
  });

  const normalizedAutofillQuery = autofillQuery.trim().toLowerCase();
  const filteredAutofillEntries = normalizedAutofillQuery
    ? autofillEntries.filter((entry) =>
        [entry.sheetName, entry.ref, entry.sourceName, entry.displayValue]
          .join(" ")
          .toLowerCase()
          .includes(normalizedAutofillQuery),
      )
    : autofillEntries;
  const filteredAutofillKeys = normalizedAutofillQuery
    ? new Set(filteredAutofillEntries.map((entry) => entry.key))
    : new Set<string>();
  const navigationEntries = filteredAutofillEntries.length > 0 ? filteredAutofillEntries : autofillEntries;
  const selectedAutofillEntry = autofillEntries.find((entry) => entry.key === selectedAutofillKey) || null;
  const selectedAutofillIndex = selectedAutofillKey
    ? navigationEntries.findIndex((entry) => entry.key === selectedAutofillKey)
    : -1;
  const selectedAutofillSourceThemeClass = getSourceThemeClass(selectedAutofillEntry?.sourceName);

  function focusAutofillEntry(entry: AutofillEntry) {
    clearActiveCell();
    setSelectedAutofillKey(entry.key);
    const nextTabIndex = template ? template.sheets.findIndex((candidate) => candidate.name === entry.sheetName) : -1;
    if (nextTabIndex >= 0) {
      setActiveTab(nextTabIndex);
    }
  }

  function moveAutofillSelection(direction: -1 | 1) {
    if (navigationEntries.length === 0) {
      return;
    }

    const currentIndex = selectedAutofillIndex >= 0 ? selectedAutofillIndex : direction > 0 ? -1 : navigationEntries.length;
    const nextIndex = Math.max(0, Math.min(navigationEntries.length - 1, currentIndex + direction));
    focusAutofillEntry(navigationEntries[nextIndex]);
  }

  const sheet = template.sheets[activeTab];
  const sheetEdits = edits[sheet.name] || {};
  const sheetAi = aiCells[sheet.name] || new Set<string>();
  const sheetAiSources = aiSources[sheet.name] || {};
  const sheetFormulaValues = formulaValues[sheet.name] || {};
  const columnWidths = Array.from({ length: sheet.maxCol }, (_, index) =>
    getColumnWidth(sheet, sheetEdits, index, sheetFormulaValues),
  );

  function getResolvedValueForCell(cell: TemplateCell | null): CellValue {
    return getResolvedCellValue(cell, sheetEdits, sheetFormulaValues);
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

    const nextEdits = handleCellChange(
      activeCell.sheetName,
      activeCell.row,
      activeCell.col,
      draftValue,
    );
    openCellByPosition(nextCell);
    void runRecalculation(nextEdits);
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
    <div className="underwriting-panel">
      <div className="underwriting-toolbar">
        <span className="underwriting-toolbar-title">
          📊 {template.filename}
        </span>
        <div className="underwriting-toolbar-actions">
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xls"
            onChange={handleUpload}
            aria-label="Replace underwriting template"
            title="Replace underwriting template"
            hidden
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className={`underwriting-button underwriting-button-secondary${uploading ? " underwriting-button-disabled" : ""}`}
          >
            Re-upload
          </button>
          <button
            onClick={handleExtract}
            disabled={extracting}
            className={`underwriting-button underwriting-button-accent${extracting ? " underwriting-button-disabled" : ""}`}
          >
            {extracting ? "Extracting…" : "⚡ Auto-Fill from Docs"}
          </button>
          {autofillEntries.length > 0 && (
            <button
              type="button"
              onClick={() => setShowAutofillPanel((current) => !current)}
              className={`underwriting-button ${showAutofillPanel ? "underwriting-button-accent" : "underwriting-button-secondary"}`}
              aria-expanded={showAutofillPanel}
              aria-controls="underwriting-autofill-panel"
            >
              {showAutofillPanel
                ? "Hide Matches"
                : `Show Matches (${autofillEntries.length})`}
            </button>
          )}
          <button
            onClick={handleDownload}
            className="underwriting-button underwriting-button-success"
          >
            ⬇ Download .xlsx
          </button>
        </div>
      </div>

      <div className="underwriting-documents-bar">
        <span className="underwriting-documents-label">Documents</span>
        {loadingDocuments ? (
          <span>Loading uploaded files...</span>
        ) : documents.length > 0 ? (
          <>
            {documents.slice(0, 6).map((document) => (
              <span
                key={document.filename}
                title={`${document.filename} · ${document.chunks} chunk${document.chunks === 1 ? "" : "s"}`}
                className={`underwriting-document-pill ${getSourceThemeClass(document.filename)}`}
              >
                <span className="underwriting-document-dot" />
                <span className="underwriting-document-name">
                  {document.filename}
                </span>
              </span>
            ))}
            {documents.length > 6 && <span>+{documents.length - 6} more</span>}
          </>
        ) : (
          <span>No supporting documents uploaded for this project yet.</span>
        )}
      </div>

      {statusMessage && !error && (
        <div className="underwriting-status-bar">
          {statusMessage}
        </div>
      )}

      <div className="underwriting-tabs">
        {template.sheets.map((tabSheet, index) => (
          <button
            key={tabSheet.name}
            onClick={() => {
              clearActiveCell();
              setActiveTab(index);
            }}
            className={`underwriting-tab${index === activeTab ? " underwriting-tab-active" : ""}`}
          >
            <span>{tabSheet.name.length > 22 ? `${tabSheet.name.slice(0, 22)}…` : tabSheet.name}</span>
            {aiCountBySheet[tabSheet.name] > 0 && (
              <span className="underwriting-tab-count">{aiCountBySheet[tabSheet.name]}</span>
            )}
          </button>
        ))}
      </div>

      {error && (
        <div className="underwriting-error-bar">
          {error}
        </div>
      )}

      {formulaWarnings.length > 0 && (
        <div className="underwriting-warning-bar">
          {formulaWarnings
            .map((warning) => {
              const refs =
                warning.refs && warning.refs.length > 0
                  ? ` (${warning.refs.join(", ")})`
                  : "";
              return warning.sheet
                ? `${warning.sheet}: ${warning.message}${refs}`
                : `${warning.message}${refs}`;
            })
            .join(" | ")}
        </div>
      )}

      <div className="underwriting-grid-shell">
        <div className="underwriting-grid-scroll">
          <table className="underwriting-grid-table">
            <colgroup>
              <col width={ROW_HEADER_WIDTH} />
              {columnWidths.map((width, index) => (
                <col key={colToLetter(index + 1)} width={width} />
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
              {sheet.data.map((row, rowIndex) => (
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
                    const aiSource = sheetAiSources[ref];
                    const autofillKey = getAutofillKey(sheet.name, ref);
                    const sourceThemeClass = getSourceThemeClass(aiSource);
                    const isActive =
                      activeCell?.sheetName === sheet.name &&
                      activeCell.row === cell.r &&
                      activeCell.col === cell.c;
                    const isFilteredAutofillHit = filteredAutofillKeys.has(autofillKey);
                    const isSelectedAutofill = selectedAutofillKey === autofillKey;
                    const isLabel = isLabelValue(resolvedValue);
                    const isNumeric = typeof resolvedValue === "number";
                    const displayValue = formatWorkbookDisplayValue(cell, resolvedValue);
                    const rawValueText = toInputValue(resolvedValue);
                    const displayTitle =
                      displayValue && displayValue !== rawValueText
                        ? `${displayValue}\nRaw: ${rawValueText}`
                        : displayValue || rawValueText || ref;
                    const className = [
                      "underwriting-grid-cell",
                      isFormula ? "underwriting-grid-cell-formula" : "",
                      isLabel ? "underwriting-grid-cell-label" : "",
                      isNumeric ? "underwriting-grid-cell-value" : "",
                      hasEdit ? "underwriting-grid-cell-edited" : "",
                      isAi ? "underwriting-grid-cell-ai" : "",
                      isAi && aiSource ? "underwriting-grid-cell-ai-sourced" : "",
                      isFilteredAutofillHit ? "underwriting-grid-cell-search-hit" : "",
                      isSelectedAutofill ? "underwriting-grid-cell-search-hit-active" : "",
                      sourceThemeClass,
                      isActive ? "underwriting-grid-cell-active" : "",
                    ]
                      .filter(Boolean)
                      .join(" ");
                    const title = aiSource
                      ? `${displayTitle}\nFilled from: ${aiSource}`
                      : displayTitle;

                    return (
                      <td
                        key={ref}
                        className={className}
                        ref={(node) => {
                          cellElementRefs.current[autofillKey] = node;
                        }}
                      >
                        {isActive ? (
                          <input
                            ref={activeInputRef}
                            value={draftValue}
                            onChange={(event) => setDraftValue(event.target.value)}
                            onBlur={handleActiveInputBlur}
                            onKeyDown={handleActiveInputKeyDown}
                            className="underwriting-grid-input"
                            aria-label={`Edit cell ${ref}`}
                            title={title}
                          />
                        ) : isFormula ? (
                          <div className="underwriting-grid-cell-view" title={title}>
                            {displayValue}
                          </div>
                        ) : (
                          <button
                            type="button"
                            className="underwriting-grid-button"
                            onClick={() => activateCell(cell)}
                            title={title}
                            aria-label={`Edit cell ${ref}`}
                          >
                            {displayValue}
                          </button>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {showAutofillPanel && autofillEntries.length > 0 && (
          <aside
            id="underwriting-autofill-panel"
            className="underwriting-autofill-panel"
            aria-label="Autofill matches"
          >
            <div className="underwriting-autofill-panel-header">
              <div className="underwriting-autofill-panel-heading-row">
                <div className="underwriting-autofill-panel-heading">
                  <div className="underwriting-autofill-panel-title">Autofill matches</div>
                  <div className="underwriting-autofill-panel-subtitle">
                    {filteredAutofillEntries.length} of {autofillEntries.length} locations
                  </div>
                </div>
                <div className="underwriting-autofill-nav">
                  <button
                    type="button"
                    className="underwriting-autofill-nav-button"
                    onClick={() => moveAutofillSelection(-1)}
                    disabled={navigationEntries.length === 0 || selectedAutofillIndex === 0}
                    aria-label="Previous autofill match"
                  >
                    ←
                  </button>
                  <div className="underwriting-autofill-nav-status">
                    {navigationEntries.length === 0
                      ? "0 / 0"
                      : `${Math.max(selectedAutofillIndex, 0) + 1} / ${navigationEntries.length}`}
                  </div>
                  <button
                    type="button"
                    className="underwriting-autofill-nav-button"
                    onClick={() => moveAutofillSelection(1)}
                    disabled={navigationEntries.length === 0 || selectedAutofillIndex === navigationEntries.length - 1}
                    aria-label="Next autofill match"
                  >
                    →
                  </button>
                </div>
              </div>
              <input
                value={autofillQuery}
                onChange={(event) => setAutofillQuery(event.target.value)}
                className="underwriting-autofill-search"
                placeholder="Filter by sheet, cell, value, or document"
                aria-label="Filter autofill locations"
              />
            </div>

            {selectedAutofillEntry && (
              <div className="underwriting-autofill-summary">
                <div className="underwriting-autofill-summary-header">
                  <div className="underwriting-autofill-summary-copy">
                    <div className="underwriting-autofill-summary-location">
                      {selectedAutofillEntry.locationLabel}
                    </div>
                    <div className="underwriting-autofill-summary-coordinates">
                      {selectedAutofillEntry.coordinatesLabel}
                    </div>
                  </div>
                  <span
                    className={[
                      "underwriting-autofill-source-badge",
                      "underwriting-autofill-source-badge-strong",
                      selectedAutofillSourceThemeClass,
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    <span className="underwriting-autofill-source-dot" />
                    <span className="underwriting-autofill-source-name">
                      {selectedAutofillEntry.sourceName}
                    </span>
                  </span>
                </div>

                <div className="underwriting-autofill-summary-value-block">
                  <div className="underwriting-autofill-summary-value-label">
                    Displayed value
                  </div>
                  <div className="underwriting-autofill-summary-value">
                    {selectedAutofillEntry.displayValue}
                  </div>
                </div>

                <div className="underwriting-autofill-summary-meta-row">
                  <div
                    className={[
                      "underwriting-autofill-summary-raw",
                      selectedAutofillEntry.rawDiffersFromDisplay
                        ? ""
                        : "underwriting-autofill-summary-raw-muted",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    <span className="underwriting-autofill-summary-raw-label">
                      Raw value
                    </span>
                    <span className="underwriting-autofill-summary-raw-value">
                      {selectedAutofillEntry.rawValue}
                    </span>
                  </div>
                  <span className={`underwriting-autofill-confidence underwriting-autofill-confidence-${selectedAutofillEntry.confidence}`}>
                    {selectedAutofillEntry.confidence}
                  </span>
                </div>
              </div>
            )}

            <div className="underwriting-autofill-list">
              {filteredAutofillEntries.length > 0 ? (
                filteredAutofillEntries.map((entry) => {
                  const isSelected = selectedAutofillKey === entry.key;
                  const sourceThemeClass = getSourceThemeClass(entry.sourceName);
                  return (
                    <button
                      key={entry.key}
                      type="button"
                      className={[
                        "underwriting-autofill-item",
                        isSelected ? "underwriting-autofill-item-active" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      onClick={() => focusAutofillEntry(entry)}
                      title={`${entry.sheetName} ${entry.ref}\n${entry.sourceName}`}
                    >
                      <div className="underwriting-autofill-item-main">
                        <div className="underwriting-autofill-item-copy">
                          <span className="underwriting-autofill-item-ref">
                            {entry.locationLabel}
                          </span>
                          <span className="underwriting-autofill-item-coordinates">
                            {entry.coordinatesLabel}
                          </span>
                        </div>
                        <span className="underwriting-autofill-item-value">
                          {entry.displayValue}
                        </span>
                      </div>
                      <div className="underwriting-autofill-item-meta">
                        <span
                          className={[
                            "underwriting-autofill-source-badge",
                            "underwriting-autofill-source-badge-subtle",
                            sourceThemeClass,
                          ]
                            .filter(Boolean)
                            .join(" ")}
                        >
                          <span className="underwriting-autofill-source-dot" />
                          <span className="underwriting-autofill-source-name">
                            {entry.sourceName}
                          </span>
                        </span>
                        <span className={`underwriting-autofill-confidence underwriting-autofill-confidence-${entry.confidence}`}>
                          {entry.confidence}
                        </span>
                        {isSelected && entry.rawDiffersFromDisplay && (
                          <span className="underwriting-autofill-item-raw-preview">
                            Raw: {entry.rawValue}
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="underwriting-autofill-empty">No autofill matches for the current filter.</div>
              )}
            </div>
          </aside>
        )}
      </div>

      <div className="underwriting-footer">
        <span>
          {sheet.maxRow} rows × {sheet.maxCol} cols
        </span>
        <span>{Object.keys(sheetEdits).length} edits</span>
        {sheetAi.size > 0 && <span>{sheetAi.size} AI-filled</span>}
        <span>
          {recalculating
            ? "Recalculating formulas..."
            : "Formulas recalculate in-app and stay intact on export"}
        </span>
        {activeCell?.sheetName === sheet.name && <span>Active: {activeCell.ref}</span>}
      </div>
    </div>
  );
}
