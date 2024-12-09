import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime, timedelta
import math

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

def plot_multi_asset_rates(rates_df):
    """Plot supply and borrow rates over time for multiple assets"""
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
        temp_df['apy'] = temp_df[col]
        plot_data.append(temp_df[['datetime', 'asset', 'rate_type', 'apy']])
    
    # Process borrow rates
    for col in borrow_cols:
        asset = col.split('_')[0]
        temp_df = rates_df[['datetime', col]].copy()
        temp_df['asset'] = asset
        temp_df['rate_type'] = 'Variable Borrow'
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
        title='Aave Lending and Borrowing Rates Over Time by Asset'
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
        y='optimal_spread',
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

def plot_backtest_results(results_df, time_interval_hours, moving_average=7):
    """
    Plot the backtest results showing the final APY compared to base rates
    """
    results_df['final_apy_ma'] = results_df['final_apy'].rolling(int(moving_average*(24/time_interval_hours))).mean()
    # Create figure with secondary y-axis
    fig = px.line(
        results_df,
        x='datetime',
        y=['final_apy', 'final_apy_ma',  'max_supply_apy', 'optimal_spread'],
        title='Strategy Performance vs Base Rates'
    )
    
    # Update layout
    fig.update_layout(
        xaxis_title='Date',
        yaxis_title='APY (%)',
        legend_title='Metric',
        template='plotly_white',
        hovermode='x unified'
    )
    
    # Add hover template with asset information
    fig.update_traces(
        hovertemplate=(
            "Date: %{x}<br>" +
            "%{y:.2f}%<br>" +
            "<extra></extra>"
        )
    )
    
    return fig