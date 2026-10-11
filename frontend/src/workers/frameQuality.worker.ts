// Frame-quality analysis off the main thread so the camera preview and TalkBack
// stay responsive. The main thread sends small (160x120) ImageBitmaps; this worker
// returns brightness, blur, motion, a stability counter and a framing hint.
//
// Thresholds match backend/safety/confidence.py. They are first guesses: tune them
// on the Hyderabad sign photo set.

export const ANALYSIS_WIDTH = 160;
export const ANALYSIS_HEIGHT = 120;
export const MIN_BRIGHTNESS = 45;
export const MAX_BRIGHTNESS = 225;
export const MIN_BLUR_SCORE = 60;
export const MAX_STABLE_MOTION = 4;
export const REQUIRED_STABLE_FRAMES = 5;

export type FramingHint =
  | 'good'
  | 'too_dark'
  | 'too_bright'
  | 'blurry'
  | 'moving'
  | 'no_text'
  | 'move_up'
  | 'move_down'
  | 'move_left'
  | 'move_right'
  | 'move_closer';

export interface FrameStats {
  brightness: number;
  blur_score: number;
  motion: number;
  stable_frames: number;
  ready: boolean;
  hint: FramingHint;
}

export function toGray(rgba: Uint8ClampedArray, n: number): Float32Array {
  const g = new Float32Array(n);
  for (let i = 0, j = 0; i < n; i++, j += 4) {
    g[i] = 0.299 * rgba[j] + 0.587 * rgba[j + 1] + 0.114 * rgba[j + 2];
  }
  return g;
}

export function mean(g: Float32Array): number {
  let s = 0;
  for (let i = 0; i < g.length; i++) s += g[i];
  return s / g.length;
}

/** Variance of the 4-neighbour Laplacian: low means blurry. */
export function laplacianVariance(g: Float32Array, w: number, h: number): number {
  let sum = 0;
  let sumSq = 0;
  let n = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const v = 4 * g[i] - g[i - 1] - g[i + 1] - g[i - w] - g[i + w];
      sum += v;
      sumSq += v * v;
      n++;
    }
  }
  const m = sum / n;
  return sumSq / n - m * m;
}

/** Mean absolute difference between consecutive frames. */
export function motion(a: Float32Array, b: Float32Array | null): number {
  if (!b || a.length !== b.length) return Infinity;
  let s = 0;
  for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]);
  return s / a.length;
}

/**
 * Where the strong edges (text, board borders) are. Text that piles up against one
 * border while the centre is empty usually means the board is cut off on that side.
 * Directions are for moving the phone, so content at the top edge -> "move up".
 */
export function framingHint(g: Float32Array, w: number, h: number): FramingHint {
  const edgeThreshold = 40;
  const strip = 0.15;
  let total = 0;
  let top = 0;
  let bottom = 0;
  let left = 0;
  let right = 0;
  let minX = w;
  let maxX = 0;
  let minY = h;
  let maxY = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const gx = g[i + 1] - g[i - 1];
      const gy = g[i + w] - g[i - w];
      if (Math.abs(gx) + Math.abs(gy) < edgeThreshold) continue;
      total++;
      if (y < h * strip) top++;
      else if (y > h * (1 - strip)) bottom++;
      if (x < w * strip) left++;
      else if (x > w * (1 - strip)) right++;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  const area = (w - 2) * (h - 2);
  if (total < area * 0.01) return 'no_text';
  // A strip holds 15% of the frame; much more than its share means content runs off that edge.
  const share = (k: number) => k / total;
  const cut = 0.35;
  if (share(top) > cut && share(top) > share(bottom) * 2) return 'move_up';
  if (share(bottom) > cut && share(bottom) > share(top) * 2) return 'move_down';
  if (share(left) > cut && share(left) > share(right) * 2) return 'move_left';
  if (share(right) > cut && share(right) > share(left) * 2) return 'move_right';
  const boxArea = (maxX - minX) * (maxY - minY);
  if (boxArea < area * 0.12) return 'move_closer';
  return 'good';
}

export class FrameAnalyzer {
  private prev: Float32Array | null = null;
  private stable = 0;

  analyze(rgba: Uint8ClampedArray, w: number, h: number): FrameStats {
    const g = toGray(rgba, w * h);
    const brightness = mean(g);
    const blur = laplacianVariance(g, w, h);
    const m = motion(g, this.prev);
    this.prev = g;

    let hint: FramingHint;
    if (brightness < MIN_BRIGHTNESS) hint = 'too_dark';
    else if (brightness > MAX_BRIGHTNESS) hint = 'too_bright';
    else if (m > MAX_STABLE_MOTION) hint = 'moving';
    else if (blur < MIN_BLUR_SCORE) hint = 'blurry';
    else hint = framingHint(g, w, h);

    // Framing issues don't block capture (the model may still read it); light,
    // blur and motion do.
    const capturable = !['too_dark', 'too_bright', 'moving', 'blurry'].includes(hint);
    this.stable = capturable ? this.stable + 1 : 0;
    return {
      brightness: Math.round(brightness),
      blur_score: Math.round(blur),
      motion: Number.isFinite(m) ? Math.round(m * 10) / 10 : 99,
      stable_frames: this.stable,
      ready: this.stable >= REQUIRED_STABLE_FRAMES && hint === 'good',
      hint,
    };
  }

  reset() {
    this.prev = null;
    this.stable = 0;
  }
}

// ---- Worker wiring (skipped when imported by unit tests) -----------------------

declare const WorkerGlobalScope: { new (): unknown } | undefined;

if (typeof WorkerGlobalScope !== 'undefined' && self instanceof (WorkerGlobalScope as never)) {
  const analyzer = new FrameAnalyzer();
  const canvas = new OffscreenCanvas(ANALYSIS_WIDTH, ANALYSIS_HEIGHT);
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!;

  self.onmessage = (e: MessageEvent<{ type: 'frame'; bitmap: ImageBitmap } | { type: 'reset' }>) => {
    if (e.data.type === 'reset') {
      analyzer.reset();
      return;
    }
    const { bitmap } = e.data;
    ctx.drawImage(bitmap, 0, 0, ANALYSIS_WIDTH, ANALYSIS_HEIGHT);
    bitmap.close();
    const { data } = ctx.getImageData(0, 0, ANALYSIS_WIDTH, ANALYSIS_HEIGHT);
    (self as unknown as Worker).postMessage(analyzer.analyze(data, ANALYSIS_WIDTH, ANALYSIS_HEIGHT));
  };
}
