import type { JobState } from "../lib/api";

interface Props {
  job: JobState | null;
  errorMessage: string | null;
}

const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  generating_audio: "Generating audio (Kokoro TTS)",
  generating_video: "Generating video (MuseTalk lip-sync)",
  completed: "Completed",
  failed: "Failed",
};

export function JobStatusPanel({ job, errorMessage }: Props) {
  if (errorMessage && !job) {
    return (
      <div className="status-banner fail" role="status" data-testid="status-banner">
        <span style={{ fontSize: 18 }}>{errorMessage}</span>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="status-banner" role="status" data-testid="status-banner">
        <span style={{ color: "var(--fg-1)" }}>Ready to generate.</span>
      </div>
    );
  }

  const klass =
    job.status === "completed" ? "ok" : job.status === "failed" ? "fail" : "";
  const showSpinner =
    job.status === "queued" ||
    job.status === "generating_audio" ||
    job.status === "generating_video";

  return (
    <div className={`status-banner ${klass}`} role="status" data-testid="status-banner">
      {showSpinner && <span className="spinner" aria-hidden="true" />}
      <span style={{ flex: 1 }}>
        <strong>{STATUS_LABELS[job.status] ?? job.status}</strong>
        {job.message && job.message !== job.status ? (
          <span style={{ color: "var(--fg-1)" }}> — {job.message}</span>
        ) : null}
      </span>
      <span className={`status-pill ${job.mode}`} data-testid="job-mode-pill">
        {job.mode.toUpperCase()}
      </span>
    </div>
  );
}

export default JobStatusPanel;
