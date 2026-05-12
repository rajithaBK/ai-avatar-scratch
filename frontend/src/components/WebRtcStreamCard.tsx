import { useCallback, useEffect, useRef, useState } from "react";
import type { JobState } from "../lib/api";
import { getWebRtcIceConfig, wsApiUrl } from "../lib/api";

type WsMsg =
  | { type: "answer"; sdp: string; sdpType: RTCSdpType }
  | { type: "ice"; candidate: string | null; sdpMid?: string | null; sdpMLineIndex?: number | null }
  | { type: "error"; message: string };

type StreamState = "idle" | "connecting" | "streaming" | "error";

interface Props {
  job: JobState | null;
}

/**
 * Optional WebRTC playback of the completed MP4 (server streams file-based
 * tracks over a peer connection). Falls back to the HTML5 ``<video src>`` path
 * in ``AvatarVideoCard`` when WebRTC is not used.
 */
export default function WebRtcStreamCard({ job }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const [state, setState] = useState<StreamState>("idle");
  const [wsError, setWsError] = useState<string | null>(null);

  const teardown = useCallback(() => {
    try {
      wsRef.current?.close();
    } catch {
      /* ignore */
    }
    wsRef.current = null;

    if (pcRef.current) {
      try {
        pcRef.current.getSenders().forEach((s) => s.track?.stop());
      } catch {
        /* ignore */
      }
      try {
        pcRef.current.close();
      } catch {
        /* ignore */
      }
      pcRef.current = null;
    }

    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;

    const v = videoRef.current;
    if (v) {
      v.srcObject = null;
    }
    setState("idle");
  }, []);

  useEffect(() => () => teardown(), [teardown]);

  useEffect(() => {
    teardown();
    setWsError(null);
  }, [job?.job_id, teardown]);

  const startStream = useCallback(async () => {
    if (!job || job.status !== "completed") return;
    teardown();
    setWsError(null);
    setState("connecting");

    let iceServers: RTCIceServer[];
    try {
      iceServers = (await getWebRtcIceConfig()) as unknown as RTCIceServer[];
    } catch (e) {
      setWsError(e instanceof Error ? e.message : String(e));
      setState("error");
      return;
    }

    const pc = new RTCPeerConnection({ iceServers });
    pcRef.current = pc;

    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });

    pc.ontrack = (ev) => {
      const v = videoRef.current;
      if (!v) return;
      if (!mediaStreamRef.current) {
        mediaStreamRef.current = new MediaStream();
      }
      mediaStreamRef.current.addTrack(ev.track);
      v.srcObject = mediaStreamRef.current;
      setState("streaming");
      void v.play().catch(() => undefined);
    };

    pc.onicecandidate = (ev) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      if (ev.candidate) {
        ws.send(
          JSON.stringify({
            type: "ice",
            candidate: ev.candidate.candidate,
            sdpMid: ev.candidate.sdpMid,
            sdpMLineIndex: ev.candidate.sdpMLineIndex,
          })
        );
      } else {
        ws.send(JSON.stringify({ type: "ice", candidate: null }));
      }
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const ws = new WebSocket(wsApiUrl(`/api/webrtc/${job.job_id}`));
    wsRef.current = ws;

    ws.onmessage = async (evt) => {
      let msg: WsMsg;
      try {
        msg = JSON.parse(String(evt.data)) as WsMsg;
      } catch {
        return;
      }
      if (msg.type === "error") {
        setWsError(msg.message);
        setState("error");
        teardown();
        return;
      }
      if (msg.type === "answer") {
        await pc.setRemoteDescription({ type: msg.sdpType, sdp: msg.sdp });
        return;
      }
      if (msg.type === "ice") {
        if (msg.candidate == null) {
          await pc.addIceCandidate(null);
          return;
        }
        const init: RTCIceCandidateInit = {
          candidate: msg.candidate,
          sdpMid: msg.sdpMid ?? undefined,
          sdpMLineIndex: msg.sdpMLineIndex ?? undefined,
        };
        await pc.addIceCandidate(init);
      }
    };

    try {
      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        ws.onerror = () => reject(new Error("WebSocket failed to open"));
      });
    } catch (e) {
      setWsError(e instanceof Error ? e.message : String(e));
      setState("error");
      teardown();
      return;
    }

    ws.send(
      JSON.stringify({
        type: "offer",
        sdp: pc.localDescription?.sdp,
        sdpType: "offer",
      })
    );
  }, [job, teardown]);

  const canStart = Boolean(job?.job_id && job.status === "completed");

  return (
    <section className="card video-card" aria-label="WebRTC stream">
      <div className="brand-subtitle" style={{ display: "flex", justifyContent: "space-between" }}>
        <span>WebRTC stream</span>
        {job?.job_id ? (
          <span style={{ color: "var(--fg-1)", fontSize: 12 }} data-testid="webrtc-job-id">
            Job {job.job_id.slice(0, 8)}
          </span>
        ) : null}
      </div>

      <p style={{ fontSize: 14, marginTop: 0, color: "var(--fg-1)" }}>
        Streams the finished MP4 over WebRTC (same encode as download). Tunneled or strict NAT setups
        may need TURN in <code>WEBRTC_ICE_SERVERS</code> — see docs/TROUBLESHOOTING.md.
      </p>

      <div className="video-frame" style={{ position: "relative" }}>
        <video
          ref={videoRef}
          controls
          playsInline
          muted={false}
          data-testid="webrtc-video"
          style={{ width: "100%", display: state === "idle" ? "none" : "block" }}
        />
        {state === "idle" ? (
          <div className="video-placeholder">
            <p style={{ fontSize: 16, margin: 0 }}>Press &quot;Start WebRTC&quot; after a job completes.</p>
          </div>
        ) : null}
      </div>

      {wsError ? (
        <p style={{ color: "#f87171", fontSize: 14 }} data-testid="webrtc-error">
          {wsError}
        </p>
      ) : null}

      <div className="actions" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!canStart || state === "connecting"}
          onClick={() => void startStream()}
          data-testid="webrtc-start"
        >
          {state === "connecting" ? "Connecting…" : "Start WebRTC"}
        </button>
        <button
          type="button"
          className="btn"
          disabled={state === "idle"}
          onClick={teardown}
          data-testid="webrtc-stop"
        >
          Stop
        </button>
      </div>

      <p style={{ fontSize: 13, marginBottom: 0, color: "var(--fg-1)" }} data-testid="webrtc-state">
        State: {state}
      </p>
    </section>
  );
}
