#ifndef AURA_MAINTENANCE_H
#define AURA_MAINTENANCE_H
#include "journal.h"
/* Internal NVS intent precedes the first destructive erase. An interrupted
 * attempt resumes the complete erase, so removed tombstones cannot resurrect data. */
struct aura_maintenance_io {
    int (*intent)(bool);
    int (*erase)(uint32_t);
};
static inline bool aura_all_deleted(const struct aj_store *s)
{
    if (s->active >= 0)
        return false;
    for (unsigned i = 0; i < s->count; i++)
        if (!s->notes[i].deleted)
            return false;
    return true;
}
static inline int aura_erase_run(struct aj_store *s, struct aura_maintenance_io m, bool resuming)
{
    if (!resuming && !aura_all_deleted(s))
        return -1;
    int r = m.intent(true);
    if (r)
        return r;
    for (uint32_t b = 0; b < s->io.pages / 64; b++) {
        if (s->io.bad(b))
            continue;
        r = m.erase(b);
        if (r)
            return r;
    }
    struct aj_io io = s->io;
    r = aj_mount(s, io);
    if (r)
        return r;
    return m.intent(false);
}
#endif
