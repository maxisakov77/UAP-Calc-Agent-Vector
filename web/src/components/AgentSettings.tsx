"use client";

import { useState, useEffect } from "react";
import {
  getAgentSettings,
  updateAgentSettings,
  type AgentSettingsMap,
} from "@/lib/api";

const AGENT_CONFIGS: Record<
  string,
  { label: string; params: { key: string; label: string; min: number; max: number; step: number; type: "range" | "number" }[] }
> = {
  librarian: {
    label: "Librarian",
    params: [
      { key: "top_k", label: "Context Depth (top_k)", min: 1, max: 20, step: 1, type: "range" },
    ],
  },
  researcher: {
    label: "Researcher",
    params: [
      { key: "top_k", label: "Search Depth (top_k)", min: 1, max: 100, step: 1, type: "range" },
      { key: "temperature", label: "Creativity (temperature)", min: 0, max: 2, step: 0.05, type: "range" },
    ],
  },
  writer: {
    label: "Writer",
    params: [
      { key: "temperature", label: "Creativity (temperature)", min: 0, max: 2, step: 0.05, type: "range" },
    ],
  },
  summarizer: {
    label: "Summarizer",
    params: [
      { key: "temperature", label: "Creativity (temperature)", min: 0, max: 2, step: 0.05, type: "range" },
      { key: "max_length", label: "Max Length (tokens)", min: 100, max: 10000, step: 100, type: "range" },
    ],
  },
};

export default function AgentSettings() {
  const [settings, setSettings] = useState<AgentSettingsMap | null>(null);
  const [savedSettings, setSavedSettings] = useState<AgentSettingsMap | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  async function refresh() {
    try {
      const res = await getAgentSettings();
      setSettings(res.settings);
      setSavedSettings(JSON.parse(JSON.stringify(res.settings)));
      setError("");
    } catch {
      setError("Failed to load settings");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  function hasChanges(agentName: string): boolean {
    if (!settings || !savedSettings) return false;
    const current = settings[agentName] || {};
    const saved = savedSettings[agentName] || {};
    return AGENT_CONFIGS[agentName]?.params.some(
      (p) => current[p.key] !== saved[p.key],
    ) ?? false;
  }

  async function handleSave(agentName: string) {
    if (!settings) return;
    setSaving(agentName);
    setError("");
    setSavedMessage(null);
    try {
      const res = await updateAgentSettings({ [agentName]: settings[agentName] });
      setSettings(res.settings);
      setSavedSettings(JSON.parse(JSON.stringify(res.settings)));
      setSavedMessage(agentName);
      setTimeout(() => setSavedMessage((prev) => (prev === agentName ? null : prev)), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving("");
    }
  }

  function handleReset(agentName: string) {
    if (!savedSettings || !settings) return;
    setSettings({
      ...settings,
      [agentName]: { ...savedSettings[agentName] },
    });
  }

  function handleChange(agent: string, key: string, value: number) {
    if (!settings) return;
    setSettings({
      ...settings,
      [agent]: { ...settings[agent], [key]: value },
    });
  }

  if (loading) {
    return (
      <p style={{ fontSize: 12, color: "var(--brand-granite-gray)" }}>Loading settings...</p>
    );
  }

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
          Agent Settings
        </h2>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--brand-granite-gray)" }}>
          Tune each agent&apos;s behavior
        </p>
      </div>

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

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {Object.entries(AGENT_CONFIGS).map(([agentKey, config]) => {
          const isExpanded = expanded === agentKey;
          const agentData = settings?.[agentKey] || {};
          const description = agentData.description as string | undefined;
          const dirty = hasChanges(agentKey);
          const isSaving = saving === agentKey;
          const justSaved = savedMessage === agentKey;

          return (
            <div
              key={agentKey}
              style={{
                padding: "8px 10px",
                background: isExpanded ? "rgba(59,130,246,0.08)" : "var(--bg-card)",
                border: isExpanded
                  ? "1px solid rgba(59,130,246,0.2)"
                  : "1px solid var(--glass-border)",
                transition: "all 0.15s ease",
              }}
            >
              {/* Header row */}
              <button
                onClick={() => setExpanded(isExpanded ? null : agentKey)}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--foreground)",
                  cursor: "pointer",
                  padding: 0,
                  fontSize: 13,
                  fontWeight: 600,
                  textAlign: "left",
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <span style={{ fontSize: 10, color: "var(--brand-granite-gray)" }}>
                  {isExpanded ? "▾" : "▸"}
                </span>
                {config.label}
                {dirty && (
                  <span style={{ fontSize: 9, color: "#f59e0b", marginLeft: 4 }}>● unsaved</span>
                )}
                {justSaved && !dirty && (
                  <span style={{ fontSize: 9, color: "#22c55e", marginLeft: 4 }}>✓ saved</span>
                )}
              </button>

              {/* Saved confirmation banner */}
              {isExpanded && justSaved && !dirty && (
                <div
                  style={{
                    margin: "6px 0",
                    padding: "5px 8px",
                    background: "rgba(34,197,94,0.1)",
                    border: "1px solid rgba(34,197,94,0.25)",
                    fontSize: 11,
                    color: "#22c55e",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  ✓ {config.label} settings applied — active on next chat message
                </div>
              )}

              {/* Description */}
              {isExpanded && description && (
                <p
                  style={{
                    margin: "6px 0 8px",
                    fontSize: 11,
                    color: "var(--brand-granite-gray)",
                    lineHeight: 1.4,
                  }}
                >
                  {description}
                </p>
              )}

              {/* Params */}
              {isExpanded && (
                <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
                  {config.params.map((param) => {
                    const rawValue = agentData[param.key];
                    const value = typeof rawValue === "number" ? rawValue : param.min;

                    return (
                      <div key={param.key}>
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            marginBottom: 4,
                          }}
                        >
                          <label style={{ fontSize: 12, color: "var(--brand-granite-gray)" }}>
                            {param.label}
                          </label>
                          <span
                            style={{
                              fontSize: 12,
                              fontWeight: 600,
                              color: "var(--foreground)",
                              minWidth: 40,
                              textAlign: "right",
                            }}
                          >
                            {param.step < 1 ? value.toFixed(2) : value}
                          </span>
                        </div>
                        <input
                          type="range"
                          min={param.min}
                          max={param.max}
                          step={param.step}
                          value={value}
                          onChange={(e) =>
                            handleChange(agentKey, param.key, parseFloat(e.target.value))
                          }
                          style={{
                            width: "100%",
                            accentColor: "var(--blue-accent)",
                            cursor: "pointer",
                          }}
                        />
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            fontSize: 10,
                            color: "var(--brand-granite-gray)",
                          }}
                        >
                          <span>{param.min}</span>
                          <span>{param.max}</span>
                        </div>
                      </div>
                    );
                  })}

                  {/* Action buttons */}
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      onClick={() => handleSave(agentKey)}
                      disabled={isSaving || !dirty}
                      style={{
                        flex: 1,
                        padding: "6px 0",
                        background: isSaving
                          ? "var(--bg-elevated)"
                          : dirty
                            ? "var(--blue)"
                            : "var(--bg-elevated)",
                        border: "1px solid var(--border-color)",
                        color: dirty ? "var(--foreground)" : "var(--brand-granite-gray)",
                        cursor: isSaving || !dirty ? "not-allowed" : "pointer",
                        fontSize: 12,
                        fontWeight: 600,
                        opacity: dirty ? 1 : 0.5,
                      }}
                    >
                      {isSaving ? "Saving..." : dirty ? "Apply Changes" : "No Changes"}
                    </button>
                    {dirty && (
                      <button
                        onClick={() => handleReset(agentKey)}
                        style={{
                          padding: "6px 10px",
                          background: "none",
                          border: "1px solid var(--border-color)",
                          color: "var(--brand-granite-gray)",
                          cursor: "pointer",
                          fontSize: 12,
                        }}
                      >
                        Reset
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
