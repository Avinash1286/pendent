import { query, mutation, internalMutation, internalQuery } from "./_generated/server";
import { getAuthUserId } from "@convex-dev/auth/server";
import { v, ConvexError } from "convex/values";

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
      .withIndex("by_owner", (q) => q.eq("ownerId", ownerId).eq("archived", archived))
      .order("desc")
      .take(200);
  },
});

export const save = mutation({
  args: { id: v.optional(v.id("notes")), ...fields },
  handler: async (ctx, args) => {
    const ownerId = await getAuthUserId(ctx);
    if (!ownerId) throw new ConvexError("Sign in first.");
    validate(args);
    const { id, ...data } = args;
    const searchText = [data.title, data.transcript, ...data.summary, ...data.tags].join(" ");
    if (id) {
      const previous = await ctx.db.get(id);
      if (!previous || previous.ownerId !== ownerId) throw new ConvexError("Note not found.");
      await ctx.db.patch(id, { ...data, searchText, updatedAt: Date.now() });
      return id;
    }
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
  args: { tokenId: v.id("tokens"), sourceId: v.string(), ...fields },
  handler: async (ctx, args) => {
    const token = await ctx.db.get(args.tokenId);
    if (!token || token.revoked || token.expiresAt < Date.now() || token.scope !== "ingest")
      throw new ConvexError("Invalid device token.");
    validate(args);
    if (!args.sourceId.trim() || args.sourceId.length > 160)
      throw new ConvexError("Invalid source ID.");
    const sourceId = `${token._id}:${args.sourceId}`;
    const previous = await ctx.db
      .query("notes")
      .withIndex("by_source", (q) => q.eq("ownerId", token.ownerId).eq("sourceId", sourceId))
      .unique();
    if (previous) return previous._id;
    const { tokenId: _tokenId, ...data } = args;
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
      .withIndex("by_live_context", (q) =>
        q.eq("ownerId", args.ownerId).eq("archived", false).eq("contextEnabled", true),
      )
      .order("desc")
      .take(20);
    return { profile, notes };
  },
});
