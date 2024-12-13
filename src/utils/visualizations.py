import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime, timedelta
import math

import plotly.graph_objects as go
from plotly.subplots import make_subplots

def plot_aave_rates(rates_df):
    """Plot supply and borrow rates over time"""
    # Melt the DataFrame to get it into the right format for plotting
    plot_columns = ['supply_apy', 'variable_borrow_apy']
    long_df = rates_df.melt(
        id_vars=['datetime'], 
        value_vars=plot_columns,
        var_name='rate_type',
        value_name='apy'
    )
    
    fig = px.line(
        long_df, 
        x='datetime', 
        y='apy', 
        color='rate_type',
        title='Aave Lending and Borrowing Rates Over Time'
    )
    fig.update_layout(
        xaxis_title='Date',
        yaxis_title='APY (%)',
        legend_title='Rate Type',
        template='plotly_white'
    )
    return fig


def plot_spreads(spreads_df):
    """Plot the spreads between supply and borrow rates"""
    plot_columns = ['supply_stable_spread', 'supply_variable_spread']
    long_df = spreads_df.melt(
        id_vars=['datetime'], 
        value_vars=plot_columns,
        var_name='spread_type',
        value_name='spread'
    )
    
    fig = px.line(
        long_df, 
        x='datetime', 
        y='spread', 
        color='spread_type',
        title='Aave Rate Spreads Over Time'
    )
    fig.update_layout(
        xaxis_title='Date',
        yaxis_title='Spread (%)',
        legend_title='Spread Type',
        template='plotly_white'
    )
    return fig

def plot_multi_asset_rates(rates_df, show_ma=False, window=7):
    """
    Plot supply and borrow rates over time for multiple assets
    
    Args:
        rates_df (pd.DataFrame): DataFrame containing the rates data
        show_ma (bool): If True, show moving averages instead of raw rates
        window (int): Window size for moving average calculation in days
    """
    # Get all supply and variable borrow columns
    supply_cols = [col for col in rates_df.columns if col.endswith('supply_apy')]
    borrow_cols = [col for col in rates_df.columns if col.endswith('variable_borrow_apy')]
    
    # Melt the DataFrame for plotting
    plot_data = []
    
    # Process supply rates
    for col in supply_cols:
        asset = col.split('_')[0]
        temp_df = rates_df[['datetime', col]].copy()
        temp_df['asset'] = asset
        temp_df['rate_type'] = 'Supply'
        if show_ma:
            temp_df['apy'] = temp_df[col].rolling(window=window).mean()
        else:
            temp_df['apy'] = temp_df[col]
        plot_data.append(temp_df[['datetime', 'asset', 'rate_type', 'apy']])
    
    # Process borrow rates
    for col in borrow_cols:
        asset = col.split('_')[0]
        temp_df = rates_df[['datetime', col]].copy()
        temp_df['asset'] = asset
        temp_df['rate_type'] = 'Variable Borrow'
        if show_ma:
            temp_df['apy'] = temp_df[col].rolling(window=window).mean()
        else:
            temp_df['apy'] = temp_df[col]
        plot_data.append(temp_df[['datetime', 'asset', 'rate_type', 'apy']])
    
    # Combine all data
    long_df = pd.concat(plot_data, ignore_index=True)
    
    # Create plot
    fig = px.line(
        long_df,
        x='datetime',
        y='apy',
        color='asset',
        line_dash='rate_type',
        title=f'Aave Lending and Borrowing Rates Over Time by Asset'
    )
    
    fig.update_layout(
        xaxis_title='Date',
        yaxis_title='APY (%)',
        legend_title='Asset & Rate Type',
        template='plotly_white'
    )
    
    return fig

def plot_optimal_spread(spreads_df):
    """
    Plot the optimal spread (highest supply - lowest borrow) over time,
    along with information about which assets provided these rates
    """
    # Create the main spread plot
    fig = px.line(
        spreads_df,
        x='datetime',
        y='spread',
        title='Optimal Supply-Borrow Spread Over Time'
    )
    
    # Add hover data to show which assets are being used
    if 'best_supply_asset' in spreads_df.columns and 'best_borrow_asset' in spreads_df.columns:
        fig.update_traces(
            hovertemplate=(
                "Date: %{x}<br>" +
                "Spread: %{y:.2f}%<br>" +
                "Best Supply Asset: %{customdata[0]}<br>" +
                "Best Borrow Asset: %{customdata[1]}<br>" +
                "<extra></extra>"
            ),
            customdata=spreads_df[['best_supply_asset', 'best_borrow_asset']]
        )
    
    fig.update_layout(
        xaxis_title='Date',
        template='plotly_white',
        showlegend=True,
        # Add more descriptive y-axis title
        yaxis_title="Spread (Supply APY - Borrow APY) %"
    )
    
    return fig

def plot_cumulative_counts(results_df):
    """
    Plot cumulative rebalances and transactions
    """
    # Convert datetime to pandas datetime if it isn't already
    results_df['datetime'] = pd.to_datetime(results_df['datetime'])
    
    # Calculate cumulative sums
    cum_rebalances = results_df['rebalance_count'].cumsum()
    cum_transactions = results_df['transaction_count'].cumsum()
    
    # Create figure with secondary y-axis
    fig = px.line(
        pd.DataFrame({
            'datetime': results_df['datetime'],
            'Cumulative Rebalances': cum_rebalances,
            'Cumulative Transactions': cum_transactions
        }),
        x='datetime',
        y=['Cumulative Rebalances', 'Cumulative Transactions'],
        title='Cumulative Rebalances and Transactions'
    )
    
    fig.update_layout(
        xaxis_title='Date',
        yaxis_title='Count',
        template='plotly_white',
        hovermode='x unified'
    )
    
    return fig

def plot_backtest_results(results_df, time_interval_hours, moving_average=7):
    """
    Plot the backtest results showing APY and performance metrics
    """
    # Convert datetime to pandas datetime if it isn't already
    results_df['datetime'] = pd.to_datetime(results_df['datetime'])
    
    # Calculate period returns
    results_df['period_return'] = results_df['position_value'].pct_change()
    
    # Calculate annualized returns
    periods_per_year = (365 * 24) / time_interval_hours
    results_df['annualized_return'] = (
        (1 + results_df['period_return']).rolling(
            window=int(moving_average*(24/time_interval_hours))
        ).apply(lambda x: (np.prod(1 + x))**(periods_per_year/len(x)) - 1) * 100
    )
    
    # Create plot data
    plot_data = pd.DataFrame({
        'datetime': results_df['datetime'],
        'Annualized Return (Moving Average)': results_df['annualized_return'],
        'Current Supply Rate': results_df['current_supply_rate'],
        'Current Spread': results_df['current_spread']
    })
    
    # Create figure
    fig = px.line(
        plot_data,
        x='datetime',
        y=['Annualized Return (Moving Average)', 'Current Supply Rate', 'Current Spread'],
        title='Strategy Performance'
    )
    
    # Update layout
    fig.update_layout(
        xaxis_title='Date',
        yaxis_title='APY (%)',
        legend_title='Metric',
        template='plotly_white',
        hovermode='x unified'
    )
    
    # Add hover template
    fig.update_traces(
        hovertemplate=(
            "Date: %{x}<br>" +
            "%{y:.2f}%<br>" +
            "<extra></extra>"
        )
    )
    
    # Add position changes as markers
    rebalance_points = results_df[results_df['rebalance_count'] > 0]
    if len(rebalance_points) > 0:
        fig.add_scatter(
            x=rebalance_points['datetime'],
            y=rebalance_points['annualized_return'],
            mode='markers',
            name='Rebalance Points',
            marker=dict(size=10, symbol='x'),
            hovertemplate=(
                "Date: %{x}<br>" +
                "Rebalanced: %{customdata}<br>" +
                "<extra></extra>"
            ),
            customdata=rebalance_points['rebalance_status']
        )
    
    return fig

def create_strategy_plots(results_df, window=42):
    """
    Create interactive Plotly visualizations for strategy analysis.
    
    Args:
        results_df (pd.DataFrame): DataFrame containing strategy results
        
    Returns:
        tuple: Three Plotly figure objects (rates_fig, transactions_fig, positions_fig)
    """
    # Calculate moving average for supply rate
    rate_ma = results_df['annualized_return'].rolling(window=window, min_periods=1).mean()
    
    # 1. Rates and Spread Chart
    rates_fig = go.Figure()
    
    # Add supply rate
    rates_fig.add_trace(
        go.Scatter(
            x=results_df['datetime'],
            y=results_df['annualized_return'],
            name='Annualized Rate',
            line=dict(color='blue')
        )
    )
    
    # Add moving average
    rates_fig.add_trace(
        go.Scatter(
            x=results_df['datetime'],
            y=rate_ma,
            name='7-day MA Supply Rate',
            line=dict(color='darkblue', dash='dash')
        )
    )
    
    # Add spread
    rates_fig.add_trace(
        go.Scatter(
            x=results_df['datetime'],
            y=results_df['current_spread'],
            name='Spread',
            line=dict(color='gray')
        )
    )
    
    # Add rebalancing points
    rebalancing_mask = results_df['rebalance_count'] > 0
    rates_fig.add_trace(
        go.Scatter(
            x=results_df.loc[rebalancing_mask, 'datetime'],
            y=results_df.loc[rebalancing_mask, 'current_spread'],
            name='Rebalancing Points',
            mode='markers',
            marker=dict(color='red', size=8)
        )
    )
    
    rates_fig.update_layout(
        title='Rates and Spread Analysis',
        xaxis_title='Date',
        yaxis_title='Rate (%)',
        height=500,
        showlegend=True,
        hovermode='x unified'
    )
    
    # 2. Transaction Counts Chart
    transactions_fig = go.Figure()
    
    # Add total transactions
    transactions_fig.add_trace(
        go.Scatter(
            x=results_df['datetime'],
            y=results_df['total_transactions'],
            name='Total Transactions',
            line=dict(color='purple')
        )
    )
    
    # Add total swaps
    transactions_fig.add_trace(
        go.Scatter(
            x=results_df['datetime'],
            y=results_df['total_swaps'],
            name='Total Swaps',
            line=dict(color='orange')
        )
    )
    
    # Calculate and add cumulative rebalancings
    cumulative_rebalancings = (results_df['rebalance_count'] > 0).cumsum()
    transactions_fig.add_trace(
        go.Scatter(
            x=results_df['datetime'],
            y=cumulative_rebalancings,
            name='Total Rebalancings',
            line=dict(color='red')
        )
    )
    
    transactions_fig.update_layout(
        title='Cumulative Transaction Analysis',
        xaxis_title='Date',
        yaxis_title='Count',
        height=500,
        showlegend=True,
        hovermode='x unified'
    )
    
    # 3. Position Value Chart
    positions_fig = go.Figure()

    # Add normalized performance line (starting at 100)
    positions_fig.add_trace(
        go.Scatter(
            x=results_df['datetime'],
            y=100 * results_df['position_value'] / results_df['position_value'].iloc[0],
            name='Performance (%)',
            line=dict(color='blue')
        )
    )

    # Original traces
    positions_fig.add_trace(
        go.Scatter(
            x=results_df['datetime'],
            y=results_df['position_value'],
            name='Position Value (Before Costs)',
            line=dict(color='green')
        )
    )

    positions_fig.add_trace(
        go.Scatter(
            x=results_df['datetime'],
            y=results_df['position_value_after_costs'],
            name='Position Value (After Costs)',
            line=dict(color='red')
        )
    )

    positions_fig.add_trace(
        go.Scatter(
            x=results_df['datetime'],
            y=results_df['total_costs_usd'],
            name='Cumulative Costs',
            line=dict(color='orange', dash='dot')
        )
    )

    # Add secondary y-axis for percentage
    positions_fig.update_layout(
        title='Position Value and Costs Over Time',
        xaxis_title='Date',
        yaxis_title='% Performance',
        yaxis2=dict(
            title='Value (USD)',
            overlaying='y',
            side='right'
        ),
        height=500,
        showlegend=True,
        hovermode='x unified'
    )

    # Update first trace to use secondary y-axis
    positions_fig.data[1].update(yaxis='y2')
    positions_fig.data[2].update(yaxis='y2')
    positions_fig.data[3].update(yaxis='y2')
    
    return rates_fig, transactions_fig, positions_fig

def save_strategy_plots(results_df, output_dir='./plots'):
    """
    Create and save strategy plots as HTML files.
    
    Args:
        results_df (pd.DataFrame): DataFrame containing strategy results
        output_dir (str): Directory to save the plots
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    rates_fig, transactions_fig, positions_fig = create_strategy_plots(results_df)
    
    # Save interactive HTML files
    rates_fig.write_html(os.path.join(output_dir, 'rates_analysis.html'))
    transactions_fig.write_html(os.path.join(output_dir, 'transactions_analysis.html'))
    positions_fig.write_html(os.path.join(output_dir, 'positions_analysis.html'))
    
    # Optionally save as static images
    rates_fig.write_image(os.path.join(output_dir, 'rates_analysis.png'))
    transactions_fig.write_image(os.path.join(output_dir, 'transactions_analysis.png'))
    positions_fig.write_image(os.path.join(output_dir, 'positions_analysis.png'))