from flask import Flask
from flask_hookserver import Hooks

app = Flask(__name__)
app.config['VALIDATE_SIGNATURE'] = False
app.config['GITHUB_WEBHOOKS_KEY'] = 'my_secret_key'

@app.route("/")
def hello():
    return "Hello World!"

hooks = Hooks(app, url='/hooks')

@hooks.hook('ping')
def ping(data, guid):
    return 'pong'
