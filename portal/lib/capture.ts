/** Sender-declared capture provenance. Authentication comes from the owner session/token. */
export type Capture = {
  version: 2;
  deviceId: string;
  captureId: string;
  archiveDigest: string;
  sampleRate: 16000;
  sourceSamples: number;
  startedAtMs: number;
  timeConfidence: "unknown" | "host_synced";
  interrupted: boolean;
  bookmarks: number[];
  transcriptRevision: string;
  segments: { start: number; end: number; text: string }[];
  transcription: { engine: string; model: string; version: string };
};

function invalid(): never {
  throw new Error("Invalid capture provenance or source bounds.");
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  return value as Record<string, unknown>;
}
function exactKeys(value: Record<string, unknown>, keys: string[]) {
  if (Object.keys(value).length !== keys.length || keys.some((key) => !(key in value))) invalid();
}
function integer(value: unknown, maximum: number): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0 || value > maximum)
    return invalid();
  return value;
}
function hex(value: unknown, length: number, nonzero = false): string {
  if (
    typeof value !== "string" ||
    value.length !== length ||
    !/^[0-9a-f]+$/.test(value) ||
    (nonzero && /^0+$/.test(value))
  )
    return invalid();
  return value;
}

/** Validate without truncating. Return a fixed field order for structural replay comparison. */
export function parseCapture(value: unknown, recordedAt: number, now = Date.now()): Capture {
  const data = object(value);
  exactKeys(data, [
    "version",
    "deviceId",
    "captureId",
    "archiveDigest",
    "sampleRate",
    "sourceSamples",
    "startedAtMs",
    "timeConfidence",
    "interrupted",
    "bookmarks",
    "transcriptRevision",
    "segments",
    "transcription",
  ]);
  if (data.version !== 2 || data.sampleRate !== 16000 || typeof data.interrupted !== "boolean")
    invalid();
  // Shared bounded import limit; actual firmware journal/session limits can be smaller.
  const sourceSamples = integer(data.sourceSamples, 320000000);
  const startedAtMs = integer(data.startedAtMs, now + 86400000);
  if (
    recordedAt !== startedAtMs ||
    (data.timeConfidence !== "unknown" && data.timeConfidence !== "host_synced") ||
    (data.timeConfidence === "unknown" ? startedAtMs !== 0 : startedAtMs === 0)
  )
    invalid();
  if (!Array.isArray(data.bookmarks) || data.bookmarks.length > 1000) invalid();
  let previousBookmark = -1;
  const bookmarks = data.bookmarks.map((value) => {
    const sample = integer(value, data.interrupted ? 320000000 : sourceSamples);
    if (sample < previousBookmark) invalid();
    previousBookmark = sample;
    return sample;
  });
  if (!Array.isArray(data.segments) || data.segments.length > 2000) invalid();
  let previousEnd = 0;
  let textLength = 0;
  const segments = data.segments.map((value) => {
    const segment = object(value);
    exactKeys(segment, ["start", "end", "text"]);
    if (
      typeof segment.start !== "number" ||
      typeof segment.end !== "number" ||
      !Number.isFinite(segment.start) ||
      !Number.isFinite(segment.end) ||
      segment.start < previousEnd ||
      segment.end < segment.start ||
      segment.end > sourceSamples / 16000 ||
      typeof segment.text !== "string" ||
      segment.text.length > 2000
    )
      invalid();
    previousEnd = segment.end;
    textLength += segment.text.length;
    if (textLength > 60000) invalid();
    return { start: segment.start, end: segment.end, text: segment.text };
  });
  const method = object(data.transcription);
  exactKeys(method, ["engine", "model", "version"]);
  for (const value of Object.values(method))
    if (typeof value !== "string" || !value.trim() || value.length > 160) invalid();
  return {
    version: 2,
    deviceId: hex(data.deviceId, 32, true),
    captureId: hex(data.captureId, 32, true),
    archiveDigest: hex(data.archiveDigest, 64),
    sampleRate: 16000,
    sourceSamples,
    startedAtMs,
    timeConfidence: data.timeConfidence,
    interrupted: data.interrupted,
    bookmarks,
    transcriptRevision: hex(data.transcriptRevision, 64),
    segments,
    transcription: {
      engine: method.engine as string,
      model: method.model as string,
      version: method.version as string,
    },
  };
}

/** Exact UTF-8 transcript bytes; no normalization or canonical JSON is involved. */
export async function transcriptDigest(transcript: string): Promise<string> {
  // TextEncoder replaces lone UTF-16 surrogates with U+FFFD. Reject them so a claimed
  // exact UTF-8 revision cannot silently refer to replacement bytes instead of the source.
  for (let index = 0; index < transcript.length; index++) {
    const unit = transcript.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = transcript.charCodeAt(++index);
      if (!(next >= 0xdc00 && next <= 0xdfff)) invalid();
    } else if (unit >= 0xdc00 && unit <= 0xdfff) invalid();
  }
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(transcript));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function captureKey(capture: Capture): string {
  return `v2:${capture.deviceId}:${capture.captureId}`;
}
