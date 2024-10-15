import requests
import pandas as pd
from typing import Dict, List

class LlamaClient:
    BASE_URL = "https://yields.llama.fi/chartlendBorrow/"

    def __init__(self):
        self.llama_pools = {
            # protocol_chain_asset
            'aave_arb_usdc': 'd9fa8e14-0447-4207-9ae8-7810199dfa1f',
            'aave_arb_usdt': '3a6cc030-738d-4e19-8a40-e63e9c4d5a6f',
            'aave_arb_usdce': '7aab7b0f-01c1-4467-bc0d-77826d870f19',
            'aave_arb_dai': 'a8e3d841-2788-4647-ad54-5a36fac451b1',    
            'aave_arb_eth': '',    
            'aave_arb_weth': '',    
            'aave_pol_usdc': '1b8b4cdb-0728-42a8-bf13-2c8fea7427ee',
            'aave_pol_usdt': '7e7821a2-3d20-4ae7-9c3d-04cd57904555',
            'aave_pol_dai': 'c57bdc97-3100-41ff-845f-075363f6f5a4',
            'aave_pol_usdce': '37b04faa-95bb-4ccb-9c4e-c70fa167342b',

            'comp_arb_usdc' : 'd9c395b9-00d0-4426-a6b3-572a6dd68e54',
            'comp_pol_usdc' : 'a17d8b32-48cb-4446-aad7-ed4278f144e0',
            'comp_eth_usdc' : '7da72d09-56ca-4ec5-a45f-59114353e487',
        }

    def fetch_pool_data(self, pool_name: str, pool_id: str) -> pd.DataFrame:
        api_url = f"{self.BASE_URL}{pool_id}"
        response = requests.get(api_url)
        
        if response.status_code == 200:
            data = response.json()['data']
            pool_df = pd.DataFrame(data)
            pool_df['timestamp'] = pd.to_datetime(pool_df['timestamp'])
            pool_df.set_index('timestamp', inplace=True)
            pool_df.rename(columns={'apyBase': f'{pool_name}_apyBase', 'apyBaseBorrow': f'{pool_name}_apyBaseBorrow'}, inplace=True)
            return pool_df[[f'{pool_name}_apyBase', f'{pool_name}_apyBaseBorrow']]
        else:
            print(f"Error: Unable to fetch data for {pool_name} (status code: {response.status_code})")
            return pd.DataFrame()

    def fetch_all_pools_data(self) -> pd.DataFrame:
        time_series_df = pd.DataFrame()
        for pool_name, pool_id in self.llama_pools.items():
            pool_df = self.fetch_pool_data(pool_name, pool_id)
            if time_series_df.empty:
                time_series_df = pool_df
            else:
                time_series_df = time_series_df.join(pool_df, how='outer')
        return time_series_df

    def calculate_pool_stats(self, pool_df: pd.DataFrame, pool_name: str) -> List[Dict]:
        stats_list = []
        for metric in ['apyBase', 'apyBaseBorrow']:
            column_name = f'{pool_name}_{metric}'
            stats = {
                'Pool': pool_name,
                'Metric': metric,
                'Last': pool_df[column_name].iloc[-1],
                'Average': pool_df[column_name].mean(),
                'Median': pool_df[column_name].median(),
                'Volatility': pool_df[column_name].std(),
                'Max': pool_df[column_name].max(),
                'Min': pool_df[column_name].min(),
                '10th Percentile': pool_df[column_name].quantile(0.1),
                '90th Percentile': pool_df[column_name].quantile(0.9),
            }
            stats_list.append(stats)
        return stats_list

    def calculate_all_pools_stats(self, time_series_df: pd.DataFrame) -> pd.DataFrame:
        stats_list = []
        for pool_name in self.llama_pools.keys():
            pool_df = time_series_df[[f'{pool_name}_apyBase', f'{pool_name}_apyBaseBorrow']]
            stats_list.extend(self.calculate_pool_stats(pool_df, pool_name))
        return pd.DataFrame(stats_list)

    def categorize_pools(self, stats_df: pd.DataFrame) -> pd.DataFrame:
        stats_df['Category'] = stats_df['Pool'].apply(lambda x: 'Polygon' if x.startswith('pol') else 'Arbitrum')
        return stats_df

    def calculate_average_metrics(self, stats_df: pd.DataFrame) -> pd.DataFrame:
        numeric_columns = ['Average', 'Median', 'Volatility', 'Max', 'Min', '10th Percentile', '90th Percentile']
        average_metrics_df = stats_df.groupby('Category')[numeric_columns].mean().reset_index()
        
        metric_row = pd.DataFrame({
            'Category': ['apyBase', 'apyBaseBorrow'],
            'Average': [stats_df[stats_df['Metric'] == 'apyBase']['Average'].mean(), stats_df[stats_df['Metric'] == 'apyBaseBorrow']['Average'].mean()],
            'Median': [stats_df[stats_df['Metric'] == 'apyBase']['Median'].median(), stats_df[stats_df['Metric'] == 'apyBaseBorrow']['Median'].median()],
            'Volatility': [stats_df[stats_df['Metric'] == 'apyBase']['Volatility'].mean(), stats_df[stats_df['Metric'] == 'apyBaseBorrow']['Volatility'].mean()],
            'Max': [stats_df[stats_df['Metric'] == 'apyBase']['Max'].max(), stats_df[stats_df['Metric'] == 'apyBaseBorrow']['Max'].max()],
            'Min': [stats_df[stats_df['Metric'] == 'apyBase']['Min'].min(), stats_df[stats_df['Metric'] == 'apyBaseBorrow']['Min'].min()],
            '10th Percentile': [stats_df[stats_df['Metric'] == 'apyBase']['10th Percentile'].quantile(0.1), stats_df[stats_df['Metric'] == 'apyBaseBorrow']['10th Percentile'].quantile(0.1)],
            '90th Percentile': [stats_df[stats_df['Metric'] == 'apyBase']['90th Percentile'].quantile(0.9), stats_df[stats_df['Metric'] == 'apyBaseBorrow']['90th Percentile'].quantile(0.9)]
        })
        
        return pd.concat([average_metrics_df, metric_row], ignore_index=True)