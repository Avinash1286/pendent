/* SPDX-License-Identifier: MIT */
#include <zephyr/kernel.h>
void uart_poll_out(const struct device *,unsigned char);
int uart_err_check(const struct device *);
int uart_irq_update(const struct device *);
int uart_irq_rx_ready(const struct device *);
int uart_fifo_read(const struct device *,uint8_t *,int);
int uart_irq_callback_user_data_set(const struct device *,void (*)(const struct device *,void *),void *);
void uart_irq_rx_enable(const struct device *);
