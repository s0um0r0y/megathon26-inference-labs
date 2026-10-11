import { describe, expect, it } from 'vitest';
import { FrameAnalyzer, framingHint, laplacianVariance, REQUIRED_STABLE_FRAMES } from './frameQuality.worker';

const W = 160;
const H = 120;

/** RGBA frame from a grayscale function. */
function frame(fn: (x: number, y: number) => number): Uint8ClampedArray {
  const d = new Uint8ClampedArray(W * H * 4);
  for (let y = 0; y < H; y++)
    for (let x = 0; x < W; x++) {
      const v = fn(x, y);
      const i = (y * W + x) * 4;
      d[i] = d[i + 1] = d[i + 2] = v;
      d[i + 3] = 255;
    }
  return d;
}

/** Fake "text": dark bars on a light board within a rectangle. */
const textIn = (x0: number, y0: number, x1: number, y1: number) => (x: number, y: number) =>
  x >= x0 && x < x1 && y >= y0 && y < y1 && x % 6 < 3 && y % 10 < 6 ? 20 : 200;

const gray = (fn: (x: number, y: number) => number) => {
  const g = new Float32Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) g[y * W + x] = fn(x, y);
  return g;
};

describe('frame quality', () => {
  it('flags dark frames', () => {
    const a = new FrameAnalyzer();
    expect(a.analyze(frame(() => 10), W, H).hint).toBe('too_dark');
  });

  it('flat frames are blurry, textured frames are sharp', () => {
    expect(laplacianVariance(gray(() => 128), W, H)).toBe(0);
    expect(laplacianVariance(gray(textIn(20, 20, 140, 100)), W, H)).toBeGreaterThan(60);
  });

  it('becomes ready after enough stable, well-framed frames', () => {
    const a = new FrameAnalyzer();
    const f = frame(textIn(20, 20, 140, 100));
    let last = a.analyze(f, W, H);
    expect(last.hint).toBe('moving'); // no previous frame yet
    for (let i = 0; i < REQUIRED_STABLE_FRAMES; i++) last = a.analyze(f, W, H);
    expect(last.hint).toBe('good');
    expect(last.ready).toBe(true);
  });

  it('motion resets stability', () => {
    const a = new FrameAnalyzer();
    const f1 = frame(textIn(20, 20, 140, 100));
    const f2 = frame(textIn(40, 30, 150, 110));
    for (let i = 0; i < 4; i++) a.analyze(f1, W, H);
    expect(a.analyze(f2, W, H).stable_frames).toBe(0);
  });

  it('text crowding the top edge asks to move up', () => {
    expect(framingHint(gray(textIn(20, 0, 140, 22)), W, H)).toBe('move_up');
  });

  it('small text in the middle asks to move closer', () => {
    expect(framingHint(gray(textIn(70, 52, 92, 70)), W, H)).toBe('move_closer');
  });

  it('empty scene asks to look around', () => {
    expect(framingHint(gray(() => 128), W, H)).toBe('no_text');
  });
});
