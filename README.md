# OMEC Charm

Open Mobile Evolved Core (OMEC) is an opensource EPC (4G) Core
Consisting of the MME, HSS, SPGWC and SPGWU components.

## Usage

This section details the steps needed for installing OMEC using k3s.

### Pre-requisites

Install Docker and Helm:

```bash
$ make install_docker_helm
```

Configure group membership to use `docker`: 

```bash
$ newgrp docker
```

Install OMEC pre-requisites:

```bash
$ make install
```

The above comment will deploy all needed resources with required versions:

| Software   | Version       |
|------------|---------------|
| Docker     | 19.03.15      |
| Helm       | 3.5.4         |
| k3s        | v1.20.7+k3s1  |
| lxd        | 4.18/stable   |
| charmcraft | latest/stable |

> Note: k3s clsuter is need to be accessible from non-root user. Will set kubeconfig path in non-root location
> You can move the kubeconfig file to `bashrc`:
> 
> ```bash
> $ echo "export KUBECONFIG=~/.kube/config" >> ~/.bashrc
> $ source ~/.bashrc
> ```


###  Build OMEC  charm

```bash
$ make build_omec
```

###  Deploy OMEC charms

```bash
$ make deploy_omec
```

Check the charm status:

```bash
watch -c juju status --color
```

View logs:

```bash
juju debug-log
```

### Build or deploy individual components e.g. spgwu

```bash
$ make build-\<component-name\> <br/>
$ make deploy-\<component-name\>
```

Example:

```bash
$ make build-spgwu
$ make deploy-spgwu
```

### Deploy oaisim

```bash
$ make oaisim
```

### Cleanup oaisim

```bash
$ make clean-oaisim
```

### Cleanup OMEC applications

```bash
$ make reset-omec
```

## TODO

1. Use cassandra charm instead of cassandra helm chart (Unable to implement  currently due to relations and cassandra charm stability issue)
2. Deploy network-attachment-definition through charm for spgwu instead of deploying directly using kubectl.
3. Use relations between all component intead of creating service through python-kubernetes-API
4. Enhance `bundle.yaml` use. 
