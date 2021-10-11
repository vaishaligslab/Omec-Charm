# OMEC Charm

Open Mobiled Evolved Core (OMEC) is an opensource EPC (4G) Core
Consisten of MME,HSS,SPGWC and SPGWU components


## Steps for setup installation with k3s

### Install Docker and Helm
```
$ make install_docker_helm
```
Need to access docker with unprivledged access run below command
```
$ newgrp docker
```

### Install k3s, charmcraft, lxd and juju
Note: k3s clsuter is need to be accessible from non-root user. Will set kubeconfig path in non-root location
```
$ echo "export KUBECONFIG=~/.kube/config" >> ~/.bashrc
$ source ~/.bashrc
```
Config file will be copied through makefile with non-root user grp

```
$ make install
```
Above make rule will dpeloy all needed resources with required versions


**Docker:** v19.03.15

**Helm:** v3.5.4

**k3s:** "v1.20.7+k3s1"

**lxd:** 4.18/stable

**charmcraft:** latest/stable

**juju:** 2.9/stable


##  Build OMEC  charm
```
$ make build_omec
```
##  Deploy OMEC charm
```
$ make deploy_omec
```

Can check the status of charm through following command
```
watch -c juju status --color
```
Command to view logs
```
juju debug-log
```

### Build or deploy individual components e.g. spgwu
$ make build-\<component-name\> <br/>
$ make deploy-\<component-name\>
```
e.g.

$make build-spgwu
$make deploy-spgwu
```

## Deploy oaisim
```
$ make oaisim
```

## Cleanup oaisim
```
make clean-oaisim
```

## Cleanup omec applications
```
$ make reset-omec
```

TODO:
#1 Use cassandra charm instead of cassandra helm chart (Unable to implement  currently due to relations and cassandra charm stability issue)

#2 Deploy network-attachment-definition through charm for spgwu instead of deploying directly using kubectl.

#3 Use relations between all component intead of creating service through python-kubernetes-API

#4 Enhance bundle.yaml use. 


