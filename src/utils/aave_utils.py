from typing import Dict, Any
from web3 import Web3

def process_get_reserve_data_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Process the result of getReserveData function call."""
    from .web3_utils import from_ray  # local import to avoid circular dependency

    (
        configuration,
        liquidityIndex,
        currentLiquidityRate,
        variableBorrowIndex,
        currentVariableBorrowRate,
        currentStableBorrowRate,
        lastUpdateTimestamp,
        id,
        aTokenAddress,
        stableDebtTokenAddress,
        variableDebtTokenAddress,
        interestRateStrategyAddress,
        accruedToTreasury,
        unbacked,
        isolationModeTotalDebt,
    ) = result

    return {
        "configuration": configuration,
        "liquidityIndex": from_ray(liquidityIndex),
        "currentLiquidityRate": from_ray(currentLiquidityRate),
        "variableBorrowIndex": from_ray(variableBorrowIndex),
        "currentVariableBorrowRate": from_ray(currentVariableBorrowRate),
        "currentStableBorrowRate": from_ray(currentStableBorrowRate),
        "lastUpdateTimestamp": lastUpdateTimestamp,
        "id": id,
        "aTokenAddress": aTokenAddress,
        "stableDebtTokenAddress": stableDebtTokenAddress,
        "variableDebtTokenAddress": variableDebtTokenAddress,
        "interestRateStrategyAddress": interestRateStrategyAddress,
        "accruedToTreasury": accruedToTreasury,
        "unbacked": unbacked,
        "isolationModeTotalDebt": isolationModeTotalDebt,
    }

def process_get_user_account_data_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Process the result of getUserAccountData function call."""
    from .web3_utils import from_market_base_ccy  # local import to avoid circular dependency

    (
        totalCollateralBase,
        totalDebtBase,
        availableBorrowsBase,
        currentLiquidationThreshold,
        ltv,
        healthFactor,
    ) = result

    return {
        "totalCollateralBase": from_market_base_ccy(totalCollateralBase),
        "totalDebtBase": from_market_base_ccy(totalDebtBase),
        "availableBorrowsBase": from_market_base_ccy(availableBorrowsBase),
        "currentLiquidationThreshold": currentLiquidationThreshold,
        "ltv": ltv,
        "healthFactor": healthFactor,
    }