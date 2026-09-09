/* SPDX-License-Identifier: MIT */
#ifndef AURA_A04_SESSION_AUTH_H
#define AURA_A04_SESSION_AUTH_H
#include "aura_release_auth.h"
#include <stdbool.h>

#define AURA_SESSION_CHALLENGE_BYTES 144u
#define AURA_SESSION_CONFIRM_BYTES 48u
#define AURA_SESSION_FRAME_BYTES 20u
#define AURA_SESSION_PROOF_MS 30000u
#define AURA_SESSION_GRANT_MS 600000u
enum aura_session_phase { AURA_SESSION_CLOSED=0, AURA_SESSION_BEGIN,
    AURA_SESSION_CHALLENGE, AURA_SESSION_HALF, AURA_SESSION_GRANTED };
enum aura_session_result { AURA_SESSION_OK=0, AURA_SESSION_ARGUMENT=-900,
    AURA_SESSION_DENIED=-901, AURA_SESSION_EXPIRED=-902,
    AURA_SESSION_FORMAT=-903, AURA_SESSION_PROOF=-904, AURA_SESSION_RANDOM=-905 };

/* All calls belong to one serialized owner. Trusted local context and CSPRNG
 * are mandatory; this provider never provisions keys or establishes SMP L4.
 * The caller must immediately revoke on link/security/ownership loss. Neither
 * this grant nor confirmation permits deletion or changes RLS1 authority. */
struct aura_session_auth {
    struct aura_release_auth_context context;
    int (*random)(void *user, uint8_t *out, size_t bytes);
    void *random_user;
    uint64_t connection, high_water, deadline, last_now;
    uint8_t challenge[AURA_SESSION_CHALLENGE_BYTES], proof[32];
    uint8_t confirmation[AURA_SESSION_CONFIRM_BYTES], last_frame[20];
    enum aura_session_phase phase;
    bool configured, have_frame;
};
int aura_session_auth_init(struct aura_session_auth *session,
    const struct aura_release_auth_context *trusted,
    int (*csprng)(void *, uint8_t *, size_t), void *user);
int aura_session_auth_bind(struct aura_session_auth *session, uint64_t generation,
                           uint64_t now_ms, bool authenticated_l4);
int aura_session_auth_receive(struct aura_session_auth *session, uint64_t generation,
    uint64_t now_ms, bool authenticated_l4, const uint8_t *frame, size_t bytes);
/* Copy the immutable challenge or post-proof confirmation. Zero bytes means
 * BEGIN has not arrived. Output must not alias private session memory. */
int aura_session_auth_snapshot(struct aura_session_auth *session, uint64_t generation,
    uint64_t now_ms, bool authenticated_l4, uint8_t *out, size_t capacity, size_t *bytes);
bool aura_session_auth_granted(struct aura_session_auth *session, uint64_t generation,
                               uint64_t now_ms, bool authenticated_l4);
/* End wipes handshake/proof state, preserving configured trusted context for
 * another fresh generation. Forget also wipes the key and disables the provider. */
void aura_session_auth_end(struct aura_session_auth *session);
void aura_session_auth_forget(struct aura_session_auth *session);
#endif
