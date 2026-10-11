// REST + WebSocket client. Types mirror backend/schemas/{request,response}.py - keep in sync.

export type Language = 'en' | 'hi' | 'te';
export type Profile = 'default' | 'visual' | 'hearing' | 'ageing';
export type Status = 'ok' | 'needs_retake' | 'needs_confirmation' | 'cancelled' | 'error';
export type Intent =
  | 'read_sign'
  | 'bus_route'
  | 'shop_info'
  | 'traffic_signal'
  | 'navigation'
  | 'emergency'
  | 'out_of_scope';
export type Stage =
  | 'received'
  | 'listening'
  | 'reading'
  | 'locating'
  | 'translating'
  | 'thinking'
  | 'checking'
  | 'speaking'
  | 'done';

export interface Session {
  session_id: string;
  language: Language;
  profile: Profile;
  speech_rate: number;
}

export interface GeoFix {
  lat: number;
  lon: number;
  accuracy_m?: number;
  heading_deg?: number;
}

export interface FrameQuality {
  brightness: number;
  blur_score: number;
  motion: number;
  stable_frames: number;
}

export interface AnalyzeMetadata {
  session_id: string;
  request_id: string;
  query_text?: string;
  confirmed?: boolean;
  answer_language?: Language;
  location?: GeoFix;
  frame_quality?: FrameQuality;
  include_audio?: boolean;
}

export interface Answer {
  short: string;
  steps: string[];
  details: string[];
  simpler?: string;
  follow_up?: string;
  caution?: string;
}

export interface Landmark {
  name: string;
  kind: string;
  distance_m: number;
  direction?: string;
  bearing_deg: number;
}

export interface HelpOffer {
  message: string;
  call_number?: string;
  sms_body?: string;
}

export interface AnalyzeResponse {
  request_id: string;
  status: Status;
  intent?: Intent;
  language: Language;
  answer?: Answer;
  spoken_text: string;
  audio_b64?: string;
  audio_mime?: string;
  transcript?: string;
  sign_text?: string;
  retake_hint?: string;
  confidence?: { score: number; level: 'high' | 'medium' | 'low'; reasons: string[] };
  landmarks: Landmark[];
  bus_routes: { ref: string; name?: string; to?: string }[];
  help?: HelpOffer;
  raw_answer?: string;
  timings_ms: Record<string, number>;
  error?: string;
}

export interface ProgressEvent {
  type: 'progress';
  request_id: string;
  stage: Stage;
  message: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export function createSession(body: Partial<Omit<Session, 'session_id'>>): Promise<Session> {
  return fetch('/api/sessions', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  }).then(json<Session>);
}

export function updateSession(id: string, body: Partial<Omit<Session, 'session_id'>>): Promise<Session> {
  return fetch(`/api/sessions/${id}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  }).then(json<Session>);
}

export function analyze(
  meta: AnalyzeMetadata,
  image: Blob,
  audio: Blob | null,
  signal?: AbortSignal,
): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append('metadata', JSON.stringify(meta));
  form.append('image', image, 'frame.jpg');
  if (audio) form.append('audio', audio, 'question.wav');
  return fetch('/api/analyze', { method: 'POST', body: form, signal }).then(json<AnalyzeResponse>);
}

export function speak(
  sessionId: string,
  text: string,
  language?: Language,
): Promise<{ audio_b64?: string; audio_mime?: string }> {
  return fetch('/api/speak', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, text, language }),
  }).then(json<{ audio_b64?: string; audio_mime?: string }>);
}

export function requestHelp(
  sessionId: string,
  reason: 'user_requested' | 'low_confidence' | 'emergency',
  location?: GeoFix,
): Promise<HelpOffer> {
  return fetch('/api/help', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, reason, location }),
  }).then(json<HelpOffer>);
}

export function newRequestId(): string {
  return crypto.randomUUID().replace(/-/g, '').slice(0, 16);
}

/** Session WebSocket: progress events in, cancel out. Reconnects with backoff. */
export class SessionSocket {
  private ws: WebSocket | null = null;
  private retry = 0;
  private closed = false;
  private pingTimer: number | undefined;

  constructor(
    private readonly sessionId: string,
    private readonly onProgress: (e: ProgressEvent) => void,
  ) {
    this.connect();
  }

  private connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws/${this.sessionId}`);
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      this.pingTimer = window.setInterval(() => this.send({ type: 'ping' }), 25_000);
    };
    ws.onmessage = (m) => {
      try {
        const data = JSON.parse(m.data);
        if (data.type === 'progress') this.onProgress(data as ProgressEvent);
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = (ev) => {
      window.clearInterval(this.pingTimer);
      // 4404: the session expired server-side; the app recreates it on next use.
      if (this.closed || ev.code === 4404) return;
      const delay = Math.min(15_000, 500 * 2 ** this.retry++);
      window.setTimeout(() => this.connect(), delay);
    };
  }

  private send(msg: object) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  cancel(requestId: string) {
    this.send({ type: 'cancel', request_id: requestId });
  }

  close() {
    this.closed = true;
    window.clearInterval(this.pingTimer);
    this.ws?.close();
  }
}
