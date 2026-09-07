import { convexAuth } from '@convex-dev/auth/server';
import { Password } from '@convex-dev/auth/providers/Password';

export const { auth, signIn, signOut, store, isAuthenticated } = convexAuth({
  providers: [Password({
    validatePasswordRequirements(password) {
      if (password.length < 12) throw new Error('Use a password with at least 12 characters.');
      if (password.length > 200) throw new Error('Password is too long.');
    },
  })],
});
