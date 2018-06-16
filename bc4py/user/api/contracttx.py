from bc4py import __chain_version__
from bc4py.config import C, V, P, BlockChainError
from bc4py.contract.utils import *
from bc4py.contract.finishtx import create_finish_tx
from bc4py.user import CoinObject
from bc4py.user.txcreation import *
from bc4py.database.create import closing, create_db
from bc4py.database.builder import builder
from bc4py.database.tools import *
from bc4py.database.account import *
from bc4py.user.network.sendnew import send_newtx
from bc4py.chain.tx import TX
from bc4py.user.utils import message2signature
from bc4py.user.api import web_base
from aiohttp import web
from binascii import hexlify, unhexlify
from nem_ed25519.base import Encryption
import bjson
import time


"""
def contract(c_address, c_tx):\n
    # something
    return outputs, contract_storage
"""


async def contract_detail(request):
    try:
        c_address = request.query['address']
        c_bin = get_contract_binary(c_address)
        c_cs = get_contract_storage(c_address)
        c_cs_data = {k.decode(errors='ignore'): v.decode(errors='ignore')
                     for k, v in c_cs.key_value.items()}
        pickle_dis = binary2dis(c_bin)
        c_obj = binary2contract(c_bin)
        contract_dis = contract2dis(c_obj)
        data = {
            'c_address': c_address,
            'c_cs_data': c_cs_data,
            'c_cs_ver': c_cs.version,
            'pickle_dis': pickle_dis,
            'contract_dis': contract_dis,
            'c_bin': hexlify(c_bin).decode()}
        return web_base.json_res(data)
    except BaseException:
        return web_base.error_res()


async def contract_history(request):
    try:
        c_address = request.query['address']
        data = list()
        for index, start_hash, finish_hash, is_unconfirmed in get_contract_history_iter(c_address):
            data.append({
                'index': index,
                'unconfirmed': is_unconfirmed,
                'start_hash': hexlify(start_hash).decode(),
                'finish_hash': hexlify(finish_hash).decode()})
        return web_base.json_res(data)
    except BaseException:
        return web_base.error_res()


async def source_compile(request):
    post = await web_base.content_type_json_check(request)
    try:
        # TODO:仕様変更の対応
        if 'source' in post:
            source = str(post['source'])
            name = str(post.get('name', None))
            c_obj = string2contract(source, name, limited=False)
        elif 'path' in post:
            c_obj = filepath2contract(path=post['path'])
        else:
            raise BaseException('You need set "source" or "path".')
        c_bin = contract2binary(c_obj)
        c_dis = contract2dis(c_obj)
        return web_base.json_res({
            'hex': hexlify(c_bin).decode(),
            'dis': c_dis})
    except BaseException:
        return web_base.error_res()


async def contract_create(request):
    post = await web_base.content_type_json_check(request)
    with closing(create_db(V.DB_ACCOUNT_PATH, f_on_memory=True)) as db:
        cur = db.cursor()
        try:
            # バイナリをピックルしオブジェクトに戻す
            c_bin = unhexlify(post['hex'].encode())
            c_cs = {k.encode(errors='ignore'): v.encode(errors='ignore')
                    for k, v in post.get('c_cs', dict()).items()}
            binary2contract(c_bin)  # can compile?
            sender_name = post.get('account', C.ANT_UNKNOWN)
            sender_id = read_name2user(sender_name, cur)
            c_address, c_tx = create_contract_tx(c_bin, cur, sender_id, c_cs)
            if not send_newtx(new_tx=c_tx):
                raise BaseException('Failed to send new tx.')
            db.commit()
            data = c_tx.getinfo()
            data['c_address'] = c_address
            data['fee'] = c_tx.gas_price * c_tx.gas_amount
            return web_base.json_res(data)
        except BaseException:
            return web_base.error_res()


async def contract_start(request):
    post = await web_base.content_type_json_check(request)
    with closing(create_db(V.DB_ACCOUNT_PATH, f_on_memory=True)) as db:
        cur = db.cursor()
        try:
            c_address = post['address']
            c_data = post.get('data', None)
            outputs = post.get('outputs', list())
            account = post.get('account', C.ANT_UNKNOWN)
            user_id = read_name2user(account, cur)
            # TX作成
            outputs = [(address, coin_id, amount) for address, coin_id, amount in outputs]
            start_tx = start_contract_tx(c_address, c_data, cur, outputs, user_id)
            # 送信
            if not send_newtx(start_tx):
                raise BaseException('Failed to send new tx.')
            db.commit()
            data = start_tx.getinfo()
            data['c_address'] = c_address
            data['fee'] = start_tx.gas_price * start_tx.gas_amount
            data['c_data'] = c_data
            return web_base.json_res(data)
        except BaseException:
            return web_base.error_res()


__all__ = [
    "contract_detail",
    "contract_history",
    "source_compile",
    "contract_create",
    "contract_start",
]
