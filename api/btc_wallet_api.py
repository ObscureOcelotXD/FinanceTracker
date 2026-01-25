import hashlib
import json
import os
import socket
import ssl
import time
from flask import Blueprint, jsonify
from dotenv import load_dotenv
from bip_utils import Bip32Slip10Secp256k1, P2PKHAddr, P2WPKHAddr

load_dotenv()

btc_wallet_api = Blueprint("btc_wallet_api", __name__)

CACHE = {"data": None, "ts": 0}

class ElectrumClient:
    def __init__(self, host, port, use_ssl, timeout=10):
        self._host = host
        self._port = port
        self._use_ssl = use_ssl
        self._timeout = timeout
        self._sock = None
        self._file = None
        self._next_id = 0

    def __enter__(self):
        raw_sock = socket.create_connection((self._host, self._port), timeout=self._timeout)
        if self._use_ssl:
            context = ssl.create_default_context()
            self._sock = context.wrap_socket(raw_sock, server_hostname=self._host)
        else:
            self._sock = raw_sock
        self._file = self._sock.makefile("rwb")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._file:
                self._file.close()
        finally:
            if self._sock:
                self._sock.close()

    def request(self, method, params=None):
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params or [],
        }
        message = (json.dumps(payload) + "\n").encode("utf-8")
        self._file.write(message)
        self._file.flush()
        line = self._file.readline()
        if not line:
            raise RuntimeError("No response from Electrum server")
        response = json.loads(line.decode("utf-8"))
        if response.get("error"):
            raise RuntimeError(response["error"])
        return response.get("result")


def _get_env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _hash160(data):
    sha = hashlib.sha256(data).digest()
    ripe = hashlib.new("ripemd160")
    ripe.update(sha)
    return ripe.digest()


def _scriptpubkey_from_pubkey(pub_key, address_type):
    pubkey_hash = _hash160(pub_key).hex()
    if address_type == "p2wpkh":
        return f"0014{pubkey_hash}"
    return f"76a914{pubkey_hash}88ac"


def _scripthash_from_pubkey(pub_key, address_type):
    scriptpubkey = bytes.fromhex(_scriptpubkey_from_pubkey(pub_key, address_type))
    digest = hashlib.sha256(scriptpubkey).digest()
    return digest[::-1].hex()


def _derive_address(xpub, chain, index, address_type):
    ctx = Bip32Slip10Secp256k1.FromExtendedKey(xpub)
    child = ctx.DerivePath(f"{chain}/{index}")
    pub_key = child.PublicKey().RawCompressed().ToBytes()
    if address_type == "p2wpkh":
        return P2WPKHAddr.EncodeKey(pub_key, hrp="bc")
    return P2PKHAddr.EncodeKey(pub_key, net_ver=0x00)


def _derive_scripthash(xpub, chain, index, address_type):
    ctx = Bip32Slip10Secp256k1.FromExtendedKey(xpub)
    child = ctx.DerivePath(f"{chain}/{index}")
    pub_key = child.PublicKey().RawCompressed().ToBytes()
    return _scripthash_from_pubkey(pub_key, address_type)


def _scan_addresses(client, xpub, gap_limit, address_type):
    used_addresses = []
    used_scripthashes = []
    total_scanned = 0
    for chain in (0, 1):
        consecutive_unused = 0
        index = 0
        while consecutive_unused < gap_limit:
            address = _derive_address(xpub, chain, index, address_type)
            scripthash = _derive_scripthash(xpub, chain, index, address_type)
            history = client.request("blockchain.scripthash.get_history", [scripthash])
            total_scanned += 1
            if history:
                used_addresses.append(address)
                used_scripthashes.append(scripthash)
                consecutive_unused = 0
            else:
                consecutive_unused += 1
            index += 1
    return used_addresses, used_scripthashes, total_scanned


def _sum_balances(client, scripthashes):
    confirmed = 0
    unconfirmed = 0
    use_listunspent = True
    for scripthash in scripthashes:
        if use_listunspent:
            try:
                utxos = client.request("blockchain.scripthash.listunspent", [scripthash])
                for utxo in utxos:
                    confirmed += int(utxo.get("value", 0))
            except Exception:
                use_listunspent = False
        if not use_listunspent:
            balance = client.request("blockchain.scripthash.get_balance", [scripthash])
            confirmed += int(balance.get("confirmed", 0))
            unconfirmed += int(balance.get("unconfirmed", 0))
    return confirmed, unconfirmed


@btc_wallet_api.route("/btc/wallet_summary", methods=["GET"])
def wallet_summary():
    cache_ttl = int(os.getenv("BTC_WALLET_CACHE_TTL", "300"))
    if CACHE["data"] and (time.time() - CACHE["ts"] < cache_ttl):
        return jsonify(CACHE["data"])

    xpub = os.getenv("BTC_WALLET_XPUB")
    if not xpub:
        return jsonify({"error": "BTC_WALLET_XPUB not configured"}), 400

    host = os.getenv("BTC_ELECTRUM_HOST", "umbrel.local").strip()
    port = int(os.getenv("BTC_ELECTRUM_PORT", "50001"))
    use_ssl = _get_env_bool("BTC_ELECTRUM_SSL", False)
    gap_limit = int(os.getenv("BTC_WALLET_GAP_LIMIT", "20"))
    address_type = os.getenv("BTC_WALLET_ADDRESS_TYPE", "p2pkh").strip().lower()
    if address_type not in {"p2pkh", "p2wpkh"}:
        return jsonify({"error": "Unsupported BTC_WALLET_ADDRESS_TYPE"}), 400

    try:
        with ElectrumClient(host, port, use_ssl) as client:
            client.request("server.version", ["FinanceTracker", "1.4"])
            used_addresses, used_scripthashes, scanned = _scan_addresses(client, xpub, gap_limit, address_type)
            confirmed, unconfirmed = _sum_balances(client, used_scripthashes)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    total = confirmed + unconfirmed
    result = {
        "balance_btc": total / 1e8,
        "confirmed_btc": confirmed / 1e8,
        "unconfirmed_btc": unconfirmed / 1e8,
        "addresses_used": len(used_addresses),
        "addresses_scanned": scanned,
        "address_type": address_type,
    }
    CACHE["data"] = result
    CACHE["ts"] = time.time()
    return jsonify(result)
