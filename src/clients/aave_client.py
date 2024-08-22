import logging
from typing import Optional, Union, List, Dict, Any
from web3 import Web3
from web3._utils.encoding import HexBytes
from web3.gas_strategies.time_based import fast_gas_price_strategy, medium_gas_price_strategy, slow_gas_price_strategy, glacial_gas_price_strategy
from web3.middleware import geth_poa_middleware
from dataclasses import dataclass
from datetime import datetime
import requests
from concurrent.futures import ThreadPoolExecutor

from src.utils.web3_utils import convert_to_decimal_units, convert_from_decimal_units, get_abi
from src.utils.aave_utils import process_get_reserve_data_result, process_get_user_account_data_result
from src.utils.abi_references import ABIReference

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ReserveToken:
    """Dataclass for easily accessing Aave reserve token properties"""
    aTokenAddress: str
    aTokenSymbol: str
    stableDebtTokenAddress: str
    variableDebtTokenAddress: str
    symbol: str
    address: str
    decimals: int

@dataclass
class AaveTrade:
    """Dataclass for easily accessing transaction receipt properties"""
    hash: str
    timestamp: int
    datetime: str
    contract_address: str
    from_address: str
    to_address: str
    gas_price: float
    asset_symbol: str
    asset_address: str
    asset_amount: float
    asset_amount_decimal_units: int
    interest_rate_mode: Optional[str]
    operation: str

class BaseNetworkConfig:
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
        self.aave_tokens = []

    def fetch_aave_tokens(self, aave_client) -> List[ReserveToken]:
        raise NotImplementedError("This method should be implemented by subclasses")

class PolygonConfig(BaseNetworkConfig):
    def __init__(self, polygon_rpc_url: str):
        super().__init__(polygon_rpc_url)
        self.net_name = "Polygon"
        self.chain_id = 137
        self.pool_addresses_provider = '0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb'
        self.pool_data_provider = '0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654'
        self.wallet_balance_provider = ''
        self.liquidity_swap_adapter = ''
        self.collateral_repay_adapter = ''
        self.augustus_swapper = '0xDEF171Fe48CF0115B1d80b88dc8eAB59176FEe57'
        self.WMATIC = '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619'
        self.USDC = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
        self.USDT = '0xc2132D05D31c914a87C6611C10748AEb04B58e8F'
        self.DAI = '0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063'

    def fetch_aave_tokens(self, aave_client) -> List[ReserveToken]:
        try:
            tokens = []
            lending_pool = aave_client.get_lending_pool()
            token_symbols = {
                self.WMATIC: "WMATIC",
                self.USDC: "USDC",
                self.USDT: "USDT",
                self.DAI: "DAI"
            }

            for token_address in [self.WMATIC, self.USDC, self.USDT, self.DAI]:
                pool_data = aave_client.get_pool_data(lending_pool, "getReserveData", token_address)
                decimals = aave_client.get_protocol_data("getReserveConfigurationData", token_address)[0]
                
                token_data = {
                    "aTokenAddress": pool_data["aTokenAddress"],
                    "aTokenSymbol": None,  # This data might not be directly available
                    "stableDebtTokenAddress": pool_data["stableDebtTokenAddress"],
                    "variableDebtTokenAddress": pool_data["variableDebtTokenAddress"],
                    "symbol": token_symbols[token_address],
                    "address": token_address,
                    "decimals": decimals
                }
                
                tokens.append(ReserveToken(**token_data))
                
            return tokens
        
        except Exception as e:
            raise ConnectionError(f"Could not fetch Aave tokenlist for the Polygon network - Error: {e}")

class ArbitrumConfig(BaseNetworkConfig):
    def __init__(self, arbitrum_rpc_url: str):
        super().__init__(arbitrum_rpc_url)
        self.net_name = "Arbitrum"
        self.chain_id = 42161
        self.pool_addresses_provider = '0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb'
        self.pool_data_provider = '0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654'
        self.wallet_balance_provider = '0xBc790382B3686abffE4be14A030A96aC6154023a'
        self.liquidity_swap_adapter = '0xF3C3F14dd7BDb7E03e6EBc3bc5Ffc6D66De12251'
        self.collateral_repay_adapter = '0x28201C152DC5B69A86FA54FCfd21bcA4C0eff3BA'
        self.augustus_swapper = '0xDEF171Fe48CF0115B1d80b88dc8eAB59176FEe57'
        self.token_transfer_proxy = '0x216b4b4ba9f3e719726886d34a177484278bfcae'
        self.WETH = '0x82aF49447D8a07e3bd95BD0d56f35241523fBab1'
        self.USDC = '0xaf88d065e77c8cC2239327C5EDb3A432268e5831' 
        self.USDCE = '0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8' 
        self.USDT = '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9'
        self.DAI = '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1'

    def fetch_aave_tokens(self, aave_client) -> List[ReserveToken]:
        try:
            tokens = []
            lending_pool = aave_client.get_lending_pool()
            token_symbols = {
                self.WETH: "WETH",
                self.USDC: "USDC",
                self.USDCE: "USDCE",
                self.USDT: "USDT",
                self.DAI: "DAI"
            }

            for token_address in [self.WETH, self.USDC, self.USDCE, self.USDT, self.DAI]:
                pool_data = aave_client.get_pool_data(lending_pool, "getReserveData", token_address)
                decimals = aave_client.get_protocol_data("getReserveConfigurationData", token_address)[0]
                
                token_data = {
                    "aTokenAddress": pool_data["aTokenAddress"],
                    "aTokenSymbol": None,  # This data might not be directly available
                    "stableDebtTokenAddress": pool_data["stableDebtTokenAddress"],
                    "variableDebtTokenAddress": pool_data["variableDebtTokenAddress"],
                    "symbol": token_symbols[token_address],
                    "address": token_address,
                    "decimals": decimals
                }
                
                tokens.append(ReserveToken(**token_data))
                
            return tokens
        
        except Exception as e:
            raise ConnectionError(f"Could not fetch Aave tokenlist for the Arbitrum network - Error: {e}")

class AaveClient:
    """Fully plug-and-play AAVE client in Python3"""
    def __init__(self, wallet_address: str, private_key: str, network: str, rpc_url: str, gas_strategy: str = "fast"):
        self.wallet_address = Web3.to_checksum_address(wallet_address)
        self.private_key = private_key
        self.active_network = self._get_network_config(network, rpc_url)
        self.w3 = self._connect()
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        self._set_gas_strategy(gas_strategy)
        self.active_network.aave_tokens = self.active_network.fetch_aave_tokens(self)

    def _get_network_config(self, network: str, rpc_url: str) -> BaseNetworkConfig:
        if network.lower() == "polygon":
            return PolygonConfig(rpc_url)
        elif network.lower() == "arbitrum":
            return ArbitrumConfig(rpc_url)
        else:
            raise ValueError(f"Unsupported network: {network}")

    def _connect(self) -> Web3:
        try:
            return Web3(Web3.HTTPProvider(self.active_network.rpc_url))
        except Exception as e:
            logger.error(f"Could not connect to {self.active_network.net_name} network: {e}")
            raise ConnectionError(f"Could not connect to {self.active_network.net_name} network with RPC URL: "
                                  f"{self.active_network.rpc_url}")

    def _set_gas_strategy(self, strategy: str):
        strategy_map = {
            "fast": (fast_gas_price_strategy, 60),
            "medium": (medium_gas_price_strategy, 300),
            "slow": (slow_gas_price_strategy, 3600),
            "glacial": (glacial_gas_price_strategy, 86400)
        }
        if strategy.lower() not in strategy_map:
            raise ValueError(f"Invalid gas strategy. Available strategies are: {', '.join(strategy_map.keys())}")
        
        self.w3.eth.set_gas_price_strategy(strategy_map[strategy.lower()][0])
        self.timeout = strategy_map[strategy.lower()][1]

    def process_transaction_receipt(self, tx_hash: HexBytes, asset_amount: float,
                                    reserve_token: ReserveToken, operation: str, interest_rate_mode: Optional[str] = None,
                                    approval_gas_cost: float = 0) -> AaveTrade:
        logger.info(f"Awaiting transaction receipt for transaction hash: {tx_hash.hex()} (timeout = {self.timeout} seconds)")
        receipt = dict(self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=self.timeout))

        verification_timestamp = datetime.utcnow()
        gas_fee = self.w3.from_wei(int(receipt['effectiveGasPrice']) * int(receipt['gasUsed']), 'ether') + approval_gas_cost

        return AaveTrade(hash=tx_hash.hex(),
                         timestamp=int(datetime.timestamp(verification_timestamp)),
                         datetime=verification_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                         contract_address=receipt['contractAddress'],
                         from_address=receipt['from'],
                         to_address=receipt['to'],
                         gas_price=gas_fee,
                         asset_symbol=reserve_token.symbol,
                         asset_address=reserve_token.address,
                         asset_amount=asset_amount,
                         asset_amount_decimal_units=convert_to_decimal_units(reserve_token.decimals, asset_amount),
                         interest_rate_mode=interest_rate_mode,
                         operation=operation)

    def get_lending_pool(self):
        try:
            pool_addresses_provider_address = self.w3.to_checksum_address(
                self.active_network.pool_addresses_provider
            )
            pool_addresses_provider = self.w3.eth.contract(
                address=pool_addresses_provider_address,
                abi=ABIReference.pool_addresses_provider_abi,
            )
            lending_pool_address = (
                pool_addresses_provider.functions.getPool().call()
            )
            lending_pool = self.w3.eth.contract(
                address=lending_pool_address, abi=ABIReference.pool_abi)
            return lending_pool
        except Exception as exc:
            logger.error(f"Could not fetch the Aave lending pool smart contract: {exc}")
            raise Exception(f"Could not fetch the Aave lending pool smart contract - Error: {exc}")

    def approve_erc20(self, erc20_address: str, spender_address: str, amount_in_decimal_units: int, nonce: Optional[int] = None) -> tuple:
        """
        Approve the smart contract to take the tokens out of the wallet
        For lending pool transactions, the 'spender_address' is the lending pool contract's address.

        Returns a tuple of the following:
            (transaction hash string, approval gas cost)
        """
        nonce = nonce if nonce else self.w3.eth.get_transaction_count(self.wallet_address)

        spender_address = self.w3.to_checksum_address(spender_address)
        erc20_address = self.w3.to_checksum_address(erc20_address)
        erc20 = self.w3.eth.contract(address=erc20_address, abi=ABIReference.erc20_abi)
        function_call = erc20.functions.approve(spender_address, amount_in_decimal_units)
        transaction = function_call.build_transaction(
            {
                "chainId": self.active_network.chain_id,
                "from": self.wallet_address,
                "nonce": nonce,
            }
        )
        signed_txn = self.w3.eth.account.sign_transaction(
            transaction, private_key=self.private_key
        )
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        receipt = dict(self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=self.timeout))

        logger.info(f"Approved {amount_in_decimal_units} of {erc20_address} for contract {spender_address}")
        return tx_hash.hex(), self.w3.from_wei(int(receipt['effectiveGasPrice']) * int(receipt['gasUsed']), 'ether')

    def deposit(self, deposit_token: ReserveToken, deposit_amount: float, nonce: Optional[int] = None) -> AaveTrade:
        """
        Deposits the 'deposit_amount' of the 'deposit_token' to Aave collateral.

        Parameters:
            deposit_token: The ReserveToken object of the token to be deposited/collateralized on Aave
            deposit_amount: The amount of the 'deposit_token' to deposit on Aave (e.g. 0.001 WETH)
            nonce: Manually specify the transaction count/ID. Leave as None to get the current transaction count from
                   the user's wallet set at self.wallet_address.

        Returns:
            The AaveTrade object - See line 52 for datapoints reference

        Smart Contract Reference ((outdated)):
            https://docs.aave.com/developers/v/2.0/the-core-protocol/lendingpool#deposit
        """
        lending_pool_contract = self.get_lending_pool()
        
        nonce = nonce if nonce else self.w3.eth.get_transaction_count(self.wallet_address)

        amount_in_decimal_units = convert_to_decimal_units(deposit_token.decimals, deposit_amount)

        logger.info(f"Approving transaction to deposit {deposit_amount} of {deposit_token.symbol} to Aave...")
        try:
            approval_hash, approval_gas = self.approve_erc20(
                erc20_address=self.w3.to_checksum_address(deposit_token.address),
                spender_address=self.w3.to_checksum_address(lending_pool_contract.address),
                amount_in_decimal_units=amount_in_decimal_units,
                nonce=nonce
            )
            logger.info("Transaction approved!")
        except Exception as exc:
            logger.error(f"Could not approve deposit transaction - Error Code {exc}")
            raise UserWarning(f"Could not approve deposit transaction - Error Code {exc}")

        logger.info(f"Depositing {deposit_amount} of {deposit_token.symbol} to Aave...")
        function_call = lending_pool_contract.functions.supply(
            deposit_token.address,
            amount_in_decimal_units,
            self.wallet_address,
            0
        )
        transaction = function_call.build_transaction(
            {
                "chainId": self.active_network.chain_id,
                "from": self.wallet_address,
                "nonce": nonce + 1,
            }
        )
        signed_txn = self.w3.eth.account.sign_transaction(
            transaction, private_key=self.private_key
        )
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        receipt = self.process_transaction_receipt(tx_hash, deposit_amount, deposit_token,
                                                   operation="Deposit", approval_gas_cost=approval_gas)
        logger.info(f"Successfully deposited {deposit_amount} of {deposit_token.symbol}")
        return receipt

    def withdraw(self, withdraw_token: ReserveToken, withdraw_amount: float,
                 nonce: Optional[int] = None) -> AaveTrade:
        """
        Withdraws the amount of the withdraw_token from Aave, and burns the corresponding aToken.

        Parameters:
            withdraw_token: The ReserveToken object of the token to be withdrawn from Aave.
            withdraw_amount:  The amount of the 'withdraw_token' to withdraw from Aave (e.g. 0.001 WETH)
            nonce: Manually specify the transaction count/ID. Leave as None to get the current transaction count from
                   the user's wallet set at self.wallet_address.

        Returns:
            The AaveTrade object - See line 52 for datapoints reference

        Smart Contract Reference:
            https://docs.aave.com/developers/v/2.0/the-core-protocol/lendingpool#withdraw
        """
        nonce = nonce if nonce else self.w3.eth.get_transaction_count(self.wallet_address)
        amount_in_decimal_units = convert_to_decimal_units(withdraw_token.decimals, withdraw_amount)
        lending_pool_contract = self.get_lending_pool()

        logger.info(f"Withdrawing {withdraw_amount} of {withdraw_token.symbol} from Aave...")
        function_call = lending_pool_contract.functions.withdraw(
            withdraw_token.address,
            amount_in_decimal_units,
            self.wallet_address
        )
        transaction = function_call.build_transaction(
            {
                "chainId": self.active_network.chain_id,
                "from": self.wallet_address,
                "nonce": nonce,
            }
        )
        signed_txn = self.w3.eth.account.sign_transaction(
            transaction, private_key=self.private_key
        )
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        receipt = self.process_transaction_receipt(tx_hash, withdraw_amount, withdraw_token,
                                                   operation="Withdraw")
        logger.info(f"Successfully withdrew {withdraw_amount:.{withdraw_token.decimals}f} of {withdraw_token.symbol} from Aave")
        return receipt

    def withdraw_percentage(self, withdraw_token: ReserveToken, withdraw_percentage: float,
                            lending_pool_contract, nonce=None) -> AaveTrade:
        """Same parameters as the self.withdraw() function, except instead of 'withdraw_amount', you will pass the
        percentage of total available collateral on Aave that you would like to withdraw from in the 'withdraw_percentage'
        parameter in the following format: 0.0 (0% of borrowing power) to 1.0 (100% of borrowing power)"""

        if withdraw_percentage > 1.0:
            raise ValueError("Cannot withdraw more than 100% of available collateral of Aave. "
                             "Please pass a value between 0.0 and 1.0")

        total_collateral = self.get_user_data(lending_pool_contract)[2]
        weth_to_withdraw_asset = self.get_asset_price(base_address=self.get_reserve_token("WETH").address,
                                                      quote_address=withdraw_token.address)
        withdraw_amount = weth_to_withdraw_asset * (total_collateral * withdraw_percentage)

        return self.withdraw(withdraw_token, withdraw_amount, lending_pool_contract, nonce)

    def borrow(self, lending_pool_contract, borrow_amount: float, borrow_asset: ReserveToken,
               nonce: Optional[int] = None, interest_rate_mode: str = "variable") -> AaveTrade:
        """
        Borrows the underlying asset (erc20_address) as long as the amount is within the confines of
        the user's buying power.

        Parameters:
            lending_pool_contract: The web3.eth.Contract class object fetched from the self.get_lending_pool function.
            borrow_amount: Amount of the underlying asset to borrow. The amount should be measured in the asset's
                        currency (e.g. for ETH, borrow_amount=0.05, as in 0.05 ETH)
            borrow_asset: The ReserveToken which you want to borrow from Aave. To get the reserve token, you can use the
                        self.get_reserve_token(symbol: str) function.
            nonce: Manually specify the transaction count/ID. Leave as None to get the current transaction count from
                the user's wallet set at self.wallet_address.
            interest_rate_mode: The type of Aave interest rate mode for borrow debt, with the options being a 'stable'
                                or 'variable' interest rate.

        Returns:
            The AaveTrade object - See line 52 for datapoints reference

        Smart Contract Docs:
        https://docs.aave.com/developers/v/2.0/the-core-protocol/lendingpool#borrow
        """
        
        logger.info("Let's borrow...")

        rate_mode_str = interest_rate_mode
        if interest_rate_mode.lower() == "stable":
            interest_rate_mode = 1
        elif interest_rate_mode.lower() == "variable":
            interest_rate_mode = 2
        else:
            raise ValueError(f"Invalid interest rate mode passed to the borrow_erc20 function ({interest_rate_mode}) - "
                            f"Valid interest rate modes are 'stable' and 'variable'")

        # Calculate amount to borrow in decimal units:
        borrow_amount_in_decimal_units = convert_to_decimal_units(borrow_asset.decimals, borrow_amount)

        # Create and send transaction to borrow assets against collateral:
        logger.info(f"\nCreating transaction to borrow {borrow_amount:.{borrow_asset.decimals}f} {borrow_asset.symbol}...")
        function_call = lending_pool_contract.functions.borrow(
            self.w3.to_checksum_address(borrow_asset.address),
            borrow_amount_in_decimal_units,
            interest_rate_mode, 0,
            # 0 must not be changed, it is deprecated
            self.w3.to_checksum_address(self.wallet_address))
        
        transaction = function_call.build_transaction(
            {
                "chainId": self.active_network.chain_id,
                "from": self.wallet_address,
                "nonce": nonce if nonce else self.w3.eth.get_transaction_count(self.wallet_address),
            }
        )
        signed_txn = self.w3.eth.account.sign_transaction(
            transaction, private_key=self.private_key
        )
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        receipt = self.process_transaction_receipt(tx_hash, borrow_amount, borrow_asset, operation="Borrow",
                                                interest_rate_mode=rate_mode_str)

        logger.info(f"\nBorrowed {borrow_amount:.{borrow_asset.decimals}f} of {borrow_asset.symbol}")
        logger.info(f"Remaining Borrowing Power: {self.get_user_data(lending_pool_contract)[0]:.18f}")
        logger.info(f"Transaction Hash: {tx_hash.hex()}")
        return receipt

    def borrow_percentage(self, lending_pool_contract, borrow_percentage: float,
                        borrow_asset: ReserveToken, nonce=None, interest_rate_mode: str = "variable") -> AaveTrade:
        """Same parameters as the self.borrow() function, except instead of 'borrow_amount', you will pass the
        percentage of borrowing power that you would like to borrow from in the 'borrow_percentage' parameter in the
        following format: 0.0 (0% of borrowing power) to 1.0 (100% of borrowing power)"""

        if borrow_percentage > 1.0:
            raise ValueError("Cannot borrow more than 100% of borrowing power. Please pass a value between 0.0 and 1.0")

        # Calculate borrow amount from available borrow percentage:
        total_borrowable_in_eth = self.get_user_data(lending_pool_contract)[0]
        weth_to_borrow_asset = self.get_asset_price(base_address=self.get_reserve_token("WETH").address,
                                                    quote_address=borrow_asset.address)
        borrow_amount = weth_to_borrow_asset * (total_borrowable_in_eth * borrow_percentage)
        print(f"Borrowing {borrow_percentage * 100}% of total borrowing power: "
            f"{borrow_amount:.{borrow_asset.decimals}f} {borrow_asset.symbol}")

        return self.borrow(lending_pool_contract=lending_pool_contract, borrow_amount=borrow_amount,
                        borrow_asset=borrow_asset, nonce=nonce, interest_rate_mode=interest_rate_mode)

    def repay(self, lending_pool_contract, repay_amount: float, repay_asset: ReserveToken,
              nonce: Optional[int] = None, interest_rate_mode: str = "variable") -> AaveTrade:
        """
        Parameters:
            lending_pool_contract: The web3.eth.Contract object returned by the self.get_lending_pool() function.
            repay_amount: The amount of the target asset to repay. (e.g. 0.5 DAI)
            repay_asset: The ReserveToken object for the target asset to repay. Use self.get_reserve_token("SYMBOL") to
                        get the ReserveToken object.
            nonce: Manually specify the transaction count/ID. Leave as None to get the current transaction count from
                the user's wallet set at self.wallet_address.
            interest_rate_mode: the type of borrow debt,'stable' or 'variable'

        Returns:
            The AaveTrade object - See line 52 for datapoints reference

        https://docs.aave.com/developers/v/2.0/the-core-protocol/lendingpool#repay
        """
        logger.info("Time to repay...")

        rate_mode_str = interest_rate_mode
        if interest_rate_mode == "stable":
            interest_rate_mode = 1
        else:
            interest_rate_mode = 2

        amount_in_decimal_units = convert_to_decimal_units(repay_asset.decimals, repay_amount)

        # First, attempt to approve the transaction:
        logger.info(f"Approving transaction to repay {repay_amount} of {repay_asset.symbol} to Aave...")
        try:
            approval_hash, approval_gas = self.approve_erc20(
                erc20_address=self.w3.to_checksum_address(repay_asset.address),
                spender_address=self.w3.to_checksum_address(lending_pool_contract.address),
                amount_in_decimal_units=amount_in_decimal_units,
                nonce=nonce
            )
            logger.info("Transaction approved!")
        except Exception as exc:
            logger.error(f"Could not approve repay transaction - Error Code {exc}")
            raise UserWarning(f"Could not approve repay transaction - Error Code {exc}")

        logger.info(f"Repaying {repay_amount} of {repay_asset.symbol}...")
        function_call = lending_pool_contract.functions.repay(
            self.w3.to_checksum_address(repay_asset.address),
            amount_in_decimal_units,
            interest_rate_mode,  # the interest rate mode
            self.w3.to_checksum_address(self.wallet_address),
        )
        transaction = function_call.build_transaction(
            {
                "chainId": self.active_network.chain_id,
                "from": self.wallet_address,
                "nonce": nonce if nonce else self.w3.eth.get_transaction_count(self.wallet_address),
            }
        )
        signed_txn = self.w3.eth.account.sign_transaction(
            transaction, private_key=self.private_key
        )
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        receipt = self.process_transaction_receipt(tx_hash, repay_amount, repay_asset, "Repay",
                                                interest_rate_mode=rate_mode_str, approval_gas_cost=approval_gas)
        logger.info(f"Repaid {repay_amount} {repay_asset.symbol}  |  "
            f"{self.get_user_data(lending_pool_contract)[1]:.18f} ETH worth of debt remaining.")
        return receipt

    def repay_percentage(self, lending_pool_contract, repay_percentage: float,
                        repay_asset: ReserveToken, nonce=None) -> AaveTrade:
        """
        Same parameters as the self.repay() function, except instead of 'repay_amount', you will pass the
        percentage of outstanding debt that you would like to repay from in the 'repay_percentage' parameter using the
        following format:

        0.0 (0% of borrowing power) to 1.0 (100% of borrowing power)
        """

        if repay_percentage > 1.0:
            raise ValueError("Cannot repay more than 100% of debts. Please pass a value between 0.0 and 1.0")

        # Calculate debt amount from outstanding debt percentage:
        total_debt_in_eth = self.get_user_data(lending_pool_contract)[1]
        weth_to_repay_asset = self.get_asset_price(base_address=self.get_reserve_token("WETH").address,
                                                quote_address=repay_asset.address)
        repay_amount = weth_to_repay_asset * (total_debt_in_eth * repay_percentage)

        return self.repay(lending_pool_contract, repay_amount, repay_asset, nonce)

    def get_user_data(self, lending_pool_contract) -> tuple:
        """
        - Fetches user account data (shown below) across all reserves
        - Only returns the borrowing power (in ETH), and the total user debt (in ETH)

        Parameters:
            lending_pool_contract: The Web3.eth.Contract object fetched from self.get_lending_pool() to represent the
            Aave lending pool smart contract.

        https://docs.aave.com/developers/v/2.0/the-core-protocol/lendingpool#getuseraccountdata
        """
        user_data = lending_pool_contract.functions.getUserAccountData(self.wallet_address).call()
        try:
            processed_data = process_get_user_account_data_result(user_data)
            return processed_data['availableBorrowsBase'], processed_data['totalDebtBase'], processed_data['totalCollateralBase']
        except Exception as e:
            logger.error(f"Error processing user data: {e}")
            raise Exception(f"Could not process user data - Error: {e}")

    def get_protocol_data(self, function_name: str = "getAllReservesTokens", *args, **kwargs) -> tuple:
        """
        Peripheral contract to collect and pre-process information from the Pool.

        Parameters:
        - function_name: defines the function we want to call from the contract. Possible function
        names are:
            - getAllReservesTokens(): Returns list of the existing reserves in the pool.
            - getAllATokens(): Returns list of the existing ATokens in the pool.
            - getReserveConfigurationData(address asset): Returns the configuration data of the reserve as described below (see docs)
            - getReserveEModeCategory(address asset): Returns reserve's efficiency mode category.
            - getReserveCaps(address asset): Returns the caps parameters of the reserve
            - getPaused(address asset): Returns True if the pool is paused.
            - getSiloedBorrowing(address asset): Returns True if the asset is siloed for borrowing.
            - getLiquidationProtocolFee(address asset): Returns the protocol fee on the liquidation bonus.
            - getUnbackedMintCap(address asset): Returns the unbacked mint cap of the reserve
            - getDebtCeiling(): Returns the debt ceiling of the reserve
            - getDebtCeilingDecimals(address asset): Returns the debt ceiling decimals
            - getReserveData(address asset): Returns the following reserve data (see docs)
            - getATokenTotalSupply(address asset)
            - getTotalDebt(address asset)
            - getUserReserveData(address asset, address user): output is described below
            - getReserveTokensAddresses(address asset)
            - getInterestRateStrategyAddress(address asset)


            if function is getUserReserveData, output has 9 values:
                1) The current AToken balance of the user
                2) The current stable debt of the user
                3) The current variable debt of the user
                4) The principal stable debt of the user
                5) The scaled variable debt of the user
                6) The stable borrow rate of the user
                7) The liquidity rate of the reserve
                8) The timestamp of the last update of the user stable rate
                9) True if the user is using the asset as collateral, else false

        https://docs.aave.com/developers/core-contracts/aaveprotocoldataprovider
        """
        pool_data_address = self.w3.to_checksum_address(self.active_network.pool_data_provider)
        pool_data_contract = self.w3.eth.contract(address=pool_data_address, abi=ABIReference.pool_data_provider_abi)
        
        try:
            contract_function = getattr(pool_data_contract.functions, function_name)
            result = contract_function(*args, **kwargs).call()
            return result
        except AttributeError:
            logger.error(f"Function {function_name} does not exist in the contract.")
            raise ValueError(f"Function {function_name} does not exist in the contract.")
        except Exception as e:
            logger.error(f"An error occurred while calling the function {function_name}: {e}")
            raise Exception(f"An error occurred while calling the function {function_name}: {e}")

    def get_pool_data(self, pool_contract, function_name: str = "getReserveData", *args, **kwargs) -> Dict[str, Any]:
        """
        The pool.sol contract is the main user facing contract of the protocol. It exposes the 
        liquidity management methods that can be invoked using either Solidity or Web3 libraries.

        Parameters:
        - function_name: defines the function we want to call from the contract. Possible function
        names are:
            - getReserveData(address asset): Returns the state and configuration of the reserve.
            - getUserAccountData(address user): Returns the user account data across all the reserves
            - getConfiguration(address asset): Returns the configuration of the reserve
            - getUserConfiguration(address user): Returns the configuration of the user across all the reserves
            - getReserveNormalizedIncome(address asset): Returns the ongoing normalized income for the reserve.
            ...

        https://docs.aave.com/developers/core-contracts/aaveprotocoldataprovider
        """
        try:
            contract_function = getattr(pool_contract.functions, function_name)
            result = contract_function(*args, **kwargs).call()

            if function_name == "getReserveData":
                return process_get_reserve_data_result(result)
            elif function_name == "getUserAccountData":
                return process_get_user_account_data_result(result)
            else:
                return result

        except AttributeError:
            logger.error(f"Method {function_name} does not exist in the contract.")
            raise ValueError(f"Method {function_name} does not exist in the contract.")
        except Exception as e:
            logger.error(f"An error occurred while calling the method {function_name}: {e}")
            raise Exception(f"An error occurred while calling the method {function_name}: {e}")

    def get_wallet_balance_data(self, function_name="getReserveData", *args, **kwargs) -> dict:
        """
        Implements a logic of getting multiple tokens balance for one user address.

        Parameters:
        - function_name: defines the function we want to call from the contract. Possible function
        names are:
            - balanceOf(address user, address token): Returns the balance of the token for user (ETH included with 0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE).
            - batchBalanceOf(address[] calldata users, address[] calldata tokens): Returns balances for a list of users and tokens (ETH included with MOCK_ETH_ADDRESS).
            - getUserWalletBalances(address provider, address user): Provides balances of user wallet for all reserves available on the pool
            ...

        https://docs.aave.com/developers/periphery-contracts/walletbalanceprovider
        """
        wallet_balance_provider = self.w3.to_checksum_address(self.active_network.wallet_balance_provider)
        
        wallet_balance_contract = self.w3.eth.contract(address=wallet_balance_provider, abi=ABIReference.wallet_balance_provide_abi)
        
        try:
            # Get the function dynamically
            contract_function = getattr(wallet_balance_contract.functions, function_name)
            # Call the function with provided arguments
            result = contract_function(*args, **kwargs).call()

            # Handle specific case for getReserveData
            
        except AttributeError:
            raise ValueError(f"Method {function_name} does not exist in the contract.")
        except Exception as e:
            raise Exception(f"An error occurred while calling the method {function_name}: {e}")

        return result

    def get_asset_price(self, base_address: str, quote_address: str = None) -> float:
            """
            If quote_address is None, returns the asset price in Ether
            If quote_address is not None, returns the pair price of BASE/QUOTE

            https://docs.aave.com/developers/v/2.0/the-core-protocol/price-oracle#getassetprice
            """

            # For calling Chainlink price feeds (Deprecated):
            # link_eth_address = Web3.toChecksumAddress(self.active_network.link_eth_price_feed)
            # link_eth_price_feed = self.w3.eth.contract(
            #     address=link_eth_address, abi=ABIReference.price_feed_abi)
            # latest_price = Web3.fromWei(link_eth_price_feed.functions.latestRoundData().call()[1], "ether")
            # print(f"The LINK/ETH price is {latest_price}")

            # For calling the Aave price oracle:
            price_oracle_address = self.w3.eth.contract(
                address=Web3.toChecksumAddress(self.active_network.lending_pool_addresses_provider),
                abi=ABIReference.lending_pool_addresses_provider_abi,
            ).functions.getPriceOracle().call()

            price_oracle_contract = self.w3.eth.contract(
                address=price_oracle_address, abi=ABIReference.aave_price_oracle_abi
            )

            latest_price = Web3.fromWei(int(price_oracle_contract.functions.getAssetPrice(base_address).call()),
                                        'ether')
            if quote_address is not None:
                quote_price = Web3.fromWei(int(price_oracle_contract.functions.getAssetPrice(quote_address).call()),
                                        'ether')
                latest_price = latest_price / quote_price
            return float(latest_price)

    def get_abi(self, smart_contract_address: str):
        """
        Used to fetch the JSON ABIs for the deployed Aave smart contracts here:
        https://docs.aave.com/developers/v/2.0/deployed-contracts/deployed-contracts
        """
        print(f"Fetching ABI for smart contract: {smart_contract_address}")
        abi_endpoint = f'https://api.etherscan.io/api?module=contract&action=getabi&address={smart_contract_address}'

        retry_count = 0
        json_abi = None
        err = None
        while retry_count < 5:
            etherscan_response = requests.get(abi_endpoint).json()
            if str(etherscan_response['status']) == '0':
                err = etherscan_response['result']
                retry_count += 1
                time.sleep(1)
            else:
                try:
                    json_abi = json.loads(etherscan_response['result'])
                except json.decoder.JSONDecodeError:
                    err = "Could not load ABI into JSON format"
                except Exception as exc:
                    err = f"Response status was valid, but an unexpected error occurred '{exc}'"
                finally:
                    break
        if json_abi is not None:
            return json_abi
        else:
            raise Exception(f"could not fetch ABI for contract: {smart_contract_address} - Error: {err}")

    def get_reserve_token(self, symbol: str) -> ReserveToken:
        """Returns the ReserveToken class containing the Aave reserve token with the passed symbol"""
        try:
            return [token for token in self.active_network.aave_tokens
                    if token.symbol.lower() == symbol.lower() or token.aTokenSymbol.lower() == symbol.lower()][0]
        except IndexError:
            raise ValueError(
                f"Could not match '{symbol}' with a valid reserve token on aave for the {self.active_network.net_name} network.")

    def swap(self, swap_from_token: ReserveToken, swap_to_token: ReserveToken, amount_to_swap: float) -> AaveTrade:
        """
        Execute the swap operation using ParaSwap API and send transaction via web3.
        
        Parameters:
            swap_from_token: The ReserveToken object representing the token to swap from.
            swap_to_token: The ReserveToken object representing the token to swap to.
            amount_to_swap: The amount of tokens to swap.
        """
        try:
            amount_in_decimal_units = convert_to_decimal_units(swap_from_token.decimals, amount_to_swap)
            
            erc20_address = Web3.to_checksum_address(swap_from_token.address)
            spender_address = Web3.to_checksum_address(self.active_network.token_transfer_proxy)
            
            approval_hash, approval_gas = self.approve_erc20(
                erc20_address=erc20_address,
                spender_address=spender_address,
                amount_in_decimal_units=amount_in_decimal_units
            )

            prices_data = self.get_paraswap_prices(swap_from_token.address, swap_to_token.address, amount_in_decimal_units, swap_from_token.decimals, swap_to_token.decimals)
            transaction_data = self.get_paraswap_transaction(prices_data, self.wallet_address)

            nonce = self.w3.eth.get_transaction_count(self.wallet_address)
            transaction = {
                'from': transaction_data['from'],
                'to': transaction_data['to'],
                'value': int(transaction_data['value']),
                'data': transaction_data['data'],
                'gasPrice': int(transaction_data['gasPrice']),
                'gas': int(transaction_data['gas']),
                'chainId': int(transaction_data['chainId']),
                'nonce': nonce
            }

            signed_txn = self.w3.eth.account.sign_transaction(transaction, private_key=self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            receipt = self.process_transaction_receipt(tx_hash, amount_to_swap, swap_from_token, operation="Swap", approval_gas_cost=approval_gas)
            
            return receipt

        except Exception as exc:
            logger.error(f"Could not execute swap - Error: {exc}")
            raise Exception(f"Could not execute swap - Error: {exc}")

    def list_reserve_tokens(self) -> list:
        """Returns all Aave ReserveToken class objects stored on the active network"""
        return self.active_network.aave_tokens

    def get_paraswap_prices(self, src_token, dest_token, src_amount, src_decimals, dest_decimals, network='42161'):
        """Call ParaSwap API to get price data."""
        url = "https://apiv5.paraswap.io/prices"
        params = {
            "srcToken": src_token,
            "destToken": dest_token,
            "srcDecimals": src_decimals,
            "destDecimals": dest_decimals,
            "amount": src_amount,
            "side": "SELL",
            "network": network,
            "includeDEXS": "true",
            "excludeContractMethods": "simpleSwap",
        }
        response = requests.get(url, params=params)
        if response.status_code != 200:
            raise Exception(f"ParaSwap prices API call failed: {response.text}")

        return response.json()

    def get_paraswap_transaction(self, prices_data, user_address):
        """Call ParaSwap API to get transaction data."""
        url = f"https://apiv5.paraswap.io/transactions/{prices_data['priceRoute']['network']}"
        body = {
            "priceRoute": prices_data['priceRoute'],
            "srcToken": prices_data['priceRoute']['srcToken'],
            "destToken": prices_data['priceRoute']['destToken'],
            "srcAmount": prices_data['priceRoute']['srcAmount'],
            "destAmount": prices_data['priceRoute']['destAmount'],
            "userAddress": user_address,
            "partnerAddress": user_address,
        }
        headers = {
            "Content-Type": "application/json"
        }
        response = requests.post(url, json=body, headers=headers)
        if response.status_code != 200:
            raise Exception(f"ParaSwap transactions API call failed: {response.text}")

        return response.json()

    def get_allowance(self, erc20_address: str, spender_address: str) -> int:
        """
        Get the current allowance for a given ERC20 token and spender.
        
        Parameters:
            erc20_address: The address of the ERC20 token.
            spender_address: The address of the spender.
        
        Returns:
            The current allowance as an integer.
        """
        erc20 = self.w3.eth.contract(address=erc20_address, abi=ABIReference.erc20_abi)
        return erc20.functions.allowance(self.wallet_address, spender_address).call()
