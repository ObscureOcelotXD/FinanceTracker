# Mapping from common ticker symbols to CoinGecko IDs
base_mapping = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "ltc": "litecoin",
    "litecoin": "litecoin",
    "xrp": "ripple",
    "ripple": "ripple",
    "doge": "dogecoin",
    "dogecoin": "dogecoin",
    "ada": "cardano",
    "cardano": "cardano",
    "dot": "polkadot",
    "polkadot": "polkadot",
    "usdt": "tether",
    "tether": "tether",
    "usdc": "usd-coin",
    "usd-coin": "usd-coin",
    "bnb": "binancecoin",
    "binancecoin": "binancecoin",
    "sol": "solana",
    "solana": "solana",
    "uni": "uniswap",
    "uniswap": "uniswap",
    "link": "chainlink",
    "chainlink": "chainlink",
    "matic": "matic-network",
    "matic-network": "matic-network",
    "xlm": "stellar",
    "stellar": "stellar",
    "v": "vechain",
    "vechain": "vechain",
    "theta": "theta-network",
    "theta-network": "theta-network",
    "fil": "filecoin",
    "filecoin": "filecoin",
    "etc": "ethereum-classic",
    "ethereum-classic": "ethereum-classic",
    "shib": "shiba-inu",
    "shiba-inu": "shiba-inu",
    "bch": "bitcoin-cash",
    "bitcoin-cash": "bitcoin-cash",
    "dash": "dash",
    "dash": "dash",
    "xmr": "monero",
    "monero": "monero",
    "zec": "zcash",
    "zcash": "zcash",
    "trx": "tron",
    "tron": "tron",
    "eos": "eos",
    "eos": "eos",
    "atom": "cosmos",
    "cosmos": "cosmos",
    "algo": "algorand",
    "algorand": "algorand",
    "xtz": "tezos",
    "tezos": "tezos",
    "luna": "terra",
    "terra": "terra",
    "ftt": "ftx-token",
    "ftx-token": "ftx-token",
    "bsv": "bitcoin-sv",
    "bitcoin-sv": "bitcoin-sv",
    "cro": "crypto-com-chain",
    "crypto-com-chain": "crypto-com-chain",
    "ht": "huobi-token",
    "huobi-token": "huobi-token",
    "leo": "unus-sed-leo",
    "unus-sed-leo": "unus-sed-leo",
    "dai": "dai",
    "dai": "dai",
    "aave": "aave",
    "aave": "aave",
    "ftm": "fantom",
    "fantom": "fantom",
    "snx": "synthetix-network-token",
    "synthetix-network-token": "synthetix-network-token",
    "okb": "okb",
    "okb": "okb",
    "comp": "compound",
    "compound": "compound",
    "yfi": "yearn-finance",
    "yearn-finance": "yearn-finance",
    "uma": "uma",
    "uma": "uma",
    "sushi": "sushi",
    "sushi": "sushi",
    "chz": "chiliz",
    "chiliz": "chiliz",
    "enj": "enjincoin",
    "enjincoin": "enjincoin",
    "zil": "zilliqa",
    "zilliqa": "zilliqa",
    "bat": "basic-attention-token",
    "basic-attention-token": "basic-attention-token",
    "mana": "decentraland",
    "decentraland": "decentraland",
    "knc": "kyber-network",
    "kyber-network": "kyber-network",
    "rune": "thorchain",
    "thorchain": "thorchain",
    "vet": "vechain",
    "vechain": "vechain",
    "xem": "nem",
    "nem": "nem",
    "omg": "omisego",
    "omisego": "omisego",
    "zrx": "0x",
    "0x": "0x",
    "icx": "icon",
    "icon": "icon",
    "grt": "the-graph",
    "the-graph": "the-graph",
    "band": "band-protocol",
    "band-protocol": "band-protocol",
    "ren": "ren",
    "ren": "ren",
    "bal": "balancer",
    "balancer": "balancer",
    "lrc": "loopring",
    "loopring": "loopring",
    # add more mappings as needed...
}

# Create a complete mapping that also maps the canonical value to itself.
COIN_MAPPING = {}
for key, value in base_mapping.items():
    COIN_MAPPING[key] = value
    # Ensure that the canonical coin name maps to itself
    if value not in COIN_MAPPING:
        COIN_MAPPING[value] = value

def get_coin_id(user_input: str) -> str:
    """
    Normalize user input (e.g. "DASH", "dash") and return the canonical coin id.
    """
    ticker = user_input.strip().lower()
    return COIN_MAPPING.get(ticker)