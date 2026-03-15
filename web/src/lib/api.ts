const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Helper: fetch with a generous timeout and clear error messages
async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120_000); // 2 min global max
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("Request timed out — is the backend running?");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  reply: string;
  sources: { filename: string; distance: number }[];
}

export interface DocumentInfo {
  filename: string;
  chunks: number;
}

export interface DocumentsResponse {
  documents: DocumentInfo[];
  total_chunks: number;
}

export interface UploadResponse {
  filename: string;
  chunks: number;
}

export async function sendChat(
  messages: ChatMessage[],
  useRag: boolean = true,
): Promise<ChatResponse> {
  const res = await apiFetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, use_rag: useRag }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Chat failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Upload failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function listDocuments(): Promise<DocumentsResponse> {
  const res = await apiFetch(`${API_BASE}/api/documents`);
  if (!res.ok) throw new Error(`Failed to list documents (${res.status})`);
  return res.json();
}

export async function deleteDocument(filename: string): Promise<void> {
  const res = await apiFetch(
    `${API_BASE}/api/documents/${encodeURIComponent(filename)}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(`Failed to delete document (${res.status})`);
}

export async function checkHealth(): Promise<{ status: string; documents: number }> {
  const res = await apiFetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error("Backend unavailable");
  return res.json();
}

// ── Agent Settings ─────────────────────────────────────────────────────

export interface AgentSettingsMap {
  [agentName: string]: {
    [key: string]: number | string;
  };
}

export async function getAgentSettings(): Promise<{ settings: AgentSettingsMap }> {
  const res = await apiFetch(`${API_BASE}/api/settings`);
  if (!res.ok) throw new Error(`Failed to get settings (${res.status})`);
  return res.json();
}

export async function updateAgentSettings(
  settings: AgentSettingsMap,
): Promise<{ settings: AgentSettingsMap }> {
  const res = await apiFetch(`${API_BASE}/api/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Update settings failed (${res.status}): ${detail}`);
  }
  return res.json();
}

// ── Pinecone Index Management ──────────────────────────────────────────

export interface PineconeIndex {
  name: string;
  dimension: number;
  metric: string;
  host: string;
  ready: boolean;
  state: string;
}

export interface IndexListResponse {
  indexes: PineconeIndex[];
  active: string;
}

export interface ActiveIndexResponse {
  name: string;
  total_vectors: number;
  dimension: number;
  namespaces: Record<string, { vector_count: number }>;
}

export async function listIndexes(): Promise<IndexListResponse> {
  const res = await apiFetch(`${API_BASE}/api/indexes`);
  if (!res.ok) throw new Error(`Failed to list indexes (${res.status})`);
  return res.json();
}

export async function getActiveIndex(): Promise<ActiveIndexResponse> {
  const res = await apiFetch(`${API_BASE}/api/indexes/active`);
  if (!res.ok) throw new Error(`Failed to get active index (${res.status})`);
  return res.json();
}

export async function createIndex(
  name: string,
  dimension: number = 3072,
  metric: string = "cosine",
  cloud: string = "aws",
  region: string = "us-east-1",
): Promise<{ created: string }> {
  const res = await apiFetch(`${API_BASE}/api/indexes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, dimension, metric, cloud, region }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Create index failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function deleteIndex(name: string): Promise<{ deleted: string }> {
  const res = await apiFetch(`${API_BASE}/api/indexes/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Delete index failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function switchIndex(name: string): Promise<{ active: string }> {
  const res = await apiFetch(`${API_BASE}/api/indexes/switch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Switch index failed (${res.status}): ${detail}`);
  }
  return res.json();
}

// ── Blueprint Management (ContextLibrary) ──────────────────────────────

export interface Blueprint {
  id: string;
  subject: string;
  instructions: string;
}

export async function listBlueprints(): Promise<{ blueprints: Blueprint[] }> {
  const res = await apiFetch(`${API_BASE}/api/blueprints`);
  if (!res.ok) throw new Error(`Failed to list blueprints (${res.status})`);
  return res.json();
}

export async function createBlueprint(
  subject: string,
  instructions: string,
): Promise<{ id: string; subject: string }> {
  const res = await apiFetch(`${API_BASE}/api/blueprints`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject, instructions }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Create blueprint failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function generateBlueprint(
  subject: string,
): Promise<{ id: string; subject: string; instructions: string }> {
  const res = await apiFetch(`${API_BASE}/api/blueprints/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Generate blueprint failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function deleteBlueprint(id: string): Promise<{ deleted: string }> {
  const res = await apiFetch(`${API_BASE}/api/blueprints/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Delete blueprint failed (${res.status}): ${detail}`);
  }
  return res.json();
}
