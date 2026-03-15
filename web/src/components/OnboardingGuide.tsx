"use client";

const steps = [
  {
    number: 1,
    title: "Select a Project",
    description:
      "Choose an existing Pinecone index or create a new one. Each project is an isolated vector space — documents and conversations stay separate between projects.",
    action: "Use the Project dropdown at the top of the sidebar.",
    icon: "📂",
  },
  {
    number: 2,
    title: "Upload Documents",
    description:
      "Add files to build your knowledge base. Supported formats include PDF, DOCX, XLSX, TXT, Markdown, JSON, Python, and many more. Files are automatically chunked and embedded into vectors.",
    action: 'Click "+ Upload Files" at the bottom of the sidebar.',
    icon: "📄",
  },
  {
    number: 3,
    title: "Set a Blueprint",
    description:
      "Blueprints are writing instructions that tell the Writer agent how to format and style its responses. You can type a subject and auto-generate one with AI, or write your own.",
    action: "Open the Blueprints section in the sidebar.",
    icon: "📐",
  },
  {
    number: 4,
    title: "Tune Agent Settings",
    description:
      "Each agent in the pipeline has tunable parameters. Adjust the Librarian's retrieval depth, the Researcher's creativity, or the Writer's temperature to control output style.",
    action: "Expand Agent Settings and move the sliders.",
    icon: "⚙️",
  },
  {
    number: 5,
    title: "Ask a Question",
    description:
      "Type your question below. The multi-agent system will plan the task, retrieve relevant context from your documents, research an answer, and compose a final response.",
    action: "Type in the chat input and press Enter.",
    icon: "💬",
  },
];

export default function OnboardingGuide() {
  return (
    <div className="animate-in" style={{ maxWidth: 620, margin: "0 auto", padding: "40px 0" }}>
      {/* Header */}
      <h2
        style={{
          margin: 0,
          fontSize: 22,
          fontWeight: 700,
          color: "var(--blue-accent)",
          textAlign: "center",
        }}
      >
        Getting Started
      </h2>
      <p
        style={{
          margin: "8px 0 32px",
          fontSize: 14,
          color: "var(--brand-granite-gray)",
          textAlign: "center",
          lineHeight: 1.5,
        }}
      >
        Follow these steps to set up your workspace and start chatting with your documents.
      </p>

      {/* Steps */}
      <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
        {steps.map((step, idx) => (
          <div key={step.number} style={{ display: "flex", gap: 16 }}>
            {/* Left: number line */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                width: 36,
                flexShrink: 0,
              }}
            >
              {/* Circle */}
              <div
                style={{
                  width: 36,
                  height: 36,
                  border: "2px solid var(--blue-accent)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 15,
                  fontWeight: 700,
                  color: "var(--blue-accent)",
                  background: "var(--bg-dark)",
                  flexShrink: 0,
                }}
              >
                {step.number}
              </div>

              {/* Connector line */}
              {idx < steps.length - 1 && (
                <div
                  style={{
                    flex: 1,
                    width: 2,
                    background: "var(--border-color)",
                    minHeight: 20,
                  }}
                />
              )}
            </div>

            {/* Right: content card */}
            <div
              style={{
                flex: 1,
                padding: "10px 14px 20px",
                marginBottom: idx < steps.length - 1 ? 0 : 0,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 16 }}>{step.icon}</span>
                <h3
                  style={{
                    margin: 0,
                    fontSize: 15,
                    fontWeight: 600,
                    color: "var(--foreground)",
                  }}
                >
                  {step.title}
                </h3>
              </div>
              <p
                style={{
                  margin: "0 0 6px",
                  fontSize: 13,
                  color: "var(--brand-granite-gray)",
                  lineHeight: 1.55,
                }}
              >
                {step.description}
              </p>
              <span
                style={{
                  fontSize: 12,
                  color: "var(--blue-light)",
                  fontStyle: "italic",
                }}
              >
                {step.action}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Pipeline diagram */}
      <div
        style={{
          marginTop: 32,
          padding: "16px 20px",
          background: "var(--bg-card)",
          border: "1px solid var(--glass-border)",
        }}
      >
        <p
          style={{
            margin: "0 0 10px",
            fontSize: 12,
            fontWeight: 600,
            color: "var(--blue-accent)",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          Multi-Agent Pipeline
        </p>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 0,
            flexWrap: "wrap",
          }}
        >
          {["Planner", "Librarian", "Researcher", "Writer"].map((agent, i) => (
            <div key={agent} style={{ display: "flex", alignItems: "center" }}>
              <div
                style={{
                  padding: "6px 14px",
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border-color)",
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--foreground)",
                  whiteSpace: "nowrap",
                }}
              >
                {agent}
              </div>
              {i < 3 && (
                <span
                  style={{
                    padding: "0 6px",
                    fontSize: 14,
                    color: "var(--brand-granite-gray)",
                  }}
                >
                  →
                </span>
              )}
            </div>
          ))}
        </div>
        <p
          style={{
            margin: "10px 0 0",
            fontSize: 11,
            color: "var(--brand-granite-gray)",
            textAlign: "center",
            lineHeight: 1.5,
          }}
        >
          Your question flows through each agent: planning the task, retrieving context, researching
          an answer, and composing the final response.
        </p>
      </div>
    </div>
  );
}
