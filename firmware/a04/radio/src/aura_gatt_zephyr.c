/* SPDX-License-Identifier: MIT */
#include "aura_gatt_zephyr.h"
#include <zephyr/kernel.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/sys/byteorder.h>
#include <errno.h>
#include <string.h>

/* One unenhanced ATT bearer makes a long auth read one ordered snapshot. */
BUILD_ASSERT(CONFIG_BT_MAX_CONN == 1, "AURA radio admits one connection");
BUILD_ASSERT(IS_ENABLED(CONFIG_BT_SMP), "AURA requires SMP");
BUILD_ASSERT(IS_ENABLED(CONFIG_BT_SMP_SC_ONLY), "AURA requires Secure Connections");
BUILD_ASSERT(!IS_ENABLED(CONFIG_BT_EATT), "AURA auth snapshots require one ATT bearer");

#define UUID(n) BT_UUID_128_ENCODE(n, 0x1b15, 0x4f0d, 0x8fe5, 0x3f942170a004)
#define TX_MAX 514u
#define TX_TIMEOUT_MS 10000
#define TX_RETRIES 5u
static struct bt_uuid_128 service_uuid = BT_UUID_INIT_128(UUID(0x7f520000));
static struct bt_uuid_128 command_uuid = BT_UUID_INIT_128(UUID(0x7f520001));
static struct bt_uuid_128 response_uuid = BT_UUID_INIT_128(UUID(0x7f520002));
static struct bt_uuid_128 auth_uuid = BT_UUID_INIT_128(UUID(0x7f520003));

enum tx_state { TX_FREE, TX_PREPARING, TX_READY, TX_SENDING, TX_SUBMITTED, TX_DONE };
struct tx_slot {
    struct bt_conn *conn;
    struct bt_gatt_notify_params params;
    uint64_t connection, engine, epoch, delivery;
    int64_t deadline;
    uint16_t transaction, offset, total, bytes, mtu;
    uint8_t data[TX_MAX], retries;
    enum tx_state state;
    bool success, completion_seen;
};
struct command_slot {
    uint64_t generation;
    uint8_t bytes, data[AURA_GATT_FRAME_MAX];
    bool full;
};
/* Shared fields below owner are protected by lock. owner is touched ONLY by
 * aura_gatt_owner_tick on the serialized storage thread. */
static struct {
    struct k_spinlock lock;
    struct k_work_delayable tx_work, control_work, deadline_work;
    struct bt_conn *conn;
    struct aura_gatt_link link;
    uint64_t generation_counter, tx_epoch, security_request;
    int64_t auth_deadline;
    bool initialized, closing, admitted, disconnect_request;
    uint8_t disconnect_retries;
    struct command_slot command, auth;
    uint8_t auth_snapshot[AURA_GATT_AUTH_MAX], auth_read[AURA_GATT_AUTH_MAX];
    uint16_t auth_bytes, auth_read_bytes;
    bool auth_read_valid;
    struct tx_slot tx;
    struct {
        struct aura_transfer *transfer;
        uint64_t connection, engine, epoch, delivery;
        uint16_t transaction, offset, total;
        bool preempted;
        uint8_t response[AURA_TRANSFER_RESPONSE_MAX];
    } owner;
} aura_gatt_state;
#define S aura_gatt_state

static void tx_work_handler(struct k_work *work);
static void control_work_handler(struct k_work *work);
static void deadline_work_handler(struct k_work *work);
static void notify_complete(struct bt_conn *conn, void *user_data);
static void refresh_subscription(void);
static bool link_security(const struct bt_conn *conn)
{ return conn && bt_conn_get_security(conn) == BT_SECURITY_L4 && bt_conn_enc_key_size(conn) == 16; }

/* lock held: revocation has no dependence on mailbox capacity or owner speed. */
static void invalidate_locked(bool closing)
{
    S.admitted = false;
    memset(&S.command, 0, sizeof(S.command));
    memset(&S.auth, 0, sizeof(S.auth));
    memset(S.auth_snapshot, 0, sizeof(S.auth_snapshot));
    memset(S.auth_read, 0, sizeof(S.auth_read));
    S.auth_bytes = S.auth_read_bytes = 0;
    S.auth_read_valid = false;
    S.security_request = 0;
    S.auth_deadline = 0;
    if (S.tx_epoch != UINT64_MAX) ++S.tx_epoch;
    else closing = true;
    if (S.generation_counter != UINT64_MAX) ++S.generation_counter;
    else closing = true;
    S.closing = closing;
    S.link.generation = S.conn && !closing ? S.generation_counter : 0;
    if (S.link.generation) {
        memcpy(S.auth_snapshot, "ASNO", 4);
        S.auth_bytes = 4;
    }
    if (closing && S.conn) S.disconnect_request = true;
}

static bool current_locked(struct bt_conn *conn, uint64_t generation)
{
    return S.initialized && !S.closing && S.conn == conn && conn &&
           generation && S.link.generation == generation &&
           (!S.auth_deadline || k_uptime_get() < S.auth_deadline);
}
static bool tx_allowed_locked(const struct tx_slot *t)
{
    return current_locked(t->conn, t->connection) && S.admitted &&
           S.auth_deadline > k_uptime_get() && S.link.secure_l4 &&
           S.link.subscribed && t->epoch == S.tx_epoch;
}
static void schedule_control(void)
{ (void)k_work_reschedule(&S.control_work, K_NO_WAIT); }
static void expire_now(void)
{
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    bool expired = S.auth_deadline > 0 && k_uptime_get() >= S.auth_deadline;
    if (expired) invalidate_locked(true);
    k_spin_unlock(&S.lock, key);
    if (expired) schedule_control();
}
static void deadline_work_handler(struct k_work *work)
{
    ARG_UNUSED(work);
    expire_now();
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    int64_t remaining = S.auth_deadline ? S.auth_deadline - k_uptime_get() : 0;
    k_spin_unlock(&S.lock, key);
    if (remaining > 0) (void)k_work_reschedule(&S.deadline_work, K_MSEC(remaining));
}
int aura_gatt_auth_deadline(uint64_t generation, int64_t absolute_ms)
{
    expire_now();
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    int64_t now = k_uptime_get();
    if (!current_locked(S.conn, generation)) {
        k_spin_unlock(&S.lock, key); return -ESTALE;
    }
    if (absolute_ms <= now) {
        invalidate_locked(true);
        k_spin_unlock(&S.lock, key); schedule_control(); return -ETIMEDOUT;
    }
    if (absolute_ms - now > INT32_MAX) {
        k_spin_unlock(&S.lock, key); return -EINVAL;
    }
    S.auth_deadline = absolute_ms;
    k_spin_unlock(&S.lock, key);
    (void)k_work_reschedule(&S.deadline_work, K_MSEC(absolute_ms - now));
    return 0;
}
uint64_t aura_gatt_connection_generation(struct bt_conn *conn)
{
    expire_now();
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    uint64_t result = current_locked(conn, S.link.generation) ? S.link.generation : 0;
    k_spin_unlock(&S.lock, key);
    return result;
}

void aura_gatt_disconnect(uint64_t generation)
{
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    bool match = S.conn && generation && S.link.generation == generation;
    if (match) invalidate_locked(true);
    k_spin_unlock(&S.lock, key);
    if (match) schedule_control();
}
void aura_gatt_request_security(uint64_t generation)
{
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    bool match = current_locked(S.conn, generation);
    if (match) S.security_request = generation;
    k_spin_unlock(&S.lock, key);
    if (match) schedule_control();
}
void aura_gatt_link_snapshot(struct aura_gatt_link *out)
{
    if (!out) return;
    expire_now();
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    *out = S.link;
    out->transfer_ready = S.admitted && current_locked(S.conn, S.link.generation) &&
                          S.auth_deadline > k_uptime_get();
    k_spin_unlock(&S.lock, key);
}
bool aura_gatt_auth_take(struct aura_gatt_auth_frame *out)
{
    if (!out) return false;
    expire_now();
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    bool have = S.auth.full && current_locked(S.conn, S.auth.generation) && S.link.secure_l4;
    memset(out, 0, sizeof(*out));
    if (have) {
        out->generation = S.auth.generation;
        out->bytes = S.auth.bytes;
        memcpy(out->data, S.auth.data, S.auth.bytes);
    }
    memset(&S.auth, 0, sizeof(S.auth));
    k_spin_unlock(&S.lock, key);
    return have;
}
int aura_gatt_auth_publish(uint64_t generation, const uint8_t *data, size_t bytes)
{
    if (bytes > AURA_GATT_AUTH_MAX || (!data && bytes)) return -EINVAL;
    expire_now();
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    if (!current_locked(S.conn, generation) || !S.link.secure_l4) {
        k_spin_unlock(&S.lock, key); return -ESTALE;
    }
    memset(S.auth_snapshot, 0, sizeof(S.auth_snapshot));
    if (bytes) memcpy(S.auth_snapshot, data, bytes);
    S.auth_bytes = (uint16_t)bytes;
    /* An existing long read keeps its independent snapshot until offset zero. */
    k_spin_unlock(&S.lock, key);
    return 0;
}

static ssize_t receive_frame(struct bt_conn *conn, const void *buf, uint16_t len,
                             uint16_t offset, uint8_t flags, bool auth)
{
    if (offset) return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    if (flags) return BT_GATT_ERR(BT_ATT_ERR_NOT_SUPPORTED);
    if (!buf || len < 4 || len > AURA_GATT_FRAME_MAX)
        return BT_GATT_ERR(BT_ATT_ERR_INVALID_ATTRIBUTE_LEN);
    expire_now();
    if (!link_security(conn)) return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    if (!current_locked(conn, S.link.generation) || !S.link.secure_l4 ||
        (!auth && (!S.admitted || !S.link.subscribed))) {
        k_spin_unlock(&S.lock, key); return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
    }
    struct command_slot *slot = auth ? &S.auth : &S.command;
    if (slot->full) {
        bool same = slot->generation == S.link.generation && slot->bytes == len &&
                    !memcmp(slot->data, buf, len);
        k_spin_unlock(&S.lock, key);
        return same ? len : BT_GATT_ERR(BT_ATT_ERR_INSUFFICIENT_RESOURCES);
    }
    slot->generation = S.link.generation;
    slot->bytes = (uint8_t)len;
    memcpy(slot->data, buf, len);
    slot->full = true;
    k_spin_unlock(&S.lock, key);
    return len;
}
static ssize_t command_write(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                             const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{ ARG_UNUSED(attr); return receive_frame(conn, buf, len, offset, flags, false); }
static ssize_t auth_write(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                          const void *buf, uint16_t len, uint16_t offset, uint8_t flags)
{ ARG_UNUSED(attr); return receive_frame(conn, buf, len, offset, flags, true); }
static ssize_t auth_read(struct bt_conn *conn, const struct bt_gatt_attr *attr,
                         void *buf, uint16_t len, uint16_t offset)
{
    ARG_UNUSED(attr);
    if (!buf && len) return BT_GATT_ERR(BT_ATT_ERR_UNLIKELY);
    expire_now();
    if (!link_security(conn)) return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    if (!current_locked(conn, S.link.generation) || !S.link.secure_l4) {
        k_spin_unlock(&S.lock, key); return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
    }
    if (!offset) {
        memcpy(S.auth_read, S.auth_snapshot, sizeof(S.auth_read));
        S.auth_read_bytes = S.auth_bytes;
        S.auth_read_valid = true;
    }
    if (!S.auth_read_valid || offset > S.auth_read_bytes) {
        k_spin_unlock(&S.lock, key); return BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
    }
    size_t n = S.auth_read_bytes - offset;
    if (n > len) n = len;
    if (n) memcpy(buf, S.auth_read + offset, n);
    k_spin_unlock(&S.lock, key);
    return (ssize_t)n;
}
static ssize_t ccc_write(struct bt_conn *conn, const struct bt_gatt_attr *attr, uint16_t value)
{
    ARG_UNUSED(attr);
    if (value != 0 && value != BT_GATT_CCC_NOTIFY)
        return BT_GATT_ERR(BT_ATT_ERR_VALUE_NOT_ALLOWED);
    expire_now();
    if (!link_security(conn)) return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    if (!current_locked(conn, S.link.generation) || !S.link.secure_l4) {
        k_spin_unlock(&S.lock, key); return BT_GATT_ERR(BT_ATT_ERR_AUTHORIZATION);
    }
    if (!value && S.link.subscribed) {
        S.link.subscribed = false;
        invalidate_locked(false);
    }
    k_spin_unlock(&S.lock, key);
    return sizeof(uint16_t);
}
static void ccc_changed(const struct bt_gatt_attr *attr, uint16_t value)
{ ARG_UNUSED(attr); ARG_UNUSED(value); refresh_subscription(); }

BT_GATT_SERVICE_DEFINE(aura_radio_service,
    BT_GATT_PRIMARY_SERVICE(&service_uuid),
    BT_GATT_CHARACTERISTIC(&command_uuid.uuid, BT_GATT_CHRC_WRITE,
        BT_GATT_PERM_WRITE_LESC, NULL, command_write, NULL),
    BT_GATT_CHARACTERISTIC(&response_uuid.uuid, BT_GATT_CHRC_NOTIFY,
        BT_GATT_PERM_READ_LESC, NULL, NULL, NULL),
    BT_GATT_CCC_WITH_WRITE_CB(ccc_changed, ccc_write,
        BT_GATT_PERM_READ_LESC | BT_GATT_PERM_WRITE_LESC),
    BT_GATT_CHARACTERISTIC(&auth_uuid.uuid, BT_GATT_CHRC_READ | BT_GATT_CHRC_WRITE,
        BT_GATT_PERM_READ_LESC | BT_GATT_PERM_WRITE_LESC, auth_read, auth_write, NULL)
);
#define RESPONSE_ATTR (&aura_radio_service.attrs[4])

static void refresh_subscription(void)
{
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    struct bt_conn *conn = S.conn ? bt_conn_ref(S.conn) : NULL;
    uint64_t generation = S.link.generation;
    k_spin_unlock(&S.lock, key);
    if (!conn) return;
    bool subscribed = bt_gatt_is_subscribed(conn, RESPONSE_ATTR, BT_GATT_CCC_NOTIFY);
    key = k_spin_lock(&S.lock);
    if (current_locked(conn, generation)) {
        if (S.link.subscribed && !subscribed) invalidate_locked(false);
        S.link.subscribed = subscribed;
    }
    k_spin_unlock(&S.lock, key);
    bt_conn_unref(conn);
}
static void connected(struct bt_conn *conn, uint8_t err)
{
    if (err) return;
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    bool reject = !S.initialized || S.conn;
    if (!reject) {
        S.conn = bt_conn_ref(conn);
        S.link.connected = true;
        S.link.mtu = 23;
        S.link.secure_l4 = false;
        S.link.subscribed = false;
        S.disconnect_request = false;
        S.disconnect_retries = 0;
        invalidate_locked(false);
    }
    bool exhausted = !reject && S.closing;
    k_spin_unlock(&S.lock, key);
    if (reject) (void)bt_conn_disconnect(conn, BT_HCI_ERR_CONN_LIMIT_EXCEEDED);
    if (exhausted) schedule_control();
}
static void disconnected(struct bt_conn *conn, uint8_t reason)
{
    ARG_UNUSED(reason);
    struct bt_conn *release = NULL;
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    if (S.conn == conn) {
        release = S.conn;
        S.conn = NULL;
        invalidate_locked(false);
        memset(&S.link, 0, sizeof(S.link));
        S.disconnect_request = false;
    }
    k_spin_unlock(&S.lock, key);
    if (release) bt_conn_unref(release);
    /* Submitted callback slot/ref remains retained until notify_complete. */
}
static void security_changed(struct bt_conn *conn, bt_security_t level, enum bt_security_err err)
{
    bool secure = !err && level == BT_SECURITY_L4 && link_security(conn);
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    bool reject = S.conn == conn && !secure;
    if (S.conn == conn) {
        S.link.secure_l4 = secure;
        if (reject) invalidate_locked(true);
    }
    k_spin_unlock(&S.lock, key);
    if (reject) schedule_control();
    else refresh_subscription();
}
BT_CONN_CB_DEFINE(aura_radio_callbacks) = {
    .connected = connected, .disconnected = disconnected, .security_changed = security_changed,
};
static void mtu_updated(struct bt_conn *conn, uint16_t tx, uint16_t rx)
{
    uint16_t mtu = tx < rx ? tx : rx;
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    bool reject = S.conn == conn &&
        (mtu < 23 || mtu > 517 || (S.admitted && mtu != S.link.mtu));
    if (S.conn == conn) {
        if (reject) invalidate_locked(true);
        else S.link.mtu = mtu;
    }
    k_spin_unlock(&S.lock, key);
    if (reject) schedule_control();
}
static struct bt_gatt_cb gatt_callbacks = { .att_mtu_updated = mtu_updated };

static void control_work_handler(struct k_work *work)
{
    ARG_UNUSED(work);
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    struct bt_conn *conn = S.conn ? bt_conn_ref(S.conn) : NULL;
    bool disconnect = S.disconnect_request;
    bool security = current_locked(S.conn, S.security_request);
    S.security_request = 0;
    k_spin_unlock(&S.lock, key);
    if (!conn) return;
    int r = 0;
    if (disconnect) r = bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
    else if (security) r = bt_conn_set_security(conn, BT_SECURITY_L4);
    bool retry = false;
    key = k_spin_lock(&S.lock);
    if (S.conn == conn && r && r != -ENOTCONN) {
        if (!disconnect) invalidate_locked(true);
        retry = S.disconnect_retries++ < 3;
    }
    k_spin_unlock(&S.lock, key);
    bt_conn_unref(conn);
    if (retry) (void)k_work_reschedule(&S.control_work, K_MSEC(100));
}
static void notify_complete(struct bt_conn *conn, void *user_data)
{
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    struct tx_slot *t = &S.tx;
    if (user_data == t && t->conn == conn &&
        (t->state == TX_SENDING || t->state == TX_SUBMITTED)) {
        if (t->state == TX_SENDING) t->completion_seen = true;
        else { t->success = true; t->state = TX_DONE; }
    }
    k_spin_unlock(&S.lock, key);
    /* No slot access after unlocking: the owner may now reclaim it. */
}
static void tx_work_handler(struct k_work *work)
{
    ARG_UNUSED(work);
    expire_now();
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    struct tx_slot *t = &S.tx;
    if (t->state == TX_SUBMITTED) {
        bool expired = k_uptime_get() >= t->deadline;
        uint64_t generation = t->connection;
        k_spin_unlock(&S.lock, key);
        if (expired) aura_gatt_disconnect(generation);
        return; /* Do not reuse callback storage on timeout/disconnect. */
    }
    if (t->state != TX_READY) { k_spin_unlock(&S.lock, key); return; }
    if (!tx_allowed_locked(t) || k_uptime_get() >= t->deadline) {
        uint64_t generation = t->connection;
        bool close = current_locked(t->conn, generation) && t->epoch == S.tx_epoch;
        t->state = TX_DONE; t->success = false;
        k_spin_unlock(&S.lock, key);
        if (close) aura_gatt_disconnect(generation);
        return;
    }
    t->state = TX_SENDING;
    struct bt_conn *conn = t->conn; /* Slot owns this ref through callback. */
    uint64_t generation = t->connection;
    uint16_t mtu = t->mtu;
    k_spin_unlock(&S.lock, key);
    int r = -ECANCELED;
    bool available = link_security(conn) &&
        bt_gatt_is_subscribed(conn, RESPONSE_ATTR, BT_GATT_CCC_NOTIFY) &&
        bt_gatt_get_mtu(conn) == mtu;
    key = k_spin_lock(&S.lock);
    available = available && tx_allowed_locked(t);
    k_spin_unlock(&S.lock, key);
    /* Revocation after this admission point cannot recall submitted radio data. */
    if (available) r = bt_gatt_notify_cb(conn, &t->params);
    bool retry = false, close = false;
    key = k_spin_lock(&S.lock);
    if (!r) {
        if (t->state == TX_SENDING) {
            t->success = t->completion_seen;
            t->state = t->completion_seen ? TX_DONE : TX_SUBMITTED;
        }
    } else if (t->state == TX_SENDING) {
        bool resource = r == -ENOMEM || r == -ENOBUFS || r == -EAGAIN || r == -EBUSY;
        retry = resource && tx_allowed_locked(t) && t->retries++ < TX_RETRIES &&
                k_uptime_get() < t->deadline;
        t->state = retry ? TX_READY : TX_DONE;
        t->success = false;
        close = !retry && current_locked(t->conn, generation) && t->epoch == S.tx_epoch;
    }
    k_spin_unlock(&S.lock, key);
    if (close) aura_gatt_disconnect(generation);
    if (retry) (void)k_work_reschedule(&S.tx_work, K_MSEC(20));
    else if (!r) (void)k_work_reschedule(&S.tx_work, K_MSEC(TX_TIMEOUT_MS));
}

void aura_gatt_init(void)
{
    if (S.initialized) return;
    k_work_init_delayable(&S.tx_work, tx_work_handler);
    k_work_init_delayable(&S.control_work, control_work_handler);
    k_work_init_delayable(&S.deadline_work, deadline_work_handler);
    S.initialized = true;
    bt_gatt_cb_register(&gatt_callbacks);
}
size_t aura_gatt_static_bytes(void) { return sizeof(S); }

/* From here on, all transfer calls belong to the one storage owner. */
static void clear_owner_delivery(void)
{ S.owner.delivery = 0; S.owner.transaction = S.owner.offset = S.owner.total = 0; }
static void cancel_copies(void)
{
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    S.admitted = false;
    memset(&S.command, 0, sizeof(S.command));
    if (S.tx_epoch != UINT64_MAX) ++S.tx_epoch;
    else invalidate_locked(true);
    k_spin_unlock(&S.lock, key);
    clear_owner_delivery();
}
static int owner_fail(int result, uint64_t connection)
{
    aura_gatt_disconnect(connection);
    if (S.owner.engine)
        (void)aura_transfer_session_end(S.owner.transfer, S.owner.engine);
    S.owner.engine = S.owner.connection = 0;
    cancel_copies();
    return result;
}
static int drain_completion(void)
{
    /* Copy only immutable identity fields; never put the 514-byte slot on stack. */
    uint64_t connection = 0, engine = 0, epoch = 0, delivery = 0;
    uint16_t transaction = 0, offset = 0, total = 0, bytes = 0;
    bool success = false;
    struct bt_conn *release = NULL;
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    if (S.tx.state == TX_DONE) {
        struct tx_slot *t = &S.tx;
        connection = t->connection; engine = t->engine; epoch = t->epoch;
        delivery = t->delivery; transaction = t->transaction;
        offset = t->offset; total = t->total; bytes = t->bytes;
        success = t->success && tx_allowed_locked(t);
        release = t->conn;
        memset(t, 0, sizeof(*t));
    }
    k_spin_unlock(&S.lock, key);
    if (release) bt_conn_unref(release);
    if (!release || connection != S.owner.connection || engine != S.owner.engine ||
        epoch != S.owner.epoch || delivery != S.owner.delivery ||
        transaction != S.owner.transaction || offset != S.owner.offset) return 0;
    if (!success || bytes <= 8 || offset + bytes - 8 > total)
        return owner_fail(AURA_TRANSFER_STATE, connection);
    S.owner.offset = (uint16_t)(offset + bytes - 8);
    if (S.owner.offset == total) {
        int r = aura_transfer_response_sent(S.owner.transfer, engine, transaction, delivery);
        clear_owner_delivery();
        if (r) return owner_fail(r, connection);
    }
    return 0;
}
static int publish_fragment(void)
{
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    bool free = S.tx.state == TX_FREE;
    k_spin_unlock(&S.lock, key);
    if (!free) return 0;
    size_t bytes = 0; uint64_t delivery = 0;
    int r = aura_transfer_copy_response(S.owner.transfer, S.owner.engine,
        S.owner.response, sizeof(S.owner.response), &bytes, &delivery);
    if (r) return owner_fail(r, S.owner.connection);
    if (bytes < 4 || bytes > AURA_TRANSFER_RESPONSE_MAX)
        return owner_fail(AURA_TRANSFER_STATE, S.owner.connection);
    if (S.owner.delivery != delivery) {
        S.owner.delivery = delivery; S.owner.offset = 0;
        S.owner.total = (uint16_t)bytes;
        S.owner.transaction = sys_get_le16(S.owner.response + 2);
    }
    key = k_spin_lock(&S.lock);
    if (!current_locked(S.conn, S.owner.connection) || !S.admitted ||
        !S.link.secure_l4 || !S.link.subscribed || S.tx.state != TX_FREE) {
        k_spin_unlock(&S.lock, key); return 0;
    }
    struct tx_slot *t = &S.tx;
    t->state = TX_PREPARING; t->conn = bt_conn_ref(S.conn);
    t->connection = S.owner.connection; t->engine = S.owner.engine;
    t->epoch = S.tx_epoch; S.owner.epoch = t->epoch;
    t->transaction = S.owner.transaction; t->delivery = delivery;
    t->offset = S.owner.offset; t->total = S.owner.total; t->mtu = S.link.mtu;
    k_spin_unlock(&S.lock, key);
    size_t fragment_bytes = 0;
    r = aura_transfer_copy_fragment(S.owner.transfer, S.owner.engine,
        t->transaction, delivery, t->mtu, t->offset, t->data, sizeof(t->data), &fragment_bytes);
    key = k_spin_lock(&S.lock);
    bool ready = !r && fragment_bytes >= 9 && fragment_bytes <= TX_MAX && tx_allowed_locked(t);
    if (ready) {
        t->bytes = (uint16_t)fragment_bytes;
        t->params.attr = RESPONSE_ATTR; t->params.data = t->data;
        t->params.len = t->bytes; t->params.func = notify_complete; t->params.user_data = t;
        t->deadline = k_uptime_get() + TX_TIMEOUT_MS;
        t->state = TX_READY;
    } else { t->state = TX_DONE; t->success = false; }
    k_spin_unlock(&S.lock, key);
    if (ready) (void)k_work_reschedule(&S.tx_work, K_NO_WAIT);
    if (r) return owner_fail(r, S.owner.connection);
    return 0;
}
int aura_gatt_owner_tick(struct aura_transfer *transfer, const struct aura_gatt_owner_gate *gate)
{
    if (!S.initialized || !transfer || !gate) return -EINVAL;
    if (S.owner.transfer && S.owner.transfer != transfer) return -EINVAL;
    S.owner.transfer = transfer;
    struct aura_gatt_link link;
    aura_gatt_link_snapshot(&link);
    bool authorized = gate->authorization == AURA_GATT_GRANTED &&
        gate->connection_generation && gate->connection_generation == link.generation &&
        link.connected && link.secure_l4 && link.subscribed;
    k_spinlock_key_t deadline_key = k_spin_lock(&S.lock);
    authorized = authorized && S.auth_deadline > k_uptime_get();
    k_spin_unlock(&S.lock, deadline_key);
    if (S.owner.engine && (!authorized || S.owner.connection != link.generation)) {
        cancel_copies();
        (void)aura_transfer_session_end(transfer, S.owner.engine);
        S.owner.engine = S.owner.connection = 0;
    }
    if (S.owner.engine && authorized && gate->capture_preempt && !S.owner.preempted) {
        cancel_copies();
        int r = aura_transfer_cancel_work(transfer, S.owner.engine);
        if (r) return owner_fail(r, link.generation);
        S.owner.preempted = true;
    }
    /* Old callbacks must be drained even while no authorized connection exists. */
    int r = drain_completion();
    if (r || !authorized || gate->capture_preempt) return r;
    if (!S.owner.engine) {
        r = aura_transfer_session_begin(transfer, true, &S.owner.engine);
        if (r) return owner_fail(r, link.generation);
        S.owner.connection = link.generation;
        S.owner.preempted = false;
    }
    S.owner.preempted = false;
    struct command_slot command = {0};
    k_spinlock_key_t key = k_spin_lock(&S.lock);
    bool current = current_locked(S.conn, link.generation) &&
                   S.link.secure_l4 && S.link.subscribed;
    if (current) {
        S.admitted = true;
        if (S.command.full && S.command.generation == link.generation) command = S.command;
        memset(&S.command, 0, sizeof(S.command));
    }
    k_spin_unlock(&S.lock, key);
    if (!current) return 0;
    if (command.full) {
        r = aura_transfer_submit(transfer, S.owner.engine, command.data, command.bytes);
        memset(&command, 0, sizeof(command));
        if (r < 0) return owner_fail(r, link.generation);
    }
    r = aura_transfer_step(transfer, S.owner.engine);
    if (r < 0) return owner_fail(r, link.generation);
    return r == AURA_TRANSFER_RESPONSE ? publish_fragment() : 0;
}
