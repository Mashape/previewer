# Previewer

## Manual Setup Instructions

1. https://705622348339.signin.aws.amazon.com/console
2. Create EC2 instance. Give it a public IP and 80GB of storage
3. Install docker per ( https://docs.docker.com/engine/installation/linux/docker-ce/ubuntu/#install-using-the-repository )
```
sudo apt-get update
sudo apt-get install \
    apt-transport-https \
    ca-certificates \
    curl \
    software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository \
   "deb [arch=amd64] https://download.docker.com/linux/ubuntu \
   $(lsb_release -cs) \
   stable"
sudo apt-get update
sudo apt-get install docker-ce
sudo usermod -aG docker ubuntu
```

4. Install docker-compose per
```
sudo curl -o /usr/local/bin/docker-compose -L "https://github.com/docker/compose/releases/download/1.15.0/docker-compose-$(uname -s)-$(uname -m)"
sudo chmod +x /usr/local/bin/docker-compose
```

5. Install previewer
```
sudo apt-get install -y git make python-virtualenv
git clone https://github.com/Mashape/previewer.git
cd previewer
vi main.py #change the GITHUB_WEBHOOKS_KEY
make setup
place a ssh private key with access to github at /home/ubuntu/.ssh/id_rsa
place the previewer.service unit file in /etc/systemd/system/previewer.system
sudo systemctl daemon-reload
sudo systemctl enable previewer
sudo systemctl start previewer
sudo systemctl status previewer #verify its running
sudo journalctl -u previewer  #view the logs
ssh -T git@github.com #verify we can access github
```

6. Setup a github webhook for http://IP:5000/hooks with content type `application/json` #TODO elastic IP
7. Push all events #TODO more restrictive
8. Make sure the ping event gets a pong response
9. Make a test PR in the repository (known bug the open pr webhook will timeout)
10. docker ps #should see proxy-nginx and the docker-compose containers running
11. create an ELB. Use port 5000 as the health check and send traffic from 80 to 8111
12. setup R53 to point to the ELB ( https://mashape.signin.aws.amazon.com/console )