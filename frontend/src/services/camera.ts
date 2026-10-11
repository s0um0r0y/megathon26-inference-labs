// Rear camera stream, downscaled frames for the quality worker, and capture of the
// selected full-resolution frame as a compressed JPEG.

import { ANALYSIS_HEIGHT, ANALYSIS_WIDTH } from '../workers/frameQuality.worker';
import type { FrameStats } from '../workers/frameQuality.worker';

const UPLOAD_MAX_SIDE = 1280; // enough for sign text; keeps uploads ~150-300 KB
const JPEG_QUALITY = 0.82;
const ANALYSIS_INTERVAL_MS = 150; // ~6-7 analysed frames per second

export async function openCamera(video: HTMLVideoElement): Promise<MediaStream> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: {
      facingMode: { ideal: 'environment' },
      width: { ideal: 1920 },
      height: { ideal: 1080 },
    },
  });
  video.srcObject = stream;
  video.muted = true;
  video.playsInline = true;
  await video.play();
  return stream;
}

export function stopCamera(stream: MediaStream | null) {
  stream?.getTracks().forEach((t) => t.stop());
}

/** Torch helps at night; only some Android cameras expose it. */
export function torchSupported(stream: MediaStream | null): boolean {
  const track = stream?.getVideoTracks()[0];
  const caps = track?.getCapabilities?.() as MediaTrackCapabilities & { torch?: boolean };
  return !!caps?.torch;
}

export async function setTorch(stream: MediaStream | null, on: boolean) {
  const track = stream?.getVideoTracks()[0];
  await track?.applyConstraints({ advanced: [{ torch: on } as MediaTrackConstraintSet] });
}

/** Grab the current full-resolution frame and compress it for upload. */
export async function captureJpeg(video: HTMLVideoElement): Promise<Blob> {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  const scale = Math.min(1, UPLOAD_MAX_SIDE / Math.max(vw, vh));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(vw * scale);
  canvas.height = Math.round(vh * scale);
  canvas.getContext('2d')!.drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('encode failed'))), 'image/jpeg', JPEG_QUALITY),
  );
}

/**
 * Feeds downscaled frames to the quality worker with backpressure (one frame in
 * flight at a time) and reports each result.
 */
export class FrameMonitor {
  private worker: Worker;
  private timer: number | undefined;
  private busy = false;

  constructor(
    private readonly video: HTMLVideoElement,
    private readonly onStats: (s: FrameStats) => void,
  ) {
    this.worker = new Worker(new URL('../workers/frameQuality.worker.ts', import.meta.url), { type: 'module' });
    this.worker.onmessage = (e: MessageEvent<FrameStats>) => {
      this.busy = false;
      this.onStats(e.data);
    };
  }

  start() {
    this.stop();
    this.worker.postMessage({ type: 'reset' });
    this.timer = window.setInterval(() => void this.tick(), ANALYSIS_INTERVAL_MS);
  }

  stop() {
    window.clearInterval(this.timer);
    this.timer = undefined;
    this.busy = false;
  }

  dispose() {
    this.stop();
    this.worker.terminate();
  }

  private async tick() {
    if (this.busy || this.video.readyState < 2 || document.hidden) return;
    this.busy = true;
    try {
      // Downscale during decode (cheap, on the GPU path in Chrome).
      const bitmap = await createImageBitmap(this.video, {
        resizeWidth: ANALYSIS_WIDTH,
        resizeHeight: ANALYSIS_HEIGHT,
        resizeQuality: 'low',
      });
      this.worker.postMessage({ type: 'frame', bitmap }, [bitmap]);
    } catch {
      this.busy = false;
    }
  }
}
