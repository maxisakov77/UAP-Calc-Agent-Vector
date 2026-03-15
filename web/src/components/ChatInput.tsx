"use client";

import { useState, useRef } from "react";

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled: boolean;
}

export default function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSubmit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleInput() {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }

  return (
    <div
      style={{
        padding: "12px 20px",
        borderTop: "1px solid var(--border-color)",
        background: "var(--header-bg)",
        display: "flex",
        gap: 10,
        alignItems: "flex-end",
      }}
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        placeholder="Ask about the site, zoning, UAP, 485-x, or the best development strategy..."
        disabled={disabled}
        rows={1}
        style={{
          flex: 1,
          resize: "none",
          background: "var(--bg-elevated)",
          border: "1px solid var(--border-color)",
          color: "var(--foreground)",
          padding: "10px 14px",
          fontSize: 14,
          lineHeight: 1.5,
          fontFamily: "var(--font-geist-sans), sans-serif",
          outline: "none",
        }}
      />
      <button
        onClick={handleSubmit}
        disabled={disabled || !value.trim()}
        style={{
          padding: "10px 20px",
          background: disabled || !value.trim() ? "var(--bg-elevated)" : "var(--blue)",
          border: "1px solid var(--border-color)",
          color: disabled || !value.trim() ? "var(--brand-granite-gray)" : "var(--foreground)",
          cursor: disabled || !value.trim() ? "not-allowed" : "pointer",
          fontSize: 14,
          fontWeight: 600,
          transition: "background 0.15s ease",
        }}
      >
        Send
      </button>
    </div>
  );
}
