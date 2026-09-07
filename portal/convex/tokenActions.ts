'use node';
import { randomBytes, createHash } from 'node:crypto';
import { action } from './_generated/server';
import { internal } from './_generated/api';
import { getAuthUserId } from '@convex-dev/auth/server';
import { v, ConvexError } from 'convex/values';

export const create = action({ args: { name: v.string(), scope: v.union(v.literal('ingest'), v.literal('context')), autoContext: v.boolean() }, handler: async (ctx, args): Promise<{ secret: string; id: string }> => {
  const ownerId = await getAuthUserId(ctx);
  if (!ownerId) throw new ConvexError('Sign in first.');
  const secret = `aura_${args.scope}_${randomBytes(32).toString('base64url')}`;
  const id = await ctx.runMutation(internal.tokens.insert, { ...args, ownerId, hash: createHash('sha256').update(secret).digest('hex'), prefix: secret.slice(0, 20) });
  return { secret, id };
} });
