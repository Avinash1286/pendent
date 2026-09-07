#ifndef AURA_GESTURES_H
#define AURA_GESTURES_H
#include <stdint.h>
#include <stdbool.h>
enum aura_gesture { AG_NONE, AG_PRESS, AG_DOUBLE, AG_HOLD, AG_MAINTENANCE };
struct aura_gesture_state {
    int raw, stable, clicks;
    int64_t change, pressed, deadline;
    bool held, maintenance;
};
static inline enum aura_gesture aura_gesture_tick(struct aura_gesture_state *g, int raw,
                                                  int64_t now)
{
    if (raw != g->raw) {
        g->raw = raw;
        g->change = now;
    }
    if (raw != g->stable && now - g->change >= 25) {
        g->stable = raw;
        if (raw) {
            g->pressed = now;
            g->held = false;
            g->maintenance = false;
        } else if (!g->held) {
            g->clicks++;
            g->deadline = now + 300;
        }
    }
    if (g->stable && !g->held && now - g->pressed >= 3000) {
        g->held = true;
        g->clicks = 0;
        return AG_HOLD;
    }
    if (g->stable && !g->maintenance && now - g->pressed >= 10000) {
        g->maintenance = true;
        g->clicks = 0;
        return AG_MAINTENANCE;
    }
    if (g->clicks && now >= g->deadline && !g->stable) {
        int n = g->clicks;
        g->clicks = 0;
        return n >= 2 ? AG_DOUBLE : AG_PRESS;
    }
    return AG_NONE;
}
#endif
