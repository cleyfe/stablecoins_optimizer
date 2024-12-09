def pow10(exponent):
    return 10 ** exponent

SECONDS_PER_YEAR = 365 * 24 * 3600
WAD = pow10(18)
ORACLE_PRICE_SCALE = 1000000000000000000000000000000000000
MAX_UINT256 = 115792089237316195423570985008687907853269984665640564039457584007913129639935
ZERO_ADDRESS = "0x000000000000000000000000000000000000000"
RAY = 1e27

chain_map_moralis = {
    "Arbitrum": "arbitrum",
    "Polygon": "polygon",
    "Ethereum": "eth",
    "Base": "base",
    "Optimism": "optimism",
    "Gnosis": "gnosis"
}
