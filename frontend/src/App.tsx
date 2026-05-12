import { useCallback, useEffect, useRef, useState } from "react";
import TextInputPanel from "./components/TextInputPanel";
import AvatarVideoCard from "./components/AvatarVideoCard";
import { createJob, getHealth, getJob, JobState } from "./lib/api";

type Connection = "checking" | "ok" | "bad";

const POLL_INTERVAL_MS = 1500;
// Hard upper bound to avoid runaway polling if the backend is wedged.
const POLL_MAX_MS = 15 * 60 * 1000;

export default function App() {
  const [text, setText] = useState(
    "Hello! Welcome to the demo. I am your AI assistant on a Webex Desk device."
  );
  const [job, setJob] = useState<JobState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connection, setConnection] = useState<Connection>("checking");
  const pollerRef = useRef<number | null>(null);
  const pollStartedAtRef = useRef<number>(0);

  const stopPolling = useCallback(() => {
    if (pollerRef.current !== null) {
      window.clearTimeout(pollerRef.current);
      pollerRef.current = null;
    }
  }, []);

  const checkHealth = useCallback(async () => {
    try {
      const r = await getHealth();
      setConnection(r.status === "ok" ? "ok" : "bad");
    } catch (e) {
      setConnection("bad");
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const id = window.setInterval(checkHealth, 10_000);
    return () => window.clearInterval(id);
  }, [checkHealth]);

  useEffect(() => stopPolling, [stopPolling]);

  const pollJob = useCallback(
    (jobId: string) => {
      const tick = async () => {
        try {
          const j = await getJob(jobId);
          setJob(j);
          if (j.status === "completed" || j.status === "failed") {
            stopPolling();
            return;
          }
          if (Date.now() - pollStartedAtRef.current > POLL_MAX_MS) {
            setError("Generation is taking longer than expected. Check backend logs.");
            stopPolling();
            return;
          }
          pollerRef.current = window.setTimeout(tick, POLL_INTERVAL_MS);
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e));
          stopPolling();
        }
      };
      pollStartedAtRef.current = Date.now();
      pollerRef.current = window.setTimeout(tick, 0);
    },
    [stopPolling]
  );

  const onGenerate = useCallback(async () => {
    setError(null);
    setJob(null);
    stopPolling();
    if (text.trim().length === 0) {
      setError("Please enter some text to speak.");
      return;
    }
    try {
      const created = await createJob(text);
      setJob({
        job_id: created.job_id,
        status: created.status,
        message: "queued",
        video_url: null,
        error: null,
        // Use the mode echoed by the backend so we never flash "REAL"
        // on a mock-mode job.
        mode: created.mode,
      });
      pollJob(created.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [text, pollJob, stopPolling]);

  const onClear = useCallback(() => {
    setText("");
    setJob(null);
    setError(null);
    stopPolling();
  }, [stopPolling]);

  const isGenerating =
    job?.status === "queued" ||
    job?.status === "generating_audio" ||
    job?.status === "generating_video";

  return (
    <div className="app">
      <header className="topbar" role="banner">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">AI</div>
          <div>
            <div className="brand-title">AI Avatar Demo</div>
            <div className="brand-subtitle">Local · open-source · Webex Desk-friendly</div>
          </div>
        </div>
        <div
          className={`connection ${connection === "ok" ? "ok" : connection === "bad" ? "bad" : ""}`}
          role="status"
          aria-live="polite"
          data-testid="connection-status"
        >
          <span className="dot" />
          {connection === "ok"
            ? "Backend connected"
            : connection === "bad"
            ? "Backend unreachable"
            : "Checking backend..."}
        </div>
      </header>

      <main className="main" role="main">
        <TextInputPanel
          text={text}
          onTextChange={setText}
          onGenerate={onGenerate}
          onClear={onClear}
          isGenerating={isGenerating}
          disabled={connection === "bad"}
          errorMessage={error}
        />

        <AvatarVideoCard job={job} errorMessage={error} />
      </main>

      <footer className="footer">
        Local pipeline: Kokoro TTS → MuseTalk → MP4 · No external APIs.
      </footer>
    </div>
  );
}
