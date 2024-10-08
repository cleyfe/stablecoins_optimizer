# Client designed for basis trade implementation.
# The basis trade is a delta-neutral strategy taking advantage from positive (or negative) funding rates

import ccxt
import pandas as pd
from typing import List, Dict, Any
from decimal import Decimal, InvalidOperation
import traceback
from datetime import datetime, timedelta
import logging
import time
from websocket import WebSocketApp
import json
import threading
import hmac
import hashlib
import requests
import urllib.parse


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, leverage: int = 1, verbose: bool = False):
        self.futures_exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        self.margin_exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'margin'}
        })

        self.leverage = leverage
        self.verbose = verbose
        self.latest_prices = {}
        # Preload markets
        self.futures_markets = self.futures_exchange.load_markets()
        self.margin_markets = self.margin_exchange.load_markets()
        #self.margin_exchange.verbose = True
        #self.futures_exchange.verbose = True

        if self.verbose:
            logger.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.WARNING)

    # METHODS
    def fetch_accounts(self) -> List[Dict]:
        try:
            accounts = self.margin_exchange.fetchAccounts()
            logger.info(f"Fetched account information: {accounts}")
            return accounts
        except Exception as e:
            logger.error(f"Error fetching account information: {str(e)}")
            return []

    def get_current_funding_rates(self, symbols: List[str]) -> pd.DataFrame:
        """
        Fetch current funding rates for specified symbols.
        
        :param symbols: List of symbol strings (e.g., ['BTC/USDT:USDT', 'ETH/USDT:USDT'])
        :return: DataFrame with current funding rates
        """
        funding_rates = []
        for symbol in symbols:
            try:
                funding_info = self.futures_exchange.fetchFundingRate(symbol)
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


    def get_ohlcv(self, symbol: str, timeframe: str = '1d', since: datetime = None, limit: int = None, is_futures: bool = False) -> pd.DataFrame:
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
            exchange = self.futures_exchange if is_futures else self.spot_exchange
            ohlcv = exchange.fetchOHLCV(symbol, timeframe, since_timestamp, limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"Error fetching OHLCV data for {symbol}: {e}")
            return pd.DataFrame()


    def fetch_spot_position(self, symbol: str, time_window: int = 24) -> Dict[str, Any]:
        """
        Fetch detailed spot position for a given symbol, considering only recent trades.
        
        :param symbol: Symbol string (e.g., 'BTC/USDT')
        :param time_window: Time window in hours to consider for recent trades (default: 24)
        :return: Dictionary containing spot position details
        """
        try:
            balance = self.spot_exchange.fetch_balance()
            base_currency = symbol.split('/')[0]
            quote_currency = symbol.split('/')[1]

            # Get the amount of the base currency
            amount = balance['total'].get(base_currency, 0)

            # Calculate the start time for fetching trades
            start_time = int((datetime.now() - timedelta(hours=time_window)).timestamp() * 1000)

            # Fetch recent trades
            trades = self.spot_exchange.fetch_my_trades(symbol, since=start_time)

            if trades:
                # Sort trades by timestamp in descending order
                trades.sort(key=lambda x: x['timestamp'], reverse=True)
                
                # Get the most recent trade
                last_trade = trades[0]
                entry_price = last_trade['price']
                trade_amount = last_trade['amount']
                trade_side = last_trade['side']
            else:
                entry_price = None
                trade_amount = 0
                trade_side = None

            # Fetch current market price
            ticker = self.spot_exchange.fetch_ticker(symbol)
            current_price = ticker['last']

            return {
                'symbol': symbol,
                'amount': amount,
                'entry_price': entry_price,
                'current_price': current_price,
                'pnl': (current_price - entry_price) * amount if entry_price else None,
                'pnl_percentage': ((current_price - entry_price) / entry_price) * 100 if entry_price else None,
                'value_base': amount,
                'value_quote': amount * current_price,
                'last_trade_amount': trade_amount,
                'last_trade_side': trade_side,
                'last_trade_time': datetime.fromtimestamp(last_trade['timestamp'] / 1000) if trades else None
            }
        except Exception as e:
            logger.error(f"Error fetching spot position for {symbol}: {e}")
            return None


    def fetch_futures_position(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch detailed futures position for a given symbol.
        
        :param symbol: Symbol string (e.g., 'BTC/USDT')
        :return: Dictionary containing futures position details
        """
        try:
            positions = self.futures_exchange.fetch_positions([symbol])
            if positions:
                position = positions[0]
                return {
                    'symbol': position['symbol'],
                    'amount': position['contracts'],
                    'entry_price': position['entryPrice'],
                    'current_price': position['markPrice'],
                    'pnl': position['unrealizedPnl'],
                    'pnl_percentage': position['percentage'],
                    'leverage': position['leverage'],
                    'side': 'long' if position['contracts'] > 0 else 'short',
                    'liquidation_price': position['liquidationPrice'],
                }
            else:
                return None
        except Exception as e:
            logger.error(f"Error fetching futures position for {symbol}: {e}")
            return None

    def fetch_futures_prices(self, futures_symbols: List[str]) -> Dict[str, float]:
        """
        Fetch the latest futures prices for the given symbols.
        """
        prices = {}
        for symbol in futures_symbols:
            ticker = self.futures_exchange.fetch_ticker(symbol)
            prices[symbol] = ticker['last']
        return prices


    def fetch_real_time_prices(self, symbol: str) -> Dict[str, float]:
        """
        Fetch real-time prices for both spot and futures markets.
        
        :param symbol: Symbol string (e.g., 'BTC/USDT')
        :return: Dictionary with spot and futures prices
        """
        try:
            spot_ticker = self.spot_exchange.fetch_ticker(symbol)
            future_ticker = self.futures_exchange.fetch_ticker(symbol)
            
            return {
                'spot': spot_ticker['last'],
                'future': future_ticker['last']
            }
        except Exception as e:
            logger.error(f"Error fetching real-time prices for {symbol}: {e}")
            return {'spot': None, 'future': None}
        

    def fetch_minute_spot_prices(self, symbol: str, limit: int = 1000) -> pd.DataFrame:
        """
        Fetch spot prices at 1-minute intervals for a given symbol.
        
        :param symbol: Symbol string (e.g., 'BTC/USDT')
        :param limit: Number of 1-minute candles to fetch (max 1000 for Binance)
        :return: DataFrame with minute-level spot prices
        """
        self.exchange.options['defaultType'] = 'spot'
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='1m', limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"Error fetching minute-level spot prices for {symbol}: {e}")
            return pd.DataFrame()

    def fetch_minute_futures_prices(self, symbol: str, limit: int = 1000) -> pd.DataFrame:
        """
        Fetch futures prices at 1-minute intervals for a given symbol.
        
        :param symbol: Symbol string (e.g., 'BTC/USDT')
        :param limit: Number of 1-minute candles to fetch (max 1000 for Binance)
        :return: DataFrame with minute-level futures prices
        """
        self.exchange.options['defaultType'] = 'future'
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='1m', limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"Error fetching minute-level futures prices for {symbol}: {e}")
            return pd.DataFrame()

    def get_cross_margin_balance(self) -> dict:
        try:
            cross_margin_account = self.margin_exchange.fetch_balance({'type': 'margin'})
            #logger.info(f"Cross margin account balance: {cross_margin_account}")
            return cross_margin_account
        except Exception as e:
            logger.error(f"Error fetching cross margin balance: {str(e)}")
            return {}

    def fetch_borrow_rate(self, code: str) -> float:
        try:
            borrow_rate = self.margin_exchange.fetchCrossBorrowRate(code)
            logger.info(f"Borrow rate for {code}: {borrow_rate}")
            return borrow_rate['rate']
        except Exception as e:
            logger.error(f"Error fetching borrow rate for {code}: {str(e)}")
            return None

    def get_margin_balance(self) -> float:
        try:
            cross_margin_account = self.margin_exchange.fetch_balance({'type': 'margin'})
            usdt_balance = cross_margin_account['free']['USDT']
            logger.info(f"Current cross margin USDT balance: {usdt_balance}")
            return usdt_balance
        except Exception as e:
            logger.error(f"Error fetching cross margin balance: {str(e)}")
            return 0.0

    def calculate_basis_spread(self, symbol: str, limit: int = 1000) -> pd.DataFrame:
        """
        Calculate the basis spread between spot and futures prices.
        
        :param symbol: Symbol string (e.g., 'BTC/USDT')
        :param limit: Number of 1-minute candles to fetch (max 1000 for Binance)
        :return: DataFrame with basis spread calculations
        """
        spot_df = self.fetch_minute_spot_prices(symbol, limit)
        futures_df = self.fetch_minute_futures_prices(symbol, limit)
        
        if spot_df.empty or futures_df.empty:
            logger.error("Failed to fetch either spot or futures data.")
            return pd.DataFrame()
        
        # Merge dataframes on timestamp
        merged_df = pd.merge(spot_df, futures_df, on='timestamp', suffixes=('_spot', '_futures'))
        
        # Calculate basis spread
        merged_df['basis_spread'] = (merged_df['close_futures'] - merged_df['close_spot']) / merged_df['close_spot']
        merged_df['basis_spread_percentage'] = merged_df['basis_spread'] * 100
        
        return merged_df  

    def start_websocket_streams(self, symbols: List[str]):
        """
        Start WebSocket streams for both margin and futures markets.
        """
        margin_streams = [f"{s.lower()}@ticker" for s in symbols]
        futures_streams = [f"{s.lower()}@markPrice" for s in symbols]
        
        margin_stream_url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(margin_streams)}"
        futures_stream_url = f"wss://fstream.binance.com/stream?streams={'/'.join(futures_streams)}"

        self.ws_margin = WebSocketApp(
            margin_stream_url,
            on_message=self.on_message_margin,
            on_error=self.on_error,
            on_close=self.on_close
        )

        self.ws_futures = WebSocketApp(
            futures_stream_url,
            on_message=self.on_message_futures,
            on_error=self.on_error,
            on_close=self.on_close
        )

        self.ws_margin_thread = threading.Thread(target=self.ws_margin.run_forever)
        self.ws_futures_thread = threading.Thread(target=self.ws_futures.run_forever)

        self.ws_margin_thread.start()
        self.ws_futures_thread.start()

    def stop_websocket_streams(self):
        """
        Stop WebSocket streams for both margin and futures markets.
        """
        if self.ws_margin:
            self.ws_margin.close()
        if self.ws_futures:
            self.ws_futures.close()
        
        if self.ws_margin_thread:
            self.ws_margin_thread.join()
        if self.ws_futures_thread:
            self.ws_futures_thread.join()
        
        logger.info("WebSocket streams stopped.")

    def on_message_margin(self, ws, message):
        data = json.loads(message)
        symbol = data['data']['s']
        price = float(data['data']['c'])
        self.latest_prices[f"{symbol}_margin"] = price
        logger.debug(f"Margin {symbol}: {price}")

    def on_message_futures(self, ws, message):
        data = json.loads(message)
        symbol = data['data']['s']
        price = float(data['data']['p'])
        self.latest_prices[f"{symbol}_futures"] = price
        logger.debug(f"Futures {symbol}: {price}")

    def on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        logger.info("WebSocket connection closed")

    def monitor_basis_spreads(self, symbols: List[str], entry_threshold: float = 0.004, exit_threshold: float = 0.0005, 
                              interval: int = 5, update_interval: int = 300, log_all_prices: bool = False,
                              execute_trades: bool = False, trade_amount_usd: float = 0.0, slippage: float = 0.0005):
        """
        Monitor basis spreads for multiple symbols, log potential entry and exit points, and optionally execute trades.
        
        :param symbols: List of symbol strings (e.g., ['LINKUSDT', 'ETHUSDT'])
        :param entry_threshold: Threshold for flagging entry points (futures different from margin)
        :param exit_threshold: Threshold for flagging exit points (futures different from margin)
        :param interval: Checking interval in seconds (default 5 seconds)
        :param update_interval: Interval for printing current spreads (default 300 seconds / 5 minutes)
        :param log_all_prices: If True, log all price fetches; if False, only log regular updates
        :param execute_trades: If True, execute trades when opportunities are identified (default False)
        :param trade_amount_usd: USD amount to trade when executing trades (required if execute_trades is True)
        """
        positions = {symbol: {'spread': None, 'direction': None} for symbol in symbols}  # To keep track of open positions
        last_update_time = time.time()
        check_count = 0

        if execute_trades and trade_amount_usd <= 0:
            raise ValueError("trade_amount_usd must be positive when execute_trades is True")

        logger.info(f"Starting to monitor basis spreads for {symbols}")
        logger.info(f"Settings: entry_threshold={entry_threshold}, exit_threshold={exit_threshold}, "
                    f"interval={interval}, update_interval={update_interval}, log_all_prices={log_all_prices}, "
                    f"execute_trades={execute_trades}, trade_amount_usd={trade_amount_usd}")

        while True:
            current_time = time.time()
            
            # Print current spreads every update_interval
            if current_time - last_update_time >= update_interval:
                logger.info(f"\nCurrent spreads at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}:")
                for symbol in symbols:
                    spread_info = self.get_latest_basis_spread(symbol)
                    if spread_info:
                        logger.info(f"{symbol}: {spread_info['basis_spread_percentage']:.4f}%")
                last_update_time = current_time

            for symbol in symbols:
                spread_info = self.get_latest_basis_spread(symbol)
                if spread_info:
                    basis_spread_percentage = spread_info['basis_spread_percentage']

                    if log_all_prices:
                        logger.info(f"{symbol} - Margin: {spread_info['margin_price']:.8f}, "
                                    f"Futures: {spread_info['futures_price']:.8f}, "
                                    f"Spread %: {basis_spread_percentage:.8f}%")

                    # Entries and Exits
                    # Entry logic
                    if abs(basis_spread_percentage) > (entry_threshold * 100) and positions[symbol]['spread'] is None:
                        logger.info(f"\nENTRY POINT for {symbol}: "
                                    f"{'Futures much higher than margin' if basis_spread_percentage > 0 else 'Margin much higher than futures'}. "
                                    f"Spread: {spread_info}")
                        if execute_trades:
                            success = self.execute_trade(symbol, trade_amount_usd, spread_info, is_entry=True, slippage=slippage)
                            if success:
                                positions[symbol]['spread'] = basis_spread_percentage
                                positions[symbol]['direction'] = 'long_futures' if basis_spread_percentage > 0 else 'short_futures'
                        else:
                            positions[symbol]['spread'] = basis_spread_percentage
                            positions[symbol]['direction'] = 'long_futures' if basis_spread_percentage > 0 else 'short_futures'
                    
                    # Exit logic
                    elif positions[symbol]['spread'] is not None:
                        if (positions[symbol]['direction'] == 'long_futures' and basis_spread_percentage < (exit_threshold * 100)) or \
                            (positions[symbol]['direction'] == 'short_futures' and basis_spread_percentage > -(exit_threshold * 100)):
                                initial_spread = positions[symbol]['spread']
                                profit = abs(initial_spread - basis_spread_percentage)
                                logger.info(f"\nEXIT POINT for {symbol}: Spread narrowed. Spread: {spread_info}")
                                logger.info(f"Potential profit for {symbol}: {profit:.4f}%")
                
                                if execute_trades:
                                    success = self.execute_trade(symbol, trade_amount_usd, spread_info, is_entry=False, 
                                                                current_position=positions[symbol]['direction'], slippage=slippage)
                                    if success:
                                        positions[symbol]['spread'] = None
                                        positions[symbol]['direction'] = None
                                    else:
                                        pass
       
            if not log_all_prices:
                check_count += 1
                if check_count % 2 == 0:
                    print("Still checking...", end="\r")
                else:
                    print("Checking...     ", end="\r")

            time.sleep(interval)

    def execute_trade(self, symbol: str, amount_usd: float, spread_info: Dict, is_entry: bool = True, 
                        current_position: str = None, slippage: float = 0.0005, retry_delay: int = 5, max_retries: int = 3):
        borrowed_amount = 0
        for attempt in range(max_retries):
            try:
                margin_symbol = self.margin_exchange.fetch_ticker(symbol)['symbol']
                futures_symbol = self.futures_exchange.fetch_ticker(symbol)['symbol']
                base_asset = symbol.split('USDT')[0] if 'USDT' in symbol else symbol.split('USDC')[0]

                # Check available balance
                margin_balance = self.get_cross_margin_balance()
                futures_balance = self.futures_exchange.fetch_balance()['USDT']['free']

                logger.info(f"Attempting trade for {symbol}. Amount: {amount_usd} USDT")
                logger.info(f"Available balance - Cross Margin: {margin_balance['USDT']['free']} USDT, Futures: {futures_balance} USDT")

                # Fetch latest prices
                margin_price = spread_info['margin_price']
                futures_price = spread_info['futures_price']

                if is_entry:
                    quantity = self.margin_exchange.amount_to_precision(margin_symbol, amount_usd / ((margin_price + futures_price) / 2))                
                    logger.info(f"Trade quantity: {quantity}")
                else:
                    # For exit trades, fetch both margin and futures positions
                    margin_positions = self.margin_exchange.fetch_positions([margin_symbol])
                    futures_positions = self.futures_exchange.fetch_positions([futures_symbol])

                    margin_quantity = abs(float(margin_positions[0]['amount'])) if margin_positions else 0
                    futures_quantity = abs(float(futures_positions[0]['amount'])) if futures_positions else 0

                    if margin_quantity == 0 or futures_quantity == 0:
                        logger.warning(f"No open position found for {symbol}. Skipping trade.")
                        return False

                    logger.info(f"Trade quantities - Margin: {margin_quantity}, Futures: {futures_quantity}")

                margin_limit_price = margin_price * (1 + slippage if futures_price > margin_price else 1 - slippage)
                futures_limit_price = futures_price * (1 - slippage if futures_price > margin_price else 1 + slippage)

                margin_limit_price = self.margin_exchange.price_to_precision(margin_symbol, margin_limit_price)
                futures_limit_price = self.futures_exchange.price_to_precision(futures_symbol, futures_limit_price)

                logger.info(f"Limit prices - Margin: {margin_limit_price}, Futures: {futures_limit_price}")

                # Set leverage for futures trade
                self.futures_exchange.set_leverage(self.leverage, futures_symbol)

                order_type = 'limit'
                if is_entry:
                    if margin_price > futures_price and borrowed_amount == 0:
                        # Borrow asset for short selling on margin
                        borrow_amount = float(quantity)
                        logger.info(f"Attempting to borrow {borrow_amount} {base_asset} for short selling")
                        if not self.direct_margin_transaction(base_asset, borrow_amount, 'borrow'):
                            logger.error(f"Failed to borrow {borrow_amount} {base_asset} for short selling. Skipping trade.")
                            return False
                        borrowed_amount = borrow_amount
                        margin_order = self.margin_exchange.create_order(margin_symbol, order_type, 'sell', quantity, margin_limit_price, {'marginMode': 'cross'})                        
                        futures_order = self.futures_exchange.create_order(futures_symbol, order_type, 'buy', quantity, futures_limit_price)
                    else:
                        margin_order = self.margin_exchange.create_order(margin_symbol, order_type, 'buy', margin_quantity, margin_limit_price, {'marginMode': 'cross'})
                        futures_order = self.futures_exchange.create_order(futures_symbol, order_type, 'sell', futures_quantity, futures_limit_price)
                else:
                    # Exit trade logic
                    if current_position == 'long_futures':
                        margin_order = self.margin_exchange.create_order(margin_symbol, order_type, 'buy', margin_quantity, margin_limit_price, {'marginMode': 'cross'})
                        futures_order = self.futures_exchange.create_order(futures_symbol, order_type, 'sell', futures_quantity, futures_limit_price)
                        # Repay borrowed asset if any
                        if borrowed_amount > 0:
                            self.direct_margin_transaction(base_asset, borrowed_amount, 'repay')
                            borrowed_amount = 0
                    elif current_position == 'short_futures':
                        margin_order = self.margin_exchange.create_order(margin_symbol, order_type, 'sell', margin_quantity, margin_limit_price, {'marginMode': 'cross'})
                        futures_order = self.futures_exchange.create_order(futures_symbol, order_type, 'buy', futures_quantity, futures_limit_price)

                logger.info(f"Placed {'entry' if is_entry else 'exit'} orders - Margin: {margin_order}, Futures: {futures_order}")

                # Check if both orders are filled (wait for up to 10 seconds)
                start_time = time.time()
                while time.time() - start_time < 10:
                    margin_order = self.margin_exchange.fetch_order(margin_order['id'], margin_symbol)
                    futures_order = self.futures_exchange.fetch_order(futures_order['id'], futures_symbol)

                    if margin_order['status'] == 'closed' and futures_order['status'] == 'closed':
                        logger.info(f"Basis trade {'entry' if is_entry else 'exit'} executed successfully for {symbol}")
                        return True

                    if margin_order['status'] == 'canceled' or futures_order['status'] == 'canceled':
                        logger.warning(f"One of the orders was canceled. Margin: {margin_order['status']}, Futures: {futures_order['status']}")
                        break

                    time.sleep(0.5)

                # If orders are not filled after 10 seconds, cancel them and handle partial fills
                margin_filled = float(margin_order['filled'])
                futures_filled = float(futures_order['filled'])

                if margin_order['status'] not in ['closed', 'canceled']:
                    self.margin_exchange.cancel_order(margin_order['id'], margin_symbol)
                if futures_order['status'] not in ['closed', 'canceled']:
                    self.futures_exchange.cancel_order(futures_order['id'], futures_symbol)

                logger.warning(f"Orders not fully filled within timeout. Margin filled: {margin_filled}, Futures filled: {futures_filled}")

                # Handle partial fills
                if margin_filled > 0 or futures_filled > 0:
                    logger.info("Handling partial fills...")
                    if margin_filled > futures_filled:
                        # Close excess margin position
                        excess = margin_filled - futures_filled
                        self.close_partial_position(margin_symbol, 'margin', excess, margin_order['side'] == 'buy')
                    elif futures_filled > margin_filled:
                        # Close excess futures position
                        excess = futures_filled - margin_filled
                        self.close_partial_position(futures_symbol, 'futures', excess, futures_order['side'] == 'buy')

                # If entry trade failed and we borrowed, repay the borrowed amount
                if is_entry and borrowed_amount > 0:
                    repay_amount = borrowed_amount if margin_filled == 0 else borrowed_amount - margin_filled
                    if repay_amount > 0:
                        self.direct_margin_transaction(base_asset, repay_amount, 'repay')
                    borrowed_amount = 0

                return margin_filled > 0 and futures_filled > 0

            except Exception as e:
                logger.error(f"Error executing basis trade for {symbol}: {str(e)}")
                logger.error(f"Error details: {type(e).__name__}, {str(e)}")
                # If we borrowed and an exception occurred, make sure to repay
                if borrowed_amount > 0:
                    self.direct_margin_transaction(base_asset, borrowed_amount, 'repay')
                    borrowed_amount = 0

            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)

        logger.error(f"Failed to execute basis trade for {symbol} after {max_retries} attempts")
        return False

    def close_partial_position(self, symbol: str, market_type: str, amount: float, is_long: bool):
        try:
            order_type = 'market'
            side = 'sell' if is_long else 'buy'
            
            if market_type == 'margin':
                order = self.margin_exchange.create_order(symbol, order_type, side, amount, None, {'marginMode': 'cross'})
            else:  # futures
                order = self.futures_exchange.create_order(symbol, order_type, side, amount)
            
            logger.info(f"Closed partial {market_type} position: {order}")
        except Exception as e:
            logger.error(f"Error closing partial {market_type} position: {str(e)}")

    def get_latest_basis_spread(self, symbol: str) -> Dict:
        """
        Get the latest basis spread for a given symbol.
        """
        try:
            margin_price = self.latest_prices.get(f"{symbol}_margin")
            futures_price = self.latest_prices.get(f"{symbol}_futures")

            if margin_price is None or futures_price is None:
                logger.warning(f"Latest prices not available for {symbol}. Fetching from API.")
                margin_ticker = self.margin_exchange.fetch_ticker(symbol)
                futures_ticker = self.futures_exchange.fetch_ticker(symbol)
                margin_price = margin_ticker['last']
                futures_price = futures_ticker['last']

            basis_spread = futures_price - margin_price
            basis_spread_percentage = (basis_spread / margin_price) * 100
            
            return {
                'margin_price': margin_price,
                'futures_price': futures_price,
                'basis_spread': basis_spread,
                'basis_spread_percentage': basis_spread_percentage
            }
        except Exception as e:
            logger.error(f"Error fetching basis spread for {symbol}: {str(e)}")
            return None

    def place_order(self, symbol: str, side: str, amount: float, price: float, use_margin: bool):
        """
        Place an order on either the spot or margin market.
        
        :param symbol: Trading symbol (e.g., 'BTCUSDT')
        :param side: 'buy' or 'sell'
        :param amount: Amount to trade
        :param price: Limit price
        :param use_margin: If True, use margin trading instead of spot
        :return: Order information
        """
        if use_margin:
            return self.margin_exchange.create_order(symbol, 'limit', side, amount, price)
        else:
            return self.spot_exchange.create_order(symbol, 'limit', side, amount, price)

    def check_order_status(self, order_id: str, symbol: str, use_margin: bool):
        """
        Check the status of an order on either the spot or margin market.
        
        :param order_id: ID of the order to check
        :param symbol: Trading symbol (e.g., 'BTCUSDT')
        :param use_margin: If True, check on margin market instead of spot
        :return: Order status
        """
        if use_margin:
            return self.margin_exchange.fetch_order(order_id, symbol)['status']
        else:
            return self.spot_exchange.fetch_order(order_id, symbol)['status']

    def cancel_order(self, order_id: str, symbol: str, use_margin: bool):
        """
        Cancel an order on either the spot or margin market.
        
        :param order_id: ID of the order to cancel
        :param symbol: Trading symbol (e.g., 'BTCUSDT')
        :param use_margin: If True, cancel on margin market instead of spot
        """
        if use_margin:
            self.margin_exchange.cancel_order(order_id, symbol)
        else:
            self.spot_exchange.cancel_order(order_id, symbol)

    def direct_margin_transaction(self, asset: str, amount: float, direction: str):
        try:
            base_url = "https://api.binance.com"
            endpoint = "/sapi/v1/margin/borrow-repay"
            timestamp = int(time.time() * 1000)
            
            # Prepare parameters
            params = {
                'asset': asset,
                'amount': str(amount),
                'isIsolated': 'FALSE',
                'type': direction.upper(),
                'timestamp': str(timestamp)
            }

            # Create the query string
            query_string = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in sorted(params.items())])

            # Get the API key and secret
            api_key = self.margin_exchange.apiKey
            api_secret = self.margin_exchange.secret

            # Create the signature
            signature = hmac.new(api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

            # Add the signature to the query string
            full_url = f"{base_url}{endpoint}?{query_string}&signature={signature}"

            # Prepare headers
            headers = {
                'X-MBX-APIKEY': api_key
            }

            # Make the request
            response = requests.post(full_url, headers=headers)

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Direct margin {direction} response: {result}")
                if 'tranId' in result:
                    logger.info(f"{direction} transaction ID: {result['tranId']}")
                    return True
                else:
                    logger.warning("Unexpected response format. No transaction ID found.")
                    return False
            else:
                logger.error(f"Error in direct margin {direction}: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error in direct margin {direction}: {str(e)}")
            return False
     
    def check_api_permissions(self):
        try:
            response = self.margin_exchange.private_get_account()
            permissions = response.get('permissions', [])
            logger.info(f"API key permissions: {permissions}")
            if 'MARGIN' in permissions:
                logger.info("API key has margin trading permission")
            else:
                logger.warning("API key does not have margin trading permission")
        except Exception as e:
            logger.error(f"Error checking API permissions: {str(e)}")    


    def execute_triangular_arbitrage(self, symbols: List[str], trades: List[str], trade_amount_usd: float, 
                                    prices: Dict[str, Decimal], max_slippage: float) -> bool:
        """
        Execute a triangular arbitrage trade using margin markets, starting with USD.
        """
        try:
            current_amount_usd = Decimal(str(trade_amount_usd))
            borrowed_amount = 0
            base_asset = None

            for i, (symbol, side) in enumerate(zip(symbols, trades)):
                price = prices[symbol]
                
                if side == 'buy':
                    # Convert USD to asset quantity
                    quantity = float(current_amount_usd / price)
                else:
                    # For sell, use the current amount directly (it's already in the asset quantity)
                    quantity = float(current_amount_usd)

                # Apply leverage to the quantity
                leveraged_quantity = quantity * self.leverage if i == 0 else quantity
                
                # Use exchange's precision
                precise_quantity = self.margin_exchange.amount_to_precision(symbol, leveraged_quantity)

                # Calculate limit price
                limit_price = float(price) * (1 + max_slippage if side == 'buy' else 1 - max_slippage)
                limit_price = self.margin_exchange.price_to_precision(symbol, limit_price)

                logger.info(f"Executing trade: Symbol={symbol}, Side={side}, Quantity={precise_quantity}, Limit Price={limit_price}")

                # Check if we need to borrow for a short sell
                if side == 'sell' and i == 0:
                    base_asset = symbol.split('/')[0]
                    borrow_amount = float(precise_quantity)
                    logger.info(f"Attempting to borrow {borrow_amount} {base_asset} for short selling")
                    if not self.direct_margin_transaction(base_asset, borrow_amount, 'borrow'):
                        logger.error(f"Failed to borrow {borrow_amount} {base_asset} for short selling. Skipping trade.")
                        return False
                    borrowed_amount = borrow_amount

                # Execute the margin trade
                try:
                    order = self.margin_exchange.create_order(symbol, 'limit', side, precise_quantity, limit_price, {'marginMode': 'cross'})
                    logger.info(f"Placed margin {side} order for {symbol}: {order}")
                except Exception as e:
                    logger.error(f"Error placing margin order: {str(e)}")
                    logger.error(f"Order details: Symbol={symbol}, Side={side}, Quantity={precise_quantity}, Limit Price={limit_price}")
                    if borrowed_amount > 0:
                        self.direct_margin_transaction(base_asset, borrowed_amount, 'repay')
                    raise

                # Wait for the order to be filled (with a timeout)
                start_time = time.time()
                while time.time() - start_time < 10:  # 10 seconds timeout
                    order = self.margin_exchange.fetch_order(order['id'], symbol)
                    if order['status'] == 'closed':
                        break
                    time.sleep(0.5)

                if order['status'] != 'closed':
                    logger.warning(f"Order not filled within timeout. Cancelling order.")
                    self.margin_exchange.cancel_order(order['id'], symbol)
                    if borrowed_amount > 0:
                        self.direct_margin_transaction(base_asset, borrowed_amount, 'repay')
                    return False

                # Update current_amount for the next trade
                if side == 'buy':
                    current_amount_usd = Decimal(str(order['filled']))  # This is now in asset quantity
                else:
                    current_amount_usd = Decimal(str(order['filled'])) * Decimal(str(order['average']))  # Convert back to USD

            # Repay borrowed asset if any
            if borrowed_amount > 0:
                self.direct_margin_transaction(base_asset, borrowed_amount, 'repay')

            return True

        except Exception as e:
            logger.error(f"Error executing margin triangular arbitrage: {str(e)}")
            logger.error(f"Error details: {type(e).__name__}, {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            if borrowed_amount > 0:
                self.direct_margin_transaction(base_asset, borrowed_amount, 'repay')
            return False

    def execute_margin_trade(self, symbol: str, side: str, amount: str) -> dict:
        """
        Execute a margin trade using direct Binance API calls.
        """
        try:
            base_url = "https://api.binance.com"
            endpoint = "/sapi/v1/margin/order"
            timestamp = int(time.time() * 1000)

            # Prepare parameters
            params = {
                'symbol': symbol.replace('/', ''),
                'side': side.upper(),
                'type': 'MARKET',
                'quantity': amount,
                'isIsolated': 'FALSE',  # for cross margin
                'timestamp': str(timestamp)
            }

            # Create the query string
            query_string = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in sorted(params.items())])

            # Create the signature
            signature = hmac.new(self.margin_exchange.secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

            # Add the signature to the query string
            full_url = f"{base_url}{endpoint}?{query_string}&signature={signature}"

            # Prepare headers
            headers = {
                'X-MBX-APIKEY': self.margin_exchange.apiKey
            }

            # Make the request
            response = requests.post(full_url, headers=headers)

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Error in margin trade execution: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error in margin trade execution: {str(e)}")
            return None
    
    def monitor_triangular_arbitrage(self, symbol_triplet: List[str], trades: List[str],
                                    profit_threshold: float = 0.001, 
                                    interval: int = 5, update_interval: int = 300, 
                                    execute_trades: bool = False, trade_amount: float = 100.0,
                                    max_slippage: float = 0.001):
        """
        Monitor and potentially execute bidirectional triangular arbitrage opportunities using margin markets.
        """
        logger.info(f"Starting bidirectional margin triangular arbitrage monitoring for {symbol_triplet}")
        logger.info(f"Initial trade sequence: {trades}")
        logger.info(f"Settings: profit_threshold={profit_threshold}, interval={interval}, "
                    f"update_interval={update_interval}, execute_trades={execute_trades}, "
                    f"trade_amount={trade_amount}, max_slippage={max_slippage}, leverage={self.leverage}")

        last_update_time = time.time()

        while True:
            current_time = time.time()

            try:
                # Fetch latest margin prices
                prices = self.fetch_margin_prices(symbol_triplet)

                # Calculate potential profit in both directions
                forward_profit = self.calculate_triangular_arbitrage_profit(prices, trades, trade_amount)
                reverse_trades = [self.reverse_trade(t) for t in trades[::-1]]
                reverse_prices = {symbol: price for symbol, price in reversed(prices.items())}
                reverse_profit = self.calculate_triangular_arbitrage_profit(reverse_prices, reverse_trades, trade_amount)

                # Determine if there's a profitable opportunity in either direction
                if abs(forward_profit) > profit_threshold * 100 or abs(reverse_profit) > profit_threshold * 100:
                    if forward_profit > reverse_profit:
                        logger.info(f"Forward arbitrage: {forward_profit:.4f}% profit")
                        if execute_trades and forward_profit > profit_threshold * 100:
                            success = self.execute_triangular_arbitrage(symbol_triplet, trades, trade_amount, prices, max_slippage)
                            if success:
                                logger.info("Forward margin triangular arbitrage trade executed successfully")
                            else:
                                logger.warning("Failed to execute forward margin triangular arbitrage trade")
                    else:
                        logger.info(f"Reverse arbitrage: {reverse_profit:.4f}% profit")
                        if execute_trades and reverse_profit > profit_threshold * 100:
                            success = self.execute_triangular_arbitrage(symbol_triplet[::-1], reverse_trades, trade_amount, prices, max_slippage)
                            if success:
                                logger.info("Reverse margin triangular arbitrage trade executed successfully")
                            else:
                                logger.warning("Failed to execute reverse margin triangular arbitrage trade")

                # Print current arbitrage opportunities every update_interval
                if current_time - last_update_time >= update_interval:
                    logger.info(f"\nCurrent margin arbitrage opportunities at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}:")
                    logger.info(f"Forward potential profit: {forward_profit:.4f}%")
                    logger.info(f"Reverse potential profit: {reverse_profit:.4f}%")
                    logger.info(f"Prices: {prices}")
                    last_update_time = current_time

            except Exception as e:
                logger.error(f"Error in bidirectional margin triangular arbitrage monitoring: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")

            time.sleep(interval)
            
    def fetch_margin_prices(self, symbols: List[str]) -> Dict[str, Decimal]:
        """
        Fetch the latest margin prices for the given symbol triplet.
        """
        prices = {}
        for symbol in symbols:
            try:
                ticker = self.margin_exchange.fetch_ticker(symbol)
                prices[symbol] = Decimal(str(ticker['last']))
            except Exception as e:
                logger.error(f"Error fetching price for {symbol}: {str(e)}")
                raise
        return prices

    def reverse_trade(self, trade: str) -> str:
        """
        Reverse the trade direction.
        """
        return 'sell' if trade == 'buy' else 'buy'

    def calculate_triangular_arbitrage_profit(self, prices: Dict[str, Decimal], trades: List[str], trade_amount_usd: float) -> float:
        """
        Calculate the potential profit percentage from a margin triangular arbitrage trade, starting with USD.
        """
        try:
            current_amount_usd = Decimal(str(trade_amount_usd))

            for symbol, trade in zip(prices.keys(), trades):
                price = prices[symbol]
                if trade == 'buy':
                    # Convert USD to asset quantity
                    quantity = current_amount_usd / price
                    current_amount_usd = quantity  # Keep track of the quantity for the next trade
                elif trade == 'sell':
                    # Convert asset quantity to USD
                    current_amount_usd = current_amount_usd * price

            # Calculate profit percentage
            profit_percentage = (float(current_amount_usd) / float(trade_amount_usd) - 1) * 100
            return profit_percentage
        except Exception as e:
            logger.error(f"Error in profit calculation: {str(e)}")
            logger.error(f"Prices: {prices}, Trades: {trades}, Trade amount USD: {trade_amount_usd}")
            raise
    
            
            