import type { RefObject } from 'react';
import type { Strings } from '../i18n';
import type { Phase } from '../state/interactionMachine';
import type { FramingHint } from '../workers/frameQuality.worker';

interface Props {
  videoRef: RefObject<HTMLVideoElement>;
  t: Strings;
  phase: Phase;
  hint: FramingHint | 'raise_phone' | null;
  stableFrames: number;
  requiredStable: number;
  torchAvailable: boolean;
  torchOn: boolean;
  onTorch: () => void;
  onReadSign: () => void;
  onCancel: () => void;
}

/**
 * The live preview is decorative for screen-reader users (aria-hidden); everything
 * it conveys is also given as text (the framing hint) and through announcer cues
 * and earcons fired by App.
 */
export function CameraView(p: Props) {
  const capturing = p.phase === 'capturing';
  const progress = Math.min(1, p.stableFrames / p.requiredStable);
  const hintText = p.hint ? p.t.framing[p.hint] : '';

  return (
    <section className="camera" aria-labelledby="camera-title">
      <h2 id="camera-title" className="sr-only">
        {p.t.cameraSection}
      </h2>
      <div className="viewfinder" data-hint={p.hint ?? 'none'} data-capturing={capturing}>
        <video ref={p.videoRef} aria-hidden="true" playsInline muted />
        <div className="frame-guide" aria-hidden="true">
          {capturing && <div className="stability" style={{ transform: `scaleX(${progress})` }} />}
        </div>
      </div>

      {/* Visible framing text. Not a live region: App announces it throttled. */}
      <p className="framing-hint" data-hint={p.hint ?? 'none'}>
        {capturing ? hintText || p.t.holdStill : hintText}
      </p>

      <div className="camera-actions">
        {capturing ? (
          <button type="button" className="secondary big" onClick={p.onCancel}>
            {p.t.cancel}
          </button>
        ) : (
          <button
            type="button"
            className="primary big"
            onClick={p.onReadSign}
            disabled={p.phase === 'processing' || p.phase === 'listening'}
          >
            {p.t.readSign}
          </button>
        )}
        {p.torchAvailable && (
          <button type="button" className="secondary" aria-pressed={p.torchOn} onClick={p.onTorch}>
            {p.torchOn ? p.t.torchOff : p.t.torchOn}
          </button>
        )}
      </div>
    </section>
  );
}
