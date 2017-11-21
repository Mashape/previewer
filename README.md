# Previewer

## WARNING

**DO NOT RUN THIS ON A PUBLIC REPOSITORY BAD THINGS WILL HAPPEN**

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
make setup
place a ssh private key with access to github at /home/ubuntu/.ssh/id_rsa
place the previewer.service unit files in /etc/systemd/system/previewer-[web|task].system
edit the previewer-[web|task].system file and update the two changeme env variables
sudo systemctl daemon-reload
sudo systemctl enable previewer-web
sudo systemctl enable previewer-task
sudo systemctl start previewer-web
sudo systemctl start previewer-task
sudo systemctl status previewer-web #verify its running
sudo systemctl status previewer-task #verify its running
sudo journalctl -u previewer-web  #view the logs
sudo journalctl -u previewer-task  #view the logs
ssh -T git@github.com #verify we can access github
```

6. Setup a github webhook for http://IP:5000/hooks with content type `application/json` #TODO elastic IP
7. Select the individual events create, delete, pull request and push
8. Make sure the ping event gets a pong response
9. Make a test PR in the repository
10. docker ps #should see proxy-nginx and the docker-compose containers running
11. create an ELB. Use port 5000 as the health check and send traffic from 80 to 8111
12. setup R53 to point to the ELB ( https://mashape.signin.aws.amazon.com/console )

## Adding Your Project to Previewer

1. Make sure my github user (hutchic) can clone the repository
2. Setup a github webhook for http://IP:5000/hooks with content type application/json #TODO elastic IP
3. Select the individual events create, delete, pull request and push
4. Get the previewer webhook secret out of 1password
5. Make sure the ping event gets a pong response
6. Make a test PR in the repository
7. setup R53 to point to the ELB ( https://mashape.signin.aws.amazon.com/console )

## Adding Your IP

Login to 705622348339.signin.aws.amazon.com/console and edit the security group sg-79786d09. Be sure to note
in the description `who - where` the IP exception is for. Set yourself a reminder to clean up locations that 
are temporary (coffee shop, library, customer premises etc)
