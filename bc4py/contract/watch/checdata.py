from bc4py.config import C, V, NewInfo
from bc4py.chain import Block, TX
from bc4py.database.create import closing, create_db
from bc4py.database.account import read_address2user, read_user2name
from bc4py.database.validator import *
from expiringdict import ExpiringDict
from time import time
import bjson


watching_tx = ExpiringDict(max_len=1000, max_age_seconds=10800)
cashe = ExpiringDict(max_len=100, max_age_seconds=3600)


def check_new_tx(tx: TX):
    if tx.height is not None:
        raise CheckWatchError('is not unconfirmed? {}'.format(tx))
    elif tx.message_type != C.MSG_BYTE:
        return
    elif tx.type == C.TX_CONCLUDE_CONTRACT:
        # 十分な署名が集まったら消す
        c_address, start_hash, c_storage = bjson.loads(tx.message)
        v = get_validator_object(c_address=c_address, stop_txhash=tx.hash)
        related_list = check_related_address(v.validators)
        if related_list:
            watching_tx[tx.hash] = (time(), tx, related_list, c_address, start_hash, c_storage)
    elif tx.type == C.TX_VALIDATOR_EDIT:
        # 十分な署名が集まったら消す
        c_address, new_address, flag, sig_diff = bjson.loads(tx.message)
        v = get_validator_object(c_address=c_address, stop_txhash=tx.hash)
        related_list = check_related_address(v.validators)
        if related_list:
            watching_tx[tx.hash] = (time(), tx, related_list, c_address, new_address, flag, sig_diff)
    else:
        pass


def check_new_block(block: Block):
    for tx in block.txs:
        if tx.height is None:
            raise CheckWatchError('is not confirmed? {}'.format(tx))
        elif tx.message_type != C.MSG_BYTE:
            return
        elif tx.type == C.TX_TRANSFER:
            # ConcludeTXを作成するべきフォーマットのTXを見つける
            c_address, c_method, c_args = bjson.loads(tx.message)
            v = get_validator_object(c_address=c_address)
            related_list = check_related_address(v.validators)
            if related_list:
                watching_tx[tx.hash] = (time(), tx, related_list, c_address, c_method, c_args)
        elif tx.type == C.TX_CONCLUDE_CONTRACT:
            if tx.hash in watching_tx:
                del watching_tx[tx.hash]
        elif tx.type == C.TX_VALIDATOR_EDIT:
            if tx.hash in watching_tx:
                del watching_tx[tx.hash]
        else:
            pass


def check_related_address(address_list):
    r = list()
    with closing(create_db(V.DB_ACCOUNT_PATH)) as db:
        cur = db.cursor()
        for address in address_list:
            user = read_address2user(address=address, cur=cur)
            if user:
                r.append((read_user2name(user, cur), address))
    return r


def decode(b):
    if isinstance(b, bytes) or isinstance(b, bytearray):
        return b.decode(errors='ignore')
    elif isinstance(b, set) or isinstance(b, list) or isinstance(b, tuple):
        return tuple(decode(data) for data in b)
    elif isinstance(b, dict):
        return {decode(k): decode(v) for k, v in b.items()}
    else:
        return b
        # return 'Cannot decode type {}'.format(type(b))


class CheckWatchError(Exception):
    pass  # use for check fail


__all__ = [
    "watching_tx",
    "check_new_tx",
    "check_new_block",
    "CheckWatchError"
]