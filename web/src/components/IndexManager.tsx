"use client";

import { useState, useEffect } from "react";
import {
  listIndexes,
  getActiveIndex,
  createIndex,
  deleteIndex,
  switchIndex,
  type PineconeIndex,
  type ActiveIndexResponse,
} from "@/lib/api";

export default function IndexManager({ onSwitch }: { onSwitch?: () => void }) {
  const [indexes, setIndexes] = useState<PineconeIndex[]>([]);
  const [active, setActive] = useState("");
  const [activeStats, setActiveStats] = useState<ActiveIndexResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Create form
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDim, setNewDim] = useState(3072);
  const [creating, setCreating] = useState(false);

  async function refresh() {
    try {
      const [listRes, statsRes] = await Promise.all([listIndexes(), getActiveIndex()]);
      setIndexes(listRes.indexes);
      setActive(listRes.active);
      setActiveStats(statsRes);
      setError("");
    } catch {
      setError("Failed to load indexes");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleSwitch(name: string) {
    try {
      setError("");
      const res = await switchIndex(name);
      setActive(res.active);
      const stats = await getActiveIndex();
      setActiveStats(stats);
      onSwitch?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Switch failed");
    }
  }

  async function handleCreate() {
    if (!newName.trim()) return;
    setCreating(true);
    setError("");
    try {
      await createIndex(newName.trim(), newDim);
      setNewName("");
      setShowCreate(false);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(name: string) {
    if (name === active) return;
    setError("");
    try {
      await deleteIndex(name);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 16 }}>
        <p style={{ fontSize: 12, color: "var(--brand-granite-gray)" }}>Loading indexes...</p>
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
          Pinecone Indexes
        </h2>
        {activeStats && (
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--brand-granite-gray)" }}>
            Active: <strong style={{ color: "var(--foreground)" }}>{active}</strong> · {activeStats.total_vectors.toLocaleString()} vectors
          </p>
        )}
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

      {/* Index List */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {indexes.map((idx) => (
          <div
            key={idx.name}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "8px 10px",
              background: idx.name === active ? "rgba(59,130,246,0.12)" : "var(--bg-card)",
              border: idx.name === active ? "1px solid rgba(59,130,246,0.3)" : "1px solid var(--glass-border)",
              fontSize: 13,
              color: "var(--foreground)",
            }}
          >
            <div style={{ flex: 1, overflow: "hidden" }}>
              <span
                style={{
                  display: "block",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  fontWeight: idx.name === active ? 600 : 400,
                }}
              >
                {idx.name}
                {idx.name === active && (
                  <span style={{ fontSize: 10, color: "var(--blue-accent)", marginLeft: 6 }}>● ACTIVE</span>
                )}
              </span>
              <span style={{ fontSize: 11, color: "var(--brand-granite-gray)" }}>
                {idx.dimension}d · {idx.metric} · {idx.ready ? "Ready" : idx.state}
              </span>
            </div>
            <div style={{ display: "flex", gap: 4, marginLeft: 8, flexShrink: 0 }}>
              {idx.name !== active && (
                <>
                  <button
                    onClick={() => handleSwitch(idx.name)}
                    title="Switch to this index"
                    style={{
                      background: "var(--blue)",
                      border: "none",
                      color: "var(--foreground)",
                      cursor: "pointer",
                      fontSize: 11,
                      padding: "3px 8px",
                      fontWeight: 600,
                    }}
                  >
                    Use
                  </button>
                  <button
                    onClick={() => handleDelete(idx.name)}
                    title="Delete this index"
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--brand-granite-gray)",
                      cursor: "pointer",
                      fontSize: 14,
                      padding: "0 4px",
                    }}
                  >
                    ✕
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Create New Index */}
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
            placeholder="Index name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={{
              padding: "6px 8px",
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-color)",
              color: "var(--foreground)",
              fontSize: 13,
              outline: "none",
            }}
          />
          <select
            value={newDim}
            onChange={(e) => setNewDim(Number(e.target.value))}
            aria-label="Embedding dimension"
            style={{
              padding: "6px 8px",
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-color)",
              color: "var(--foreground)",
              fontSize: 13,
            }}
          >
            <option value={3072}>3072 dims (text-embedding-3-large)</option>
            <option value={1536}>1536 dims (text-embedding-3-small)</option>
            <option value={768}>768 dims</option>
          </select>
          <div style={{ display: "flex", gap: 6 }}>
            <button
              onClick={handleCreate}
              disabled={creating || !newName.trim()}
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
              {creating ? "Creating..." : "Create"}
            </button>
            <button
              onClick={() => setShowCreate(false)}
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
          + New Index
        </button>
      )}
    </div>
  );
}
