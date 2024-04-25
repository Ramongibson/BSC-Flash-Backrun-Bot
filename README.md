# BSC Backrun Bot

This is a MEV (Maximum Extractable Value) bot written in Python designed to backrun transactions on the Binance Smart Chain (BSC) using smart contracts and decentralized exchange (DEX) integrations. The bot listens to pending transactions and attempts to execute profitable transactions by leveraging flash loans and arbitrage opportunities.

## Prerequisites

Before setting up the bot, ensure you have the following:

- Python 3.8 or later
- `web3.py`
- An Ethereum wallet with BSC supported, and some BNB for gas fees

## Setup

1. **Clone the repository:**

2. **Install dependencies:**

    ```bash
    pip install web3 sqlalchemy asyncio loguru decimal hexbytes
    ```

3. **Configuration:**

    Create a `config` directory and inside, create `bot_config.json` and `dex_config.json` to store your configuration settings such as API keys, network settings, and smart contract addresses.

    Example `bot_config.json`:

    ```json
    {
        "log_level": "INFO",
        "gas_limit": 500000,
        "max_gas_price": 20000000000,
        "arbitrage_address": "<your_arbitrage_contract_address>",
        "arbitrage_abi_filename": "abi/arbitrage_abi.json",
        "mainnet_ws": "<mainnet_websocket_url>",
        "testnet_ws": "<testnet_websocket_url>",
        "flashloan_address": "<your_flashloan_contract_address>",
        "flashloan_abi_filename": "abi/flashloan_abi.json",
        "aggregator": "<price_aggregator_address>",
        "production_private_key": "<mainnet_private_key>",
        "test_private_key": "<testnet_private_key>",
        "token_filename": "config/tokens.json",
        "loan_token_filename": "config/loan_tokens.json",
        "mode": "test"  // or "production"
    }
    ```

4. **Smart Contract ABIs:**

    Place your smart contract ABIs in the `abi` directory and reference them in your configuration files.

## Running the Bot

1. **Start the Bot:**

    ```bash
    python back_runner.py
    ```

    This will initiate the bot, connect to the BSC network, and start listening for profitable opportunities.

2. **Monitoring:**

    The bot uses `loguru` for logging, and logs can be monitored directly on the console or piped to a log management system.

## Understanding the Bot

The bot consists of several key components:

- **Transaction Listening:** Monitors the BSC network for pending transactions.
- **Decoding and Execution:** Decodes transactions to find arbitrage opportunities and executes them using flash loans if profitable.
- **Gas Management:** Manages gas usage to ensure profitability, adjusting bids based on network conditions.

## Security Considerations

Ensure your private keys are stored securely and never hard-coded directly into your configuration files. Use environment variables or secure key management solutions.

## Disclaimer

This bot is for educational and development purposes only.


