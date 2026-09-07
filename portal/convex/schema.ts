import { defineSchema, defineTable } from "convex/server";
import { authTables } from "@convex-dev/auth/server";
import { v } from "convex/values";

export default defineSchema({
  ...authTables,
  notes: defineTable({
    ownerId: v.id("users"),
    title: v.string(),
    transcript: v.string(),
    summary: v.array(v.string()),
    actions: v.array(v.string()),
    tags: v.array(v.string()),
    recordedAt: v.number(),
    updatedAt: v.number(),
    source: v.string(),
    sourceId: v.optional(v.string()),
    archived: v.boolean(),
    contextEnabled: v.boolean(),
    searchText: v.string(),
  })
    .index("by_owner", ["ownerId", "archived", "recordedAt"])
    .index("by_live_context", ["ownerId", "archived", "contextEnabled", "recordedAt"])
    .index("by_source", ["ownerId", "sourceId"])
    .searchIndex("search_notes", {
      searchField: "searchText",
      filterFields: ["ownerId", "archived"],
    }),
  profiles: defineTable({
    ownerId: v.id("users"),
    name: v.string(),
    about: v.string(),
    goals: v.string(),
    preferences: v.string(),
    updatedAt: v.number(),
  }).index("by_owner", ["ownerId"]),
  tokens: defineTable({
    ownerId: v.id("users"),
    name: v.string(),
    hash: v.string(),
    prefix: v.string(),
    scope: v.union(v.literal("ingest"), v.literal("context")),
    autoContext: v.boolean(),
    expiresAt: v.number(),
    revoked: v.boolean(),
    createdAt: v.number(),
  })
    .index("by_hash", ["hash"])
    .index("by_owner", ["ownerId"]),
});
