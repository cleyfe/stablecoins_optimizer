from web3 import Web3
from typing import Dict, Any
import requests
import json
import time

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