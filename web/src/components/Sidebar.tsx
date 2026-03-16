"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { listDocuments, uploadDocument, deleteDocument, type DocumentInfo, type PropertyContext } from "@/lib/api";
import IndexManager from "./IndexManager";
import PropertyWizard from "./PropertyWizard";
import BlueprintManager from "./BlueprintManager";
import AgentSettings from "./AgentSettings";

type FileStatus = "pending" | "uploading" | "done" | "error";
interface QueuedFile {
  file: File;
  status: FileStatus;
  chunks?: number;
  error?: string;
}

export default function Sidebar({
  onPropertyChange,
  onProjectSwitch,
}: {
  onPropertyChange?: (context: PropertyContext | null) => void;
  onProjectSwitch?: () => void;
}) {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleProjectSwitch = useCallback(() => {
    setRefreshKey((k) => k + 1);
    refresh();
    onProjectSwitch?.();
  }, [onProjectSwitch]);

  async function refresh() {
    try {
      const res = await listDocuments();
      setDocuments(res.documents);
      setTotalChunks(res.total_chunks);
      setError("");
    } catch {
      setError("Backend offline");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const items: QueuedFile[] = Array.from(files).map((f) => ({
      file: f,
      status: "pending" as FileStatus,
    }));
    setQueue(items);
    setUploading(true);
    setError("");

    for (let i = 0; i < items.length; i++) {
      items[i].status = "uploading";
      setQueue([...items]);
      try {
        const res = await uploadDocument(items[i].file);
        items[i].status = "done";
        items[i].chunks = res.chunks;
      } catch (err) {
        items[i].status = "error";
        items[i].error = err instanceof Error ? err.message : "Upload failed";
      }
      setQueue([...items]);
    }

    await refresh();
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
    // Clear the queue after a short delay so user can see final state
    setTimeout(() => setQueue([]), 4000);
  }

  async function handleDelete(filename: string) {
    try {
      await deleteDocument(filename);
      setSelected((prev) => { const next = new Set(prev); next.delete(filename); return next; });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  function toggleSelect(filename: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename); else next.add(filename);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selected.size === documents.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(documents.map((d) => d.filename)));
    }
  }

  async function handleDeleteSelected() {
    if (selected.size === 0) return;
    setDeleting(true);
    setError("");
    try {
      for (const filename of selected) {
        await deleteDocument(filename);
      }
      setSelected(new Set());
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch delete failed");
      await refresh();
    } finally {
      setDeleting(false);
    }
  }

  async function handleDeleteAll() {
    if (documents.length === 0) return;
    setDeleting(true);
    setError("");
    try {
      for (const doc of documents) {
        await deleteDocument(doc.filename);
      }
      setSelected(new Set());
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete all failed");
      await refresh();
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: 16, gap: 0, overflowY: "auto" }}>
      {/* Step 1 — Project */}
      <StepLabel number={1} guide="Choose or create a Pinecone index to isolate your data" />
      <IndexManager onSwitch={handleProjectSwitch} />

      <SectionDivider />

      {/* Step 2 — Property */}
      <StepLabel number={2} guide="Select the NYC site and optional same-block lots for live UAP / 485-x context" />
      <PropertyWizard refreshKey={refreshKey} onPropertyChange={onPropertyChange} />

      <SectionDivider />

      {/* Step 3 — Documents */}
      <StepLabel number={3} guide="Upload files to build the knowledge base for this project" />
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
            Documents
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--brand-granite-gray)" }}>
            {totalChunks} chunks across {documents.length} file{documents.length !== 1 ? "s" : ""}
          </p>
        </div>

        {/* Upload */}
        <div>
          <input
            ref={fileRef}
            type="file"
            multiple
            accept=".txt,.md,.csv,.json,.py,.ts,.js,.html,.css,.pdf,.docx,.xlsx,.xls,.yaml,.yml,.xml,.log,.sql,.sh,.bat,.env,.toml,.cfg,.ini,.rst,.tex"
            onChange={handleUpload}
            style={{ display: "none" }}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            style={{
              width: "100%",
              padding: "10px 0",
              background: uploading ? "var(--bg-elevated)" : "var(--blue)",
              border: "1px solid var(--border-color)",
              color: "var(--foreground)",
              cursor: uploading ? "not-allowed" : "pointer",
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            {uploading
              ? `Uploading ${queue.filter((q) => q.status === "done").length}/${queue.length}...`
              : "+ Upload Files"}
          </button>
        </div>

        {/* Upload Queue */}
        {queue.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            {queue.map((q, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "6px 8px",
                  fontSize: 12,
                  background: "var(--bg-card)",
                  border: `1px solid ${
                    q.status === "error"
                      ? "rgba(238,85,85,0.3)"
                      : q.status === "done"
                        ? "rgba(85,238,85,0.3)"
                        : "var(--glass-border)"
                  }`,
                }}
              >
                <span style={{ flexShrink: 0, width: 16, textAlign: "center" }}>
                  {q.status === "pending" && (
                    <span style={{ color: "var(--brand-granite-gray)" }}>○</span>
                  )}
                  {q.status === "uploading" && (
                    <span
                      style={{
                        display: "inline-block",
                        width: 12,
                        height: 12,
                        border: "2px solid var(--blue-accent)",
                        borderTopColor: "transparent",
                        borderRadius: "50%",
                        animation: "spin 0.8s linear infinite",
                      }}
                    />
                  )}
                  {q.status === "done" && (
                    <span style={{ color: "#5e5" }}>✓</span>
                  )}
                  {q.status === "error" && (
                    <span style={{ color: "#e55" }}>✕</span>
                  )}
                </span>
                <span
                  style={{
                    flex: 1,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    color:
                      q.status === "error"
                        ? "#e55"
                        : q.status === "done"
                          ? "var(--foreground)"
                          : "var(--brand-granite-gray)",
                  }}
                >
                  {q.file.name}
                </span>
                <span style={{ flexShrink: 0, fontSize: 11, color: "var(--brand-granite-gray)" }}>
                  {q.status === "pending" && "queued"}
                  {q.status === "uploading" && "processing…"}
                  {q.status === "done" && `${q.chunks} chunks`}
                  {q.status === "error" && (q.error ?? "failed")}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <p style={{ margin: 0, fontSize: 12, color: "#e55", padding: "6px 8px", background: "rgba(238,85,85,0.1)", border: "1px solid rgba(238,85,85,0.2)" }}>
            {error}
          </p>
        )}

        {/* Document List */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 160, overflowY: "auto" }}>
          {documents.map((doc) => (
            <div
              key={doc.filename}
              className="animate-in"
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 10px",
                background: selected.has(doc.filename) ? "var(--bg-elevated)" : "var(--bg-card)",
                border: selected.has(doc.filename) ? "1px solid var(--blue-accent)" : "1px solid var(--glass-border)",
                fontSize: 13,
                color: "var(--foreground)",
              }}
            >
              <input
                type="checkbox"
                checked={selected.has(doc.filename)}
                onChange={() => toggleSelect(doc.filename)}
                aria-label={`Select ${doc.filename}`}
                style={{ marginRight: 8, accentColor: "var(--blue-accent)", cursor: "pointer" }}
              />
              <div style={{ overflow: "hidden", flex: 1 }}>
                <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {doc.filename}
                </span>
                <span style={{ fontSize: 11, color: "var(--brand-granite-gray)" }}>
                  {doc.chunks} chunk{doc.chunks !== 1 ? "s" : ""}
                </span>
              </div>
              <button
                onClick={() => handleDelete(doc.filename)}
                title="Delete document"
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--brand-granite-gray)",
                  cursor: "pointer",
                  fontSize: 14,
                  padding: "0 4px",
                  marginLeft: 8,
                }}
              >
                ✕
              </button>
            </div>
          ))}

          {documents.length === 0 && !error && (
            <p style={{ fontSize: 12, color: "var(--brand-granite-gray)", textAlign: "center", marginTop: 8 }}>
              No documents uploaded yet.
            </p>
          )}
        </div>

        {/* Batch Actions */}
        {documents.length > 0 && (
          <div style={{ display: "flex", gap: 6 }}>
            <button
              onClick={toggleSelectAll}
              style={{
                flex: 1,
                padding: "6px 0",
                background: "none",
                border: "1px solid var(--border-color)",
                color: "var(--brand-granite-gray)",
                cursor: "pointer",
                fontSize: 11,
              }}
            >
              {selected.size === documents.length ? "Deselect All" : "Select All"}
            </button>
            {selected.size > 0 && (
              <button
                onClick={handleDeleteSelected}
                disabled={deleting}
                style={{
                  flex: 1,
                  padding: "6px 0",
                  background: "rgba(238,85,85,0.15)",
                  border: "1px solid rgba(238,85,85,0.3)",
                  color: "#e55",
                  cursor: deleting ? "not-allowed" : "pointer",
                  fontSize: 11,
                  fontWeight: 600,
                }}
              >
                {deleting ? "Deleting…" : `Delete ${selected.size} Selected`}
              </button>
            )}
            <button
              onClick={handleDeleteAll}
              disabled={deleting}
              style={{
                flex: 1,
                padding: "6px 0",
                background: "rgba(238,85,85,0.15)",
                border: "1px solid rgba(238,85,85,0.3)",
                color: "#e55",
                cursor: deleting ? "not-allowed" : "pointer",
                fontSize: 11,
                fontWeight: 600,
              }}
            >
              {deleting ? "Deleting…" : "Delete All"}
            </button>
          </div>
        )}
      </div>

      <SectionDivider />

      {/* Step 4 — Blueprints */}
      <StepLabel number={4} guide="Define how the Writer agent formats and styles responses" />
      <BlueprintManager refreshKey={refreshKey} />

      <SectionDivider />

      {/* Step 5 — Agent Settings */}
      <StepLabel number={5} guide="Fine-tune retrieval depth, temperature, and other params" />
      <AgentSettings />
    </div>
  );
}

/* ── Helpers ──────────────────────────────────────────── */

function StepLabel({ number, guide }: { number: number; guide: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
      <span
        style={{
          width: 22,
          height: 22,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          border: "1.5px solid var(--blue-accent)",
          fontSize: 11,
          fontWeight: 700,
          color: "var(--blue-accent)",
          background: "var(--bg-dark)",
          flexShrink: 0,
        }}
      >
        {number}
      </span>
      <span style={{ fontSize: 11, color: "var(--brand-granite-gray)", lineHeight: 1.35 }}>
        {guide}
      </span>
    </div>
  );
}

function SectionDivider() {
  return (
    <div style={{ height: 1, background: "var(--border-color)", margin: "14px -16px" }} />
  );
}
