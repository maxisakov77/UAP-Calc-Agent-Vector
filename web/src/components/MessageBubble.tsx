"use client";

import type { ChatMessage } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div
      className="animate-in"
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
      }}
    >
      <div
        style={{
          maxWidth: "75%",
          padding: "12px 16px",
          border: `1px solid ${isUser ? "var(--blue)" : "var(--glass-border)"}`,
          background: isUser ? "var(--blue-dark)" : "var(--bg-card)",
          color: "var(--foreground)",
          fontSize: 14,
          lineHeight: 1.6,
          wordBreak: "break-word",
        }}
      >
        <span
          style={{
            display: "block",
            fontSize: 11,
            fontWeight: 600,
            marginBottom: 4,
            color: isUser ? "var(--blue-accent)" : "var(--blue-light)",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          {isUser ? "You" : "Assistant"}
        </span>
        {isUser ? (
          <div style={{ whiteSpace: "pre-wrap" }}>{message.content}</div>
        ) : (
          <div className="assistant-markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ children, href, ...props }) => (
                  <a
                    {...props}
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {children}
                  </a>
                ),
                table: ({ children, ...props }) => (
                  <div className="assistant-table-wrap">
                    <table {...props}>{children}</table>
                  </div>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
