from web3 import Web3
from typing import Dict, Any
import requests
import json
import time
from datetime import datetime
from moralis import evm_api
import os
from dotenv import load_dotenv
from src.utils.constants import chain_map_moralis, RAY, SECONDS_PER_YEAR
import time

load_dotenv()

def convert_to_decimal_units(decimals: int, token_amount: float) -> int:
    """Convert float amount to integer units based on token decimals."""
    return int(token_amount * (10 ** decimals))

def convert_from_decimal_units(decimals: int, token_amount: int) -> float:
    """Convert integer units to float based on token decimals."""
    return float(token_amount / (10 ** decimals))

def get_abi(smart_contract_address: str) -> Dict[str, Any]:
    """
    Fetch the JSON ABI for a smart contract.
    """
    print(f"Fetching ABI for smart contract: {smart_contract_address}")
    abi_endpoint = f'https://api.etherscan.io/api?module=contract&action=getabi&address={smart_contract_address}'

    retry_count = 0
    json_abi = None
    err = None
    while retry_count < 5:
        etherscan_response = requests.get(abi_endpoint).json()
        if str(etherscan_response['status']) == '0':
            err = etherscan_response['result']
            retry_count += 1
            time.sleep(1)
        else:
            try:
                json_abi = json.loads(etherscan_response['result'])
            except json.decoder.JSONDecodeError:
                err = "Could not load ABI into JSON format"
            except Exception as exc:
                err = f"Response status was valid, but an unexpected error occurred '{exc}'"
            finally:
                break
    if json_abi is not None:
        return json_abi
    else:
        raise Exception(f"could not fetch ABI for contract: {smart_contract_address} - Error: {err}")

def from_ray(value: int) -> float:
    """Convert a value from ray units (1e27) to a float."""
    return value / 10**27

def from_market_base_ccy(value: int) -> float:
    """Convert a value from market base currency units (1e8) to a float."""
    return value / 10**8

def get_block_number_from_date(dt: datetime, chain="eth") -> int:
    """Get the block number associated with a specific datetime."""
    time.sleep(1)
    params = {
    "chain": chain,
    "date": dt.isoformat(),
    }
    
    result = evm_api.block.get_date_to_block(
        api_key=os.getenv("MORALIS_API_KEY"),
        params=params,
    )

    return result["block"]

def ray_to_apy(ray_rate):
    rate = float(ray_rate) / RAY
    return ((1 + rate / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1) * 100