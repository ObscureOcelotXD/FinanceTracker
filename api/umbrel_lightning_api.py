# api/umbrel_lightning_api.py
from flask import Blueprint, jsonify
import os
import json
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

umbrel_lightning_api = Blueprint('umbrel_lightning_api', __name__)

def get_lightning_info():
    """
    Connect to the LND REST API on your Umbrel node to fetch basic Lightning node info.
    Assumes the LND REST API is accessible at the given host and port.
    """
    host = os.getenv("UMBREL_LIGHTNING_HOST")
    port = os.getenv("UMBREL_LIGHTNING_PORT", "8080")
    rpc_user = os.getenv("UMBREL_RPC_USER")
    rpc_pass = os.getenv("UMBREL_RPC_PASS")
    macaroon_hex = os.getenv("UMBREL_LIGHTNING_MACAROON")
    
    macaroon_hex = macaroon_hex.strip()
    if not (host and rpc_user and rpc_pass and macaroon_hex):
        return {"error": "Missing configuration for Umbrel Lightning API."}
    
    url = f"https://{host}:{port}/v1/getinfo"  # Using HTTPS as you mentioned
    headers = {'Grpc-Metadata-macaroon': macaroon_hex}
    
    try:
        response = requests.get(url, headers=headers, verify=False)  # verify=False if using self-signed certs
        data = response.json()
        return data
    except Exception as e:
        return {"error": str(e)}

@umbrel_lightning_api.route('/umbrel/lightning/getinfo', methods=['GET'])
def lightning_getinfo():
    data = get_lightning_info()
    if "error" in data:
        return jsonify({"error": data["error"]}), 500
    return jsonify(data)
