import { v } from "convex/values";

export const captureValidator = v.object({
  version: v.literal(2),
  deviceId: v.string(),
  captureId: v.string(),
  archiveDigest: v.string(),
  sampleRate: v.literal(16000),
  sourceSamples: v.number(),
  startedAtMs: v.number(),
  timeConfidence: v.union(v.literal("unknown"), v.literal("host_synced")),
  interrupted: v.boolean(),
  bookmarks: v.array(v.number()),
  transcriptRevision: v.string(),
  segments: v.array(v.object({ start: v.number(), end: v.number(), text: v.string() })),
  transcription: v.object({ engine: v.string(), model: v.string(), version: v.string() }),
});
