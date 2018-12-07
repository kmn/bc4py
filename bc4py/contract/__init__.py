from bc4py.config import P, NewInfo
from bc4py.contract.watch import *
from bc4py.contract.em import *
from bc4py.database.builder import tx_builder
from bc4py.database.contract import *
from bc4py.user import Accounting
from bc4py.user.network.sendnew import *
from bc4py.user.txcreation.contract import create_conclude_tx
from threading import Thread, Lock
import logging
from io import StringIO
from time import sleep

emulators = list()
f_running = False
lock = Lock()


class Emulate:
    def __init__(self, c_address, f_claim_gas=True):
        self.c_address = c_address
        self.f_claim_gas = f_claim_gas
        for e in emulators:
            if c_address == e.c_address:
                raise Exception('Already registered c_address {}'.format(c_address))
        with lock:
            emulators.append(self)

    def __repr__(self):
        return "<Emulator {}>".format(self.c_address)

    def close(self):
        with lock:
            emulators.remove(self)

    def debug(self, genesis_block, start_tx, c_method, redeem_address, c_args, gas_limit=None):
        f_debug = True
        result, emulate_gas = execute(
            c_address=self.c_address, genesis_block=genesis_block, start_tx=start_tx,
            c_method=c_method, redeem_address=redeem_address, c_args=c_args, gas_limit=gas_limit, f_debug=f_debug)
        broadcast(c_address=self.c_address, start_tx=start_tx, redeem_address=redeem_address,
                  emulate_gas=emulate_gas, result=result, f_debug=f_debug)


def execute(c_address, genesis_block, start_tx, c_method, redeem_address, c_args, gas_limit, f_debug=False):
    """ execute contract emulator """
    file = StringIO()
    is_success, result, emulate_gas, work_line = emulate(
        genesis_block=genesis_block, start_tx=start_tx, c_address=c_address,
        c_method=c_method, redeem_address=redeem_address, c_args=c_args, gas_limit=gas_limit, file=file)
    if is_success:
        logging.info('Success gas={} line={} result={}'.format(emulate_gas, work_line, result))
        if f_debug:
            logging.debug("#### Start log ####")
            for data in file.getvalue().split("\n"):
                logging.debug(data)
            logging.debug("#### Finish log ####")
    else:
        logging.error('Failed gas={} line={} result=\n{}\nlog=\n{}'.format(
            emulate_gas, work_line, result, file.getvalue()))
    file.close()
    logging.debug("Close file obj {}.".format(id(file)))
    return result, emulate_gas


def broadcast(c_address, start_tx, redeem_address, emulate_gas, result, f_debug=False):
    """ broadcast conclude tx """
    if isinstance(result, tuple) and len(result) == 2:
        returns, c_storage = result
        assert returns is None or isinstance(returns, Accounting)
        assert c_storage is None or isinstance(c_storage, dict)
        # get
        if returns is None:
            send_pairs = None
        else:
            send_pairs = list()
            for address, coins in returns:
                for coin_id, amount in coins:
                    send_pairs.append((address, coin_id, amount))
    else:
        return
    # create conclude tx
    conclude_tx = create_conclude_tx(c_address=c_address, start_tx=start_tx, redeem_address=redeem_address,
                                     send_pairs=send_pairs, c_storage=c_storage, emulate_gas=emulate_gas)
    # send tx
    if f_debug:
        logging.debug("Not broadcast, send_pairs={} c_storage={} tx={}"
                      .format(send_pairs, c_storage, conclude_tx.getinfo()))
    elif send_newtx(new_tx=conclude_tx):
        logging.info("Broadcast success {}".format(conclude_tx))
    else:
        logging.error("Failed broadcast, send_pairs={} c_storage={} tx={}"
                      .format(send_pairs, c_storage, conclude_tx.getinfo()))
        # Check already confirmed another conclude tx
        another_conclude_hash = get_conclude_hash_by_start_hash(
            c_address=c_address, start_hash=start_tx.hash, stop_txhash=conclude_tx.hash)
        another_tx = tx_builder.get_tx(txhash=another_conclude_hash)
        if another_tx is None:
            logging.warning("Another problem occur on broadcast.")
        elif another_tx.height is not None:
            logging.info("Already complete contract by {}".format(another_tx))
        else:
            # TODO: Inputs以外は同じである事を確認
            logging.error("Unstable result?\nAnother=> {}\nMyResult=> {}"
                         .format(another_tx.getinfo(), conclude_tx.getinfo()))


def start_emulators(genesis_block, f_debug=False):
    def run():
        global f_running
        with lock:
            f_running = True
        while P.F_NOW_BOOTING:
            sleep(1)
        logging.info("Start emulators debug={}".format(f_debug))
        while f_running:
            try:
                data = NewInfo.get(channel='emulator', timeout=1)
                if not isinstance(data, tuple) or len(data) != 3:
                    continue
                cmd, is_public, data_list = data
                if cmd == C_RequestConclude:
                    # c_transfer tx is confirmed, create conclude tx
                    _time, start_tx, related_list, c_address, c_method, redeem_address, c_args = data_list
                    for e in emulators:
                        if e.c_address != c_address:
                            continue
                        elif c_method == M_INIT:
                            logging.warning("No work on init.")
                        # elif c_method == M_UPDATE:
                        #    pass
                        else:
                            if e.f_claim_gas:
                                gas_limit = 0
                                for address, coin_id, amount in start_tx.outputs:
                                    if address == c_address and coin_id == 0:
                                        gas_limit += amount
                            else:
                                gas_limit = None  # No limit on gas consumption, turing-complete
                            result, emulate_gas = execute(
                                c_address=c_address, genesis_block=genesis_block, start_tx=start_tx, c_method=c_method,
                                redeem_address=redeem_address, c_args=c_args, gas_limit=gas_limit, f_debug=f_debug)
                            claim_emulate_gas = emulate_gas if e.f_claim_gas else None
                            broadcast(c_address=c_address, start_tx=start_tx, redeem_address=redeem_address,
                                      emulate_gas=claim_emulate_gas, result=result, f_debug=f_debug)

                # elif cmd == C_Conclude:
                #    # sign already created conclude tx
                #    _time, tx, related_list, c_address, start_hash, c_storage = data_list
                else:
                    pass
            except NewInfo.empty:
                pass
            except BlockChainError:
                logging.warning("Emulator", exc_info=True)
            except Exception:
                logging.error("Emulator", exc_info=True)
    global f_running
    Thread(target=run, name='Emulator', daemon=True).start()


def close_emulators():
    global f_running
    assert f_running is True
    with lock:
        f_running = False
        emulators.clear()
    logging.info("Close emulators.")


__all__ = [
    "Emulate",
    "start_emulators",
    "close_emulators",
]
