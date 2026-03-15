"use client";

import { useState, useEffect } from "react";
import {
  listBlueprints,
  generateBlueprint,
  deleteBlueprint,
  type Blueprint,
} from "@/lib/api";

export default function BlueprintManager({ refreshKey }: { refreshKey?: number }) {
  const [blueprints, setBlueprints] = useState<Blueprint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Create form
  const [showCreate, setShowCreate] = useState(false);
  const [subject, setSubject] = useState("");
  const [creating, setCreating] = useState(false);

  // Expand to view full instructions
  const [expandedId, setExpandedId] = useState<string | null>(null);

  async function refresh() {
    try {
      const res = await listBlueprints();
      setBlueprints(res.blueprints);
      setError("");
    } catch {
      setError("Failed to load blueprints");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, [refreshKey]);

  async function handleCreate() {
    if (!subject.trim()) return;
    setCreating(true);
    setError("");
    try {
      await generateBlueprint(subject.trim());
      setSubject("");
      setShowCreate(false);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(id: string) {
    setError("");
    try {
      await deleteBlueprint(id);
      if (expandedId === id) setExpandedId(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 0 }}>
        <p style={{ fontSize: 12, color: "var(--brand-granite-gray)" }}>Loading blueprints...</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Header */}
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
          Blueprints
        </h2>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--brand-granite-gray)" }}>
          {blueprints.length} blueprint{blueprints.length !== 1 ? "s" : ""} · Librarian auto-matches by subject
        </p>
      </div>

      {/* Error */}
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

      {/* Blueprint List */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {blueprints.map((bp) => (
          <div
            key={bp.id}
            style={{
              padding: "8px 10px",
              background: "var(--bg-card)",
              border: "1px solid var(--glass-border)",
              fontSize: 13,
              color: "var(--foreground)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <button
                onClick={() => setExpandedId(expandedId === bp.id ? null : bp.id)}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--foreground)",
                  cursor: "pointer",
                  padding: 0,
                  fontSize: 13,
                  fontWeight: 600,
                  textAlign: "left",
                  flex: 1,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title="Click to expand"
              >
                {expandedId === bp.id ? "▾" : "▸"} {bp.subject}
              </button>
              <button
                onClick={() => handleDelete(bp.id)}
                title="Delete blueprint"
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--brand-granite-gray)",
                  cursor: "pointer",
                  fontSize: 14,
                  padding: "0 4px",
                  marginLeft: 8,
                  flexShrink: 0,
                }}
              >
                ✕
              </button>
            </div>
            {expandedId === bp.id && (
              <p
                style={{
                  margin: "6px 0 0",
                  fontSize: 12,
                  color: "var(--brand-granite-gray)",
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {bp.instructions}
              </p>
            )}
          </div>
        ))}

        {blueprints.length === 0 && !error && (
          <p style={{ fontSize: 12, color: "var(--brand-granite-gray)", textAlign: "center", margin: "8px 0" }}>
            No blueprints yet. Create one to guide the Librarian.
          </p>
        )}
      </div>

      {/* Create New Blueprint */}
      {showCreate ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 8,
            padding: 10,
            background: "var(--bg-card)",
            border: "1px solid var(--glass-border)",
          }}
        >
          <input
            type="text"
            placeholder="Subject (e.g. Legal, Medical, Finance)"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); }}
            style={{
              padding: "6px 8px",
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-color)",
              color: "var(--foreground)",
              fontSize: 13,
              outline: "none",
            }}
          />
          <p style={{ margin: 0, fontSize: 11, color: "var(--brand-granite-gray)", lineHeight: 1.4 }}>
            AI will generate Writer instructions for this subject automatically.
          </p>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              onClick={handleCreate}
              disabled={creating || !subject.trim()}
              style={{
                flex: 1,
                padding: "8px 0",
                background: creating ? "var(--bg-elevated)" : "var(--blue)",
                border: "1px solid var(--border-color)",
                color: "var(--foreground)",
                cursor: creating ? "not-allowed" : "pointer",
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              {creating ? "Generating..." : "Generate Blueprint"}
            </button>
            <button
              onClick={() => { setShowCreate(false); setSubject(""); }}
              style={{
                padding: "8px 12px",
                background: "none",
                border: "1px solid var(--border-color)",
                color: "var(--brand-granite-gray)",
                cursor: "pointer",
                fontSize: 13,
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowCreate(true)}
          style={{
            width: "100%",
            padding: "8px 0",
            background: "transparent",
            border: "1px dashed var(--border-color)",
            color: "var(--brand-granite-gray)",
            cursor: "pointer",
            fontSize: 12,
            fontWeight: 500,
          }}
        >
          + New Blueprint
        </button>
      )}
    </div>
  );
}
