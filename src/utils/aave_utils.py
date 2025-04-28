from typing import Dict, Any
from web3 import Web3
import pandas as pd
import numpy as np
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

def prepare_rates_data(combined_df):
    """
    Prepare rates data by handling unavailable assets:
    - Convert cases where both supply and borrow rates are 0 to NaN
    - These will be ignored in best pair selection
    
    Parameters:
    - combined_df: DataFrame with supply and borrow rates for all assets
    
    Returns:
    - Cleaned DataFrame with NaN for unavailable assets
    """
    cleaned_df = combined_df.copy()
    
    # Get all unique assets by looking at supply rate columns
    assets = set(col.split('_')[0] for col in cleaned_df.columns 
                if col.endswith('supply_apy'))
    
    # For each asset, check if both rates are 0 and convert to NaN
    for asset in assets:
        supply_col = f"{asset}_supply_apy"
        borrow_col = f"{asset}_variable_borrow_apy"
        
        if supply_col in cleaned_df.columns and borrow_col in cleaned_df.columns:
            mask = (cleaned_df[supply_col] == 0) & (cleaned_df[borrow_col] == 0)
            cleaned_df.loc[mask, [supply_col, borrow_col]] = np.nan
    
    return cleaned_df

def find_best_pairs(combined_df):
    """
    Find the best supply and borrow pairs across all stablecoins for each timestamp.
    Returns both the best spread and the underlying assets.
    """
    # Get supply and variable borrow columns for each asset
    supply_cols = [col for col in combined_df.columns if col.endswith('supply_apy')]
    var_borrow_cols = [col for col in combined_df.columns if col.endswith('variable_borrow_apy')]
    
    # Create DataFrame with optimal rates
    best_pairs = pd.DataFrame()
    best_pairs['datetime'] = combined_df['datetime']
    best_pairs['timestamp'] = combined_df['timestamp']
    best_pairs['block_number'] = combined_df['block_number']
    
    # Find best rates for each period
    for idx in combined_df.index:
        supply_rates = {col.split('_')[0]: combined_df.loc[idx, col] 
                       for col in supply_cols
                       if not pd.isna(combined_df.loc[idx, col])}  # Ignore NaN rates
        borrow_rates = {col.split('_')[0]: combined_df.loc[idx, col] 
                       for col in var_borrow_cols
                       if not pd.isna(combined_df.loc[idx, col])}  # Ignore NaN rates
        
        # Find best spread
        best_spread = float('-inf')
        best_supply_asset = None
        best_borrow_asset = None
        
        for supply_asset, supply_rate in supply_rates.items():
            for borrow_asset, borrow_rate in borrow_rates.items():
                spread = supply_rate - borrow_rate
                if spread > best_spread:
                    best_spread = spread
                    best_supply_asset = supply_asset
                    best_borrow_asset = borrow_asset
        
        best_pairs.loc[idx, 'best_supply_asset'] = best_supply_asset
        best_pairs.loc[idx, 'best_borrow_asset'] = best_borrow_asset
        best_pairs.loc[idx, 'supply_apy'] = supply_rates.get(best_supply_asset, np.nan)
        best_pairs.loc[idx, 'borrow_apy'] = borrow_rates.get(best_borrow_asset, np.nan)
        best_pairs.loc[idx, 'spread'] = best_spread if best_spread != float('-inf') else np.nan
    
    return best_pairs

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

def backtest_enhanced_strategy(data_df, LTV=0.9, initial_collateral=10000, stop_condition=0.5, time_interval_hours=4, consecutive_periods=3):
    """
    Enhanced backtest with sophisticated rebalancing rules and performance tracking.
    Now handles unavailable assets by preprocessing the data.

    Number of txs per loop:
    Have infinite approvals ready for all assets for both swap and supply --> 2 * number of assets
    For building position: 2 tx (multicall supply+borrow, then swap)
    Unwinding position: 2 tx (swap, then multicall repay+withdraw)
    """
    # Constants for costs
    TRANSACTION_COST_USD = 0.06  # Average cost per transaction in USD
    SWAP_FEE_PERCENTAGE = 0.000  # 0% on Aave's swap functionality 

    # Calculate best pairs from cleaned rates
    results = find_best_pairs(data_df)
    
    # Convert timestamps to datetime if they aren't already and sort
    results['timestamp'] = pd.to_datetime(results['timestamp'], unit='s')
    results = results.sort_values('timestamp').reset_index(drop=True)
    
    # Initialize all columns first
    results['hours_diff'] = pd.Series(dtype='float64')
    results['rebalance_count'] = pd.Series(dtype='int64', index=results.index).fillna(0)
    results['transaction_count'] = pd.Series(dtype='int64', index=results.index).fillna(0)
    results['total_swaps'] = pd.Series(dtype='int64', index=results.index).fillna(0)
    results['total_transactions'] = pd.Series(dtype='int64', index=results.index).fillna(0)
    results['swap_count'] = pd.Series(dtype='int64', index=results.index).fillna(0)
    results['current_supply_asset'] = pd.Series(dtype='object', index=results.index)
    results['current_borrow_asset'] = pd.Series(dtype='object', index=results.index)
    results['current_supply_rate'] = pd.Series(dtype='float64', index=results.index).fillna(0.0)
    results['current_borrow_rate'] = pd.Series(dtype='float64', index=results.index).fillna(0.0)
    results['current_spread'] = pd.Series(dtype='float64', index=results.index).fillna(0.0)
    results['position_value'] = pd.Series(dtype='float64', index=results.index)
    results['rebalance_status'] = pd.Series(dtype='object', index=results.index).fillna('no_rebalance')
    results['total_collateral'] = pd.Series(dtype='float64', index=results.index)
    results['leverage'] = pd.Series(dtype='float64', index=results.index)
    results['period_return'] = pd.Series(dtype='float64', index=results.index).fillna(0.0)
    results['annualized_return'] = pd.Series(dtype='float64', index=results.index).fillna(0.0)
    results['transaction_costs_usd'] = pd.Series(dtype='float64', index=results.index).fillna(0.0)
    results['swap_costs_usd'] = pd.Series(dtype='float64', index=results.index).fillna(0.0)
    results['total_costs_usd'] = pd.Series(dtype='float64', index=results.index).fillna(0.0)
    results['position_value_after_costs'] = pd.Series(dtype='float64', index=results.index)
    
    # Calculate time differences
    results['hours_diff'] = results['timestamp'].diff().dt.total_seconds() / 3600
    results.loc[0, 'hours_diff'] = float(time_interval_hours)
    
    # Calculate leverage metrics
    number_of_loops = math.ceil(math.log(stop_condition) / math.log(LTV))
    total_collateral = initial_collateral * ((1 - LTV**(number_of_loops + 1)) / (1 - LTV))
    leverage = total_collateral / initial_collateral
    
    # Set initial values
    results.loc[0, 'position_value'] = float(initial_collateral)
    results.loc[0, 'total_collateral'] = float(total_collateral)
    results.loc[0, 'leverage'] = float(leverage)
    
    # Initialize first position
    if results.iloc[0]['spread'] > 0:
        results.loc[0, 'current_supply_asset'] = results.iloc[0]['best_supply_asset']
        results.loc[0, 'current_borrow_asset'] = results.iloc[0]['best_borrow_asset']
        results.loc[0, 'current_spread'] = float(results.iloc[0]['spread'])
        results.loc[0, 'rebalance_count'] = 1
        results.loc[0, 'transaction_count'] = int(2 * number_of_loops)
        results.loc[0, 'swap_count'] = 1

        initial_transaction_costs = float(results.loc[0, 'transaction_count']) * TRANSACTION_COST_USD
        initial_swap_costs = float(total_collateral * SWAP_FEE_PERCENTAGE * results.loc[0, 'swap_count'])

        results.loc[0, 'transaction_costs_usd'] = initial_transaction_costs
        results.loc[0, 'swap_costs_usd'] = initial_swap_costs
        results.loc[0, 'total_costs_usd'] = initial_transaction_costs + initial_swap_costs
        results.loc[0, 'position_value_after_costs'] = float(initial_collateral - initial_transaction_costs - initial_swap_costs)
    else:
        results.loc[0, 'position_value_after_costs'] = float(initial_collateral)
    
    # Simulate strategy
    current_spread = 0.0 # Default value
    for i in range(1, len(results)):
        # Default carry forward of current position and status
        results.loc[i, 'current_supply_asset'] = results.iloc[i-1]['current_supply_asset']
        results.loc[i, 'current_borrow_asset'] = results.iloc[i-1]['current_borrow_asset']
        results.loc[i, 'rebalance_status'] = 'no_rebalance'
        results.loc[i, 'rebalance_count'] = 0
        results.loc[i, 'transaction_count'] = 0
        
        # Get latest rates and spread for current position if it exists
        if results.iloc[i-1]['current_supply_asset'] is not None and not pd.isna(results.iloc[i-1]['current_supply_asset']):
            current_supply_rate = data_df.loc[i, f"{results.iloc[i-1]['current_supply_asset']}_supply_apy"]
            results.loc[i, 'current_supply_rate'] = float(current_supply_rate)
            
            if results.iloc[i-1]['current_borrow_asset'] is not None and not pd.isna(results.iloc[i-1]['current_borrow_asset']):
                current_borrow_rate = data_df.loc[i, f"{results.iloc[i-1]['current_borrow_asset']}_variable_borrow_apy"]
                results.loc[i, 'current_borrow_rate'] = float(current_borrow_rate)
                current_spread = current_supply_rate - current_borrow_rate
                results.loc[i, 'current_spread'] = float(current_spread)
            else:
                results.loc[i, 'current_borrow_rate'] = 0.0
                results.loc[i, 'current_spread'] = 0.0
        else:
            results.loc[i, 'current_supply_rate'] = 0.0
            results.loc[i, 'current_borrow_rate'] = 0.0
            results.loc[i, 'current_spread'] = 0.0
        
        need_rebalance = False
        new_supply_asset = results.iloc[i-1]['current_supply_asset']
        new_borrow_asset = results.iloc[i-1]['current_borrow_asset']
        new_spread = current_spread if 'current_spread' in locals() else 0.0
        
        # Check for extremely negative spread
        if results.iloc[i-1]['current_supply_asset'] is not None and current_spread < -10:
            new_supply_asset = None
            new_borrow_asset = None
            new_spread = 0.0
            need_rebalance = True
            results.loc[i, 'rebalance_status'] = 'rebalanced_negative'
            
        # Check for persistent suboptimal position
        elif i >= consecutive_periods:
            current_supply = results.iloc[i-1]['current_supply_asset']
            current_borrow = results.iloc[i-1]['current_borrow_asset']
            
            has_negative_spread = any(
                results.iloc[j]['spread'] <= 0
                for j in range(i-(consecutive_periods-1), i+1)
            )
            
            if has_negative_spread and current_borrow is not None:
                new_supply_asset = current_supply
                new_borrow_asset = None
                new_spread = 0.0
                need_rebalance = True
                results.loc[i, 'rebalance_status'] = 'rebalanced_negative'
            else:
                has_different_position = True
                for j in range(i-(consecutive_periods-1), i+1):
                    best_supply = results.iloc[j]['best_supply_asset']
                    best_borrow = results.iloc[j]['best_borrow_asset']
                    
                    if (best_supply == current_supply and best_borrow == current_borrow):
                        has_different_position = False
                        break
                
                if has_different_position and results.iloc[i]['spread'] > 0:
                    new_supply_asset = results.iloc[i]['best_supply_asset']
                    new_borrow_asset = results.iloc[i]['best_borrow_asset']
                    new_spread = float(results.iloc[i]['spread'])
                    need_rebalance = True
                    results.loc[i, 'rebalance_status'] = 'rebalanced_best_pair'
        
        # Update position if rebalancing
        if need_rebalance:
            total_collateral = float(results.iloc[i-1]['position_value'] * leverage)
            results.loc[i, 'current_supply_asset'] = new_supply_asset
            results.loc[i, 'current_borrow_asset'] = new_borrow_asset
            results.loc[i, 'current_spread'] = float(new_spread)
            results.loc[i, 'rebalance_count'] = 1
            results.loc[i, 'total_collateral'] = total_collateral

            # TRANSACTIONS COUNT
            current_has_debt = results.iloc[i-1]['current_borrow_asset'] is not None
            new_has_debt = new_borrow_asset is not None
            
            if current_has_debt:
                # Closing leveraged position
                if new_has_debt:
                    # Full leveraged rebalance
                    results.loc[i, 'transaction_count'] = 4 * number_of_loops
                    results.loc[i, 'swap_count'] = 2 # 2 * the total_collateral
                else:
                    # Deleveraging to simple position
                    # Withdraw + repay + swap for each loop to close, then one approve + supply
                    results.loc[i, 'transaction_count'] = (2 * number_of_loops) + 2
                    results.loc[i, 'swap_count'] = 1
            else:
                if new_has_debt:
                    # Moving from simple to leveraged
                    results.loc[i, 'transaction_count'] = 2 * number_of_loops
                    results.loc[i, 'swap_count'] = 1
                else:
                    # Simple position to simple position
                    if new_supply_asset != results.iloc[i-1]['current_supply_asset']:
                        # Different asset: withdraw + approve + supply + swap
                        results.loc[i, 'transaction_count'] = 2
                        results.loc[i, 'swap_count'] = 1 / leverage
                    else:
                        # Same asset: no transactions needed
                        results.loc[i, 'transaction_count'] = 0
                        results.loc[i, 'swap_count'] = 0
            
            # Update cumulative counts
            if i > 0:
                results.loc[i, 'total_swaps'] = results.iloc[i-1]['total_swaps'] + results.loc[i, 'swap_count']
                results.loc[i, 'total_transactions'] = results.iloc[i-1]['total_transactions'] + results.loc[i, 'transaction_count']

            # UPDATE TX COSTS
            period_transaction_costs = float(results.loc[i, 'transaction_count']) * TRANSACTION_COST_USD
            # Calculate swap costs based on the amount being swapped
            if results.loc[i, 'swap_count'] > 0:
                if new_has_debt:
                    swap_amount = total_collateral  # Use total collateral for leveraged positions
                else:
                    swap_amount = results.iloc[i-1]['position_value']  # Use position value for simple positions
                period_swap_costs = float(swap_amount * SWAP_FEE_PERCENTAGE * results.loc[i, 'swap_count'])
            else:
                period_swap_costs = 0.0
            
            # Update cumulative costs
            results.loc[i, 'transaction_costs_usd'] = period_transaction_costs
            results.loc[i, 'swap_costs_usd'] = period_swap_costs
            results.loc[i, 'total_costs_usd'] = period_transaction_costs + period_swap_costs
            
            if i > 0:
                results.loc[i, 'total_costs_usd'] += results.iloc[i-1]['total_costs_usd']

        else: 
            # TRANSACTIONS COUNT: No rebalancing needed, carry forward totals
            if i > 0:
                results.loc[i, 'total_swaps'] = results.iloc[i-1]['total_swaps']
                results.loc[i, 'total_transactions'] = results.iloc[i-1]['total_transactions']
                # Carry forward cumulative costs when no rebalancing
                results.loc[i, 'total_costs_usd'] = results.iloc[i-1]['total_costs_usd']

        # Calculate period return based on position and rates
        if results.iloc[i]['current_borrow_asset'] is not None:  # Leveraged position
            supply_rate_decimal = float(results.iloc[i]['current_supply_rate']) / 100.0
            spread_decimal = float(results.iloc[i]['current_spread']) / 100.0
            actual_hours = float(results.iloc[i]['hours_diff'])
            annualized_return = (supply_rate_decimal + spread_decimal * (leverage-1))
            period_return = annualized_return * (actual_hours / (24.0 * 365.0))
        else:  # Non-leveraged position
            supply_rate_decimal = float(results.iloc[i]['current_supply_rate']) / 100.0
            actual_hours = float(results.iloc[i]['hours_diff'])
            annualized_return = supply_rate_decimal
            period_return = annualized_return * (actual_hours / (24.0 * 365.0))

        
        # Update position value and period return
        results.loc[i, 'period_return'] = float(period_return) * 100
        results.loc[i, 'annualized_return'] = float(annualized_return) * 100
        results.loc[i, 'position_value'] = float(results.iloc[i-1]['position_value'] * (1.0 + period_return))
        results.loc[i, 'position_value_after_costs'] = results.loc[i, 'position_value'] - results.loc[i, 'total_costs_usd']
    
    return results, number_of_loops