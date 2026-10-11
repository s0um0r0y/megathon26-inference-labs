// Records a spoken question and converts it to 16 kHz mono 16-bit WAV, the format
// Bhashini ASR expects (MediaRecorder on Android Chrome only produces webm/opus).

const TARGET_RATE = 16_000;
export const MAX_RECORDING_MS = 10_000;

export async function requestMicrophone(): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
}

export class Recorder {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stopTimer: number | undefined;
  private done: ((b: Blob | null) => void) | null = null;

  constructor(private readonly stream: MediaStream) {}

  get recording(): boolean {
    return this.recorder?.state === 'recording';
  }

  /** Starts recording; resolves with WAV when stop() is called or the time limit hits. */
  start(): Promise<Blob | null> {
    this.chunks = [];
    const rec = new MediaRecorder(this.stream);
    this.recorder = rec;
    rec.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    const result = new Promise<Blob | null>((resolve) => (this.done = resolve));
    rec.onstop = async () => {
      window.clearTimeout(this.stopTimer);
      const encoded = new Blob(this.chunks, { type: rec.mimeType });
      try {
        this.done?.(encoded.size ? await toWav16k(encoded) : null);
      } catch {
        this.done?.(null);
      }
    };
    rec.start();
    this.stopTimer = window.setTimeout(() => this.stop(), MAX_RECORDING_MS);
    return result;
  }

  stop() {
    if (this.recording) this.recorder!.stop();
  }

  cancel() {
    if (!this.recorder) return;
    this.recorder.onstop = null;
    if (this.recording) this.recorder.stop();
    this.done?.(null);
  }
}

async function toWav16k(blob: Blob): Promise<Blob> {
  const ctx = new AudioContext();
  try {
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    const frames = Math.ceil(decoded.duration * TARGET_RATE);
    const offline = new OfflineAudioContext(1, frames, TARGET_RATE);
    const src = offline.createBufferSource();
    src.buffer = decoded; // downmix to mono happens in the 1-channel destination
    src.connect(offline.destination);
    src.start();
    const rendered = await offline.startRendering();
    return encodeWav(rendered.getChannelData(0), TARGET_RATE);
  } finally {
    void ctx.close();
  }
}

export function encodeWav(samples: Float32Array, rate: number): Blob {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, 'RIFF');
  v.setUint32(4, 36 + samples.length * 2, true);
  str(8, 'WAVE');
  str(12, 'fmt ');
  v.setUint32(16, 16, true); // PCM chunk size
  v.setUint16(20, 1, true); // PCM
  v.setUint16(22, 1, true); // mono
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true); // byte rate
  v.setUint16(32, 2, true); // block align
  v.setUint16(34, 16, true); // bits per sample
  str(36, 'data');
  v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: 'audio/wav' });
}
