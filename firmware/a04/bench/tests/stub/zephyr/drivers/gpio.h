/* SPDX-License-Identifier: MIT */
#ifndef BENCH_STUB_GPIO_H
#define BENCH_STUB_GPIO_H
#include "../../../../../tests/audio_stub/zephyr/drivers/gpio.h"
#define GPIO_INPUT 1
#define GPIO_INT_EDGE_BOTH 2
#define BENCH_PIN_gpios 5
#define BENCH_PIN_mic_enable_gpios 1
#define BENCH_PIN_privacy_gpios 2
#define GPIO_DT_SPEC_GET(n,p) {.port=&bench_devices[0],.pin=BENCH_PIN_##p}
typedef uint32_t gpio_port_pins_t;
struct gpio_callback {
    void (*handler)(const struct device *,struct gpio_callback *,gpio_port_pins_t);
};
int gpio_pin_get_dt(const struct gpio_dt_spec *);
void gpio_init_callback(struct gpio_callback *,
    void (*)(const struct device *,struct gpio_callback *,gpio_port_pins_t),uint32_t);
int gpio_add_callback(const struct device *,struct gpio_callback *);
int gpio_pin_interrupt_configure_dt(const struct gpio_dt_spec *,int);
#endif
