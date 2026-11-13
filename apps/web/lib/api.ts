export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type User = {
  id: string;
  email: string;
  name: string;
  plan: string;
  credits: number;
  ipfs_configured: boolean;
};

export type Project = {
  id: string;
  name: string;
  description: string;
  project_type: string;
  canvas_width: number;
  canvas_height: number;
  license: string;
  ai_disclosure: string;
  role: string;
  asset_count: number;
  collection_count: number;
  updated_at: string | null;
};

export type Asset = {
  id: string;
  original_name: string;
  width: number;
  height: number;
  sha256: string;
  kind: string;
  size: number;
  url: string;
  thumb_url: string;
  parent_asset_id?: string | null;
};

export type Trait = {
  id: string;
  category_id: string;
  name: string;
  weight: number;
  exact_count: number | null;
  always_include: boolean;
  rarity_label: string;
  url: string | null;
};

export type Category = {
  id: string;
  name: string;
  z_index: number;
  optional: boolean;
  none_weight: number;
  traits: Trait[];
};

export type Rule = { id: string; rule_type: string; trait_a_id: string; trait_b_id: string };

export type Collection = {
  id: string;
  name: string;
  supply: number;
  seed: number;
  mode: string;
  description_template: string;
  image_base_uri: string;
  external_url: string;
  symbol: string;
  metadata_schema: string;
  marketplace_profile: string;
  status: string;
};

export type NftItem = {
  id: string;
  token_id: number;
  image_url: string | null;
  thumb_url: string | null;
  attributes: { trait_type: string; value: string }[];
  metadata: Record<string, unknown> | null;
  changes: { previous?: string; next?: string }[];
};

export type Job = {
  id: string;
  kind: string;
  status: string;
  progress: number;
  error: string | null;
  attempts: number;
  result: { outputs?: { asset_id: string; name: string }[]; cids?: Record<string, { image_uri?: string; metadata_uri?: string }>; report?: Report } | null;
};

export type Report = {
  status: string;
  blocking: { code: string; message: string }[];
  warnings: { code: string; message: string }[];
  near_duplicates: { token_a: number; token_b: number; distance: number }[];
  distribution?: { name: string; traits: { name: string; count: number; percent: number; target_percent: number }[] }[];
  rendered?: number;
  supply?: number;
};

export function fileUrl(path: string | null | undefined) {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return `${API_URL}${path}`;
}

function detailMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item?.msg || JSON.stringify(item)).join(" ");
  if (detail && typeof detail === "object" && "message" in detail) {
    const record = detail as { message: string; suggestions?: string[] };
    return record.suggestions?.length ? `${record.message}. ${record.suggestions[0]}` : record.message;
  }
  return "Request failed";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = typeof window === "undefined" ? null : localStorage.getItem("nft_token");
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  const contentType = response.headers.get("content-type") || "";
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") localStorage.removeItem("nft_token");
    let message = response.statusText;
    if (contentType.includes("json")) {
      const body = await response.json();
      message = detailMessage(body.detail);
    }
    throw new Error(message);
  }
  if (contentType.includes("json")) return response.json();
  return (await response.blob()) as T;
}

export function saveSession(token: string, user: User) {
  localStorage.setItem("nft_token", token);
  localStorage.setItem("nft_user", JSON.stringify(user));
}

export function currentUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("nft_user");
  return raw ? (JSON.parse(raw) as User) : null;
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function pollJob(jobId: string): Promise<Job> {
  for (let attempt = 0; attempt < 240; attempt += 1) {
    const job = await api<Job>(`/api/jobs/${jobId}`);
    if (job.status === "succeeded" || job.status === "failed") return job;
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
  throw new Error("The job is still running. Check it again from the project.");
}
