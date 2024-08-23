import logging
import asyncio
import json
from web3 import Web3
from web3.middleware import geth_poa_middleware
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any

from src.utils.morpho_utils import accrue_interests, w_div_down, w_div_up, w_taylor_compounded, w_mul_down, to_assets_up, to_shares_down
from src.utils.abi_references import ABIReference
from src.utils.constants import SECONDS_PER_YEAR, WAD, ORACLE_PRICE_SCALE, MAX_UINT256, ZERO_ADDRESS
from src.utils.morpho_markets import ETHEREUM_MORPHO_MARKETS, BASE_MORPHO_MARKETS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class MorphoMarket:
    underlying_token: str
    morpho_token: str
    p2p_index: int
    pool_supply_index: int
    pool_borrow_index: int
    last_update_timestamp: int

@dataclass
class UserPosition:
    supply_shares: int
    borrow_shares: int
    collateral: int

@dataclass
class MarketState:
    total_supply_assets: int
    total_supply_shares: int
    total_borrow_assets: int
    total_borrow_shares: int
    last_update: int
    fee: int

@dataclass
class MarketParams:
    loan_token: str
    collateral_token: str
    oracle: str
    irm: str
    lltv: int

class BaseNetworkConfig:
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url

class EthereumConfig(BaseNetworkConfig):
    def __init__(self, ethereum_rpc_url: str):
        super().__init__(ethereum_rpc_url)
        self.net_name = "Ethereum"
        self.chain_id = 1
        self.morpho_address = '0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb'
        self.irm_address = '0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC'
        self.lens_address = '0x507fA343d0A90786d86C7cd885f5C49263A91FF4' # The Lens contract seems to be for Aave V2
        self.USDC = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'
        self.USDT = '0xdAC17F958D2ee523a2206206994597C13D831ec7'
        self.DAI = '0x6B175474E89094C44Da98b954EedeAC495271d0F'
        self.USDA = '0x0000206329b97db379d5e1bf586bbdb969c63274'

class BaseConfig(BaseNetworkConfig):
    def __init__(self, base_rpc_url: str):
        super().__init__(base_rpc_url)
        self.net_name = "Base"
        self.chain_id = 8453
        self.morpho_address = '0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb'
        self.irm_address = '0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC'
        self.lens_address = '0x8548AdDf4F50186920D0d13A7D936DD9490b8B47' # The Lens contract seems to be for Aave V2
        self.USDC = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
        self.DAI = '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb'
        self.USDA = '0x0000206329b97DB379d5E1Bf586BbDB969C63274'

class MorphoClient:
    def __init__(self, wallet_address: str, private_key: str, network: str, rpc_url: str):
        self.wallet_address = Web3.to_checksum_address(wallet_address)
        self.private_key = private_key
        self.active_network = self._get_network_config(network, rpc_url)
        self.w3 = self._connect()
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        self.morpho_contract = self._get_morpho_contract()
        self.irm_contract = self._get_irm_contract()
        #self.lens_contract = self._get_lens_contract()
        self.oracle_contract = None  # Will be set dynamically

    def _get_network_config(self, network: str, rpc_url: str) -> BaseNetworkConfig:
        if network.lower() == "ethereum":
            return EthereumConfig(rpc_url)
        elif network.lower() == "base":
            return BaseConfig(rpc_url)
        else:
            raise ValueError(f"Unsupported network: {network}")

    def _connect(self) -> Web3:
        return Web3(Web3.HTTPProvider(self.active_network.rpc_url))

    def _get_morpho_contract(self):
        return self.w3.eth.contract(
            address=self.active_network.morpho_address,
            abi=ABIReference.morpho_blue
        )

    def _get_irm_contract(self):
        return self.w3.eth.contract(
            address=self.active_network.irm_address,
            abi=ABIReference.morpho_irm
        )

    def _get_oracle_contract(self, oracle_address):
        return self.w3.eth.contract(
            address=oracle_address,
            abi=ABIReference.chainlink_oracle
        )
    
    def get_market_info(self, market_key):
        # Fetch the corresponding ID for the given market key based on the active network
        if self.active_network.net_name == "Ethereum":
            market_id = ETHEREUM_MORPHO_MARKETS.get(market_key)
        elif self.active_network.net_name == "Base":
            market_id = BASE_MORPHO_MARKETS.get(market_key)
        else:
            raise ValueError(f"Unsupported network: {self.active_network.net_name}")

        if market_id is None:
            raise ValueError(f"Market key '{market_key}' not found.")
        return market_id

    async def fetch_market_data(self, market_id: str, user_address: str):
        market_params = MarketParams(*self.morpho_contract.functions.idToMarketParams(market_id).call())
        market_state = MarketState(*self.morpho_contract.functions.market(market_id).call())
        position_user = UserPosition(*self.morpho_contract.functions.position(market_id, user_address).call())
        print('market_params:', market_params)
        print('position_user:', position_user)

        market_params_tuple = (
            market_params.loan_token,
            market_params.collateral_token,
            market_params.oracle,
            market_params.irm,
            market_params.lltv,
        )

        market_state_tuple = (
            market_state.total_supply_assets,
            market_state.total_supply_shares,
            market_state.total_borrow_assets,
            market_state.total_borrow_shares,
            market_state.last_update,
            market_state.fee,
        )

        borrow_rate = self.irm_contract.functions.borrowRateView(market_params_tuple, market_state_tuple).call()
        borrow_apy = w_taylor_compounded(borrow_rate, SECONDS_PER_YEAR)
        
        block = self.w3.eth.get_block('latest')
        market_state_updated = accrue_interests(int(block['timestamp']), market_state, borrow_rate)
        market_total_borrow = market_state_updated.total_borrow_assets 
        
        borrow_assets_user = to_assets_up(position_user.borrow_shares, market_state_updated.total_borrow_assets, market_state_updated.total_borrow_shares)
        if (market_params.irm != ZERO_ADDRESS):
            utilization = 0 if market_total_borrow == 0 else w_div_up(market_total_borrow, market_state_updated.total_supply_assets)

        supply_apy = w_mul_down(w_mul_down(borrow_apy, (WAD - market_state.fee)), utilization)

        self.oracle_contract = self._get_oracle_contract(market_params.oracle)
        collateral_price = self.oracle_contract.functions.price().call()
        collateral = position_user.collateral
        max_borrow = w_mul_down(
            w_div_down(collateral * collateral_price, ORACLE_PRICE_SCALE),
            market_params.lltv
        )

        is_healthy = max_borrow >= borrow_assets_user
        health_factor = MAX_UINT256 if borrow_assets_user == 0 else w_div_down(max_borrow, borrow_assets_user)

        return {
            'supply_apy': supply_apy / WAD,
            'borrow_apy': borrow_apy / WAD,
            'borrow_assets_user': borrow_assets_user,
            'market_total_supply': market_state_updated.total_supply_assets,
            'market_total_borrow': market_total_borrow,
            'health_factor': health_factor / (WAD**2),
            'is_healthy': is_healthy
        }

    async def fetch_all_markets_data(self, market_ids: List[str], user_address: str):
        tasks = [self.fetch_market_data(market_id, user_address) for market_id in market_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return dict(zip(market_ids, results))

    def supply(self, asset: str, amount: int):
        # Implement supply logic
        pass

    def withdraw(self, asset: str, amount: int):
        # Implement withdraw logic
        pass

    def borrow(self, asset: str, amount: int):
        # Implement borrow logic
        pass

    def repay(self, asset: str, amount: int):
        # Implement repay logic
        pass

    def claim_rewards(self):
        # Implement rewards claiming if applicable
        pass
