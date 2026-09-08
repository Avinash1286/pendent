import { query, mutation, internalMutation, internalQuery } from "./_generated/server";
import { getAuthUserId } from "@convex-dev/auth/server";
import { v, ConvexError } from "convex/values";
import type { MutationCtx } from "./_generated/server";
import type { Id } from "./_generated/dataModel";
import { captureValidator } from "./captureFields";
import { captureKey, parseCapture, transcriptDigest, type Capture } from "../lib/capture";

type NoteInput = {
  title: string;
  transcript: string;
  summary: string[];
  actions: string[];
  tags: string[];
  recordedAt: number;
  contextEnabled: boolean;
};

async function storeCapture(
  ctx: MutationCtx,
  ownerId: Id<"users">,
  data: NoteInput,
  input: Capture,
  source: "pendant" | "portal",
) {
  const capture = parseCapture(input, data.recordedAt);
  if ((await transcriptDigest(data.transcript)) !== capture.transcriptRevision)
    throw new ConvexError({ code: "INVALID_SOURCE", message: "Transcript digest does not match." });
  const key = captureKey(capture);
  // The owner comes from the authenticated token/session, never from supplied capture IDs.
  // Read + conditional insert share one Convex mutation transaction, including retries.
  const previous = await ctx.db
    .query("notes")
    .withIndex("by_capture", (q) => q.eq("ownerId", ownerId).eq("captureKey", key))
    .unique();
  if (previous) {
    if (
      previous.sourceTranscript !== data.transcript ||
      JSON.stringify(parseCapture(previous.capture, previous.capture?.startedAtMs ?? 0)) !==
        JSON.stringify(capture)
    )
      throw new ConvexError({
        code: "SOURCE_CONFLICT",
        message: "Capture already exists with different source data.",
      });
    // Preserve edits, archival status and the owner's current sharing choice on every retry.
    return previous._id;
  }
  return ctx.db.insert("notes", {
    ...data,
    ownerId,
    captureKey: key,
    sourceId: key,
    capture,
    sourceTranscript: data.transcript,
    source,
    archived: false,
    updatedAt: Date.now(),
    searchText: [data.title, data.transcript, ...data.summary, ...data.tags].join(" "),
  });
}

const fields = {
  title: v.string(),
  transcript: v.string(),
  summary: v.array(v.string()),
  actions: v.array(v.string()),
  tags: v.array(v.string()),
  recordedAt: v.number(),
  contextEnabled: v.boolean(),
};
function validate(data: {
  title: string;
  transcript: string;
  summary: string[];
  actions: string[];
  tags: string[];
  recordedAt: number;
}) {
  if (
    !data.title.trim() ||
    data.title.length > 160 ||
    data.transcript.length > 60000 ||
    data.summary.length > 20 ||
    data.actions.length > 30 ||
    data.tags.length > 10 ||
    !Number.isFinite(data.recordedAt) ||
    data.recordedAt < 0 ||
    data.recordedAt > Date.now() + 86400000
  )
    throw new ConvexError("Note exceeds the supported limits.");
  if (
    [...data.summary, ...data.actions].some((line) => line.length > 2000) ||
    data.tags.some((tag) => tag.length > 40)
  )
    throw new ConvexError("A note field is too long.");
}

export const list = query({
  args: { search: v.optional(v.string()), archived: v.optional(v.boolean()) },
  handler: async (ctx, args) => {
    const ownerId = await getAuthUserId(ctx);
    if (!ownerId) return [];
    const archived = args.archived ?? false;
    if (args.search?.trim())
      return ctx.db
        .query("notes")
        .withSearchIndex("search_notes", (q) =>
          q
            .search("searchText", args.search!.trim().slice(0, 200))
            .eq("ownerId", ownerId)
            .eq("archived", archived),
        )
        .take(100);
    return ctx.db
      .query("notes")
      .withIndex("by_owner_arrival", (q) => q.eq("ownerId", ownerId).eq("archived", archived))
      .order("desc")
      .take(200);
  },
});

export const save = mutation({
  args: { id: v.optional(v.id("notes")), capture: v.optional(captureValidator), ...fields },
  handler: async (ctx, args) => {
    const ownerId = await getAuthUserId(ctx);
    if (!ownerId) throw new ConvexError("Sign in first.");
    validate(args);
    const { id, capture, ...data } = args;
    const searchText = [data.title, data.transcript, ...data.summary, ...data.tags].join(" ");
    if (id) {
      const previous = await ctx.db.get(id);
      if (!previous || previous.ownerId !== ownerId) throw new ConvexError("Note not found.");
      if (capture) throw new ConvexError("Captured source metadata cannot be edited.");
      const retainedSource =
        previous.sourceTranscript && previous.sourceTranscript !== data.transcript
          ? ` ${previous.sourceTranscript}`
          : "";
      await ctx.db.patch(id, {
        ...data,
        searchText: searchText + retainedSource,
        updatedAt: Date.now(),
      });
      return id;
    }
    if (capture) return storeCapture(ctx, ownerId, data, capture, "portal");
    return ctx.db.insert("notes", {
      ...data,
      ownerId,
      searchText,
      source: "portal",
      archived: false,
      updatedAt: Date.now(),
    });
  },
});

export const archive = mutation({
  args: { id: v.id("notes"), archived: v.boolean() },
  handler: async (ctx, args) => {
    const ownerId = await getAuthUserId(ctx);
    const note = await ctx.db.get(args.id);
    if (!ownerId || !note || note.ownerId !== ownerId) throw new ConvexError("Note not found.");
    await ctx.db.patch(args.id, { archived: args.archived, updatedAt: Date.now() });
  },
});

export const toggleContext = mutation({
  args: { id: v.id("notes"), enabled: v.boolean() },
  handler: async (ctx, args) => {
    const ownerId = await getAuthUserId(ctx);
    const note = await ctx.db.get(args.id);
    if (!ownerId || !note || note.ownerId !== ownerId) throw new ConvexError("Note not found.");
    await ctx.db.patch(args.id, { contextEnabled: args.enabled, updatedAt: Date.now() });
  },
});

export const ingest = internalMutation({
  args: {
    tokenId: v.id("tokens"),
    sourceId: v.optional(v.string()),
    capture: v.optional(captureValidator),
    ...fields,
  },
  handler: async (ctx, args) => {
    const token = await ctx.db.get(args.tokenId);
    if (!token || token.revoked || token.expiresAt <= Date.now() || token.scope !== "ingest")
      throw new ConvexError({ code: "UNAUTHORIZED", message: "Invalid device token." });
    validate(args);
    const { tokenId: _tokenId, sourceId: inputSourceId, capture, ...data } = args;
    if (capture)
      return storeCapture(
        ctx,
        token.ownerId,
        { ...data, contextEnabled: token.autoContext },
        capture,
        "pendant",
      );
    // Legacy v1 IDs have no trustworthy device identity. Do not guess cross-token equivalence.
    if (!inputSourceId?.trim() || inputSourceId.length > 160)
      throw new ConvexError("Invalid source ID.");
    const sourceId = `${token._id}:${inputSourceId}`;
    const previous = await ctx.db
      .query("notes")
      .withIndex("by_source", (q) => q.eq("ownerId", token.ownerId).eq("sourceId", sourceId))
      .unique();
    if (previous) return previous._id;
    return ctx.db.insert("notes", {
      ...data,
      sourceId,
      contextEnabled: token.autoContext,
      ownerId: token.ownerId,
      source: "pendant",
      archived: false,
      updatedAt: Date.now(),
      searchText: [data.title, data.transcript, ...data.summary, ...data.tags].join(" "),
    });
  },
});

export const liveContext = internalQuery({
  args: { ownerId: v.id("users") },
  handler: async (ctx, args) => {
    const profile = await ctx.db
      .query("profiles")
      .withIndex("by_owner", (q) => q.eq("ownerId", args.ownerId))
      .unique();
    const notes = await ctx.db
      .query("notes")
      .withIndex("by_live_context_arrival", (q) =>
        q.eq("ownerId", args.ownerId).eq("archived", false).eq("contextEnabled", true),
      )
      .order("desc")
      .take(20);
    return { profile, notes };
  },
});
