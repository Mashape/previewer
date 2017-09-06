import os
import subprocess
from subprocess import PIPE
from datetime import datetime
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
        workingDirectory = '/tmp/' + str(data['pull_request']['id']) #warning might need to sanitize this
        prNumber = data['number']
    
        checkout_pr_merge(data['repository']['ssh_url'], workingDirectory, prNumber)
          
        dockerHelper = DockerHelper()
        dockerHelper.clean_old_images()
        dockerHelper.pull_container_image('jwilder/nginx-proxy')
        dockerHelper.create_network(str(data['pull_request']['id']) + '_default')
        containerArgs = ["-v", "/var/run/docker.sock:/tmp/docker.sock:ro", "-p", "8111:80"]
        dockerHelper.run_container('nginx-proxy', 'jwilder/nginx-proxy', containerArgs)
        
        project = get_project(workingDirectory)
        project.build()
        project.up()

def checkout_pr_merge(sshUrl, workingDirectory, prNumber):
    if os.path.isdir(workingDirectory) == True:
        repo = Repo(workingDirectory)
    else:
        repo = Repo.clone_from(sshUrl, workingDirectory, None, env={'GIT_SSH_COMMAND': 'ssh -i /home/ubuntu/.ssh/id_rsa' })
    repo.remotes.origin.fetch('+refs/pull/*:refs/heads/pull/*')
    git = repo.git
    git.checkout('pull/' + str(prNumber) + '/merge')

def run_nginx_proxy():
    dockerHelper = DockerHelper()


class NiceLogger:
    def log(self, message):
        datenow = datetime.today().strftime('%d-%m-%Y %H:%M:%S')
        print("{0} |  {1}".format(datenow, message))


class DockerHelper:
    niceLogger = NiceLogger()

    def clean_old_images(self):
        command = ["docker", "images", "-q", "-f", "dangling=true"]
        image_ids = self.run_command(command)

        for id in image_ids.stdout.readlines():
            id = id.decode("utf-8")
            id = id.replace("\n", "")

            self.niceLogger.log("Removing container image id " + id)
            command = ["docker", "rmi", "-f", str(id)]
            self.run_command(command)

    def remove_container(self, containerName):
        command = ["docker", "rm", "-f", containerName]
        self.run_command(command)
        self.niceLogger.log(" - Removed " + containerName)

    def create_network(self, networkName):
        command = ["docker", "network", "create", networkName]
        self.run_command(command)

    def pull_container_image(self, containerImage):
        command = ["docker", "pull", containerImage]
        self.run_command(command)
        self.niceLogger.log(" - Pulled " + containerImage)

    def run_container(self, containerName, containerImage, args):
        command = ["docker", "run", "-d", "--name", containerName]
        command.extend(args)
        command.append(containerImage)

        popen = self.run_command(command)

        error = popen.stderr.readline().decode("utf-8")

        if error != "":
            error = error.replace("\n", "")
            self.niceLogger.log("An error occurred:" + error)
        else:
            id = popen.stdout.readline().decode("utf-8")
            id = id.replace("\n", "")
            self.niceLogger.log(" - New container ID " + id)

    def run_container_with_exec(self, containerName, containerImage, execCommand, args):
        command = ["docker", "run", "-d", "--name", containerName]
        command.extend(args)
        command.append(containerImage)
        command.append(execCommand)

        self.run_command(command)

    def run_command(self, command):
        debugcommand = " - {0}".format(" ".join(command))
        self.niceLogger.log(debugcommand)

        popen = subprocess.Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        popen.wait() # wait for docker to complete

        return popen
