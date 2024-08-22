from typing import Dict, Any, Tuple
from dataclasses import dataclass
from decimal import Decimal, getcontext
from src.utils.constants import SECONDS_PER_YEAR, WAD

# Set precision for decimal calculations
getcontext().prec = 78

@dataclass
class UserPosition:
    supplied_p2p: Decimal
    supplied_pool: Decimal
    borrowed_p2p: Decimal
    borrowed_pool: Decimal

@dataclass
class MorphoMarket:
    underlying_token: str
    morpho_token: str
    p2p_index: Decimal
    pool_supply_index: Decimal
    pool_borrow_index: Decimal
    last_update_timestamp: int
    total_supplied_p2p: Decimal
    total_supplied_pool: Decimal
    total_borrowed_p2p: Decimal
    total_borrowed_pool: Decimal
    p2p_borrow_apy: Decimal
    p2p_supply_apy: Decimal
    pool_borrow_apy: Decimal
    pool_supply_apy: Decimal

@dataclass
class MarketState:
    total_supply_assets: int
    total_supply_shares: int
    total_borrow_assets: int
    total_borrow_shares: int
    last_update: int
    fee: int

def process_user_position(raw_position: Tuple[int, int, int, int], decimals: int) -> UserPosition:
    """
    Process raw user position data from Morpho contract.
    
    :param raw_position: Tuple containing raw position data (supplied_p2p, supplied_pool, borrowed_p2p, borrowed_pool)
    :param decimals: Number of decimals for the asset
    :return: UserPosition object with processed data
    """
    scaling_factor = Decimal(10**decimals)
    return UserPosition(
        supplied_p2p=Decimal(raw_position[0]) / scaling_factor,
        supplied_pool=Decimal(raw_position[1]) / scaling_factor,
        borrowed_p2p=Decimal(raw_position[2]) / scaling_factor,
        borrowed_pool=Decimal(raw_position[3]) / scaling_factor
    )

def process_market_data(raw_market_data: Dict[str, Any], decimals: int) -> MorphoMarket:
    """
    Process raw market data from Morpho contract.
    
    :param raw_market_data: Dictionary containing raw market data
    :param decimals: Number of decimals for the asset
    :return: MorphoMarket object with processed data
    """
    scaling_factor = Decimal(10**decimals)
    index_scaling_factor = Decimal(10**27)  # Morpho uses RAY (1e27) for index values
    
    return MorphoMarket(
        underlying_token=raw_market_data['underlying_token'],
        morpho_token=raw_market_data['morpho_token'],
        p2p_index=Decimal(raw_market_data['p2p_index']) / index_scaling_factor,
        pool_supply_index=Decimal(raw_market_data['pool_supply_index']) / index_scaling_factor,
        pool_borrow_index=Decimal(raw_market_data['pool_borrow_index']) / index_scaling_factor,
        last_update_timestamp=raw_market_data['last_update_timestamp'],
        total_supplied_p2p=Decimal(raw_market_data['total_supplied_p2p']) / scaling_factor,
        total_supplied_pool=Decimal(raw_market_data['total_supplied_pool']) / scaling_factor,
        total_borrowed_p2p=Decimal(raw_market_data['total_borrowed_p2p']) / scaling_factor,
        total_borrowed_pool=Decimal(raw_market_data['total_borrowed_pool']) / scaling_factor,
        p2p_borrow_apy=calculate_apy(raw_market_data['p2p_borrow_rate']),
        p2p_supply_apy=calculate_apy(raw_market_data['p2p_supply_rate']),
        pool_borrow_apy=calculate_apy(raw_market_data['pool_borrow_rate']),
        pool_supply_apy=calculate_apy(raw_market_data['pool_supply_rate'])
    )

def calculate_apy(rate: int) -> Decimal:
    """
    Calculate APY from a per-second interest rate.
    
    :param rate: Per-second interest rate (scaled by 1e18)
    :return: APY as a percentage
    """
    rate_decimal = Decimal(rate) / Decimal(1e18)
    apy = ((1 + rate_decimal) ** Decimal(31536000) - 1) * 100  # 31536000 seconds in a year
    return apy.quantize(Decimal('0.01'))  # Round to two decimal places

def calculate_health_factor(collateral_value: Decimal, borrowed_value: Decimal, liquidation_threshold: Decimal) -> Decimal:
    """
    Calculate the health factor for a user's position.
    
    :param collateral_value: Total value of user's collateral in base currency
    :param borrowed_value: Total value of user's borrowed assets in base currency
    :param liquidation_threshold: Liquidation threshold (e.g., 0.825 for 82.5%)
    :return: Health factor
    """
    if borrowed_value == 0:
        return Decimal('inf')
    return (collateral_value * liquidation_threshold) / borrowed_value

def estimate_liquidation_price(
    asset_price: Decimal,
    collateral_amount: Decimal,
    collateral_factor: Decimal,
    debt_amount: Decimal,
    liquidation_threshold: Decimal
) -> Decimal:
    """
    Estimate the liquidation price for a specific asset.
    
    :param asset_price: Current price of the asset
    :param collateral_amount: Amount of collateral
    :param collateral_factor: Collateral factor (e.g., 0.75 for 75%)
    :param debt_amount: Amount of debt
    :param liquidation_threshold: Liquidation threshold (e.g., 0.825 for 82.5%)
    :return: Estimated liquidation price
    """
    return (debt_amount * asset_price) / (collateral_amount * liquidation_threshold)

def calculate_borrow_power(collateral_value: Decimal, collateral_factor: Decimal, current_borrows: Decimal) -> Decimal:
    """
    Calculate the remaining borrow power.
    
    :param collateral_value: Total value of user's collateral in base currency
    :param collateral_factor: Collateral factor (e.g., 0.75 for 75%)
    :param current_borrows: Current value of user's borrows in base currency
    :return: Remaining borrow power in base currency
    """
    max_borrow = collateral_value * collateral_factor
    return max(max_borrow - current_borrows, Decimal(0))


def w_taylor_compounded(rate: int, time: int) -> int:
    """Calculate the compounded rate using Taylor series approximation."""
    x = (rate * time) // SECONDS_PER_YEAR
    return WAD + x + (x * x) // (2 * WAD)

def accrue_interests(last_block_timestamp: int, market_state: MarketState, borrow_rate: int) -> MarketState:
    """Accrue interests on the market state."""
    elapsed = last_block_timestamp - market_state.last_update
    if elapsed == 0:
        return market_state
    if market_state.total_borrow_assets != 0:
        interest = w_mul_down(
            market_state.total_borrow_assets,
            w_taylor_compounded(borrow_rate, elapsed)
        )
        new_total_supply = market_state.total_supply_assets + interest
        new_total_borrow = market_state.total_borrow_assets + interest
        new_supply_shares = market_state.total_supply_shares

        if market_state.fee != 0:
            fee_amount = w_mul_down(interest, market_state.fee)
            fee_shares = to_shares_down(
                fee_amount,
                new_total_supply - fee_amount,
                market_state.total_supply_shares
            )
            new_supply_shares += fee_shares

        return MarketState(
            total_supply_assets=new_total_supply,
            total_supply_shares=new_supply_shares,
            total_borrow_assets=new_total_borrow,
            total_borrow_shares=market_state.total_borrow_shares,
            last_update=last_block_timestamp,
            fee=market_state.fee
        )
    return market_state

def to_assets_up(shares: int, total_assets: int, total_shares: int) -> int:
    """Convert shares to assets, rounding up."""
    return (shares * total_assets + total_shares - 1) // total_shares if total_shares != 0 else shares

def to_shares_down(assets: int, total_assets: int, total_shares: int) -> int:
    """Convert assets to shares, rounding down."""
    return (assets * total_shares) // total_assets if total_assets != 0 else assets

def w_div_up(a: int, b: int) -> int:
    """Divide two numbers, rounding up."""
    return (a + b - 1) // b

def w_mul_down(a: int, b: int) -> int:
    """Multiply two numbers, rounding down."""
    return (a * b) // WAD

def w_div_down(a: int, b: int) -> int:
    """Divide two numbers, rounding down."""
    return (a * WAD) // b
