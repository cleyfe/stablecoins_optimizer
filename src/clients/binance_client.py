# Client designed for basis trade implementation.
# The basis trade is a delta-neutral strategy taking advantage from positive (or negative) funding rates

import ccxt
import pandas as pd
from typing import List, Dict, Any
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BinanceClient:
    def __init__(self, api_key: str = None, secret: str = None):
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'  # Use futures endpoints
            }
        })

    def get_current_funding_rates(self, symbols: List[str]) -> pd.DataFrame:
        """
        Fetch current funding rates for specified symbols.
        
        :param symbols: List of symbol strings (e.g., ['BTC/USDT:USDT', 'ETH/USDT:USDT'])
        :return: DataFrame with current funding rates
        """
        funding_rates = []
        for symbol in symbols:
            try:
                funding_info = self.exchange.fetchFundingRate(symbol)
                funding_rates.append({
                    'Symbol': funding_info['symbol'],
                    'Mark Price': funding_info['markPrice'],
                    'Index Price': funding_info['indexPrice'],
                    'Funding Rate': funding_info['fundingRate'],
                    'Timestamp': funding_info['timestamp'],
                    'Datetime': funding_info['datetime'],
                    'Funding Timestamp': funding_info['fundingTimestamp'],
                    'Funding Datetime': funding_info['fundingDatetime']
                })
            except Exception as e:
                logger.error(f"Error fetching funding rate for {symbol}: {e}")

        df = pd.DataFrame(funding_rates)
        if not df.empty:
            df['Annualized Funding Rate'] = df['Funding Rate'] * (3 * 365) * 100
        return df

    def get_historical_funding_rates(self, symbol: str, start_time: datetime, end_time: datetime = None) -> pd.DataFrame:
        """
        Fetch historical funding rates for a specified symbol and time range.
        
        :param symbol: Symbol string (e.g., 'BTC/USDT:USDT')
        :param start_time: Start time for historical data
        :param end_time: End time for historical data (default is current time)
        :return: DataFrame with historical funding rates
        """
        if end_time is None:
            end_time = datetime.now()

        start_timestamp = int(start_time.timestamp() * 1000)
        end_timestamp = int(end_time.timestamp() * 1000)

        try:
            funding_history = self.exchange.fetchFundingRateHistory(symbol, start_timestamp, end_timestamp)
            df = pd.DataFrame(funding_history)
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['annualized_rate'] = df['fundingRate'] * (3 * 365) * 100  # Annualized rate
            return df
        except Exception as e:
            logger.error(f"Error fetching historical funding rates for {symbol}: {e}")
            return pd.DataFrame()

    def get_ohlcv(self, symbol: str, timeframe: str = '1d', since: datetime = None, limit: int = None) -> pd.DataFrame:
        """
        Fetch OHLCV data for a specified symbol.
        
        :param symbol: Symbol string (e.g., 'BTC/USDT:USDT')
        :param timeframe: Timeframe string (e.g., '1d', '1h', '15m')
        :param since: Start time for data fetch
        :param limit: Number of candles to fetch
        :return: DataFrame with OHLCV data
        """
        try:
            since_timestamp = int(since.timestamp() * 1000) if since else None
            ohlcv = self.exchange.fetchOHLCV(symbol, timeframe, since_timestamp, limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"Error fetching OHLCV data for {symbol}: {e}")
            return pd.DataFrame()