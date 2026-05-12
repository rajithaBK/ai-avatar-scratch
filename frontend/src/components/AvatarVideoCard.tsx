import { useEffect, useRef, useState } from "react";
import type { JobState } from "../lib/api";
import { resolveBackendUrl } from "../lib/api";
import JobStatusPanel from "./JobStatusPanel";

interface Props {
  job: JobState | null;
  errorMessage: string | null;
}

export function AvatarVideoCard({ job, errorMessage }: Props) {
  const videoSrc = job?.video_url ? resolveBackendUrl(job.video_url) : "";
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [isMuted, setIsMuted] = useState(false);

  // Try to autoplay unmuted; if the browser blocks it (most do without a
  // recent user gesture), fall back to muted autoplay so the user still
  // sees the video and can press the unmute button.
  useEffect(() => {
    const v = videoRef.current;
    if (!v || job?.status !== "completed" || !videoSrc) return;
    v.muted = false;
    v.volume = 1.0;
    setIsMuted(false);
    const playUnmuted = v.play();
    if (playUnmuted && typeof playUnmuted.then === "function") {
      playUnmuted.catch(() => {
        v.muted = true;
        setIsMuted(true);
        v.play().catch(() => {
          /* user can press play manually */
        });
      });
    }
  }, [videoSrc, job?.status]);

  const unmute = () => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = false;
    v.volume = 1.0;
    setIsMuted(false);
    v.play().catch(() => undefined);
  };

  return (
    <section className="card video-card" aria-label="Generated video">
      <div className="brand-subtitle" style={{ display: "flex", justifyContent: "space-between" }}>
        <span>Generated Video</span>
        {job?.job_id ? (
          <span style={{ color: "var(--fg-1)", fontSize: 12 }} data-testid="job-id">
            Job {job.job_id.slice(0, 8)}
          </span>
        ) : null}
      </div>

      <div className="video-frame" style={{ position: "relative" }}>
        {job?.status === "completed" && videoSrc ? (
          <>
            <video
              ref={videoRef}
              controls
              autoPlay
              playsInline
              src={videoSrc}
              data-testid="avatar-video"
            />
            {isMuted && (
              <button
                type="button"
                onClick={unmute}
                data-testid="unmute-button"
                style={{
                  position: "absolute",
                  top: 16,
                  right: 16,
                  padding: "10px 18px",
                  borderRadius: 999,
                  border: "1px solid rgba(255,255,255,0.2)",
                  background: "rgba(0,0,0,0.55)",
                  backdropFilter: "blur(8px)",
                  color: "#fff",
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Tap to unmute
              </button>
            )}
          </>
        ) : (
          <div className="video-placeholder">
            <p style={{ fontSize: 18, margin: 0 }}>
              {job ? "Video will appear here when generation completes." : "Type a message and press Generate to begin."}
            </p>
            <p style={{ fontSize: 14, marginTop: 12, color: "var(--fg-1)" }}>
              Webex Desk friendly · MP4 download · Optional WebRTC playback after render
            </p>
          </div>
        )}
      </div>

      <JobStatusPanel job={job} errorMessage={errorMessage} />

      <div className="actions">
        <a
          className={`btn btn-primary ${job?.status === "completed" && videoSrc ? "" : "disabled"}`}
          href={videoSrc || "#"}
          download={job?.job_id ? `${job.job_id}.mp4` : undefined}
          aria-disabled={job?.status !== "completed" || !videoSrc}
          style={{
            pointerEvents: job?.status === "completed" && videoSrc ? "auto" : "none",
            opacity: job?.status === "completed" && videoSrc ? 1 : 0.55,
            textDecoration: "none",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
          }}
          data-testid="download-button"
        >
          Download MP4
        </a>
      </div>
    </section>
  );
}

export default AvatarVideoCard;
