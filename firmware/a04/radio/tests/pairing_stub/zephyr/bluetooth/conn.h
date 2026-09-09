#ifndef AURA_PAIRING_TEST_CONN_H
#define AURA_PAIRING_TEST_CONN_H
#include <stdint.h>
#include <stdbool.h>
struct bt_conn { unsigned refs;uint64_t generation;int security;uint8_t key_bytes;bool connected; };
typedef int bt_security_t;
#define BT_SECURITY_L4 4
enum bt_security_err { BT_SECURITY_ERR_SUCCESS=0,BT_SECURITY_ERR_AUTH_FAIL,
    BT_SECURITY_ERR_AUTH_REQUIREMENT,BT_SECURITY_ERR_PAIR_NOT_ALLOWED };
struct bt_conn_pairing_feat { uint8_t io_capability,oob_data_flag,auth_req,max_enc_key_size,init_key_dist,resp_key_dist; };
struct bt_conn_auth_cb {
    enum bt_security_err (*pairing_accept)(struct bt_conn *,const struct bt_conn_pairing_feat *);
    void (*passkey_display)(struct bt_conn *,unsigned int);
    void (*cancel)(struct bt_conn *);
    void (*pairing_confirm)(struct bt_conn *);
};
struct bt_conn_auth_info_cb {
    void (*pairing_complete)(struct bt_conn *,bool);
    void (*pairing_failed)(struct bt_conn *,enum bt_security_err);
};
struct bt_conn_cb { void (*disconnected)(struct bt_conn *,uint8_t); };
#define BT_CONN_CB_DEFINE(name) struct bt_conn_cb name
struct bt_conn *bt_conn_ref(struct bt_conn *conn);
void bt_conn_unref(struct bt_conn *conn);
int bt_conn_auth_cancel(struct bt_conn *conn);
int bt_conn_auth_cb_register(const struct bt_conn_auth_cb *cb);
int bt_conn_auth_info_cb_register(struct bt_conn_auth_info_cb *cb);
bt_security_t bt_conn_get_security(const struct bt_conn *conn);
uint8_t bt_conn_enc_key_size(const struct bt_conn *conn);
void bt_set_bondable(bool enable);
#endif
