from flask import Flask, request, abort

app = Flask(__name__)

@app.route("/", methods=['GET'])
def index():
    return "食刻機器人運行中"

if __name__ == "__main__":
    app.run()