#!/bin/bash
######################################################
# @author Amit Wankhede
# @purpose This script will install the dependancies
#
######################################################

docker_version=19.03.15
helm_version=v3.5.4

# Install docker
install_docker(){

# Install Docker CE
## Set up the repository:
### Install packages to allow apt to use a repository over HTTPS
apt-get update && apt-get install -y apt-transport-https ca-certificates curl software-properties-common jq socat curl

### Add Docker’s official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -

### Add Docker apt repository.
add-apt-repository \
  "deb [arch=amd64] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) \
  stable"

## Install Docker CE.
pkg_version=$(apt-cache madison docker-ce | grep ${docker_version} | head -n 1 | cut -d ' ' -f 4)
apt-get update && apt-get install -y docker-ce=${pkg_version}

mkdir -p /etc/systemd/system/docker.service.d

# Restart docker.
systemctl daemon-reload
systemctl restart docker

}

install_helm(){

        wget https://get.helm.sh/helm-${helm_version}-linux-amd64.tar.gz
        tar -xzvf helm-${helm_version}-linux-amd64.tar.gz
        mv linux-amd64/helm /usr/local/bin/
        rm -rf linux-amd64 helm-${helm_version}-linux-amd64.tar.gz

}

update_iptables(){

	firewall-cmd --permanent --direct --add-rule ipv4 filter INPUT 1 -i cni0 -s 10.42.0.0/16 -j ACCEPT
	firewall-cmd --permanent --direct --add-rule ipv4 filter FORWARD 1 -s 10.42.0.0/15 -j ACCEPT
	firewall-cmd --reload

}


swap_off(){

    sudo swapoff -a && sudo sysctl -w vm.swappiness=0
    sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab

}

install_mpeg(){

sudo add-apt-repository -y ppa:jonathonf/ffmpeg-4
sudo apt-get update -y
sudo apt-get install -y ffmpeg

}


install_docker
install_helm
swap_off
install_mpeg

