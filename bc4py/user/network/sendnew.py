from bc4py.config import C, V, P, BlockChainError
from bc4py.chain.checking import new_insert_block, check_tx, check_tx_time
from bc4py.user.network import BroadcastCmd
from p2p_python.client import ClientCmd
from bc4py.database.builder import tx_builder, builder
from bc4py.user.network.update import update_mining_staking_all_info
import logging
import time
import queue


def mined_newblock(que, pc):
    # 新規採掘BlockをP2Pに公開
    while True:
        try:
            new_block = que.get(timeout=1)
            new_block.create_time = int(time.time())
            if P.F_NOW_BOOTING:
                logging.debug("Mined but now booting..")
                continue
            elif new_block.height != builder.best_block.height + 1:
                logging.debug("Mined but its old block...")
                continue
            elif new_insert_block(new_block, time_check=True):
                logging.info("Mined new block {}".format(new_block.getinfo()))
            else:
                update_mining_staking_all_info()
                continue
            proof = new_block.txs[0]
            others = [tx.hash for tx in new_block.txs]
            data = {
                'cmd': BroadcastCmd.NEW_BLOCK,
                'data': {
                    'block': new_block.b,
                    'txs': others,
                    'proof': proof.b,
                    'block_flag': new_block.flag,
                    'sign': proof.signature}
            }
            try:
                pc.send_command(cmd=ClientCmd.BROADCAST, data=data)
                logging.info("Success broadcast new block {}".format(new_block))
                update_mining_staking_all_info()
            except TimeoutError:
                logging.warning("Failed broadcast new block, other nodes don\'t accept {}"
                                .format(new_block.getinfo()))
                # logging.warning("47 Set booting mode.")
                # P.F_NOW_BOOTING = True
        except queue.Empty:
            if pc.f_stop:
                logging.debug("Mined new block closed.")
                break
        except BlockChainError as e:
            logging.error('Failed mined new block "{}"'.format(e))
        except Exception as e:
            logging.error("mined_newblock()", exc_info=True)


def send_newtx(new_tx, outer_cur=None, exc_info=True):
    assert V.PC_OBJ, "PeerClient is None."
    try:
        check_tx_time(new_tx)
        check_tx(new_tx, include_block=None)
        data = {
            'cmd': BroadcastCmd.NEW_TX,
            'data': {
                'tx': new_tx.b,
                'sign': new_tx.signature}}
        V.PC_OBJ.send_command(cmd=ClientCmd.BROADCAST, data=data)
        if new_tx.type in (C.TX_VALIDATOR_EDIT, C.TX_CONCLUDE_CONTRACT)and new_tx.hash in tx_builder.unconfirmed:
            # marge contract signature
            original_tx = tx_builder.unconfirmed[new_tx.hash]
            new_signature = list(set(new_tx.signature) | set(original_tx.signature))
            original_tx.signature = new_signature
            logging.info("Marge contract tx {}".format(new_tx))
        else:
            # normal tx
            tx_builder.put_unconfirmed(new_tx, outer_cur)
            logging.info("Success broadcast new tx {}".format(new_tx))
        return True
    except Exception as e:
        logging.warning("Failed broadcast new tx, other nodes don\'t accept {}"
                        .format(new_tx.getinfo()))
        logging.warning("Reason is \"{}\"".format(e))
        logging.debug("traceback,", exc_info=exc_info)
        return False


__all__ = [
    "mined_newblock",
    "send_newtx",
]
