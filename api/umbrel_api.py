# api/umbrel_api.py
from flask import Blueprint, jsonify
import os
import json
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

umbrel_api = Blueprint('umbrel_api', __name__)

def call_umbrel_rpc(method, params=None):
    if params is None:
        params = []
    umbrel_ip = os.getenv("UMBREL_TAILSCALE_IP")
    rpc_user = os.getenv("UMBREL_RPC_USER")
    rpc_pass = os.getenv("UMBREL_RPC_PASS")
    if not (umbrel_ip and rpc_user and rpc_pass):
        return {"error": "Umbrel RPC credentials or IP not configured properly."}
    url = f"http://{umbrel_ip}:8332"
    headers = {'content-type': 'application/json'}
    payload = json.dumps({
        "method": method,
        "params": params,
        "jsonrpc": "2.0",
        "id": 0
    })
    try:
        response = requests.post(url, headers=headers, data=payload,
                                 auth=HTTPBasicAuth(rpc_user, rpc_pass))
        return response.json()
    except Exception as e:
        return {"error": str(e)}

@umbrel_api.route('/umbrel/blockcount', methods=['GET'])
def umbrel_blockcount():
    data = call_umbrel_rpc("getblockcount")
    if "result" in data:
        return jsonify({"block_count": data["result"]})
    else:
        return jsonify({"error": data.get("error", data)}), 500

@umbrel_api.route('/umbrel/networkhashps', methods=['GET'])
def umbrel_networkhashps():
    data = call_umbrel_rpc("getnetworkhashps")
    if "result" in data:
        return jsonify({"networkhashps": data["result"]})
    else:
        return jsonify({"error": data.get("error", data)}), 500

@umbrel_api.route('/umbrel/mempoolinfo', methods=['GET'])
def umbrel_mempoolinfo():
    data = call_umbrel_rpc("getmempoolinfo")
    if "result" in data:
        return jsonify({"mempoolinfo": data["result"]})
    else:
        return jsonify({"error": data.get("error", data)}), 500

@umbrel_api.route('/umbrel/estimatesmartfee', methods=['GET'])
def umbrel_estimatesmartfee():
    # Example: estimatesmartfee for 6 blocks target confirmation time
    data = call_umbrel_rpc("estimatesmartfee", [6])
    if "result" in data:
        return jsonify({"estimatesmartfee": data["result"]})
    else:
        return jsonify({"error": data.get("error", data)}), 500
