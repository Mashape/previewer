from compose.cli.command import get_project
from flask import Flask
from flask_hookserver import Hooks
from git import Repo

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

@hooks.hook('pull_request')
def pull_request(data, guid):
    if data['action'] == 'opened' or data['action'] == 'reopened':
      import pdb
      pdb.set_trace()
      repo = Repo.clone_from(data['repository']['ssh_url'], '/tmp/' + str(data['pull_request']['id']), None, env={'GIT_SSH_COMMAND': 'ssh -i /home/ubuntu/.ssh/id_rsa' })
      repo.remotes.origin.fetch('+refs/pull/*:refs/heads/pull/*')
      git = repo.git
      git.checkout('pull/' + str(data['number']) + '/merge')
      project = get_project('/tmp/' + data['pull_request']['id'] + '/')
      project.build()
      project.up()
      
