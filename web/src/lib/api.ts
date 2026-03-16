const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Helper: fetch with a generous timeout and clear error messages
async function apiFetch(
  url: string,
  init?: RequestInit,
  timeoutMs = 120_000,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
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
  sources: { filename: string; distance: number; source_type?: "property" | "document" }[];
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
  const res = await apiFetch(
    `${API_BASE}/api/upload`,
    { method: "POST", body: form },
    600_000, // 10 min — large docs need embedding per chunk
  );
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

export interface PropertySearchResult {
  bbl: string;
  address: string;
  borough: string;
  zone: string;
  overlay: string;
  lotArea: number;
  builtFar: number;
  numFloors: number;
  yearBuilt: number;
  bldgClass: string;
  lat: number;
  lng: number;
}

export interface ValidatedLotInfo {
  bbl: string;
  address: string;
  lotArea: number;
  zone: string;
}

export interface BlockLotInfo {
  lot: number;
  address: string;
  lotArea: number;
  zone: string;
}

export interface PropertyScenario {
  code: string;
  label: string;
  max_res_floor_area: number;
  max_number_of_units: number;
  affordable_floor_area: number;
  affordable_floor_area_uap: number;
  affordable_floor_area_485x: number;
  affordable_units_percentage: number;
  affordable_units_total: number;
  market_rate_units: number;
  ami_breakdown: { ami: number; units: number }[];
  triggers_prevailing_wages: boolean;
  triggers_40_ami: boolean;
  is_uap_eligible: boolean;
  available: boolean;
  notes: string[];
}

export interface PropertyLotRecord {
  bbl: string;
  borough: string;
  block: string;
  lot: string;
  address: string;
  zoning: string;
  overlay1?: string | null;
  overlay2?: string | null;
  lot_area: number;
  building_area: number;
  res_far: number;
  units_total: number;
  year_built?: number | null;
  assessed_value?: number | null;
  market_value?: number | null;
  dof_taxable?: number | null;
  has_pluto: boolean;
  has_dof: boolean;
  lot_type_code?: number | null;
  lot_type: string;
}

export interface PropertyContext {
  primary_bbl: string;
  adjacent_bbls: string[];
  selected_bbls: string[];
  address: string;
  borough: string;
  block: string;
  lots: string[];
  zoning_district: string;
  overlay: string;
  overlay_far?: number | null;
  community_facility_far?: number | null;
  standard_far?: number | null;
  qah_far?: number | null;
  standard_height_limit?: number | null;
  qah_height_limit?: number | null;
  lot_coverage_corner?: number | null;
  lot_coverage_interior?: number | null;
  street_type_assumption: string;
  has_narrow_wide: boolean;
  lot_type: string;
  lot_area: number;
  building_area: number;
  units_total: number;
  assessed_value?: number | null;
  market_value?: number | null;
  dof_taxable?: number | null;
  scenarios: PropertyScenario[];
  lots_detail: PropertyLotRecord[];
  sources: Record<string, unknown>;
  property_brief: string;
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

export async function searchPropertyAddress(query: string): Promise<PropertySearchResult[]> {
  const res = await apiFetch(`${API_BASE}/api/property/search-address?q=${encodeURIComponent(query)}`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Property search failed (${res.status}): ${detail}`);
  }
  const payload = await res.json();
  return Array.isArray(payload.results) ? payload.results : [];
}

export async function validatePropertyLot(bbl: string): Promise<ValidatedLotInfo> {
  const res = await apiFetch(`${API_BASE}/api/property/validate-lot?bbl=${encodeURIComponent(bbl)}`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Lot validation failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function getBlockLots(borough: number, block: number): Promise<BlockLotInfo[]> {
  const qp = new URLSearchParams({ borough: String(borough), block: String(block) });
  const res = await apiFetch(`${API_BASE}/api/property/block-lots?${qp.toString()}`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Block lot lookup failed (${res.status}): ${detail}`);
  }
  const payload = await res.json();
  return Array.isArray(payload.lots) ? payload.lots : [];
}

export async function setPropertyContext(primaryBbl: string, adjacentBbls: string[] = []): Promise<PropertyContext> {
  const res = await apiFetch(`${API_BASE}/api/property/context`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ primary_bbl: primaryBbl, adjacent_bbls: adjacentBbls }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Set property context failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function getPropertyContext(): Promise<PropertyContext | null> {
  const res = await apiFetch(`${API_BASE}/api/property/context`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Get property context failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function clearPropertyContext(): Promise<{ cleared: boolean }> {
  const res = await apiFetch(`${API_BASE}/api/property/context`, { method: "DELETE" });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Clear property context failed (${res.status}): ${detail}`);
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

// ── Underwriting Template ──────────────────────────────────────────────

export interface TemplateCell {
  v: string | number | boolean | null;
  r: number;
  c: number;
  f?: boolean;
}

export interface TemplateSheet {
  name: string;
  data: (TemplateCell | null)[][];
  maxRow: number;
  maxCol: number;
}

export interface ParsedTemplate {
  filename: string;
  sheets: TemplateSheet[];
}

export interface ExtractionResult {
  updates: Record<string, Record<string, string | number>>;
  sources?: Record<string, Record<string, string>>;
  message?: string;
}

export interface UnderwritingRecalculationWarning {
  sheet: string;
  message: string;
  refs?: string[];
}

export interface UnderwritingRecalculationResult {
  formulaValues: Record<
    string,
    Record<string, string | number | boolean | null>
  >;
  warnings?: UnderwritingRecalculationWarning[];
}

export async function parseUnderwritingTemplate(file: File): Promise<ParsedTemplate> {
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(
    `${API_BASE}/api/underwriting/parse-template`,
    { method: "POST", body: form },
    300_000,
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Template parse failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function extractUnderwritingValues(): Promise<ExtractionResult> {
  const res = await apiFetch(
    `${API_BASE}/api/underwriting/extract`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
    600_000,
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Extraction failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function recalculateUnderwritingFormulaValues(
  updates: Record<string, Record<string, string | number>>,
): Promise<UnderwritingRecalculationResult> {
  const res = await apiFetch(
    `${API_BASE}/api/underwriting/recalculate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates }),
    },
    300_000,
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Formula recalculation failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function downloadFilledTemplate(
  updates: Record<string, Record<string, string | number>>,
): Promise<Blob> {
  const res = await apiFetch(
    `${API_BASE}/api/underwriting/download`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ updates }),
    },
  );
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Download failed (${res.status}): ${detail}`);
  }
  return res.blob();
}
