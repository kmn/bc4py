from bc4py.contract.emulator.virtualmachine import *
from bc4py.database.builder import tx_builder
from bc4py.database.contract import *
from bc4py.user import Accounting
from bc4py.user.network.sendnew import *
from bc4py.user.txcreation.contract import create_conclude_tx, create_signed_tx_as_validator
import logging
from io import StringIO
import bjson


def execute(c_address, genesis_block, start_tx, c_method, redeem_address, c_args, gas_limit, f_show_log=False):
    """ execute contract emulator """
    file = StringIO()
    is_success, result, emulate_gas, work_line = emulate(
        genesis_block=genesis_block, start_tx=start_tx, c_address=c_address,
        c_method=c_method, redeem_address=redeem_address, c_args=c_args, gas_limit=gas_limit, file=file)
    if is_success:
        logging.info('Success gas={} line={} result={}'.format(emulate_gas, work_line, result))
        if f_show_log:
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
    elif send_newtx(new_tx=conclude_tx, exc_info=False):
        logging.info("Broadcast success {}".format(conclude_tx))
    else:
        logging.error("Failed broadcast, send_pairs={} c_storage={} tx={}"
                      .format(send_pairs, c_storage, conclude_tx.getinfo()))
        # Check already confirmed another conclude tx
        a_conclude = calc_tx_movement(
            tx=conclude_tx, c_address=c_address, redeem_address=redeem_address, emulate_gas=emulate_gas)
        a_conclude.cleanup()
        count = 0
        for another_conclude_hash in get_conclude_by_start_iter(
                c_address=c_address, start_hash=start_tx.hash, stop_txhash=conclude_tx.hash):
            another_tx = tx_builder.get_tx(txhash=another_conclude_hash)
            logging.debug("Try to check {} is same TX.".format(another_tx))
            if another_tx is None:
                logging.warning("Another problem occur on broadcast.")
            elif another_tx.height is not None:
                logging.info("Already complete contract by {}".format(another_tx))
            else:
                # check same action ConcludeTX and broadcast
                count += 1
                a_another = calc_tx_movement(tx=another_tx, c_address=c_address,
                                             redeem_address=redeem_address, emulate_gas=emulate_gas)
                a_another.cleanup()
                if another_tx.message == conclude_tx.message and a_another == a_conclude:
                    logging.info("{}: anotherTX is same with my ConcludeTX, {}".format(count, another_tx))
                    new_tx = create_signed_tx_as_validator(tx=another_tx)
                    assert another_tx is not new_tx, 'tx={}, new_tx={}'.format(id(another_tx), id(new_tx))
                    if send_newtx(new_tx=new_tx, exc_info=False):
                        logging.info("{}: Broadcast success {}".format(count, new_tx))
                        return
                # Failed check AnotherTX
                _c_address, _start_hash, another_storage = bjson.loads(another_tx.message)
                logging.info("{}: Failed confirm same ConcludeTX, please check params\n"
                             "   AnoAccount=>{}\n   MyAccount =>{}\n"
                             "   AnoStorage=>{}\n   MyStorage =>{}\n"
                             "   AnoTX=>{}\n   MyTX =>{}\n"
                             .format(count, a_another, a_conclude, another_storage, c_storage, another_tx, conclude_tx))
        # Failed confirm AnotherTXs
        logging.error("Unstable contract result? ignore request, {}".format(conclude_tx.getinfo()))


def calc_tx_movement(tx, c_address, redeem_address, emulate_gas):
    """ Calc tx inner movement """
    account = Accounting()
    for txhash, txindex in tx.inputs:
        input_tx = tx_builder.get_tx(txhash=txhash)
        address, coin_id, amount = input_tx.outputs[txindex]
        account[address][coin_id] -= amount
    account[redeem_address][0] += (tx.gas_amount+emulate_gas) * tx.gas_price
    account[c_address][0] -= emulate_gas * tx.gas_price
    for address, coin_id, amount in tx.outputs:
        account[address][coin_id] += amount
    return account


__all__ = [
    "execute",
    "broadcast",
]