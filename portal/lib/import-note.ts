export type ImportedNote = {
  title: string;
  transcript: string;
  summary: string[];
  actions: string[];
  tags: string[];
  recordedAt: number;
  contextEnabled: boolean;
};

function strings(value: unknown, name: string, count: number, length: number): string[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`The note's ${name} must be a list of text values.`);
  }
  if (value.length > count || value.some((item) => item.length > length)) {
    throw new Error(`The note's ${name} exceeds the supported limits. Nothing was imported.`);
  }
  return value;
}

/** Never silently shorten source material or import another application's sharing consent. */
export function parseImportedNote(
  value: unknown,
  fallbackTimestamp = Date.now(),
  now = Date.now(),
): ImportedNote {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Choose a JSON object containing a note and its transcript.");
  }
  const data = value as Record<string, unknown>;
  const title = data.title === undefined ? "Imported thought" : data.title;
  if (typeof title !== "string" || !title.trim() || title.length > 160) {
    throw new Error(
      "The note title must contain between 1 and 160 characters. Nothing was imported.",
    );
  }
  if (typeof data.transcript !== "string" || data.transcript.length > 60000) {
    throw new Error(
      "The note needs a text transcript of at most 60,000 characters. Nothing was imported.",
    );
  }
  const recordedAt = data.recordedAt === undefined ? fallbackTimestamp : data.recordedAt;
  if (
    typeof recordedAt !== "number" ||
    !Number.isFinite(recordedAt) ||
    recordedAt < 0 ||
    recordedAt > now + 86400000
  ) {
    throw new Error("The recording timestamp must be a valid epoch time in milliseconds.");
  }
  return {
    title,
    transcript: data.transcript,
    summary: strings(data.summary, "summary", 20, 2000),
    actions: strings(data.actions ?? data.suggested_actions, "actions", 30, 2000),
    tags: strings(data.tags, "tags", 10, 40),
    recordedAt,
    contextEnabled: false,
  };
}
