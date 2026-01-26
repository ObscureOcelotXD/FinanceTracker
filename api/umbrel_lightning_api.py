# api/umbrel_lightning_api.py
from flask import Blueprint, jsonify
import os
import json
import requests
import urllib3
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
    host = os.getenv("UMBREL_LIGHTNING_HOST") or os.getenv("UMBREL_TAILSCALE_IP") or os.getenv("UMBREL_HOST")
    port = os.getenv("UMBREL_LIGHTNING_PORT", "8080")
    macaroon_hex = os.getenv("UMBREL_LIGHTNING_MACAROON") or os.getenv("UMBREL_LND_MACAROON_HEX")
    if not host:
        return {"error": "Missing UMBREL_LIGHTNING_HOST (or UMBREL_TAILSCALE_IP/UMBREL_HOST)."}
    if not macaroon_hex:
        return {"error": "Missing UMBREL_LIGHTNING_MACAROON (hex)."}
    macaroon_hex = macaroon_hex.strip()
    
    url = f"https://{host}:{port}/v1/getinfo"  # Using HTTPS as you mentioned
    headers = {'Grpc-Metadata-macaroon': macaroon_hex}
    verify_setting = os.getenv("UMBREL_LIGHTNING_VERIFY_SSL")
    ca_bundle = os.getenv("UMBREL_LIGHTNING_CA_BUNDLE")
    if ca_bundle:
        verify = ca_bundle
    elif verify_setting is None:
        verify = False
    else:
        verify = verify_setting.strip().lower() in {"1", "true", "yes", "y", "on"}
    if verify is False:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    try:
        response = requests.get(url, headers=headers, verify=verify, timeout=15)
        if not response.ok:
            return {"error": f"LND HTTP {response.status_code}", "detail": response.text[:500]}
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
