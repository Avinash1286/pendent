import { query, mutation } from "./_generated/server";
import { getAuthUserId } from "@convex-dev/auth/server";
import { v, ConvexError } from "convex/values";
export const get = query({
  args: {},
  handler: async (ctx) => {
    const ownerId = await getAuthUserId(ctx);
    return ownerId
      ? ctx.db
          .query("profiles")
          .withIndex("by_owner", (q) => q.eq("ownerId", ownerId))
          .unique()
      : null;
  },
});
export const save = mutation({
  args: { name: v.string(), about: v.string(), goals: v.string(), preferences: v.string() },
  handler: async (ctx, args) => {
    const ownerId = await getAuthUserId(ctx);
    if (!ownerId) throw new ConvexError("Sign in first.");
    if (args.name.length > 100 || Object.values(args).some((value) => value.length > 6000))
      throw new ConvexError("Profile text is too long.");
    const previous = await ctx.db
      .query("profiles")
      .withIndex("by_owner", (q) => q.eq("ownerId", ownerId))
      .unique();
    if (previous) await ctx.db.patch(previous._id, { ...args, updatedAt: Date.now() });
    else await ctx.db.insert("profiles", { ...args, ownerId, updatedAt: Date.now() });
  },
});
