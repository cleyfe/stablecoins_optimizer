import ccxt
import pandas as pd
from typing import Dict, List
import logging
from datetime import datetime
import time
import asyncio
import nest_asyncio

# Apply nest_asyncio for Jupyter compatibility
nest_asyncio.apply()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CCXTClient:
    def __init__(self, verbose: bool = False):
        """Initialize client with multiple CEX/DEX connections"""
        self.exchanges = {
            'hyperliquid': ccxt.hyperliquid({
                'enableRateLimit': True
            }),
            'paradex': ccxt.paradex({
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap'
                }
            }),
            'vertex': ccxt.vertex({
                'enableRateLimit': True
            }),
            'defx': ccxt.defx({
                'enableRateLimit': True
            })
        }
        
        # Symbol mappings for each exchange based on inspect_markets output
        self.symbol_maps = {
            'hyperliquid': {
                'ETH': 'ETH/USDC:USDC',
            },
            'paradex': {
                'ETH': 'ETH/USD:USDC',
            },
            'vertex': {
                'ETH': 'ETH/USDC:USDC',
            },
            'defx': {
                'ETH': 'ETH/USDC:USDC',  # We'll verify this format with inspect_markets
            }
        }
        
        self.verbose = verbose
        self.markets = {}
        self.load_markets()

    def load_markets(self):
        """Load markets for all exchanges"""
        for exchange_id, exchange in self.exchanges.items():
            try:
                logger.info(f"Loading markets for {exchange_id}...")
                exchange.load_markets()
                self.markets[exchange_id] = exchange.markets
                logger.info(f"Found {len(exchange.markets)} markets on {exchange_id}")
            except Exception as e:
                logger.error(f"Error loading markets for {exchange_id}: {str(e)}")
                self.markets[exchange_id] = {}

    def inspect_markets(self):
        """Print available markets for each exchange"""
        for exchange_id, exchange in self.exchanges.items():
            print(f"\n=== {exchange_id.upper()} ===")
            if hasattr(exchange, 'markets') and exchange.markets:
                print(f"Total markets: {len(exchange.markets)}")
                # Find markets containing common tokens
                markets = exchange.markets
                btc_markets = [s for s in markets if 'BTC' in s.upper()][:5]
                eth_markets = [s for s in markets if 'ETH' in s.upper()][:5]
                sol_markets = [s for s in markets if 'SOL' in s.upper()][:5]
                print("\nBTC pairs:", btc_markets)
                print("ETH pairs:", eth_markets)
                print("SOL pairs:", sol_markets)
            else:
                print("No markets loaded")

    def get_current_prices(self, bases: List[str]) -> pd.DataFrame:
        """Fetch current prices for specified base currencies"""
        all_prices = []
        
        for exchange_id, exchange in self.exchanges.items():
            if not self.markets.get(exchange_id):
                continue
                
            for base in bases:
                try:
                    symbol = self.get_exchange_symbol(base, exchange_id)
                    if not symbol:
                        continue
                        
                    ticker = exchange.fetch_ticker(symbol)
                    
                    price_info = {
                        'exchange': exchange_id,
                        'base': base,
                        'symbol': symbol,
                        'bid': ticker.get('bid'),
                        'ask': ticker.get('ask'),
                        'last': ticker.get('last'),
                        'timestamp': datetime.fromtimestamp(ticker['timestamp'] / 1000)
                    }
                    
                    # Only add if we have at least one valid price
                    if any(v is not None for v in [price_info['bid'], price_info['ask'], price_info['last']]):
                        all_prices.append(price_info)
                        
                except Exception as e:
                    if self.verbose:
                        logger.error(f"Error fetching ticker for {base} on {exchange_id}: {str(e)}")
        
        df = pd.DataFrame(all_prices)
        if not df.empty:
            df = df.sort_values(['base', 'exchange'])
        return df

    def calculate_price_differences(self, bases: List[str], min_threshold: float = 0.1) -> pd.DataFrame:
        """Calculate price differences across exchanges"""
        prices_df = self.get_current_prices(bases)
        if prices_df.empty:
            return pd.DataFrame()
        
        differences = []
        for base in bases:
            base_prices = prices_df[prices_df['base'] == base]
            if len(base_prices) < 2:
                continue
                
            for i, row1 in base_prices.iterrows():
                for j, row2 in base_prices.iterrows():
                    if i >= j:
                        continue
                        
                    if row1['last'] is None or row2['last'] is None:
                        continue
                        
                    price_diff_pct = (row2['last'] - row1['last']) / row1['last'] * 100
                    
                    if abs(price_diff_pct) >= min_threshold:
                        differences.append({
                            'base': base,
                            'exchange1': row1['exchange'],
                            'exchange2': row2['exchange'],
                            'price1': row1['last'],
                            'price2': row2['last'],
                            'difference_percent': price_diff_pct,
                            'timestamp': row1['timestamp']
                        })
        
        df = pd.DataFrame(differences)
        if not df.empty:
            df = df.sort_values('difference_percent', ascending=False)
        return df

    def monitor_prices(self, bases: List[str], interval: int = 5):
        """Continuously monitor prices"""
        try:
            while True:
                print(f"\nPrices at {datetime.now()}:")
                prices_df = self.get_current_prices(bases)
                if not prices_df.empty:
                    print(prices_df[['base', 'exchange', 'bid', 'ask', 'last']])
                
                differences_df = self.calculate_price_differences(bases)
                if not differences_df.empty:
                    print("\nArbitrage Opportunities:")
                    print(differences_df)
                
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nStopping price monitoring...")