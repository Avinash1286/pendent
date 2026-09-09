/* SPDX-License-Identifier: MIT */
#ifndef AUDIO_STUB_GPIO_H
#define AUDIO_STUB_GPIO_H
#include <zephyr/kernel.h>
#define GPIO_OUTPUT_INACTIVE 0
struct gpio_dt_spec { const struct device *port; uint32_t pin, dt_flags; };
static inline bool gpio_is_ready_dt(const struct gpio_dt_spec *s){return s&&device_is_ready(s->port);}
int gpio_pin_configure_dt(const struct gpio_dt_spec *,int);
int gpio_pin_set_dt(const struct gpio_dt_spec *,int);
#endif
