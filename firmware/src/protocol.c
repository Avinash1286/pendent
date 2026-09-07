/* SPDX-License-Identifier: MIT */
#include "aura.h"
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/byteorder.h>
#include <errno.h>
#include <string.h>
#define UUID(n) BT_UUID_128_ENCODE(n, 0x1b15, 0x4f0d, 0x8fe5, 0x3f942170a001)
static struct bt_uuid_128 service = BT_UUID_INIT_128(UUID(0x7f510000));
static struct bt_uuid_128 cmd_uuid = BT_UUID_INIT_128(UUID(0x7f510001));
static struct bt_uuid_128 rsp_uuid = BT_UUID_INIT_128(UUID(0x7f510002));
K_MUTEX_DEFINE(response_lock);
static uint8_t response[202] = {2, 0, 0, 0}, request[20];
static uint16_t response_len = 4, request_len;
static bool busy;
static int64_t pair_until;
static struct k_spinlock pair_lock;
static int64_t pairing_remaining(void)
{
    k_spinlock_key_t key = k_spin_lock(&pair_lock);
    int64_t remaining = pair_until - k_uptime_get();
    k_spin_unlock(&pair_lock, key);
    return remaining;
}
static struct k_work cmd_work;
static struct k_work_delayable adv_work;
static struct k_work_q protocol_queue;
K_THREAD_STACK_DEFINE(protocol_stack, 4096);
static int status_for(int r)
{
    if (!r)
        return 0;
    if (r == -ENOENT)
        return 3;
    if (r == -EPERM || r == -EACCES)
        return 5;
    if (r == -EINVAL)
        return 2;
    if (r == -EBUSY)
        return 5;
    return 4;
}
static void execute(struct k_work *work)
{
    ARG_UNUSED(work);
    uint8_t reply[202] = {0, request[1], request[2], request[3]};
    size_t len = 4;
    int r = 0;
    uint8_t op = request[1];
    k_mutex_lock(&aura_store_lock, K_FOREVER);
    if (op == 3 && (aura_state == 1 || aura_state == 2 || aura_capture_pending())) {
        /* A far random seek must never block the capture thread behind a long scan. */
        r = -EACCES;
        goto done;
    }
    switch (op) {
    case 1:
        if (request_len != 4) {
            r = -EINVAL;
            break;
        }
        reply[4] = 1;
        reply[5] = aura_state;
        reply[6] = aura_privacy;
        reply[7] = (!aura_charge_allowed ? 1 : 0) | (aura_store.fault ? 2 : 0);
        sys_put_le16(aura_battery_mv, reply + 8);
        sys_put_le32(aj_free(&aura_store), reply + 10);
        uint16_t count = 0;
        for (int i = 0; i < aura_store.count; i++)
            if (!aura_store.notes[i].deleted && i != aura_store.active)
                count++;
        sys_put_le16(count, reply + 14);
        len = 16;
        break;
    case 2: {
        if (request_len != 6) {
            r = -EINVAL;
            break;
        }
        uint16_t index = sys_get_le16(request + 4);
        struct aj_note *n = NULL;
        for (int i = 0; i < aura_store.count; i++) {
            if (aura_store.notes[i].deleted || i == aura_store.active)
                continue;
            if (index-- == 0) {
                n = &aura_store.notes[i];
                break;
            }
        }
        if (!n) {
            reply[0] = 6;
            break;
        }
        if (n->fault) {
            r = -EIO;
            break;
        }
        sys_put_le32(n->id, reply + 4);
        sys_put_le64(n->time, reply + 8);
        sys_put_le32(n->bytes, reply + 16);
        sys_put_le32(n->crc, reply + 20);
        sys_put_le32(16000, reply + 24);
        reply[28] = 1;
        reply[29] = 16;
        reply[30] = n->recovered ? 1 : 0;
        len = 31;
        break;
    }
    case 3: {
        if (request_len != 14) {
            r = -EINVAL;
            break;
        }
        uint32_t id = sys_get_le32(request + 4), offset = sys_get_le32(request + 8);
        uint16_t n = sys_get_le16(request + 12);
        if (n < 1 || n > 180) {
            r = -EINVAL;
            break;
        }
        uint8_t prior_state = aura_state;
        aura_state = 2;
        r = aj_read(&aura_store, id, offset, reply + 14, n);
        aura_state = prior_state == 4 ? 4 : (aura_privacy ? 3 : 0);
        if (r >= 0) {
            sys_put_le32(id, reply + 4);
            sys_put_le32(offset, reply + 8);
            sys_put_le16(r, reply + 12);
            sys_put_le32(aj_crc(0, reply + 14, r), reply + 14 + r);
            len = 18 + r;
            r = 0;
        }
        break;
    }
    case 4:
        if (request_len != 16) {
            r = -EINVAL;
            break;
        }
        r = aj_delete(&aura_store, sys_get_le32(request + 4), sys_get_le32(request + 8),
                      sys_get_le32(request + 12));
        break;
    case 5:
        if (request_len != 12) {
            r = -EINVAL;
            break;
        }
        uint64_t t = sys_get_le64(request + 4);
        if (t < 1577836800ull || t > 4102444800ull) {
            r = -EINVAL;
            break;
        }
        aura_set_time(t);
        break;
    case 6:
        if (request_len != 8 || sys_get_le32(request + 4) != 0x53415245u) {
            r = -EINVAL;
            break;
        }
        r = aura_format();
        break;
    default:
        r = -EINVAL;
    }
done:
    k_mutex_unlock(&aura_store_lock);
    if (r) {
        reply[0] = status_for(r);
        len = 4;
    }
    k_mutex_lock(&response_lock, K_FOREVER);
    memcpy(response, reply, len);
    response_len = len;
    busy = false;
    k_mutex_unlock(&response_lock);
}
static ssize_t write_cmd(struct bt_conn *conn, const struct bt_gatt_attr *attr, const void *buf,
                         uint16_t len, uint16_t offset, uint8_t flags)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(attr);
    if (offset || len < 4 || len > 20 || (flags & BT_GATT_WRITE_FLAG_PREPARE))
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    const uint8_t *b = buf;
    if (b[0] != 1)
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    k_mutex_lock(&response_lock, K_FOREVER);
    if (busy) {
        k_mutex_unlock(&response_lock);
        return BT_GATT_ERR(BT_ATT_ERR_PROCEDURE_IN_PROGRESS);
    }
    memcpy(request, b, len);
    request_len = len;
    response[0] = 1;
    memcpy(response + 1, b + 1, 3);
    response_len = 4;
    busy = true;
    k_mutex_unlock(&response_lock);
    k_work_submit_to_queue(&protocol_queue, &cmd_work);
    return len;
}
static ssize_t read_rsp(struct bt_conn *conn, const struct bt_gatt_attr *attr, void *buf,
                        uint16_t len, uint16_t offset)
{
    k_mutex_lock(&response_lock, K_FOREVER);
    ssize_t r = bt_gatt_attr_read(conn, attr, buf, len, offset, response, response_len);
    k_mutex_unlock(&response_lock);
    return r;
}
BT_GATT_SERVICE_DEFINE(aura_service, BT_GATT_PRIMARY_SERVICE(&service),
                       BT_GATT_CHARACTERISTIC(&cmd_uuid.uuid, BT_GATT_CHRC_WRITE,
                                              BT_GATT_PERM_WRITE_ENCRYPT, NULL, write_cmd, NULL),
                       BT_GATT_CHARACTERISTIC(&rsp_uuid.uuid, BT_GATT_CHRC_READ,
                                              BT_GATT_PERM_READ_ENCRYPT, read_rsp, NULL, NULL));
static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR),
    BT_DATA_BYTES(BT_DATA_UUID128_ALL, UUID(0x7f510000))};
static const struct bt_data sd[] = {
    BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1)};
static void bond_added(const struct bt_bond_info *info, void *user)
{
    int *n = user;
    if (bt_le_filter_accept_list_add(&info->addr) == 0)
        (*n)++;
}
static void advertise(struct k_work *work)
{
    ARG_UNUSED(work);
    bt_le_adv_stop();
    bool open = pairing_remaining() > 0;
    bt_set_bondable(open);
    bt_le_filter_accept_list_clear();
    int bonds = 0;
    bt_foreach_bond(BT_ID_DEFAULT, bond_added, &bonds);
    if (!open && !bonds)
        return;
    struct bt_le_adv_param p = *BT_LE_ADV_CONN_FAST_1;
    p.options |= open ? 0 : (BT_LE_ADV_OPT_FILTER_CONN | BT_LE_ADV_OPT_FILTER_SCAN_REQ);
    int r = bt_le_adv_start(&p, ad, ARRAY_SIZE(ad), sd, ARRAY_SIZE(sd));
    if (open)
        k_work_reschedule(&adv_work, K_MSEC(MAX(1, pairing_remaining())));
    ARG_UNUSED(r);
}
static enum bt_security_err pairing_accept(struct bt_conn *conn,
                                           const struct bt_conn_pairing_feat *feat)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(feat);
    return pairing_remaining() > 0 ? BT_SECURITY_ERR_SUCCESS : BT_SECURITY_ERR_PAIR_NOT_ALLOWED;
}
static void cancel(struct bt_conn *conn)
{
    ARG_UNUSED(conn);
}
static struct bt_conn_auth_cb auth = {.pairing_accept = pairing_accept, .cancel = cancel};
static void mtu_exchanged(struct bt_conn *conn, uint8_t err, struct bt_gatt_exchange_params *params)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(err);
    ARG_UNUSED(params);
}
static struct bt_gatt_exchange_params exchange = {.func = mtu_exchanged};
static void connected(struct bt_conn *conn, uint8_t err)
{
    if (!err) {
        bt_conn_set_security(conn, BT_SECURITY_L2);
        bt_gatt_exchange_mtu(conn, &exchange);
    }
}
static void disconnected(struct bt_conn *conn, uint8_t reason)
{
    ARG_UNUSED(conn);
    ARG_UNUSED(reason);
    k_work_reschedule(&adv_work, K_MSEC(100));
}
BT_CONN_CB_DEFINE(connection_callbacks) = {.connected = connected, .disconnected = disconnected};
int aura_bluetooth_init(void)
{
    k_work_init(&cmd_work, execute);
    k_work_init_delayable(&adv_work, advertise);
    k_work_queue_start(&protocol_queue, protocol_stack, K_THREAD_STACK_SIZEOF(protocol_stack), 7,
                       NULL);
    int r = bt_conn_auth_cb_register(&auth);
    if (r)
        return r;
    r = bt_enable(NULL);
    if (r)
        return r;
    r = settings_load();
    if (r)
        return r;
    bt_set_bondable(false);
    k_work_reschedule(&adv_work, K_NO_WAIT);
    return 0;
}
void aura_pairing_window(void)
{
    k_spinlock_key_t key = k_spin_lock(&pair_lock);
    pair_until = k_uptime_get() + 60000;
    k_spin_unlock(&pair_lock, key);
    k_work_reschedule(&adv_work, K_NO_WAIT);
}
