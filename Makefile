SHELL = bash -o pipefail
BUILD		?= /tmp/build
MAKEDIR		:= $(dir $(realpath $(firstword $(MAKEFILE_LIST))))
SCRIPTDIR	:= $(MAKEDIR)/script
M		?= $(BUILD)/milestones

DOCKER_VERSION	?= 19.03.15
HELM_VERSION	?= v3.5.4
K3S_VERSION ?= "v1.20.7+k3s1"

LXD_VERSION ?= 4.18/stable
CHARMCRAFT_VERSION ?= latest/stable
JUJU_VERSION ?= 2.9/stable
MICROK8S_VERSION ?= 1.21/stable


MODEL_NAME ?= omec

cpu_family	:= $(shell lscpu | grep 'CPU family:' | awk '{print $$3}')
cpu_model	:= $(shell lscpu | grep 'Model:' | awk '{print $$2}')
os_vendor	:= $(shell lsb_release -i -s)
os_release	:= $(shell lsb_release -r -s)

.PHONY: build

deploy_omec: $(M)/system-check $(M)/deploy_omec

build: build-hss build-mme build-spgwc build-spgwu

build-hss:
	echo "bundling hss charm"
	cd charm/hss && charmcraft pack -v
build-mme:
	echo "bundling mme charm"
	cd charm/mme && charmcraft pack -v
build-spgwc:
	echo "bundling spgwc charm"
	cd charm/spgwc && charmcraft pack -v
build-spgwu:
	echo "bundling spgwu charm"
	cd charm/spgwu && charmcraft pack -v

$(M):
	mkdir -p $(M)

$(M)/system-check: | $(M)
	@if [[ $(cpu_family) -eq 6 ]]; then \
		if [[ $(cpu_model) -lt 60 ]]; then \
			echo "FATAL: haswell CPU or newer is required."; \
			exit 1; \
		fi \
	else \
		echo "FATAL: unsupported CPU family."; \
		exit 1; \
	fi
	@if [[ $(os_vendor) =~ (Ubuntu) ]]; then \
		if [ "$(os_release)" == "20.04" ]; then \
			echo "$(os_vendor) $(os_release) is supported and tested."; \
		elif [ "$(os_release)" \> "20.04" ]; then \
            echo "WARN: $(os_vendor) $(os_release) has not been tested."; \
		else \
            echo "ERR: $(os_vendor) $(os_release) not supported for omec-automation along with charmed operator SDK"; \
	    exit 1; \
		fi; \
		if dpkg --compare-versions 4.15 gt $(shell uname -r); then \
			echo "FATAL: kernel 4.15 or later is required."; \
			echo "Please upgrade your kernel by running" \
			"apt install --install-recommends linux-generic-hwe-$(os_release)"; \
			exit 1; \
		fi \
	else \
		echo "FAIL: unsupported OS."; \
		exit 1; \
	fi
	touch $@

$(M)/charmcraft: | $(M)
	sudo snap install charmcraft --classic --channel=$(CHARMCRAFT_VERSION)
	echo "$(tput setaf 2)Successfully installed chramcraft$(tput sgr0)"
	touch $@

$(M)/lxd: | $(M)
	sudo snap install lxd --classic --channel=$(LXD_VERSION)
	sudo adduser $$USER lxd
	lxd init --auto
	echo "$(tput setaf 2)Successfully installed lxd$(tput sgr0)"
	touch $@

$(M)/microk8s: | $(M)
	sudo snap install --classic microk8s --channel=$(MICROK8S_VERSION)
	sudo usermod -aG microk8s $(whoami)
	sudo microk8s status --wait-ready
	sudo microk8s enable storage dns ingress multus
	sudo snap alias microk8s.kubectl kubectl
	echo "$(tput setaf 2)Successfully installed microk8s$(tput sgr0)"
	touch $@

$(M)/juju: | $(M)
	sudo snap install juju --classic --channel=$(JUJU_VERSION)
	export KUBECONFIG=$(HOME)/.kube/config; \
	juju add-k8s k3s; \
	juju bootstrap k3s k3s;
	echo "$(tput setaf 2)Successfully installed juju$(tput sgr0)"
	echo "$(tput setaf 2)Juju instalation and cluster setup done Done$(tput sgr0)"
	touch $@

$(M)/install: | $(M)/charmcraft $(M)/lxd $(M)/install_k3s $(M)/juju

# Install Docker CE
## Set up the repository:
### Install packages to allow apt to use a repository over HTTPS
$(M)/install_docker:
	sudo apt-get update
	sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common jq socat curl
	curl https://releases.rancher.com/install-docker/19.03.sh | sh
	sudo usermod -aG docker $$USER
	touch $@

$(M)/install_helm:
	wget https://get.helm.sh/helm-$(HELM_VERSION)-linux-amd64.tar.gz
	tar -xzvf helm-$(HELM_VERSION)-linux-amd64.tar.gz
	sudo mv linux-amd64/helm /usr/local/bin/
	sudo rm -rf linux-amd64 helm-$(HELM_VERSION)-linux-amd64.tar.gz
	touch $@

$(M)/install_k3s: | $(M)/install_docker $(M)/install_helm
	curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=${K3S_VERSION} INSTALL_K3S_EXEC="--write-kubeconfig-mode=600 --flannel-backend=none --disable-network-policy --disable=traefik --cluster-cidr=10.42.0.0/16 --kube-apiserver-arg service-node-port-range=2000-36767" sh -s - --docker
	mkdir -p $(HOME)/.kube
	sudo cp -f /etc/rancher/k3s/k3s.yaml $(HOME)/.kube/config
	sudo chown $(shell id -u):$(shell id -g) $(HOME)/.kube/config
	export KUBECONFIG=$(HOME)/.kube/config; \
	kubectl create -f script/calico-tigera-operator.yaml; \
	kubectl create -f script/calico-custom-resources.yaml; \
	kubectl create -f script/multus-daemonset.yml
	touch $@

# UE images includes kernel module, ue_ip.ko
# which should be built in the exactly same kernel version of the host machine
$(BUILD)/openairinterface: | $(M)/setup
	mkdir -p $(BUILD)
	cd $(BUILD); git clone https://github.com/opencord/openairinterface.git

$(M)/ue-image: | $(M)/k8s-ready $(BUILD)/openairinterface
	cd $(BUILD)/openairinterface; \
	sudo docker build . --target lte-uesoftmodem \
		--build-arg build_base=omecproject/oai-base:1.1.0 \
		--file Dockerfile.ue \
		--tag omecproject/lte-uesoftmodem:1.1.0
	touch $@

$(M)/oaisim: | $(M)/ue-image $(M)/deploy_omec
	sudo ip addr add 127.0.0.2/8 dev lo || true
	$(eval mme_iface=$(shell ip -4 route list default | awk -F 'dev' '{ print $$2; exit }' | awk '{ print $$1 }'))
	helm upgrade --install --namespace $(MODEL_NAME) oaisim cord/oaisim -f $(AIABVALUES) \
		--set config.enb.networks.s1_mme.interface=$(mme_iface) \
		--set images.pullPolicy=IfNotPresent
	kubectl rollout status -n omec statefulset ue
	@timeout 60s bash -c \
	"until ip addr show oip1 | grep -q inet; \
	do \
		echo 'Waiting for UE 1 gets IP address'; \
		sleep 3; \
	done"
	touch $@


$(M)/omec: | $(M)/install /opt/cni/bin/simpleovs /opt/cni/bin/static $(M)/fabric
$(M)/deploy_omec: | $(M)/install
	juju deploy ./bundle.yaml --trust

deploy-deps:
	juju add-model omec || true

deploy-hss:
	juju deploy cassandra-k8s
	echo "deploying hss charm"
	cd charm/hss && juju deploy ./hss_ubuntu-20.04-amd64.charm --trust --resource hss-image=vaishalinicky/cqlshimage:v5  --debug
deploy-mme:
	echo "deploying mme charm"
	cd charm/mme && juju deploy ./mme_ubuntu-20.04-amd64.charm --trust --resource mme-image=amitinfo2k/nucleus-mme:9f86f87 --debug
deploy-spgwc:
	echo "deploying spgwc charm"
	cd charm/spgwc && juju deploy ./spgwc_ubuntu-20.04-amd64.charm --trust --resource spgwc-image=amitinfo2k/ngic-cp:1.9.0 --debug
deploy-spgwu:
	echo "deploying net-attach-def "
	cd script && ./install_dep.sh || true
	echo "deploying dp charm"
	cd charm/spgwu && juju deploy ./spgwu_ubuntu-20.04-amd64.charm --trust --resource spgwu-image=amitinfo2k/ngic-dp:1.9.0 --debug

multus:
	microk8s enable multus
	sudo cp net-plugins/* /var/snap/microk8s/current/opt/cni/bin/

set-nodeport-range:
	sed -r '/^--service-node-port-range=.*$$/d' -i  /var/snap/microk8s/current/args/kube-apiserver && sed -r '1 i\--service-node-port-range=2000-36767' -i  /var/snap/microk8s/current/args/kube-apiserver
	microk8s stop
	microk8s start
	
clean:
	juju remove-application spgwu || true
	juju remove-application spgwc || true
	juju remove-application mme || true
	juju remove-application hss || true
	juju remove-application cassandra-k8s || true
	juju destroy-model omec --destroy-storage -y

