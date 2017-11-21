import os
import re
import subprocess
import shutil
import json
import sys
import time
from subprocess import PIPE
from datetime import datetime
import docker
from compose.cli.command import get_project
from git import Repo
from github3 import login

SAFE_REGEX_PATTERN = re.compile('[\W_]+')
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']


def main():
    while True:
        time.sleep(5)
        data = {}
        if not os.path.exists('/tmp/previewer'):
            os.makedirs('/tmp/previewer')
        files = os.listdir('/tmp/previewer')
        for instruction_file in files:
            try:
                with open('/tmp/previewer/' + instruction_file) as json_data:
                    data = json.load(json_data)

                    branch_events = ['create', 'push', 'delete']
                    if data['event'] == 'pull_request':
                        pull_request(data)
                    if data['event'] in branch_events:
                        branch(data)
                    else:
                        print(
                            'Dont understand webhook action of ' +
                            data['event'])
            except BaseException:
                os.remove('/tmp/previewer/' + instruction_file)
                print "Unexpected error:", sys.exc_info()[0]
                raise
            os.remove('/tmp/previewer/' + instruction_file)


def cleanup_past_run(directory):
    if os.path.isdir(directory):
        client = docker.from_env()
        client.networks.list(names='kongadmin_default')[
            0].disconnect('nginx-proxy')

        project = get_project(directory)
        project.kill()
        project.remove_stopped()
        shutil.rmtree(directory)


def run_docker_compose(network_prefix, environment, working_directory):
    docker_helper = DockerHelper()
    docker_helper.clean_old_images()
    docker_helper.pull_container_image('jwilder/nginx-proxy')
    docker_helper.create_network(network_prefix + '_default')
    containerArgs = [
        "-v",
        "/var/run/docker.sock:/tmp/docker.sock:ro",
        "-p",
        "8111:80"]
    docker_helper.run_container(
        'nginx-proxy',
        'jwilder/nginx-proxy',
        containerArgs)
    docker_helper.container_join_network(
        network_prefix + '_default', 'nginx-proxy')

    os.environ = environment
    project = get_project(working_directory)
    project.pull()
    project.build()
    project.up(detached=True)

    docker_helper.prune_all()


def branch(data):
    branch_name = str(data['ref']).split("/", 2)[-1]
    safebranch_name = SAFE_REGEX_PATTERN.sub('', str(data['ref']).split("/")[-1])
    working_directory = '/tmp/' + \
        data['repository']['name'] + '/' + safebranch_name
    sub_domain = '.' + data['repository']['name'] + '.previewer.mashape.com'

    cleanup_past_run(working_directory)
    if data['event'] == 'delete':
        return True

    docker_helper = DockerHelper()
    docker_helper.container_disconnect_network(
        safebranch_name + '_default', 'nginx-proxy')
    checkout_branch(
        data['repository']['ssh_url'],
        working_directory,
        branch_name)

    environment = {}
    environment['KONG_VIRTUAL_HOST'] = safebranch_name + '_kong' + sub_domain
    environment['KONG_ADMIN_VIRTUAL_HOST'] = safebranch_name + sub_domain
    run_docker_compose(safebranch_name, environment, working_directory)

    return True


def pull_request(data):
    pull_request_id = SAFE_REGEX_PATTERN.sub('', str(data['pull_request']['id']))
    working_directory = '/tmp/' + \
        data['repository']['name'] + '/' + pull_request_id
    pr_number = data['number']
    sub_domain = '.' + data['repository']['name'] + '.previewer.mashape.com'
    branch_name = SAFE_REGEX_PATTERN.sub(
        '', str(data['pull_request']['head']['ref']))

    if data['action'] == 'closed' or data['action'] == 'synchronize':
        cleanup_past_run(working_directory)
        dockerHelper = DockerHelper()
        docker_helper.container_disconnect_network(
            pull_request_id + '_default', 'nginx-proxy')

    if (data['action'] == 'opened' or
            data['action'] == 'reopened' or
            data['action'] == 'synchronize'):
        checkout_pr_merge(
            data['repository']['ssh_url'],
            working_directory,
            pr_number)
        environment = {}
        environment['KONG_VIRTUAL_HOST'] = branch_name + '_pr_kong' + sub_domain
        environment['KONG_ADMIN_VIRTUAL_HOST'] = branch_name + '_pr' + sub_domain
        run_docker_compose(pull_request_id, environment, working_directory)

    if data['action'] == 'opened' or data['action'] == 'reopened':
        gh = login(token=GITHUB_TOKEN)
        issue = gh.issue(data['organization']['login'],
                         data['pull_request']['head']['repo']['name'],
                         data['number'])
        issue.create_comment(
            'The preview environment: http://' +
            environment['KONG_ADMIN_VIRTUAL_HOST'])
    return True


def checkout_branch(ssh_url, working_directory, branch_name):
    if os.path.isdir(working_directory):
        repo = Repo(working_directory)
        repo.remotes.origin.fetch()
    else:
        repo = Repo.clone_from(
            ssh_url, working_directory, None, env={
                'GIT_SSH_COMMAND': 'ssh -i /home/ubuntu/.ssh/id_rsa'})
    git = repo.git
    git.checkout(branch_name)


def checkout_pr_merge(ssh_url, working_directory, pr_number):
    if os.path.isdir(working_directory):
        repo = Repo(working_directory)
        repo.remotes.origin.fetch()
    else:
        repo = Repo.clone_from(
            ssh_url, working_directory, None, env={
                'GIT_SSH_COMMAND': 'ssh -i /home/ubuntu/.ssh/id_rsa'})
        repo.remotes.origin.fetch('+refs/pull/*:refs/heads/pull/*')
    git = repo.git
    git.checkout('pull/' + str(pr_number) + '/merge')


class NiceLogger:
    def log(self, message):
        datenow = datetime.today().strftime('%d-%m-%Y %H:%M:%S')
        print "{0} |  {1}".format(datenow, message)


class DockerHelper:
    niceLogger = NiceLogger()

    def prune_all(self):
        command = ["docker", "system", "prune", "--force"]
        self.run_command(command)

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

    def container_disconnect_network(self, networkName, containerName):
        command = [
            "docker",
            "network",
            "disconnect",
            networkName,
            containerName]
        self.run_command(command)

    def container_join_network(self, networkName, containerName):
        command = ["docker", "network", "connect", networkName, containerName]
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

    def run_container_with_exec(
            self,
            containerName,
            containerImage,
            execCommand,
            args):
        command = ["docker", "run", "-d", "--name", containerName]
        command.extend(args)
        command.append(containerImage)
        command.append(execCommand)

        self.run_command(command)

    def run_command(self, command):
        debugcommand = " - {0}".format(" ".join(command))
        self.niceLogger.log(debugcommand)

        popen = subprocess.Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        popen.wait()  # wait for docker to complete

        return popen


if __name__ == "__main__":
    main()
