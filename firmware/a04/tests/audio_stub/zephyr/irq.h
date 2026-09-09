/* SPDX-License-Identifier: MIT -- hooks defer while this simulated IRQ lock is held. */
#ifndef AUDIO_STUB_IRQ_H
#define AUDIO_STUB_IRQ_H
unsigned int irq_lock(void);
void irq_unlock(unsigned int key);
#endif
