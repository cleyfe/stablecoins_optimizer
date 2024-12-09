import pandas as pd
import numpy as np
import plotly.express as px
import math

def plot_time_series(time_series_df):
    long_df = time_series_df.melt(id_vars=['timestamp'], var_name='metric', value_name='value')
    fig = px.line(long_df, x='timestamp', y='value', color='metric', title='APY Base and Borrow Rates Over Time')
    fig.update_layout(xaxis_title='Timestamp', yaxis_title='APY', legend_title='Metric')
    return fig

def calculate_chain_differences(time_series_df):
    pol_df = time_series_df.filter(regex='timestamp|pol_')
    arb_df = time_series_df.filter(regex='timestamp|arb_')

    pol_diff = []
    arb_diff = []

    for date, data in pol_df.groupby('timestamp'):
        max_apyBase = data.filter(like='apyBase').max(axis=1).values[0]
        min_apyBaseBorrow = data.filter(like='apyBaseBorrow').min(axis=1).values[0]
        pol_diff.append({'timestamp': date, 'diff': max_apyBase - min_apyBaseBorrow})

    for date, data in arb_df.groupby('timestamp'):
        max_apyBase = data.filter(like='apyBase').max(axis=1).values[0]
        min_apyBaseBorrow = data.filter(like='apyBaseBorrow').min(axis=1).values[0]
        arb_diff.append({'timestamp': date, 'diff': max_apyBase - min_apyBaseBorrow})

    pol_diff_df = pd.DataFrame(pol_diff)
    arb_diff_df = pd.DataFrame(arb_diff)

    diff_df = pd.merge(pol_diff_df, arb_diff_df, on='timestamp', suffixes=('_pol', '_arb'))
    return diff_df

def plot_chain_differences(diff_df):
    fig = px.line(diff_df, x='timestamp', y=['diff_pol', 'diff_arb'], title='Difference Between Max APY Base and Min APY Base Borrow Over Time')
    fig.update_layout(xaxis_title='Timestamp', yaxis_title='Difference (Max APY Base - Min APY Base Borrow)', legend_title='Chain', template='plotly_white')
    return fig

def calculate_overall_differences(time_series_df):
    overall_diff = []
    max_apyBase_series = []

    for date, data in time_series_df.groupby('timestamp'):
        max_apyBase = data.filter(like='apyBase').max(axis=1).values[0]
        min_apyBaseBorrow = data.filter(like='apyBaseBorrow').min(axis=1).values[0]
        overall_diff.append({'timestamp': date, 'diff': max_apyBase - min_apyBaseBorrow})
        max_apyBase_series.append({'timestamp': date, 'max_apyBase': max_apyBase})

    overall_diff_df = pd.DataFrame(overall_diff)
    max_apyBase_df = pd.DataFrame(max_apyBase_series)

    merged_df = pd.merge(overall_diff_df, max_apyBase_df, on='timestamp')
    return merged_df

def plot_overall_differences(merged_df):
    fig = px.line(merged_df, x='timestamp', y=['diff', 'max_apyBase'], title='Difference Between Max APY Base and Min APY Base Borrow & Max APY Base Over Time (Combined Chains)')
    fig.update_layout(xaxis_title='Timestamp', yaxis_title='Values', legend_title='Metric', template='plotly_white')
    return fig

def backtest_strategy(time_series_df, LTV=0.9, initial_collateral=100, stop_condition=0.8, asset_filter='arb'):
    """
    Backtests a leveraged yield farming strategy using Aave lending pools.
    The strategy involves depositing collateral and borrowing against it multiple times
    to maximize yield, implementing a recursive borrowing pattern until reaching
    a specified stop condition.

    Args:
        time_series_df (pd.DataFrame): Time series DataFrame containing APY data.
            Must have columns: 'timestamp' and APY columns with patterns 'apyBase' and 'apyBaseBorrow'.
            APY columns should follow pattern: {asset}_apyBase and {asset}_apyBaseBorrow
        LTV (float, optional): Loan-to-Value ratio, representing the maximum borrowing power 
            against collateral. Defaults to 0.9 (90%).
        initial_collateral (float, optional): Initial amount of collateral deposited.
            Defaults to 100.
        stop_condition (float, optional): The minimum LTV ratio to stop recursive borrowing.
            Defaults to 0.8 (80%).
        asset_filter (str, optional): Filter for specific assets. Options:
            'pol': Filter for Polygon-related assets
            'arb': Filter for Arbitrum-related assets
            Any other value: No filtering applied
            Defaults to 'arb'.

    Returns:
        tuple: Contains three elements:
            - merged_df (pd.DataFrame): Complete analysis with all metrics
                (spreads, max base APY, final APY)
            - final_apy_df (pd.DataFrame): Just timestamp and final APY after leverage
            - number_of_loops (int): Number of borrowing iterations performed
    """
    number_of_loops = math.ceil(math.log(stop_condition) / math.log(LTV))
    total_collateral = initial_collateral * ((1 - LTV**(number_of_loops + 1)) / (1 - LTV))
    leverage = total_collateral / initial_collateral

    if asset_filter == 'pol':
        filtered_df = time_series_df.filter(regex='timestamp|pol_')
    elif asset_filter == 'arb':
        filtered_df = time_series_df.filter(regex='timestamp|arb_')
    else:
        filtered_df = time_series_df

    overall_diff = []
    max_apyBase_series = []
    final_apy_series = []

    for date, data in filtered_df.groupby('timestamp'):
        max_apyBase = data.filter(like='apyBase').max(axis=1).values[0]
        min_apyBaseBorrow = data.filter(like='apyBaseBorrow').min(axis=1).values[0]
        spread = max_apyBase - min_apyBaseBorrow
        
        overall_diff.append({'timestamp': date, 'diff': spread})
        max_apyBase_series.append({'timestamp': date, 'max_apyBase': max_apyBase})
        
        final_apy = (max_apyBase * initial_collateral + (total_collateral - initial_collateral) * spread) / initial_collateral
        final_apy_series.append({'timestamp': date, 'final_apy': final_apy})

    overall_diff_df = pd.DataFrame(overall_diff)
    max_apyBase_df = pd.DataFrame(max_apyBase_series)
    final_apy_df = pd.DataFrame(final_apy_series)

    merged_df = pd.merge(overall_diff_df, max_apyBase_df, on='timestamp')
    merged_df = pd.merge(merged_df, final_apy_df, on='timestamp')

    return merged_df, final_apy_df, number_of_loops

def plot_backtest_results(merged_df, asset_filter):
    fig = px.line(merged_df, x='timestamp', y=['diff', 'max_apyBase', 'final_apy'], title=f'Difference between supply and borrow (Filtered by {asset_filter.capitalize()} chains)')
    fig.update_layout(xaxis_title='Timestamp', yaxis_title='Values', legend_title='Metric', template='plotly_white')
    return fig

def calculate_compounded_balance(final_apy_df, initial_collateral):
    daily_apy = final_apy_df.dropna().assign(final_apy=lambda x: ((1 + x['final_apy']/100)**(1/365)-1))
    daily_apy['growth_factor'] = 1 + daily_apy['final_apy']
    daily_apy['compounded_balance'] = initial_collateral * daily_apy['growth_factor'].cumprod()
    return daily_apy

def plot_compounded_balance(daily_apy):
    fig = px.line(daily_apy, x='timestamp', y='compounded_balance', title='Compounded Balance Over Time', labels={'compounded_balance': 'Compounded Balance ($)', 'timestamp': 'Date'})
    fig.update_layout(
        xaxis_title='Date', 
        yaxis_title='Compounded Balance ($)', 
        legend_title='Metric',
        template='plotly_white'
    )
    return fig

def print_strategy_stats(final_apy_df, number_of_loops, initial_collateral, frq=1):
    print("--------Average APY since Sep 2022--------")
    print(f"{round(final_apy_df.mean()['final_apy'], 2)}%")

    print("\n--------Gas cost for $100k capital--------")
    print(f"{frq}h rebalancing")
    cost_per_rebalancing = 4 * number_of_loops
    print(f"{cost_per_rebalancing} txs on average per rebalancing ({number_of_loops} loops)")
    print(f"Number of tx per day: {cost_per_rebalancing*24/frq}")
    cost_per_tx = 0.05
    print(f"cost per tx (conservative for a L2): ${cost_per_tx}")
    daily_gas_cost = cost_per_tx * cost_per_rebalancing * 24/frq
    print(f"Daily gas cost: ${daily_gas_cost:.2f}")
    annual_gas_cost = 365 * daily_gas_cost
    print(f"Annual gas cost: ${annual_gas_cost:.2f}")
    print(f"With initial_collateral: {round((annual_gas_cost/initial_collateral)*10000, 2)} bps")    
    print(f"With $1M capital: {round((annual_gas_cost/1000000)*10000, 2)} bps")