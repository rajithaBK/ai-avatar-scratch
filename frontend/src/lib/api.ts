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

/** Resolve a backend-relative path (like "/outputs/foo.mp4") to a full URL. */
export function resolveBackendUrl(path: string | null | undefined): string {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  return url(path);
}
