from web3 import Web3
import secrets
import hashlib
import aiohttp
import asyncio
import logging
import time
import os
from typing import Tuple, Optional
from bit import Key  # لبيتكوين

# إعداد السجل
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename='wallet_results.log')

# شبكات مشهورة مع RPCs مجانية
NETWORKS = {
    "eth": "https://rpc.ankr.com/eth",
    "bsc": "https://bsc-dataseed.binance.org/",
    "poly": "https://rpc-mainnet.matic.network",
    "tron": "https://api.trongrid.io",
    "avax": "https://api.avax.network/ext/bc/C/rpc",
    "ftm": "https://rpc.ftm.tools/",
    "arb": "https://arb1.arbitrum.io/rpc",
    "op": "https://mainnet.optimism.io"
}

USDT_CONTRACTS = {
    "eth": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "bsc": "0x55d398326f99059fF775485246999027B3197955",
    "tron": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "poly": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
}

# مفتاح سري عشوائي
def generate_super_private_key() -> str:
    seed = secrets.token_bytes(128) + str(time.time_ns()).encode() + os.urandom(64)
    return hashlib.blake2b(seed, digest_size=32).hexdigest()

# فحص EVM
async def check_evm_balance(session: aiohttp.ClientSession, network: str, private_key: str) -> Tuple[Optional[str], float, Optional[str], float]:
    try:
        url = NETWORKS[network]
        w3 = Web3(Web3.HTTPProvider(url))
        if not w3.is_connected():
            return None, 0, None, 0
        account = w3.eth.account.from_key(private_key)
        async with session.post(url, json={"jsonrpc": "2.0", "method": "eth_getBalance", "params": [account.address, "latest"], "id": 1}, timeout=aiohttp.ClientTimeout(total=2)) as resp:
            data = await resp.json()
            balance = int(data["result"], 16) if "result" in data else 0
        usdt_balance = 0
        if network in USDT_CONTRACTS:
            usdt_abi = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}]
            contract = w3.eth.contract(address=USDT_CONTRACTS[network], abi=usdt_abi)
            usdt_balance = contract.functions.balanceOf(account.address).call() / 10**6
        if balance > 0 or usdt_balance > 0:
            return account.address, w3.from_wei(balance, 'ether'), private_key, usdt_balance
    except Exception:
        return None, 0, None, 0
    return None, 0, None, 0

# فحص بيتكوين
async def check_btc_balance(session: aiohttp.ClientSession, private_key: str) -> Tuple[Optional[str], float, Optional[str]]:
    try:
        key = Key(private_key)
        address = key.address
        async with session.get(f"https://blockstream.info/api/address/{address}", timeout=aiohttp.ClientTimeout(total=2)) as resp:
            data = await resp.json()
            balance = (data["chain_stats"]["funded_txo_sum"] - data["chain_stats"]["spent_txo_sum"]) / 10**8
            if balance > 0:
                return address, balance, private_key
    except Exception:
        return None, 0, None
    return None, 0, None

# العامل
async def worker(network: str):
    async with aiohttp.ClientSession() as session:
        logging.info(f"بدأت على {network}")
        checked = 0
        start_time = time.time()

        while time.time() - start_time < 3600:  # يعمل ساعة لكل جلسة
            tasks = []
            for _ in range(500):  # حجم مهام مناسب لـGitHub Actions
                private_key = generate_super_private_key()
                if network == "btc":
                    tasks.append(check_btc_balance(session, private_key))
                else:
                    tasks.append(check_evm_balance(session, network, private_key))

            for future in await asyncio.gather(*tasks):
                checked += 1
                if network == "btc":
                    address, balance, key = future
                    usdt_balance = 0
                else:
                    address, balance, key, usdt_balance = future
                if address:
                    with open("found_wallets.txt", "a") as f:
                        f.write(f"شبكة: {network}\n")
                        f.write(f"عنوان: {address}\n")
                        f.write(f"رصيد ({'BTC' if network == 'btc' else 'ETH/BNB/etc'}): {balance}\n")
                        if usdt_balance > 0:
                            f.write(f"رصيد USDT: {usdt_balance}\n")
                        f.write(f"مفتاح: {key}\n")
                        f.write("-" * 50 + "\n")
                    logging.info(f"نجاح في {network} بعد {checked} فحص!")
                if checked % 1000 == 0:
                    logging.info(f"{network}: فحصت {checked} مفتاح")
            await asyncio.sleep(0.0001)

# التشغيل
if __name__ == "__main__":
    logging.info("انطلقت في السحابة—مفاتيح سرية فقط!")
    all_networks = list(NETWORKS.keys()) + ["btc"]
    asyncio.run(asyncio.gather(*(worker(net) for net in all_networks)))
