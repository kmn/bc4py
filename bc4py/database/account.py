from bc4py.config import C, V, BlockChainError
from bc4py.user import CoinObject, UserCoins
from bc4py.utils import AESCipher
import time
import os
from binascii import hexlify, unhexlify


def read_txhash2log(txhash, cur, f_dict=False):
    d = cur.execute("""
        SELECT `type`,`user`,`coin_id`,`amount`,`time` FROM `log` WHERE `hash`=?
    """, (txhash,)).fetchall()
    if len(d) == 0:
        return None
    movement = UserCoins()
    _type = _time = None
    for _type, user, coin_id, amount, _time in d:
        movement.add_coins(user, coin_id, amount)
    if f_dict:
        movement = {read_user2name(user, cur): coins.coins for user, coins in movement.items()}
        return {
            'txhash': hexlify(txhash).decode(),
            'type': C.txtype2name[_type],
            'movement': movement,
            'time': _time + V.BLOCK_GENESIS_TIME}
    else:
        return _type, movement, _time


def read_log_iter(cur, start=0, f_dict=False):
    d = cur.execute("SELECT DISTINCT `hash` FROM `log` ORDER BY `id` DESC").fetchall()
    c = 0
    for (txhash,) in d:
        if start <= c:
            yield read_txhash2log(txhash, cur, f_dict)
        c += 1


def insert_log(movements, cur, _type=None, _time=None, txhash=None):
    assert isinstance(movements, UserCoins), 'movements is UserCoin.'
    _type = _type or C.TX_INNER
    _time = _time or int(time.time() - V.BLOCK_GENESIS_TIME)
    txhash = txhash or (b'\x00' * 24 + _time.to_bytes(4, 'big') + os.urandom(4))
    move = list()
    index = 0
    for user, coins in movements.items():
        for index, (coin_id, amount) in coins.items():
            move.append((txhash, index, _type, user, coin_id, amount, _time))
            index += 1
    cur.executemany("INSERT INTO `log` VALUES (?,?,?,?,?,?,?)", move)
    return txhash


def read_address2keypair(address, cur):
    d = cur.execute("""
        SELECT `id`,`sk`,`pk` FROM `pool` WHERE `ck`=?
    """, (address,)).fetchone()
    if d is None:
        raise BlockChainError('Not found address {}'.format(address))
    uuid, sk, pk = d
    if len(sk) == 32:
        sk = hexlify(sk).decode()
    elif V.ENCRYPT_KEY:
        sk = AESCipher.decrypt(V.ENCRYPT_KEY, sk)
        if len(sk) != 32:
            raise BlockChainError('Failed decrypt SecretKey. {}'.format(address))
    else:
        raise BlockChainError('Encrypted account.dat but no EncryptKey.')
    sk = hexlify(sk).decode()
    pk = hexlify(pk).decode()
    return uuid, sk, pk


def read_address2user(address, cur):
    user = cur.execute("""
        SELECT `user` FROM `pool` WHERE `ck`=?
    """, (address,)).fetxhone()
    if user is None:
        return None
    return user[0]


def update_keypair_user(uuid, user, cur):
    cur.execute("UPDATE `pool` SET `user`=? WHERE `id`=?", (user, uuid))


def insert_keypairs(pairs, cur):
    sk, pk, ck, user, _time = pairs[0]
    assert isinstance(sk, str) and isinstance(pk, str) and isinstance(ck, str) and isinstance(user, int)
    pairs = [(unhexlify(sk.encode()), unhexlify(pk.encode()), ck, user, _time)
             for sk, pk, ck, user, _time in pairs]
    cur.executemany("""
    INSERT INTO `pool` (`sk`,`pk`,`ck`,`user`,`time`) VALUES (?,?,?,?,?)
    """, pairs)


def read_account_info(user, cur):
    d = cur.execute("""
        SELECT `name`,`description`,`time` FROM `account` WHERE `id`=?
    """, (user,)).fetchone()
    if d is None:
        return None
    name, description, _time = d
    return name, description, _time


def read_pooled_address_iter(cur):
    cur.execute("SELECT `id`,`ck`,`user` FROM `pool`")
    return cur


def read_address2account(address, cur):
    user = read_address2user(address, cur)
    if user is None:
        raise BlockChainError('Not found account {}'.format(address))
    return read_account_info(user, cur)


def read_name2user(name, cur):
    d = cur.execute("""
        SELECT `id` FROM `account` WHERE `name`=?
    """, (name,)).fetchone()
    if d is None:
        return create_account(name, cur)
    return d[0]


def read_user2name(user, cur):
    d = cur.execute("""
        SELECT `name` FROM `account` WHERE `id`=?
    """, (user,)).fetchone()
    if d is None:
        raise Exception('Not found user id. {}'.format(user))
    return d[0]


def create_account(name, cur, description="", _time=None):
    _time = _time or int(time.time() - V.BLOCK_GENESIS_TIME)
    cur.execute("""
        INSERT INTO `account` VALUES (?,?,?)
    """, (name, description, _time))
    d = cur.execute("SELECT last_insert_rowid()").fetchone()
    return d[0]


def create_new_user_keypair(name, cur):
    # ReservedKeypairを１つ取得
    d = cur.execute("""
        SELECT `id`,`sk`,`pk`,`ck` FROM `pool` WHERE `user`=?
    """, (C.ANT_RESERVED,)).fetchone()
    uuid, sk, pk, ck = d
    user = read_name2user(name, cur)
    if user is None:
        # 新規にユーザー作成
        user = create_account(name, cur)
    update_keypair_user(uuid, user, cur)
    return ck


__all__ = (
    "read_txhash2log", "read_log_iter", "insert_log",
    "read_address2keypair", "read_address2user", "update_keypair_user", "insert_keypairs",
    "read_account_info", "read_pooled_address_iter", "read_address2account", "read_name2user", "read_user2name",
    "create_account", "create_new_user_keypair"
)
