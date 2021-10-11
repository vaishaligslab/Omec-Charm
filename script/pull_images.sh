#!/bin/bash

echo "Pull required images"
docker pull omecproject/pod-init:1.0.0
docker pull amitinfo2k/nucleus-mme:2.0.6-d93f862
docker pull amitinfo2k/c3po-hssdb:master-deaea91
docker pull amitinfo2k/c3po-hss:master-deaea91
docker pull amitinfo2k/ngic-cp:1.9.0
docker pull amitinfo2k/ngic-dp:1.9.0
docker pull docker.io/amitinfo2k/go-tcpdump:1.0.0
docker pull quay.io/stackanetes/kubernetes-entrypoint:v0.3.1
docker pull omecproject/lte-softmodem:1.1.0
docker pull docker.io/omecproject/omec-cni:1.0.0
docker pull opencord/quagga
docker pull docker.io/calico/node:v3.19.0
docker pull docker.io/calico/cni:v3.19.0
docker pull docker.io/calico/pod2daemon-flexvol:v3.19.0
docker pull docker.io/calico/kube-controllers:v3.19.0
docker pull calico-typha-5468fcdc98-5szql
docker pull cassandra:2.1.20
docker pull jujusolutions/charm-base:ubuntu-20.04
docker pull jujusolutions/jujud-operator:2.9.14

