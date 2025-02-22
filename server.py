# from server import Flask, request, jsonify
from flask import Flask
app = Flask(__name__)

@app.route("/")
def home():
    return "Flask server running!"

# Example: Handling OAuth callback
@app.route("/callback")
def callback():
    # auth_code = request.args.get("code")  # OAuth sends back a code
    # return f"Received authorization code: {auth_code}"
    return "Received authorization code"
if __name__ == "__main__":
    app.run(port=5000)  # Runs on http://127.0.0.1:5000
