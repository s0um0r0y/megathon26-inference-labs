// The app's interaction flow as a pure reducer (no side effects; App.tsx performs
// camera/mic/network work in response to phase changes).
//
//   onboarding -> aiming -> listening -> capturing -> processing -> answer
//                   ^           |            ^             |    -> retake  (photo unusable)
//                   |           v            |             |    -> confirm (unsure transcript)
//                   +------ (cancel) --------+-------------+    -> error
//
// Condition inference lives here too: interaction signals accumulate and, past a
// threshold, propose a profile which the user must confirm (never applied silently).

import type { AnalyzeResponse, Profile, Session, Stage } from '../services/api';

export type Phase =
  | 'onboarding'
  | 'aiming'
  | 'listening'
  | 'capturing'
  | 'processing'
  | 'answer'
  | 'retake'
  | 'confirm'
  | 'error';

export interface Question {
  text?: string;
  audio?: Blob | null;
  confirmed?: boolean;
}

export interface Signals {
  assistiveActivations: number; // TalkBack-style activations (talkback.ts)
  voiceQueries: number;
  typedQueries: number;
  replays: number;
  simplerRequests: number;
  zooms: number;
}

export type SuggestedProfile = Exclude<Profile, 'default'>;

export interface MachineState {
  phase: Phase;
  session: Session | null;
  question: Question | null;
  requestId: string | null;
  stage: Stage | null;
  response: AnalyzeResponse | null;
  error: string | null;
  stepIndex: number;
  showSimpler: boolean;
  signals: Signals;
  proposedProfile: SuggestedProfile | null;
  dismissed: SuggestedProfile[];
}

export type MachineEvent =
  | { type: 'SESSION_READY'; session: Session }
  | { type: 'START_LISTENING' }
  | { type: 'QUESTION'; question: Question; retry?: boolean }
  | { type: 'CAPTURED'; requestId: string }
  | { type: 'PROGRESS'; requestId: string; stage: Stage }
  | { type: 'RESULT'; response: AnalyzeResponse }
  | { type: 'FAILED'; error: string }
  | { type: 'CANCEL' }
  | { type: 'RESET' }
  | { type: 'NEXT_STEP' }
  | { type: 'PREV_STEP' }
  | { type: 'TOGGLE_SIMPLER' }
  | { type: 'SIGNAL'; signal: keyof Signals }
  | { type: 'RESOLVE_PROPOSAL'; accepted: boolean };

export const initialState: MachineState = {
  phase: 'onboarding',
  session: null,
  question: null,
  requestId: null,
  stage: null,
  response: null,
  error: null,
  stepIndex: 0,
  showSimpler: false,
  signals: {
    assistiveActivations: 0,
    voiceQueries: 0,
    typedQueries: 0,
    replays: 0,
    simplerRequests: 0,
    zooms: 0,
  },
  proposedProfile: null,
  dismissed: [],
};

/** Thresholds are deliberately conservative: a wrong proposal is an interruption. */
export function inferProfile(
  s: Signals,
  current: Profile,
  dismissed: SuggestedProfile[],
): SuggestedProfile | null {
  const candidates: [SuggestedProfile, boolean][] = [
    // Screen reader in use and/or voice-only use -> visual.
    ['visual', s.assistiveActivations >= 3 || (s.voiceQueries >= 3 && s.typedQueries === 0 && s.assistiveActivations >= 1)],
    // Typing instead of speaking -> hearing (or a muted, noisy environment).
    ['hearing', s.typedQueries >= 2 && s.voiceQueries === 0],
    // Replays, "explain simpler" and zooming -> ageing.
    ['ageing', s.replays + s.simplerRequests + s.zooms >= 3],
  ];
  for (const [profile, hit] of candidates) {
    if (hit && profile !== current && !dismissed.includes(profile)) return profile;
  }
  return null;
}

const BUSY: Phase[] = ['listening', 'capturing', 'processing'];

export function reduce(state: MachineState, ev: MachineEvent): MachineState {
  switch (ev.type) {
    case 'SESSION_READY':
      return {
        ...state,
        session: ev.session,
        phase: state.phase === 'onboarding' ? 'aiming' : state.phase,
        proposedProfile: state.proposedProfile === ev.session.profile ? null : state.proposedProfile,
      };

    case 'START_LISTENING':
      if (state.phase === 'processing' || state.phase === 'capturing') return state;
      return { ...state, phase: 'listening', error: null };

    case 'QUESTION': {
      if (state.phase === 'processing') return state;
      const signals = { ...state.signals };
      if (!ev.retry && ev.question.audio) signals.voiceQueries++;
      else if (!ev.retry && ev.question.text && !ev.question.confirmed) signals.typedQueries++;
      return withProposal({
        ...state,
        phase: 'capturing',
        question: ev.question,
        response: null,
        error: null,
        stage: null,
        requestId: null,
        signals,
      });
    }

    case 'CAPTURED':
      if (state.phase !== 'capturing') return state;
      return { ...state, phase: 'processing', requestId: ev.requestId, stage: 'received' };

    case 'PROGRESS':
      if (state.phase !== 'processing' || ev.requestId !== state.requestId) return state;
      return { ...state, stage: ev.stage };

    case 'RESULT': {
      if (ev.response.request_id !== state.requestId) return state;
      const phase: Phase =
        ev.response.status === 'ok'
          ? 'answer'
          : ev.response.status === 'needs_retake'
            ? 'retake'
            : ev.response.status === 'needs_confirmation'
              ? 'confirm'
              : ev.response.status === 'cancelled'
                ? 'aiming'
                : 'error';
      return {
        ...state,
        phase,
        response: ev.response,
        error: ev.response.status === 'error' ? (ev.response.error ?? null) : null,
        stage: null,
        stepIndex: 0,
        showSimpler: false,
      };
    }

    case 'FAILED':
      return { ...state, phase: 'error', error: ev.error, stage: null };

    case 'CANCEL':
      if (!BUSY.includes(state.phase)) return state;
      return { ...state, phase: 'aiming', stage: null, requestId: null };

    case 'RESET':
      return { ...state, phase: 'aiming', question: null, stage: null, requestId: null, error: null };

    case 'NEXT_STEP': {
      const n = state.response?.answer?.steps.length ?? 0;
      return { ...state, stepIndex: Math.min(state.stepIndex + 1, Math.max(0, n - 1)) };
    }

    case 'PREV_STEP':
      return { ...state, stepIndex: Math.max(0, state.stepIndex - 1) };

    case 'TOGGLE_SIMPLER': {
      const turningOn = !state.showSimpler;
      const signals = turningOn
        ? { ...state.signals, simplerRequests: state.signals.simplerRequests + 1 }
        : state.signals;
      return withProposal({ ...state, showSimpler: turningOn, signals });
    }

    case 'SIGNAL':
      return withProposal({
        ...state,
        signals: { ...state.signals, [ev.signal]: state.signals[ev.signal] + 1 },
      });

    case 'RESOLVE_PROPOSAL':
      return {
        ...state,
        proposedProfile: null,
        dismissed:
          !ev.accepted && state.proposedProfile ? [...state.dismissed, state.proposedProfile] : state.dismissed,
      };
  }
}

function withProposal(state: MachineState): MachineState {
  if (state.proposedProfile || !state.session) return state;
  return { ...state, proposedProfile: inferProfile(state.signals, state.session.profile, state.dismissed) };
}

export function isBusy(phase: Phase): boolean {
  return BUSY.includes(phase);
}
