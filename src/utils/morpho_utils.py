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

def accrue_interests(last_block_timestamp, market_state: MarketState, borrow_rate):
    elapsed = last_block_timestamp - market_state.last_update
    if elapsed == 0:
        return market_state
    if market_state.total_borrow_assets != 0:
        interest = w_mul_down(
            market_state.total_borrow_assets,
            w_taylor_compounded(borrow_rate, elapsed)
        )
        # Create a new MarketState with updated totals
        market_with_new_total = MarketState(
            market_state.total_supply_assets + interest,
            market_state.total_supply_shares,  # Will be updated below if there's a fee
            market_state.total_borrow_assets + interest,
            market_state.total_borrow_shares,
            market_state.last_update,
            market_state.fee
        )
        if market_state.fee != 0:
            fee_amount = w_mul_down(interest, market_state.fee)
            fee_shares = to_shares_down(
                fee_amount,
                market_with_new_total.total_supply_assets - fee_amount,
                market_with_new_total.total_supply_shares
            )
            # Update the total supply shares with the fee shares
            market_with_new_total.total_supply_shares += fee_shares

        return market_with_new_total
    return market_state


VIRTUAL_SHARES = 10 ** 6
VIRTUAL_ASSETS = 1

def to_shares_down(assets, total_assets, total_shares):
    return mul_div_down(assets, total_shares + VIRTUAL_SHARES, total_assets + VIRTUAL_ASSETS)

def to_assets_down(shares, total_assets, total_shares):
    return mul_div_down(shares, total_assets + VIRTUAL_ASSETS, total_shares + VIRTUAL_SHARES)

def to_shares_up(assets, total_assets, total_shares):
    return mul_div_up(assets, total_shares + VIRTUAL_SHARES, total_assets + VIRTUAL_ASSETS)

def to_assets_up(shares, total_assets, total_shares):
    return mul_div_up(shares, total_assets + VIRTUAL_ASSETS, total_shares + VIRTUAL_SHARES)

def pow10(exponent):
    return 10 ** exponent

WAD = pow10(18)

def w_mul_down(x, y):
    return mul_div_down(x, y, WAD)

def w_div_down(x, y):
    return mul_div_down(x, WAD, y)

def w_div_up(x, y):
    return mul_div_up(x, WAD, y)

def mul_div_down(x, y, d):
    if d == 0:
        raise ZeroDivisionError("Attempt to divide by zero in mul_div_down function")
    return (x * y) // d

def mul_div_up(x, y, d):
    if d == 0:
        raise ZeroDivisionError("Attempt to divide by zero in mul_div_up function")
    return (x * y + (d - 1)) // d

def min_(a, b):
    return min(a, b)

def max_(a, b):
    return max(a, b)

def w_taylor_compounded(x, n):
    first_term = x * n
    second_term = mul_div_down(first_term, first_term, 2 * WAD)
    third_term = mul_div_down(second_term, first_term, 3 * WAD)
    return first_term + second_term + third_term