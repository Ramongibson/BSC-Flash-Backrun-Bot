import sys
from sqlalchemy import false
from web3 import Web3, WebsocketProvider
from web3.middleware import geth_poa_middleware
import traceback
import json
import time
import threading
from eth_account import Account
from scripts.contract_fetcher import ContractFetcher
from decimal import Decimal
import os
from loguru import logger as log
import asyncio
from hexbytes import HexBytes
from copy import deepcopy
import math


global_gas_price = None
gas_price_lock = threading.Lock()
fetcher = None
uni_router = None
dexs = []
base_tokens = []
tokens = {}
biswap = None
arbitrage_address = None
arbitrage_abi = None
private_key = None
flashloan_address = None
account = None
gas_limit = None
max_gas_price = None
aggregator = None


def connect_to_network(network_ws):
    w3 = Web3(WebsocketProvider(network_ws))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)  # Inject PoA middleware
    return w3


def load_file(filename):
    with open(filename, "r") as json_file:
        file = json.load(json_file)
    return file


class Router:
    def __init__(self, address, abi):
        self.address = address
        self.abi = abi


class Token:
    def __init__(self, symbol, token_info, vault=None, profit=None, loan_amount=None):
        self.symbol = symbol
        self.address = Web3.to_checksum_address(token_info["address"])
        self.decimals = token_info["decimals"]
        self.profit = profit
        self.vault = vault
        self.max_loan_amount = None
        self.loan_amount = None
        self.abi = None


class Decoded_Token:
    def __init__(self, address):
        self.address = Web3.to_checksum_address(address)
        self.abi = None


class Dex:
    def __init__(self, name, dex_info):
        self.name = name
        self.factory = Web3.to_checksum_address(dex_info[Type.FACTORY])
        self.router = Web3.to_checksum_address(dex_info[Type.ROUTER])
        self.quoter = dex_info.get(Type.QUOTER, None)
        self.enabled = dex_info["enabled"]
        self.factory_abi = None
        self.router_abi = None
        self.quoter_abi = None
        self.pair_contract = None
        self.pair_abi = None
        self.src_token = None
        self.dest_token = None
        self.loan_token = None
        self.src_token_position = None
        self.dest_token_position = None
        self.src_token_reserves = None
        self.dest_token_reserves = None
        self.swap_quote = None
        self.gas_price = None
        self.calldata = None
        self.calldata2 = None


class Decoded_Transaction:
    def __init__(
        self,
        block_hash,
        block_number,
        transaction_hash,
        gas_price,
    ):
        self.block_hash = block_hash
        self.block_number = block_number
        self.transaction_hash = transaction_hash
        self.gas_price = gas_price
        self.function = None
        self.amount_out = None
        self.amount_in = None
        self.src_token_address = None
        self.dest_token_address = None


def get_token_list(token_filename):
    if os.path.exists(token_filename):
        tokens = load_file(token_filename)
        return tokens


async def get_gas_price():
    try:
        gas_price = w3.eth.gas_price
        log.info(f"Current gas price: {gas_price}")
        return int(gas_price)
    except Exception as e:
        traceback.print_exc()
        return None


async def add_percentage(wad, percentage):
    result = wad + (percentage / 100) * wad
    return int(result)


async def subtract_percentage(wad, percentage):
    result = wad - (percentage / 100) * wad
    return int(result)


async def decode_input_v2(decoded_transaction, transaction_details, dex):
    try:
        contract = w3.eth.contract(address=dex.router, abi=dex.router_abi)
        input = contract.decode_function_input(transaction_details["input"])
        if dex.quoter is not None:
            byte_array = input[1]["inputs"][0]
            call_decoded = contract.decode_function_input(byte_array)
            print(call_decoded)
        else:

            function = input[0]
            arguments = input[1]
            amount_in = None
            log.debug(dex.name)

            if "amountIn" in arguments:
                # return None
                amount_in = arguments["amountIn"]
                if amount_in == 0 or amount_in is None:
                    return None

            if "amountOutMin" not in arguments:
                log.debug("Amount out not found")
                return None

            if arguments["amountOutMin"] == 0 and (amount_in is None or amount_in == 0):
                log.debug("Amounts not found")
                return None

            if len(arguments["path"]) > 2:
                log.debug("The path is too large")
                return None

            dex.src_token = next(
                (
                    base_token
                    for base_token in base_tokens
                    if base_token.address.lower() == arguments["path"][0].lower()
                ),
                None,
            )
            if dex.src_token is None:
                log.debug("src token not found")
                return None
            log.warning(f"Decoded Input: {input}")
            dex.dest_token = Decoded_Token(arguments["path"][1])
            log.debug(f"src_token: {dex.src_token.address}")
            log.debug(f"dest_token: {dex.dest_token.address}")
            amount_out = arguments["amountOutMin"]
            decoded_transaction.function = function
            decoded_transaction.src_token_address = dex.src_token.address
            decoded_transaction.dest_token_address = dex.dest_token.address
            decoded_transaction.amount_in = amount_in
            decoded_transaction.amount_out = amount_out
            return True
    except Exception as e:
        log.error("Error decoding tx: {}".format(e))
        traceback.print_exc()


async def initial_checks(transaction):
    try:
        if transaction is not None:
            transaction_hash = transaction.hex()
            transaction_details = w3.eth.get_transaction(transaction_hash)
            if transaction_details["to"] is None:
                return False, None, None
            dex = next(
                (
                    dex
                    for dex in dexs
                    if dex.router.lower() == transaction_details["to"].lower()
                ),
                None,
            )
            if not dex:
                return False, None, None
            # log.info(transaction_details)
            if transaction_details["gasPrice"] > max_gas_price:
                log.warning(
                    f"Gas price for transcation is too high - {transaction_details['gasPrice']}"
                )
                return False, None, None
            decoded_transaction = Decoded_Transaction(
                transaction_details["blockHash"],
                transaction_details["blockNumber"],
                transaction_details["hash"],
                transaction_details["gasPrice"],
            )
            inputDecoded = await decode_input_v2(
                decoded_transaction, transaction_details, dex
            )
            if inputDecoded:
                return True, decoded_transaction, dex
            else:
                return False, None, None

    except Exception as e:
        # log.warning(f"Error in handle_transaction: {e}")
        return False, None, None


async def execute_transaction(dex, transaction, swap_type):
    arb_contract = w3.eth.contract(
        address=w3.to_checksum_address(arbitrage_address), abi=arbitrage_abi
    )
    gas_price = None
    if transaction.gas_price > dex.gas_price:
        gas_price = transaction.gas_price - 100000
    else:
        gas_price = transaction.gas_price

    tx_params = {
        "from": account.address,
        "gas": gas_limit,
        "gasPrice": dex.gas_price,
        "nonce": w3.eth.get_transaction_count(account.address),
    }

    calldata = HexBytes(dex.calldata)
    calldata2 = HexBytes(dex.calldata2)
    transaction = arb_contract.functions.executeFlashArbitrage(
        flashloan_address,
        dex.loan_token.loan_amount,
        dex.dest_token.address,
        dex.loan_token.address,
        calldata,
        calldata2,
    ).build_transaction(tx_params)

    estimated_gas = w3.eth.estimate_gas(tx_params, block_identifier=None)
    log.info(f"Estimated gas for transaction: {estimated_gas}")

    # Sign transaction
    signed_transaction = w3.eth.account.sign_transaction(transaction, private_key)

    # Send transaction
    tx_hash = w3.eth.send_raw_transaction(signed_transaction.rawTransaction)
    log.info(f"Arbitrage transaction sent: {tx_hash.hex()}")

    # Wait for the transaction receipt
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    log.info(f"Arbitrage transaction mined in block: {receipt['blockNumber']}")
    sys.exit(1)


async def build_v2_swap(dex, transaction):
    if transaction.amount_in is None:
        await fetcher.get_pair_contract_and_abi_async(
            dex,
            dex.src_token,
            dex.dest_token,
        )
        await fetcher.get_token_order(dex.dest_token, dex)
        await fetcher.get_reserves(dex)
        log.info(f"before src reserves: {dex.src_token_reserves}")
        log.info(f"before dest reserves: {dex.dest_token_reserves}")
        log.info(f"Amount out {transaction.amount_out}")
    if transaction.amount_out < dex.dest_token_reserves:
        amount_in = await fetcher.get_amount_in(
            dex,
            transaction.amount_out,
            dex.src_token_reserves,
            dex.dest_token_reserves,
        )
        dex.loan_token.loan_amount = min(amount_in, dex.loan_token.max_loan_amount)
        desired_amount = dex.loan_token.loan_amount + dex.loan_token.profit
        log.info(f"Amount in: {amount_in}")
        log.warning(f"Desired amount: {desired_amount}")
        log.warning(
            f"Loan amount {dex.loan_token.symbol}: {dex.loan_token.loan_amount}"
        )
        swap_data = await fetcher.get_swap_route_paraswap(
            dex.loan_token, dex.dest_token, dex.loan_token.loan_amount
        )
        swap2_data = await fetcher.get_swap_route_paraswap(
            dex.dest_token, dex.loan_token, swap_data["destAmount"]
        )
        if swap_data is not None and swap2_data is not None:
            swap_amount_out = int(swap_data["destAmount"])
            log.warning(f"Swap amount out: {swap_amount_out}")
            log.warning(f"Swap2 amount out: {swap2_data['destAmount']}")
            if int(swap2_data["destAmount"]) > desired_amount:
                # dex.calldata = swap_data["data"]
                dex.calldata = await fetcher.build_paraswap_transaction(
                    dex.loan_token,
                    dex.dest_token,
                    swap_data["srcAmount"],
                    swap_data,
                    arbitrage_address,
                    dex.loan_token.vault,
                )
                dex.calldata2 = await fetcher.build_paraswap_transaction(
                    dex.dest_token,
                    dex.loan_token,
                    swap2_data["srcAmount"],
                    swap2_data,
                    arbitrage_address,
                    dex.loan_token.vault,
                )
                log.success("Arbitrage found")
                dex.gas_price = await get_gas_price()
                await execute_transaction(dex, transaction, 1)
    else:
        dex.loan_token.loan_amount = min(
            transaction.amount_in, dex.loan_token.max_loan_amount
        )
        # dex.loan_token.loan_amount = dex.loan_token.max_loan_amount
        desired_amount = dex.loan_token.loan_amount + dex.loan_token.profit
        log.warning(
            f"loan amount {dex.loan_token.symbol}: {dex.loan_token.loan_amount}"
        )
        log.warning(f"Desired amount: {desired_amount}")
        swap_data = await fetcher.get_swap_route_paraswap(
            dex.loan_token, dex.dest_token, dex.loan_token.loan_amount
        )
        swap2_data = await fetcher.get_swap_route_paraswap(
            dex.dest_token, dex.loan_token, swap_data["destAmount"]
        )
        if swap_data is not None and swap2_data is not None:
            swap_amount_out = int(swap_data["destAmount"])
            log.warning(f"Swap amount out: {swap_amount_out}")
            log.warning(f"Swap2 amount out: {swap2_data['destAmount']}")
            if int(swap2_data["destAmount"]) > desired_amount:
                # dex.calldata = swap_data["data"]
                dex.calldata = await fetcher.build_paraswap_transaction(
                    dex.loan_token,
                    dex.dest_token,
                    swap_data["srcAmount"],
                    swap_data,
                    arbitrage_address,
                    dex.loan_token.vault,
                )
                dex.calldata2 = await fetcher.build_paraswap_transaction(
                    dex.dest_token,
                    dex.loan_token,
                    swap2_data["srcAmount"],
                    swap2_data,
                    arbitrage_address,
                    dex.loan_token.vault,
                )
                log.success("Arbitrage found")
                dex.gas_price = await get_gas_price()
                await execute_transaction(dex, transaction, 1)


def set_sell_dex_token_order(sell_dex, buy_dex):
    if sell_dex.src_token.symbol == buy_dex.loan_token.symbol:
        src_token = sell_dex.dest_token
        dest_token = sell_dex.src_token
        src_position = sell_dex.dest_token_position
        dest_position = sell_dex.src_token_position
        sell_dex.src_token = src_token
        sell_dex.dest_token = dest_token
        sell_dex.src_token_position = src_position
        sell_dex.dest_token_position = dest_position


async def processTransaction(transaction):
    checks_passed, decoded_transaction, dex = await initial_checks(transaction)
    if checks_passed:
        dest_token = next(
            (
                token
                for token in base_tokens
                if token.address.lower() == dex.dest_token.address.lower()
            ),
            None,
        )
        if dest_token is not None:
            dex.dest_token = dest_token
            dex.loan_token = dest_token
            if dex.quoter is not None:
                pass
            else:
                pass
        else:
            if dex.quoter is not None:
                pass
            else:
                dex.loan_token = next(
                    (
                        token
                        for token in base_tokens
                        if token.address == dex.src_token.address
                    ),
                    None,
                )
                await build_v2_swap(dex, decoded_transaction)


async def handle_transaction(transaction):
    # Handle the received transaction data here
    log.debug(f"Received transaction: {transaction}")
    await processTransaction(transaction)


async def log_loop(event_filter, poll_interval):
    while True:
        for transaction in event_filter.get_new_entries():
            await handle_transaction(transaction)
        await asyncio.sleep(poll_interval)


async def listen_to_transactions():
    transaction_filter = w3.eth.filter("pending")

    log.info("Listening for new transactions...")

    while True:
        try:
            await asyncio.gather(
                log_loop(transaction_filter, 0)
            )  # Run log_loop asynchronously
        except Exception as e:
            log.error("Error in listen_to_transactions: {}".format(e))
            traceback.print_exc()


class Type:
    FACTORY = "factory"
    ABI = "abi"
    CONTRACT = "contract"
    POOL = "pool"
    ROUTER = "router"
    QUOTER = "quoter"


class Networks:
    BSC = 56


def main():
    global uni_router, dexs, routers, w3, fetcher, base_tokens, tokens, dex_config, biswap, arbitrage_address, arbitrage_abi, private_key, flashloan_address, account, gas_limit, max_gas_price, aggregator
    config_filename = "config/bot_config.json"
    dex_config_filename = "config/dex_config.json"
    config = load_file(config_filename)
    dex_config = load_file(dex_config_filename)
    log.remove()
    log.add(sys.stdout, level=config["log_level"])
    log.opt(colors=True)
    mode = config["mode"]
    gas_limit = config["gas_limit"]
    max_gas_price = config["max_gas_price"]
    slippage = config["slippage"]
    arbitrage_address = config["arbitrage_address"]
    arbitrage_abi = load_file(config["arbitrage_abi_filename"])
    network_ws = config["testnet_ws"] if mode == "test" else config["mainnet_ws"]
    w3 = connect_to_network(network_ws)
    flashloan_address = w3.to_checksum_address(config["flashloan_address"])
    flashloan_abi = load_file(config["flashloan_abi_filename"])
    aggregator = w3.to_checksum_address(config["aggregator"])
    private_key = (
        config["test_private_key"]
        if mode == "test"
        else config["production_private_key"]
    )
    account = Account.from_key(private_key)

    fetcher = ContractFetcher(config, log, w3)
    tokens = get_token_list(config["token_filename"])
    loan_tokens = get_token_list(config["loan_token_filename"])

    flashloan_contract = w3.eth.contract(address=flashloan_address, abi=flashloan_abi)

    base_token_list = loan_tokens.keys()
    for token_name in base_token_list:
        token_info = loan_tokens.get(token_name)
        token = Token(
            token_name,
            token_info,
            token_info["vault"],
            int(token_info["profit"] * (10**18)),
        )
        fetcher.get_token_abi(token)
        token.max_loan_amount = int(
            flashloan_contract.functions.maxFlashLoan(token.address).call()
        )
        base_tokens.append(token)

    dex_list = dex_config.keys()
    for dex_name in dex_list:
        dex = Dex(dex_name, dex_config.get(dex_name))
        if dex.enabled:
            fetcher.get_abi(dex)
            fetcher.get_router_abi(dex)
            # fetcher.get_pair_contract_and_abi(dex, base_tokens[0], base_tokens[1])
            # fetcher.get_initial_token_order(base_tokens[1], dex)
            if dex.quoter is not None:
                fetcher.get_abi(dex, Type.QUOTER)
            if dex.name == "BiSwapV2":
                biswap = dex
            dexs.append(dex)

    asyncio.run(listen_to_transactions())


if __name__ == "__main__":
    main()
