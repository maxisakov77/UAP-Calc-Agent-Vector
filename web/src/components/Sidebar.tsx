"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { listDocuments, uploadDocument, deleteDocument, type DocumentInfo } from "@/lib/api";
import IndexManager from "./IndexManager";
import BlueprintManager from "./BlueprintManager";
import AgentSettings from "./AgentSettings";

export default function Sidebar() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleProjectSwitch = useCallback(() => {
    setRefreshKey((k) => k + 1);
    refresh();
  }, []);

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

    setUploading(true);
    setError("");

    try {
      for (const file of Array.from(files)) {
        await uploadDocument(file);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleDelete(filename: string) {
    try {
      await deleteDocument(filename);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: 16, gap: 0, overflowY: "auto" }}>
      {/* Step 1 — Project */}
      <StepLabel number={1} guide="Choose or create a Pinecone index to isolate your data" />
      <IndexManager onSwitch={handleProjectSwitch} />

      <SectionDivider />

      {/* Step 2 — Documents */}
      <StepLabel number={2} guide="Upload files to build the knowledge base for this project" />
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
            {uploading ? "Uploading..." : "+ Upload Files"}
          </button>
        </div>

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
                background: "var(--bg-card)",
                border: "1px solid var(--glass-border)",
                fontSize: 13,
                color: "var(--foreground)",
              }}
            >
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
      </div>

      <SectionDivider />

      {/* Step 3 — Blueprints */}
      <StepLabel number={3} guide="Define how the Writer agent formats and styles responses" />
      <BlueprintManager refreshKey={refreshKey} />

      <SectionDivider />

      {/* Step 4 — Agent Settings */}
      <StepLabel number={4} guide="Fine-tune retrieval depth, temperature, and other params" />
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
