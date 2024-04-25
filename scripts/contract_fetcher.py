from curses import flash
import os
import requests
import json
from web3 import Web3
from web3.middleware import geth_poa_middleware
from decimal import Decimal, getcontext
from fractions import Fraction
from web3.exceptions import ValidationError
from hexbytes import HexBytes

KYBERSWAP_API_URL = "https://aggregator-api.kyberswap.com/bsc/api/v1"
PARASWAP_API_URL = "https://apiv5.paraswap.io"
OPEN_OCEAN_API_URL = "https://open-api.openocean.finance/v3/bsc/swap_quote"


class ContractFetcher:
    def __init__(self, config, log, w3):
        self.config = config
        self.log = log
        self.w3 = w3

    def get_abi(self, dex, type="factory"):
        filename = f"abi/{dex.name}_{type}_abi.json"
        if os.path.exists(filename):
            with open(filename, "r") as json_file:
                abi = json.load(json_file)
                if type == "factory":
                    dex.factory_abi = abi
                else:
                    dex.quoter_abi = abi
        else:
            if type == "factory":
                abi = self.fetch_contract_abi(dex.factory)
            else:
                abi = self.fetch_contract_abi(dex.quoter)
            if abi:
                self.save_content_to_json(filename, abi)
                if type == "factory":
                    dex.factory_abi = abi
                else:
                    dex.quoter_abi = abi
            else:
                self.log.debug(
                    f"Failed to fetch ABI for {dex.name}. Check if the contract source code is verified."
                )

    def get_token_abi(self, token):
        filename = f"abi/{token.address}_abi.json"
        if os.path.exists(filename):
            with open(filename, "r") as json_file:
                abi = json.load(json_file)
                token.abi = abi
        else:
            abi = self.fetch_contract_abi(token.address)
            if abi:
                self.save_content_to_json(filename, abi)
                token.abi = abi
            else:
                self.log.debug(
                    f"Failed to fetch ABI for {token.address}. Check if the contract source code is verified."
                )

    def get_router_abi(self, dex):
        filename = f"abi/{dex.name}_router_abi.json"
        if os.path.exists(filename):
            with open(filename, "r") as json_file:
                abi = json.load(json_file)
                dex.router_abi = abi
        else:
            abi = self.fetch_contract_abi(dex.router)
            if abi:
                self.save_content_to_json(filename, abi)
                dex.router_abi = abi
            else:
                self.log.debug(
                    f"Failed to fetch ABI for {dex.name}. Check if the contract source code is verified."
                )

    def fetch_contract_abi(self, contract_address):
        api_key = self.config["bsc_api_key"]
        api_base_url = self.config["bsc_mainnet_api_url"]
        api_url = f"{api_base_url}{contract_address}&apikey={api_key}"
        response = requests.get(api_url)
        # print(f"ABI API Response: {response.text}")
        if response.status_code == 200:
            abi_data = response.json()
            if abi_data["status"] == "1":
                return abi_data["result"]

        return None

    async def get_pair_contract_and_abi_async(self, dex, token1, token2):
        pair_contract_abi = None
        pair_contract_address = None
        pair_abi_filename = (
            f"abi/{dex.name}_{token1.address}-{token2.address}_abi.json"
        )
        pair_contract_filename = f"contract/{dex.name}_{token1.address}-{token2.address}_contract.json"
        if os.path.exists(pair_abi_filename) and os.path.exists(pair_contract_filename):
            # print(
            #     f"ABI file already exists for {pair_name} in {environment} environment. Skipping..."
            # )
            with open(pair_abi_filename, "r") as pair_abi_file:
                pair_contract_abi = json.load(pair_abi_file)
            with open(pair_contract_filename, "r") as pair_contract_file:
                pair_contract_address = json.load(pair_contract_file)
                dex.pair_contract = pair_contract_address
                dex.pair_abi = pair_contract_abi
        else:
            factory_contract = self.w3.eth.contract(
                address=dex.factory, abi=dex.factory_abi
            )
            if dex.quoter is not None:
                pair_contract_address = factory_contract.functions.getPool(
                    token1.address, token2.address, 500
                ).call()
            else:
                try:
                    pair_contract_address = factory_contract.functions.getPair(
                        token1.address, token2.address
                    ).call()
                except Exception as e:
                    self.log.warning(
                        f"Error feteching pair address {dex.name}-{token1.address}-{token2.address}"
                    )
                    return
            self.log.warning(pair_contract_address)
            # Fetch the ABI for the pair contract
            pair_contract_abi = self.fetch_contract_abi(pair_contract_address)

            # Save pair contract ABI to JSON file
            if pair_contract_abi and pair_contract_address:
                self.save_content_to_json(pair_abi_filename, pair_contract_abi)
                self.save_content_to_json(pair_contract_filename, pair_contract_address)
                dex.pair_contract = pair_contract_address
                dex.pair_abi = pair_contract_abi
            else:
                self.log.error(
                    f"Failed to fetch ABI for {token1.address}-{token2.address}. Check if the contract source code is verified."
                )

    def get_pair_contract_and_abi(self, dex, token1, token2):
        pair_contract_abi = None
        pair_contract_address = None
        dex.src_token = token1
        dex.dest_token = token2
        pair_abi_filename = (
            f"abi/{dex.name}_{token1.address}-{token2.address}_abi.json"
        )
        pair_contract_filename = f"contract/{dex.name}_{token1.address}-{token2.address}_contract.json"
        if os.path.exists(pair_abi_filename) and os.path.exists(pair_contract_filename):
            # print(
            #     f"ABI file already exists for {pair_name} in {environment} environment. Skipping..."
            # )
            with open(pair_abi_filename, "r") as pair_abi_file:
                pair_contract_abi = json.load(pair_abi_file)
            with open(pair_contract_filename, "r") as pair_contract_file:
                pair_contract_address = json.load(pair_contract_file)
                dex.pair_contract = pair_contract_address
                dex.pair_abi = pair_contract_abi
        else:
            factory_contract = self.w3.eth.contract(
                address=dex.factory, abi=dex.factory_abi
            )
            if dex.quoter is not None:
                pair_contract_address = factory_contract.functions.getPool(
                    token1.address, token2.address, 500
                ).call()
            else:
                try:
                    pair_contract_address = factory_contract.functions.getPair(
                        token1.address, token2.address
                    ).call()
                except Exception as e:
                    self.log.warning(
                        f"Error feteching pair address {dex.name}-{token1.address}-{token2.address}"
                    )
                    return
            # Fetch the ABI for the pair contract
            pair_contract_abi = self.fetch_contract_abi(pair_contract_address)

            # Save pair contract ABI to JSON file
            if pair_contract_abi and pair_contract_address:
                self.save_content_to_json(pair_abi_filename, pair_contract_abi)
                self.save_content_to_json(pair_contract_filename, pair_contract_address)
                dex.pair_contract = pair_contract_address
                dex.pair_abi = pair_contract_abi
            else:
                self.log.error(
                    f"Failed to fetch ABI for {token1.address}-{token2.address}. Check if the contract source code is verified."
                )

    def save_content_to_json(self, filename, content):
        with open(f"{filename}", "w") as json_file:
            json.dump(content, json_file)
        self.log.debug(f"File saved to {filename}")

    async def get_contract_address(self, dex_name, environment, type):
        try:
            if type == "token":
                return self.token_config["tokens"][environment]["WBNB/BUSD"]["WBNB"]
            elif type == "router":
                return self.dex_config["router_config"][dex_name][environment][
                    "contract_address"
                ]
            elif dex_name == list(self.dex_config["flash_load_config"].keys())[0]:
                return self.dex_config["flash_load_config"][dex_name][environment][
                    "contract_address"
                ]
            elif type == "pool":
                return self.global_config["global_config"][dex_name]
            return self.dex_config["dex_config"][dex_name][environment][
                "contract_address"
            ]
        except KeyError:
            # print(
            #     f"Factory address not found for {dex_name} in {environment} environment."
            # )
            return None

    def get_initial_token_order(self, token2, dex):
        pair_contract = self.w3.eth.contract(
            address=dex.pair_contract, abi=dex.pair_abi
        )
        token0 = pair_contract.functions.token0().call()
        if token0 == token2.address:
            dex.src_token_position = 1
            dex.dest_token_position = 0
        else:
            dex.src_token_position = 0
            dex.dest_token_position = 1

    async def get_token_order(self, token2, dex):
        pair_contract = self.w3.eth.contract(
            address=dex.pair_contract, abi=dex.pair_abi
        )
        token0 = pair_contract.functions.token0().call()
        if token0 == token2.address:
            dex.src_token_position = 1
            dex.dest_token_position = 0
        else:
            dex.src_token_position = 0
            dex.dest_token_position = 1

    async def get_reserves(self, dex):
        pair_contract = self.w3.eth.contract(
            address=dex.pair_contract, abi=dex.pair_abi
        )
        if dex.quoter is not None:
            src_token_contract = self.w3.eth.contract(
                address=dex.src_token.address, abi=dex.src_token.abi
            )
            dest_token_contract = self.w3.eth.contract(
                address=dex.dest_token.address, abi=dex.dest_token.abi
            )
            reserves = pair_contract.functions.slot0().call()
        else:
            reserves = pair_contract.functions.getReserves().call()
            dex.src_token_reserves = reserves[dex.src_token_position]
            dex.dest_token_reserves = reserves[dex.dest_token_position]

    async def get_reserves_v3(self, dex):
        pair_contract = self.w3.eth.contract(
            address=dex.pair_contract, abi=dex.pair_abi
        )
        reserves = pair_contract.functions.slot0().call()
        return reserves

    async def get_qoute(
        self,
        dex,
        amount,
        src_reserves,
        dest_reserves,
    ):
        try:
            router_contract = self.w3.eth.contract(
                address=dex.router, abi=dex.router_abi
            )
            return router_contract.functions.getAmountOut(
                amount, src_reserves, dest_reserves
            ).call()
        except ValidationError as e:
            return router_contract.functions.getAmountOut(
                amount, src_reserves, dest_reserves, 1
            ).call()

    async def get_amount_in(
        self,
        dex,
        amount,
        src_reserves,
        dest_reserves,
    ):
        try:
            router_contract = self.w3.eth.contract(
                address=dex.router, abi=dex.router_abi
            )
            return router_contract.functions.getAmountIn(
                amount, src_reserves, dest_reserves
            ).call()
        except ValidationError as e:
            return router_contract.functions.getAmountIn(
                amount, src_reserves, dest_reserves, 1
            ).call()

    async def get_qouteV3(
        self, dex, amount, src_token, dest_token, sqrt_price_limit_X96
    ):
        quoter_contract = self.w3.eth.contract(address=dex.quoter, abi=dex.quoter_abi)
        params = {
            "tokenIn": src_token,
            "tokenOut": dest_token,
            "amountIn": amount,
            "fee": 500,
            "sqrtPriceLimitX96": sqrt_price_limit_X96,
        }
        quote = quoter_contract.functions.quoteExactInputSingle(params).call()
        return quote[0], quote[1]

    async def get_swap_route_openocean(
        self, src_token, dest_token, src_amount, receiver, gas_price
    ):

        # Specify the call parameters (only the required params are specified here, see Docs for full list)
        target_path_config = {
            "params": {
                "chain": "bsc",
                "inTokenAddress": src_token.address,
                "outTokenAddress": dest_token.address,
                "amount": str(src_amount),
                "slippage": "3",
                "gasPrice": gas_price,
                "account": receiver,
                "disabledDexids": "PancakeV2",
            },
        }

        params = target_path_config.get("params")
        # Call the API with requests to handle async calls
        try:
            response = requests.get(OPEN_OCEAN_API_URL, params=params)
            response.raise_for_status()
            json_response = json.dumps(response.json(), indent=2)
            self.log.debug(json_response)
            price_route = response.json()
            return price_route["data"]
        except requests.exceptions.HTTPError as http_err:
            self.log.error(f"HTTP error occurred: {http_err}")
            self.log.error(response.content)
            return None
        except requests.exceptions.RequestException as req_err:
            self.log.error(f"Request error occurred: {req_err}")
            return None

    async def get_swap_route_paraswap(self, src_token, dest_token, src_amount):
        try:
            requestOptions = {
                "params": {
                    "srcToken": src_token.address,
                    "srcDecimals": "18",
                    "destToken": dest_token.address,
                    "destDecimals": "18",
                    "amount": str(src_amount),
                    "side": "SELL",
                    "network": 56,
                    "maxImpact": 100,
                    # "includeDEXS": paraswap_dexs,
                }
            }

            prices_url = f"{PARASWAP_API_URL}/prices"
            params = requestOptions.get("params", {})
            response = requests.get(prices_url, params=params)
            response.raise_for_status()

            # Convert the response to JSON format and print it
            json_response = json.dumps(response.json(), indent=2)
            self.log.debug(json_response)
        except requests.exceptions.HTTPError as http_err:
            self.log.error(f"HTTP error occurred: {http_err}")
            self.log.error(response.content)
            return None
        except requests.exceptions.RequestException as req_err:
            self.log.error(f"Request error occurred: {req_err}")
            return None

        # Ensure that the response contains the expected structure
        if "priceRoute" in response.json():
            price_route = response.json()["priceRoute"]
            return price_route
        else:
            self.log.error("Unexpected response format.")
            return None

    async def get_swap_route_kyberswap(self, src_token, dest_token, src_amount):
        route_path = f"{KYBERSWAP_API_URL}/routes"

        # Specify the call parameters (only the required params are specified here, see Docs for full list)
        target_path_config = {
            "params": {
                "tokenIn": src_token.address,
                "tokenOut": dest_token.address,
                "amountIn": str(src_amount),
                "source": "v1swapper",
            },
            "headers": {"x-client-id": "v1swapper"},
        }
        params = target_path_config.get("params")
        # Call the API with requests to handle async calls
        try:
            response = requests.get(route_path, params=params)
            response.raise_for_status()
            json_response = json.dumps(response.json(), indent=2)
            self.log.debug(json_response)
            price_route = response.json()
            return price_route["data"]
        except requests.exceptions.HTTPError as http_err:
            self.log.error(f"HTTP error occurred: {http_err}")
            self.log.error(response.content)
            return None
        except requests.exceptions.RequestException as req_err:
            self.log.error(f"Request error occurred: {req_err}")
            return None

    async def build_paraswap_transaction(
        self,
        src_token,
        dest_token,
        src_amount,
        price_route,
        receiver_address,
        vault_address,
    ):
        try:
            tx_url = f"{PARASWAP_API_URL}/transactions/56"

            tx_config = {
                "priceRoute": price_route,
                "userAddress": vault_address,
                "srcToken": src_token.address,
                "srcDecimals": "18",
                "destToken": dest_token.address,
                "destDecimals": "18",
                "srcAmount": str(src_amount),
                "slippage": 1000,
                "receiver": receiver_address,
            }

            query_params = {"ignoreChecks": "true"}

            response = requests.post(tx_url, params=query_params, json=tx_config)
            response.raise_for_status()

            # Assuming the response contains the necessary data for TransactionParams
            tx_params = response.json()
            if tx_params is not None:
                json_response = json.dumps(tx_params, indent=2)
                self.log.debug(json_response)
            return tx_params["data"]
        except requests.exceptions.HTTPError as http_err:
            self.log.error(f"HTTP error occurred: {http_err}")
            self.log.error(response.content)
            return None
        except requests.exceptions.RequestException as req_err:
            self.log.error(f"Request error occurred: {req_err}")
            return None

    async def build_kyberswap_transaction(
        self,
        data,
        contract_address: str,
    ):
        try:
            tx_url = f"{KYBERSWAP_API_URL}/route/build"

            tx_config = {
                "routeSummary": data["routeSummary"],
                "sender": contract_address,
                "recipient": contract_address,
                "slippageTolerance": 500,
            }
            headers = {"x-client-id": "v1swapper"}

            response = requests.post(tx_url, headers=headers, json=tx_config)
            response.raise_for_status()

            # Assuming the response contains the necessary data for TransactionParams
            tx_params = response.json()
            if tx_params is not None:
                json_response = json.dumps(tx_params, indent=2)
                self.log.debug(json_response)
            return tx_params["data"]["data"]
        except requests.exceptions.HTTPError as http_err:
            self.log.error(f"HTTP error occurred: {http_err}")
            self.log.error(response.content)
            return None
        except requests.exceptions.RequestException as req_err:
            self.log.error(f"Request error occurred: {req_err}")
            return None
