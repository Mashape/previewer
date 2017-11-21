import os
import re
import shutil
import json
import sys
import time
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


def cleanup_past_run(network_prefix, directory):
    if os.path.isdir(directory):
        project = get_project(directory)
        project.kill()
        project.remove_stopped()
        shutil.rmtree(directory)

    client = docker.from_env()
    client.images.prune()

    nginx_proxy = client.containers.get("nginx-proxy")
    if nginx_proxy is None:
        return True

    compose_network = client.networks.list([network_prefix + '_default'])[0]
    if compose_network is None:
        return True
    compose_network.disconnect(nginx_proxy)


def run_docker_compose(network_prefix, environment, working_directory):
    os.environ = environment
    project = get_project(working_directory)
    project.pull()
    project.build()
    project.up(detached=True)

    client = docker.from_env()
    client.images.prune()
    client.images.pull('jwilder/nginx-proxy')

    nginx_proxy = client.containers.get("nginx-proxy")
    if nginx_proxy is None:
        ports = {'80/tcp': '8111'}
        volumes = {
            '/var/run/docker.sock': {'bind': '/var/run/docker.sock', 'mode': 'ro'}}
        nginx_proxy = client.containers.run('jwilder/nginx-proxy',
                                            volumes=volumes,
                                            ports=ports,
                                            name="nginx-proxy",
                                            detach=True)

    compose_network = client.networks.list([network_prefix + '_default'])[0]
    if compose_network is None:
        compose_network = client.networks.create(network_prefix + '_default')
    compose_network.disconnect(nginx_proxy)
    compose_network.connect(nginx_proxy)


def branch(data):
    branch_name = str(data['ref']).split("/", 2)[-1]
    safebranch_name = SAFE_REGEX_PATTERN.sub(
        '', str(data['ref']).split("/")[-1])
    working_directory = '/tmp/' + \
        data['repository']['name'] + '/' + safebranch_name
    sub_domain = '.' + data['repository']['name'] + '.previewer.mashape.com'

    cleanup_past_run(safebranch_name, working_directory)
    if data['event'] == 'delete':
        return True

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
    pull_request_id = SAFE_REGEX_PATTERN.sub(
        '', str(data['pull_request']['id']))
    working_directory = '/tmp/' + \
        data['repository']['name'] + '/' + pull_request_id
    pr_number = data['number']
    sub_domain = '.' + data['repository']['name'] + '.previewer.mashape.com'
    branch_name = SAFE_REGEX_PATTERN.sub(
        '', str(data['pull_request']['head']['ref']))

    if data['action'] == 'closed' or data['action'] == 'synchronize':
        cleanup_past_run(pull_request_id, working_directory)

    if (data['action'] == 'opened' or
            data['action'] == 'reopened' or
            data['action'] == 'synchronize'):
        checkout_pr_merge(
            data['repository']['ssh_url'],
            working_directory,
            pr_number)
        environment = {}
        environment['KONG_VIRTUAL_HOST'] = branch_name + \
            '_pr_kong' + sub_domain
        environment['KONG_ADMIN_VIRTUAL_HOST'] = branch_name + \
            '_pr' + sub_domain
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


if __name__ == "__main__":
    main()
