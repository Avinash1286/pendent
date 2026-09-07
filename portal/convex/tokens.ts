import { query, mutation, internalMutation, internalQuery } from './_generated/server';
import { getAuthUserId } from '@convex-dev/auth/server';
import { v, ConvexError } from 'convex/values';

export const list = query({ args: {}, handler: async ctx => {
  const ownerId = await getAuthUserId(ctx);
  if (!ownerId) return [];
  return (await ctx.db.query('tokens').withIndex('by_owner', q => q.eq('ownerId', ownerId)).collect()).map(({ hash: _hash, ...token }) => token);
} });
export const revoke = mutation({ args: { id: v.id('tokens') }, handler: async (ctx, args) => {
  const ownerId = await getAuthUserId(ctx);
  const token = await ctx.db.get(args.id);
  if (!ownerId || !token || token.ownerId !== ownerId) throw new ConvexError('Token not found.');
  await ctx.db.patch(args.id, { revoked: true });
} });
export const insert = internalMutation({ args: { ownerId: v.id('users'), name: v.string(), hash: v.string(), prefix: v.string(), scope: v.union(v.literal('ingest'), v.literal('context')), autoContext: v.boolean() }, handler: async (ctx, args) => {
  const existing = await ctx.db.query('tokens').withIndex('by_owner', q => q.eq('ownerId', args.ownerId)).collect();
  if (existing.filter(token => !token.revoked && token.expiresAt > Date.now()).length >= 10) throw new ConvexError('Revoke an unused token before creating another.');
  if (!args.name.trim() || args.name.length > 80) throw new ConvexError('Use a short token name.');
  return ctx.db.insert('tokens', { ...args, revoked: false, createdAt: Date.now(), expiresAt: Date.now() + 90 * 86400000 });
} });
export const resolve = internalQuery({ args: { hash: v.string(), scope: v.union(v.literal('ingest'), v.literal('context')) }, handler: async (ctx, args) => {
  const token = await ctx.db.query('tokens').withIndex('by_hash', q => q.eq('hash', args.hash)).unique();
  return token && !token.revoked && token.expiresAt > Date.now() && token.scope === args.scope ? token : null;
} });
