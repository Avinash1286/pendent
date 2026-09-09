/* SPDX-License-Identifier: MIT -- host-only Zephyr/Bluetooth boundary doubles. */
#ifndef AURA_RADIO_TEST_ZEPHYR_STUBS_H
#define AURA_RADIO_TEST_ZEPHYR_STUBS_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
#include <errno.h>
#ifndef ESTALE
#define ESTALE 116
#endif
#define CONFIG_BT_MAX_CONN 1
#define CONFIG_BT_SMP 1
#define CONFIG_BT_SMP_SC_ONLY 1
#define CONFIG_BT_EATT 0
#define IS_ENABLED(value) (value)
#define BUILD_ASSERT(value, message) _Static_assert(value, message)
#define ARG_UNUSED(value) (void)(value)
#define K_NO_WAIT 0
#define K_MSEC(value) (value)
struct k_spinlock { unsigned unused; };
typedef unsigned k_spinlock_key_t;
struct k_work { void (*handler)(struct k_work *); };
struct k_work_delayable { struct k_work work; int64_t due; bool pending; };
k_spinlock_key_t k_spin_lock(struct k_spinlock *);
void k_spin_unlock(struct k_spinlock *, k_spinlock_key_t);
int64_t k_uptime_get(void);
void k_work_init_delayable(struct k_work_delayable *, void (*)(struct k_work *));
int k_work_reschedule(struct k_work_delayable *, int);

typedef uint8_t bt_security_t;
enum bt_security_err { BT_SECURITY_ERR_SUCCESS, BT_SECURITY_ERR_AUTH_FAIL };
#define BT_SECURITY_L4 4
struct bt_conn { unsigned refs; bt_security_t security; uint8_t key_bytes; uint16_t mtu; bool subscribed; };
struct bt_conn *bt_conn_ref(struct bt_conn *);
void bt_conn_unref(struct bt_conn *);
bt_security_t bt_conn_get_security(const struct bt_conn *);
uint8_t bt_conn_enc_key_size(const struct bt_conn *);
int bt_conn_disconnect(struct bt_conn *, uint8_t);
int bt_conn_set_security(struct bt_conn *, bt_security_t);
struct bt_conn_cb {
    void (*connected)(struct bt_conn *, uint8_t);
    void (*disconnected)(struct bt_conn *, uint8_t);
    void (*security_changed)(struct bt_conn *, bt_security_t, enum bt_security_err);
};
#define BT_CONN_CB_DEFINE(name) static const struct bt_conn_cb name
#define BT_HCI_ERR_CONN_LIMIT_EXCEEDED 9
#define BT_HCI_ERR_REMOTE_USER_TERM_CONN 19

struct bt_uuid { uint8_t type; };
struct bt_uuid_128 { struct bt_uuid uuid; uint8_t val[16]; };
#define BT_UUID_128_ENCODE(...) 0
#define BT_UUID_INIT_128(...) { .uuid = {128}, .val = { __VA_ARGS__ } }
struct bt_gatt_attr {
    const void *user_data;
    uint16_t perm;
    ssize_t (*read)(struct bt_conn *, const struct bt_gatt_attr *, void *, uint16_t, uint16_t);
    ssize_t (*write)(struct bt_conn *, const struct bt_gatt_attr *, const void *, uint16_t, uint16_t, uint8_t);
};
#define BT_GATT_SERVICE_DEFINE(name, ...) static const struct { struct bt_gatt_attr attrs[8]; } name = { { __VA_ARGS__ } }
#define BT_GATT_PRIMARY_SERVICE(uuid) { .user_data = (uuid) }
#define BT_GATT_CHARACTERISTIC(uuid, props, permission, reader, writer, user) \
    { .user_data = (uuid) }, { .user_data = (user), .perm = (permission), .read = (reader), .write = (writer) }
#define BT_GATT_CCC_WITH_WRITE_CB(changed, writer, permission) { .perm = (permission) }
#define BT_GATT_CHRC_READ 2
#define BT_GATT_CHRC_WRITE 8
#define BT_GATT_CHRC_NOTIFY 16
#define BT_GATT_PERM_READ_LESC 128
#define BT_GATT_PERM_WRITE_LESC 256
#define BT_GATT_CCC_NOTIFY 1
#define BT_GATT_ERR(value) (-(value))
#define BT_ATT_ERR_INVALID_OFFSET 7
#define BT_ATT_ERR_NOT_SUPPORTED 6
#define BT_ATT_ERR_INVALID_ATTRIBUTE_LEN 13
#define BT_ATT_ERR_AUTHORIZATION 8
#define BT_ATT_ERR_INSUFFICIENT_RESOURCES 17
#define BT_ATT_ERR_UNLIKELY 14
#define BT_ATT_ERR_VALUE_NOT_ALLOWED 19
struct bt_gatt_notify_params {
    const struct bt_uuid *uuid;
    const struct bt_gatt_attr *attr;
    const void *data;
    uint16_t len;
    void (*func)(struct bt_conn *, void *);
    void *user_data;
};
struct bt_gatt_cb { void (*att_mtu_updated)(struct bt_conn *, uint16_t, uint16_t); };
void bt_gatt_cb_register(struct bt_gatt_cb *);
bool bt_gatt_is_subscribed(struct bt_conn *, const struct bt_gatt_attr *, uint16_t);
uint16_t bt_gatt_get_mtu(struct bt_conn *);
int bt_gatt_notify_cb(struct bt_conn *, struct bt_gatt_notify_params *);
static inline uint16_t sys_get_le16(const uint8_t *p) { return (uint16_t)(p[0] | (uint16_t)p[1] << 8); }
#endif
