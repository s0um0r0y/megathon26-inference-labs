import { describe, expect, it } from 'vitest';
import type { AnalyzeResponse, Session } from '../services/api';
import { inferProfile, initialState, reduce } from './interactionMachine';
import type { MachineEvent, MachineState } from './interactionMachine';

const session: Session = { session_id: 's1', language: 'te', profile: 'default', speech_rate: 1 };

function run(events: MachineEvent[], from: MachineState = initialState): MachineState {
  return events.reduce(reduce, from);
}

function response(status: AnalyzeResponse['status'], request_id = 'r1'): AnalyzeResponse {
  return {
    request_id,
    status,
    language: 'te',
    spoken_text: 'x',
    landmarks: [],
    bus_routes: [],
    timings_ms: {},
    answer: { short: 'x', steps: ['a', 'b', 'c'], details: [] },
  };
}

describe('interaction flow', () => {
  it('goes from question to answer', () => {
    const s = run([
      { type: 'SESSION_READY', session },
      { type: 'QUESTION', question: { text: 'which bus?' } },
      { type: 'CAPTURED', requestId: 'r1' },
      { type: 'PROGRESS', requestId: 'r1', stage: 'thinking' },
    ]);
    expect(s.phase).toBe('processing');
    expect(s.stage).toBe('thinking');
    const done = reduce(s, { type: 'RESULT', response: response('ok') });
    expect(done.phase).toBe('answer');
  });

  it('maps statuses to phases', () => {
    const base = run([
      { type: 'SESSION_READY', session },
      { type: 'QUESTION', question: {} },
      { type: 'CAPTURED', requestId: 'r1' },
    ]);
    expect(reduce(base, { type: 'RESULT', response: response('needs_retake') }).phase).toBe('retake');
    expect(reduce(base, { type: 'RESULT', response: response('needs_confirmation') }).phase).toBe('confirm');
    expect(reduce(base, { type: 'RESULT', response: response('cancelled') }).phase).toBe('aiming');
    expect(reduce(base, { type: 'RESULT', response: response('error') }).phase).toBe('error');
  });

  it('ignores stale results and progress from cancelled requests', () => {
    const s = run([
      { type: 'SESSION_READY', session },
      { type: 'QUESTION', question: {} },
      { type: 'CAPTURED', requestId: 'r2' },
    ]);
    expect(reduce(s, { type: 'RESULT', response: response('ok', 'r1') })).toBe(s);
    expect(reduce(s, { type: 'PROGRESS', requestId: 'r1', stage: 'thinking' })).toBe(s);
  });

  it('cancel returns to aiming only when busy', () => {
    const busy = run([{ type: 'SESSION_READY', session }, { type: 'START_LISTENING' }]);
    expect(reduce(busy, { type: 'CANCEL' }).phase).toBe('aiming');
    const idle = run([{ type: 'SESSION_READY', session }]);
    expect(reduce(idle, { type: 'CANCEL' })).toBe(idle);
  });

  it('steps are bounded', () => {
    let s = run([
      { type: 'SESSION_READY', session },
      { type: 'QUESTION', question: {} },
      { type: 'CAPTURED', requestId: 'r1' },
      { type: 'RESULT', response: response('ok') },
    ]);
    s = run([{ type: 'NEXT_STEP' }, { type: 'NEXT_STEP' }, { type: 'NEXT_STEP' }], s);
    expect(s.stepIndex).toBe(2);
    s = run([{ type: 'PREV_STEP' }, { type: 'PREV_STEP' }, { type: 'PREV_STEP' }], s);
    expect(s.stepIndex).toBe(0);
  });
});

describe('condition inference', () => {
  const zero = initialState.signals;

  it('proposes visual after repeated assistive activations', () => {
    expect(inferProfile({ ...zero, assistiveActivations: 3 }, 'default', [])).toBe('visual');
  });

  it('proposes hearing when the user only types', () => {
    expect(inferProfile({ ...zero, typedQueries: 2 }, 'default', [])).toBe('hearing');
    expect(inferProfile({ ...zero, typedQueries: 2, voiceQueries: 1 }, 'default', [])).toBeNull();
  });

  it('proposes ageing after replays, simpler and zoom', () => {
    expect(inferProfile({ ...zero, replays: 2, zooms: 1 }, 'default', [])).toBe('ageing');
  });

  it('never re-proposes a dismissed or current profile', () => {
    expect(inferProfile({ ...zero, assistiveActivations: 5 }, 'visual', [])).toBeNull();
    expect(inferProfile({ ...zero, assistiveActivations: 5 }, 'default', ['visual'])).toBeNull();
  });

  it('dismissal is remembered by the reducer', () => {
    let s = run([
      { type: 'SESSION_READY', session },
      { type: 'SIGNAL', signal: 'assistiveActivations' },
      { type: 'SIGNAL', signal: 'assistiveActivations' },
      { type: 'SIGNAL', signal: 'assistiveActivations' },
    ]);
    expect(s.proposedProfile).toBe('visual');
    s = reduce(s, { type: 'RESOLVE_PROPOSAL', accepted: false });
    s = reduce(s, { type: 'SIGNAL', signal: 'assistiveActivations' });
    expect(s.proposedProfile).toBeNull();
  });

  it('retries do not count as typed queries', () => {
    const s = run([
      { type: 'SESSION_READY', session },
      { type: 'QUESTION', question: { text: 'a' } },
      { type: 'RESET' },
      { type: 'QUESTION', question: { text: 'a' }, retry: true },
    ]);
    expect(s.signals.typedQueries).toBe(1);
  });
});
