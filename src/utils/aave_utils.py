from typing import Dict, Any
from web3 import Web3
import pandas as pd
import math

def process_get_reserve_data_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Process the result of getReserveData function call."""
    from .web3_utils import from_ray  # local import to avoid circular dependency

    (
        configuration,
        liquidityIndex,
        currentLiquidityRate,
        variableBorrowIndex,
        currentVariableBorrowRate,
        currentStableBorrowRate,
        lastUpdateTimestamp,
        id,
        aTokenAddress,
        stableDebtTokenAddress,
        variableDebtTokenAddress,
        interestRateStrategyAddress,
        accruedToTreasury,
        unbacked,
        isolationModeTotalDebt,
    ) = result

    return {
        "configuration": configuration,
        "liquidityIndex": from_ray(liquidityIndex),
        "currentLiquidityRate": from_ray(currentLiquidityRate),
        "variableBorrowIndex": from_ray(variableBorrowIndex),
        "currentVariableBorrowRate": from_ray(currentVariableBorrowRate),
        "currentStableBorrowRate": from_ray(currentStableBorrowRate),
        "lastUpdateTimestamp": lastUpdateTimestamp,
        "id": id,
        "aTokenAddress": aTokenAddress,
        "stableDebtTokenAddress": stableDebtTokenAddress,
        "variableDebtTokenAddress": variableDebtTokenAddress,
        "interestRateStrategyAddress": interestRateStrategyAddress,
        "accruedToTreasury": accruedToTreasury,
        "unbacked": unbacked,
        "isolationModeTotalDebt": isolationModeTotalDebt,
    }

def process_get_user_account_data_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Process the result of getUserAccountData function call."""
    from .web3_utils import from_market_base_ccy  # local import to avoid circular dependency

    (
        totalCollateralBase,
        totalDebtBase,
        availableBorrowsBase,
        currentLiquidationThreshold,
        ltv,
        healthFactor,
    ) = result

    return {
        "totalCollateralBase": from_market_base_ccy(totalCollateralBase),
        "totalDebtBase": from_market_base_ccy(totalDebtBase),
        "availableBorrowsBase": from_market_base_ccy(availableBorrowsBase),
        "currentLiquidationThreshold": currentLiquidationThreshold,
        "ltv": ltv,
        "healthFactor": healthFactor,
    }

def calculate_spreads(rates_df):
    """Calculate spreads between supply and borrow rates"""
    spreads_df = rates_df.copy()
    
    # Calculate spreads
    spreads_df['supply_variable_spread'] = spreads_df['variable_borrow_apy'] - spreads_df['supply_apy']
    
    return spreads_df

def find_best_rates(combined_df):
    """
    Find the best supply and borrow rates across all assets for each timestamp.
    Sets spread to 0 when max supply APY is lower than min borrow APY.
    """
    # Get supply and variable borrow columns for each asset
    supply_cols = [col for col in combined_df.columns if col.endswith('supply_apy')]
    var_borrow_cols = [col for col in combined_df.columns if col.endswith('variable_borrow_apy')]
    
    # Create DataFrame with optimal rates
    best_rates = pd.DataFrame()
    best_rates['datetime'] = combined_df['datetime']
    best_rates['timestamp'] = combined_df['timestamp']
    best_rates['block_number'] = combined_df['block_number']
    
    # Find best rates
    best_rates['max_supply_apy'] = combined_df[supply_cols].max(axis=1)
    best_rates['min_borrow_apy'] = combined_df[var_borrow_cols].min(axis=1)
    
    # Calculate raw spread
    raw_spread = best_rates['max_supply_apy'] - best_rates['min_borrow_apy']
    
    # Create mask for positive spreads
    positive_spread_mask = raw_spread > 0
    
    # Track which assets provide the best rates only when spread is positive
    best_rates['best_supply_asset'] = 'None'  # Default value
    best_rates['best_borrow_asset'] = 'None'  # Default value
    
    # Update assets only for positive spreads
    best_rates.loc[positive_spread_mask, 'best_supply_asset'] = \
        combined_df[supply_cols].idxmax(axis=1)[positive_spread_mask].apply(lambda x: x.split('_')[0])
    best_rates.loc[positive_spread_mask, 'best_borrow_asset'] = \
        combined_df[var_borrow_cols].idxmin(axis=1)[positive_spread_mask].apply(lambda x: x.split('_')[0])
    
    # Set optimal spread (zero for negative spreads)
    best_rates['optimal_spread'] = raw_spread.clip(lower=0)
    
    # Add percentage of time with positive spread
    positive_spread_pct = (positive_spread_mask.sum() / len(best_rates)) * 100
    print(f"Positive spread opportunities found in {positive_spread_pct:.1f}% of the time periods")
    
    return best_rates

def analyze_rate_distribution(combined_df):
    """
    Analyze the distribution of rates across assets
    """
    stats = {}
    
    # Calculate statistics for each asset
    for symbol in set(col.split('_')[0] for col in combined_df.columns if '_' in col):
        supply_col = f"{symbol}_supply_apy"
        borrow_col = f"{symbol}_variable_borrow_apy"
        
        if supply_col in combined_df.columns and borrow_col in combined_df.columns:
            stats[symbol] = {
                'avg_supply_apy': combined_df[supply_col].mean(),
                'avg_borrow_apy': combined_df[borrow_col].mean(),
                'max_supply_apy': combined_df[supply_col].max(),
                'min_borrow_apy': combined_df[borrow_col].min(),
                'supply_volatility': combined_df[supply_col].std(),
                'borrow_volatility': combined_df[borrow_col].std(),
                'best_supply_count': (combined_df[supply_col] == 
                                    combined_df[[c for c in combined_df.columns if c.endswith('supply_apy')]].max(axis=1)).sum(),
                'best_borrow_count': (combined_df[borrow_col] == 
                                    combined_df[[c for c in combined_df.columns if c.endswith('variable_borrow_apy')]].min(axis=1)).sum()
            }
    
    return pd.DataFrame(stats).T

def backtest_leveraged_strategy(spreads_df, LTV=0.9, initial_collateral=100, stop_condition=0.8):
    """
    Backtest a leveraged yield farming strategy using optimal rates across assets
    
    Parameters:
        spreads_df: DataFrame with max_supply_apy and optimal_spread columns
        LTV: Loan-to-Value ratio (e.g., 0.9 for 90% LTV)
        initial_collateral: Initial amount deposited
        stop_condition: Minimum LTV to maintain
        
    Returns:
        results_df: DataFrame with original data plus strategy metrics
        number_of_loops: Number of leverage loops used
    """
    # Calculate leverage metrics
    number_of_loops = math.ceil(math.log(stop_condition) / math.log(LTV))
    total_collateral = initial_collateral * ((1 - LTV**(number_of_loops + 1)) / (1 - LTV))
    leverage = total_collateral / initial_collateral
    
    # Create results DataFrame
    results_df = spreads_df.copy()
    
    # Calculate final APY using the optimal rates
    # For each period:
    # We earn max_supply_apy on total collateral
    # We pay min_borrow_apy on borrowed amount
    results_df['final_apy'] = (
        results_df['max_supply_apy'] * initial_collateral + 
        (total_collateral - initial_collateral) * results_df['optimal_spread']
    ) / initial_collateral
    
    # Add useful metrics
    results_df['leverage'] = leverage
    results_df['total_collateral'] = total_collateral
    results_df['loops'] = number_of_loops
    
    # Add which assets were used
    results_df['strategy_description'] = (
        'Supply ' + results_df['best_supply_asset'] + 
        ' / Borrow ' + results_df['best_borrow_asset']
    )
    
    return results_df, number_of_loops

def calculate_compounded_balance(results_df, initial_collateral, freq_hours=1):
    """Calculate compounded balance over time with proper intraday frequency"""
    daily_df = results_df.copy()

    period_fraction = freq_hours/(24*365)
    # Calculate per-period return
    daily_df['period_return'] = (1 + daily_df['final_apy']/100).pow(period_fraction) - 1
    
    # Calculate cumulative return using cumprod
    daily_df['cumulative_return'] = (1 + daily_df['period_return']).cumprod()
    
    # Calculate final balance
    daily_df['compounded_balance'] = initial_collateral * daily_df['cumulative_return']
    
    # Add annualized return for each period
    daily_df['annualized_return'] = (
        (1 + daily_df['period_return']).pow(365*24/freq_hours) - 1
    ) * 100
    
    return daily_df

def print_strategy_stats(results_df, number_of_loops, initial_collateral, freq_hours=4):
    """
    Print comprehensive strategy statistics including APY and gas costs
    
    Parameters:
        results_df: DataFrame with final_apy and other strategy metrics
        number_of_loops: Number of leverage loops used
        initial_collateral: Initial collateral amount
        freq_hours: Hours between each rebalance
    """
    # Calculate APY stats
    print("\n--------Strategy APY Stats--------")
    print(f"Average APY: {results_df['final_apy'].mean():.2f}%")
    print(f"Maximum APY: {results_df['final_apy'].max():.2f}%")
    print(f"Minimum APY: {results_df['final_apy'].min():.2f}%")
    
    # Calculate leverage stats
    print(f"\nLeverage loops: {number_of_loops}")
    leverage = results_df['leverage'].iloc[0] if 'leverage' in results_df.columns else 'N/A'
    print(f"Total leverage: {leverage:.2f}x")
    
    # Most common strategy
    if 'strategy_description' in results_df.columns:
        most_common_strategy = results_df['strategy_description'].mode().iloc[0]
        print(f"\nMost common strategy: {most_common_strategy}")

    # Gas costs analysis
    print("\n--------Gas Costs Analysis--------")
    print(f"Rebalancing frequency: {freq_hours}h")
    
    # Transaction calculations
    cost_per_rebalancing = 4 * number_of_loops  # 4 transactions per loop
    daily_rebalances = 24 / freq_hours
    daily_transactions = cost_per_rebalancing * daily_rebalances
    
    print(f"Transactions per rebalance: {cost_per_rebalancing} ({number_of_loops} loops × 4 tx)")
    print(f"Daily rebalances: {daily_rebalances:.1f}")
    print(f"Daily transactions: {daily_transactions:.1f}")
    
    # Cost calculations
    cost_per_tx = 0.05  # $0.05 per transaction on L2
    daily_gas_cost = cost_per_tx * daily_transactions
    annual_gas_cost = 365 * daily_gas_cost
    
    print(f"\nCost per transaction: ${cost_per_tx}")
    print(f"Daily gas cost: ${daily_gas_cost:.2f}")
    print(f"Annual gas cost: ${annual_gas_cost:.2f}")
    
    # Cost relative to capital
    initial_bps = (annual_gas_cost/initial_collateral) * 10000
    million_bps = (annual_gas_cost/1000000) * 10000
    
    print("\n--------Cost Relative to Capital--------")
    print(f"With {initial_collateral:,} initial capital: {initial_bps:.2f} bps")
    print(f"With $1M capital: {million_bps:.2f} bps")