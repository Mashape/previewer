import os
import io
import re
import shutil
import json
import sys
import time
import subprocess
import docker
import yaml
from git.exc import GitCommandError
from compose.cli.command import get_project
from compose.config.errors import ComposeFileNotFound
from docker.errors import APIError
from git import Repo
from github3 import login

SAFE_REGEX_PATTERN = re.compile('[\W_]+')
GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
DOMAIN = os.environ['DOMAIN']


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
                    elif data['event'] in branch_events:
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


def cleanup_past_run(network_prefix, directory):
    if os.path.isdir(directory):
        try:
            project = get_project(directory)
            project.kill()
            project.remove_stopped()
        except ComposeFileNotFound:
            pass
        shutil.rmtree(directory)

    client = docker.from_env()

    try:
        nginx_proxy = client.containers.list(
            filters={'name': 'nginx-proxy'}).pop(0)
    except IndexError:
        return True

    compose_network = None
    try:
        for network in client.networks.list([network_prefix + '_default']):
            if network.name == network_prefix + '_default':
                compose_network = network
                break
    except IndexError:
        return True

    if not compose_network:
        return True

    try:
        print('disconnect ' + compose_network.name)
        compose_network.disconnect(nginx_proxy)
    except APIError:
        pass

    client.images.prune()
    client.containers.prune()
    client.networks.prune()


def run_docker_compose(network_prefix, environment, working_directory):
    client = docker.from_env()
    client.images.pull('jwilder/nginx-proxy')

    try:
        nginx_proxy = client.containers.list(
            filters={'name': 'nginx-proxy'}).pop(0)
    except IndexError:
        ports = {
          '8000/tcp': '8000',
          '8001/tcp': '8001',
          '8002/tcp': '8002',
          '8003/tcp': '8003',
        }
        volumes = {
            '/var/run/docker.sock': {'bind': '/tmp/docker.sock', 'mode': 'ro'},
            os.getcwd() + '/nginx-proxy': {'bind': '/app/'}
        }
        nginx_proxy = client.containers.run('jwilder/nginx-proxy',
                                            ports=ports,
                                            volumes=volumes,
                                            name="nginx-proxy",
                                            detach=True)

    if not os.path.isfile(working_directory + '/docker-compose.yml'):
        print "No docker-compose file found"
        return True

    compose_network = None
    try:
        for network in client.networks.list([network_prefix + '_default']):
            if network.name == network_prefix + '_default':
                compose_network = network
                break
    except IndexError:
        pass

    if compose_network:
        try:
            print('disconnect ' + compose_network.name)
            compose_network.disconnect(nginx_proxy)
        except APIError:
            pass
    else:
        compose_network = client.networks.create(network_prefix + '_default')
    
    compose_network.connect(nginx_proxy)
    
    os.environ = environment
    project = get_project(working_directory)
    project.pull()
    project.build(pull=True)
    project.up(detached=True)

    return True


def branch(data):
    branch_name = data['ref']
    if data['event'] == 'push':
        branch_name = str(data['ref']).split("/", 2)[-1]

    safebranch_name = SAFE_REGEX_PATTERN.sub(
        '', str(data['ref']).split("/")[-1])
    working_directory = '/tmp/' + \
        data['repository']['name'] + '_' + safebranch_name
    sub_domain = '.' + data['repository']['name'] + DOMAIN
    network_prefix = str(data['repository']['name'] + '_' + safebranch_name).replace("_", "").replace("-", "")

    cleanup_past_run(network_prefix, working_directory)
    if data['event'] == 'delete':
        return True

    checkout_branch(
        data['repository']['ssh_url'],
        working_directory,
        branch_name)

    environment = {}
    environment['VIRTUAL_HOST'] = safebranch_name + sub_domain
    environment['NPM_TOKEN'] = os.environ('NPM_TOKEN')
    run_docker_compose(network_prefix, environment, working_directory)

    print "done branch should be up"

    return True


def pull_request(data):
    pull_request_id = SAFE_REGEX_PATTERN.sub(
        '', str(data['pull_request']['id']))
    working_directory = '/tmp/' + \
        data['repository']['name'] + '_' + pull_request_id
    pr_number = data['number']
    sub_domain = '.' + data['repository']['name'] + DOMAIN
    branch_name = SAFE_REGEX_PATTERN.sub(
        '', str(data['pull_request']['head']['ref']))
    network_prefix = str(data['repository']['name'] + pull_request_id).replace("_", "").replace("-", "")

    if data['action'] == 'closed' or data['action'] == 'synchronize':
        cleanup_past_run(network_prefix, working_directory)

    if (data['action'] == 'opened' or
            data['action'] == 'reopened' or
            data['action'] == 'synchronize'):
        checkout_pr_merge(
            data['repository']['ssh_url'],
            working_directory,
            pr_number)
        environment = {}
        environment['VIRTUAL_HOST'] = branch_name + \
            '_pr' + sub_domain
        run_docker_compose(network_prefix, environment, working_directory)

    if data['action'] == 'opened' or data['action'] == 'reopened':
        gh = login(token=GITHUB_TOKEN)
        issue = gh.issue(data['organization']['login'],
                         data['pull_request']['head']['repo']['name'],
                         data['number'])
        
        docker_yaml = {'x-previewer-url' : ''}
        with io.open(working_directory + '/docker-compose.yml') as stream:
            docker_yaml = yaml.load(stream)
        
        issue.create_comment(
            'The preview environment: http://' +
            environment['VIRTUAL_HOST'] + docker_yaml['x-previewer-url'])

    print "pr should be done"

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
    try:
        git.checkout(branch_name)
        return True
    except GitCommandError:
        pass


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


if __name__ == "__main__":
    main()
