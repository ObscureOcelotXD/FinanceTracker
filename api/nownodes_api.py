# api/nownodes_api.py
from flask import Blueprint, jsonify
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

nownodes_api = Blueprint('nownodes_api', __name__)

# The NOWNODES Ethereum endpoint (ensure this is set in your .env)
NOWNODES_ETH_ENDPOINT = os.getenv("NOWNODES_ETH_ENDPOINT")

def get_eth_block_number():
    """
    Call the NOWNODES ETH endpoint using JSON-RPC to get the current block number.
    """
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_blockNumber",
        "params": [],
        "id": 1
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(NOWNODES_ETH_ENDPOINT, headers=headers, json=payload)
    print("Raw response:", response.text)
    return response.json()

@nownodes_api.route('/nownodes/eth_blocknumber', methods=['GET'])
def eth_blocknumber():
    data = get_eth_block_number()
    if "result" in data:
        # The result is a hex string; convert it to an integer.
        block_number = int(data["result"], 16)
        return jsonify({"block_number": block_number})
    else:
        return jsonify({"error": data.get("error", "Unable to retrieve block number")}), 500
