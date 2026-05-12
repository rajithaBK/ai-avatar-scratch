export type JobStatus =
  | "queued"
  | "generating_audio"
  | "generating_video"
  | "completed"
  | "failed";

export interface JobState {
  job_id: string;
  status: JobStatus;
  message: string;
  video_url: string | null;
  mode: "real" | "mock";
  /** Full failure detail when status === "failed" (e.g. MuseTalk stderr). */
  error?: string | null;
}

export interface CreateJobResponse {
  job_id: string;
  status: JobStatus;
  mode: "real" | "mock";
}

const BASE = (import.meta as any).env?.VITE_BACKEND_URL ?? "";

function url(path: string): string {
  if (!BASE) return path;
  if (BASE.endsWith("/")) return BASE.slice(0, -1) + path;
  return BASE + path;
}

/** HTTP origin for the backend (no trailing slash), or browser origin when same-host. */
export function apiOrigin(): string {
  if (BASE) {
    const trimmed = BASE.endsWith("/") ? BASE.slice(0, -1) : BASE;
    return trimmed;
  }
  if (typeof window !== "undefined") {
    return window.location.origin.replace(/\/$/, "");
  }
  return "";
}

/** WebSocket URL for a backend path (e.g. ``/api/webrtc/<id>``). */
export function wsApiUrl(path: string): string {
  const origin = apiOrigin();
  const p = path.startsWith("/") ? path : `/${path}`;
  const u = new URL(origin + p);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  return u.toString();
}

export async function getHealth(): Promise<{ status: string }> {
  const res = await fetch(url("/api/health"));
  if (!res.ok) throw new Error(`health failed: ${res.status}`);
  return res.json();
}

export async function createJob(text: string): Promise<CreateJobResponse> {
  const res = await fetch(url("/api/jobs"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`createJob failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export async function getJob(jobId: string): Promise<JobState> {
  const res = await fetch(url(`/api/jobs/${jobId}`));
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`getJob failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export type IceServerDict = Record<string, string | string[] | undefined>;

export async function getWebRtcIceConfig(): Promise<IceServerDict[]> {
  const res = await fetch(url("/api/webrtc/config"));
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`getWebRtcIceConfig failed (${res.status}): ${detail}`);
  }
  const data = (await res.json()) as { iceServers?: IceServerDict[] };
  return Array.isArray(data.iceServers) ? data.iceServers : [];
}

/** Resolve a backend-relative path (like "/outputs/foo.mp4") to a full URL. */
export function resolveBackendUrl(path: string | null | undefined): string {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return url(path);
}
