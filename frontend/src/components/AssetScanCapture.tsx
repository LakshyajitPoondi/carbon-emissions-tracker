import { useEffect, useRef, useState } from "react";
import { apiClient } from "../api";
import type { EmissionSource } from "../types";
import { ErrorBanner } from "./ErrorBanner";
import { LoadingState } from "./LoadingState";

type ScanStatus =
  | "closed"
  | "requesting-camera"
  | "camera-ready"
  | "scanning"
  | "camera-denied"
  | "matched"
  | "scan-error";

interface AssetScanCaptureProps {
  facilityId: number;
  /** Called immediately on a successful match — the parent form
   * auto-selects this source. The scan panel stays open afterward so the
   * user can visually confirm before submitting (see docs/api-contract.md's
   * Asset Scan section and the frontend task's requirement #3). */
  onMatched: (source: EmissionSource, decodedValue: string) => void;
}

function canvasToBlob(canvas: HTMLCanvasElement, type: string, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

function describeCameraError(err: unknown): string {
  if (err instanceof DOMException) {
    if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
      return "Camera access was denied. You can still select the emission source manually below.";
    }
    if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
      return "No camera was found on this device. Select the emission source manually below.";
    }
  }
  return "Could not access the camera. Select the emission source manually below.";
}

export function AssetScanCapture({ facilityId, onMatched }: AssetScanCaptureProps) {
  const [status, setStatus] = useState<ScanStatus>("closed");
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [scanError, setScanError] = useState<unknown>(null);
  const [matchedResult, setMatchedResult] = useState<{
    source: EmissionSource;
    decodedValue: string;
  } | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  function stopStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  // Belt-and-suspenders: stop the camera if this component unmounts
  // outright (user navigates away from Consumption entirely) regardless of
  // whatever scan state it was in — never leave the camera light on.
  useEffect(() => stopStream, []);

  async function openScanner() {
    setStatus("requesting-camera");
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      streamRef.current = stream;
      setStatus("camera-ready");
    } catch (err) {
      setCameraError(describeCameraError(err));
      setStatus("camera-denied");
    }
  }

  function closeScanner() {
    stopStream();
    setStatus("closed");
    setCameraError(null);
    setScanError(null);
    setMatchedResult(null);
  }

  function handleRetry() {
    setScanError(null);
    setMatchedResult(null);
    setStatus("camera-ready");
  }

  async function handleCapture() {
    const video = videoRef.current;
    if (!video) return;
    setStatus("scanning");
    setScanError(null);

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      setScanError(new Error("Could not capture a frame from the camera."));
      setStatus("camera-ready");
      return;
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const blob = await canvasToBlob(canvas, "image/jpeg", 0.9);
    if (!blob) {
      setScanError(new Error("Could not capture a frame from the camera."));
      setStatus("camera-ready");
      return;
    }

    try {
      const result = await apiClient.scanAsset(facilityId, blob);
      setMatchedResult({ source: result.emission_source, decodedValue: result.decoded_value });
      setStatus("matched");
      onMatched(result.emission_source, result.decoded_value);
    } catch (err) {
      // NO_BARCODE_DETECTED / BARCODE_NOT_MATCHED render via ErrorBanner
      // below, using the API's actual error.message text — not invented
      // generic wording (requirement #4).
      setScanError(err);
      setStatus("scan-error");
    }
  }

  // Attach the live stream once the <video> element mounts (it only exists
  // in the DOM once status enters the camera-ready group below).
  function attachVideoRef(el: HTMLVideoElement | null) {
    videoRef.current = el;
    if (el && streamRef.current) {
      el.srcObject = streamRef.current;
    }
  }

  if (status === "closed") {
    return (
      <button type="button" className="scan-toggle" onClick={openScanner}>
        Scan Barcode
      </button>
    );
  }

  return (
    <div className="scan-panel">
      {status === "requesting-camera" && <LoadingState label="Requesting camera access…" />}

      {status === "camera-denied" && (
        <>
          <ErrorBanner error={new Error(cameraError ?? "Could not access the camera.")} />
          <button type="button" onClick={closeScanner}>
            Close
          </button>
        </>
      )}

      {(status === "camera-ready" ||
        status === "scanning" ||
        status === "matched" ||
        status === "scan-error") && (
        <>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video ref={attachVideoRef} autoPlay playsInline muted className="scan-panel__video" />

          {status === "camera-ready" && (
            <div className="scan-panel__actions">
              <button type="button" onClick={handleCapture}>
                Capture
              </button>
              <button type="button" className="scan-panel__cancel" onClick={closeScanner}>
                Cancel
              </button>
            </div>
          )}

          {status === "scanning" && <LoadingState label="Scanning…" />}

          {status === "scan-error" && (
            <>
              <ErrorBanner error={scanError} />
              <div className="scan-panel__actions">
                <button type="button" onClick={handleRetry}>
                  Try again
                </button>
                <button type="button" className="scan-panel__cancel" onClick={closeScanner}>
                  Use manual selection instead
                </button>
              </div>
            </>
          )}

          {status === "matched" && matchedResult && (
            <div className="result-panel" role="status">
              <h3>Barcode matched</h3>
              <p>
                Scanned <strong>{matchedResult.decodedValue}</strong> — matched{" "}
                <strong>{matchedResult.source.source_name}</strong>. Selected below.
              </p>
              <div className="scan-panel__actions">
                <button type="button" onClick={handleRetry}>
                  Scan another
                </button>
                <button type="button" className="scan-panel__cancel" onClick={closeScanner}>
                  Done
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
