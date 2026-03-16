"use client";

import { useState, useRef, useEffect } from "react";
import ChatInput from "./ChatInput";
import MessageBubble from "./MessageBubble";
import Sidebar from "./Sidebar";
import OnboardingGuide from "./OnboardingGuide";
import type { ChatMessage, PropertyContext } from "@/lib/api";
import { sendChat } from "@/lib/api";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeProperty, setActiveProperty] = useState<PropertyContext | null>(null);
  const [sources, setSources] = useState<{ filename: string; distance: number }[]>([]);
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function handleProjectSwitch() {
    setMessages([]);
    setSources([]);
    setActiveProperty(null);
  }

  function handlePropertyChange(context: PropertyContext | null) {
    // Clear stale chat when switching to a different property
    if (
      context?.primary_bbl !== activeProperty?.primary_bbl &&
      activeProperty !== null
    ) {
      setMessages([]);
      setSources([]);
    }
    setActiveProperty(context);
  }

  async function handleSend(content: string) {
    const userMsg: ChatMessage = { role: "user", content };
    const updated = [...messages, userMsg];
    setMessages(updated);
    setLoading(true);

    try {
      const res = await sendChat(updated);
      setMessages([...updated, { role: "assistant", content: res.reply }]);
      setSources(res.sources);
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Unknown error";
      setMessages([
        ...updated,
        { role: "assistant", content: `Error: ${errMsg}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", height: "100vh", background: "var(--bg-main)" }}>
      {/* Sidebar */}
      {sidebarOpen && (
        <div
          style={{
            width: 320,
            minWidth: 320,
            borderRight: "1px solid var(--border-color)",
            background: "var(--bg-dark)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <Sidebar onPropertyChange={handlePropertyChange} onProjectSwitch={handleProjectSwitch} />
        </div>
      )}

      {/* Main Chat Area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Header */}
        <header
          style={{
            padding: "12px 20px",
            borderBottom: "1px solid var(--header-border)",
            background: "var(--header-bg)",
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{
              background: "none",
              border: "1px solid var(--border-color)",
              color: "var(--foreground)",
              padding: "6px 10px",
              cursor: "pointer",
              fontSize: 14,
            }}
          >
            {sidebarOpen ? "◀" : "▶"} Sidebar
          </button>
          <h1 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: "var(--blue-accent)" }}>
            UAP 485-x NYC Development Expert
          </h1>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
            {activeProperty && (
              <span
                style={{
                  fontSize: 11,
                  color: "var(--foreground)",
                  padding: "5px 8px",
                  border: "1px solid rgba(59,130,246,0.25)",
                  background: "rgba(59,130,246,0.12)",
                  whiteSpace: "nowrap",
                }}
              >
                Active site: {activeProperty.address || activeProperty.primary_bbl} · {activeProperty.zoning_district || "No zone"}
              </span>
            )}
            {sources.length > 0 && (
              <span style={{ fontSize: 12, color: "var(--blue-light)" }}>
                {sources.length} source{sources.length !== 1 ? "s" : ""} used
              </span>
            )}
          </div>
        </header>

        {/* Messages */}
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "20px 24px",
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          {messages.length === 0 && !loading && <OnboardingGuide />}

          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} />
          ))}

          {loading && (
            <div className="animate-in" style={{ display: "flex", gap: 6, padding: "8px 0" }}>
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <ChatInput onSend={handleSend} disabled={loading} />
      </div>
    </div>
  );
}
