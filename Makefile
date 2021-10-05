SHELL = bash -o pipefail
BUILD		?= /tmp/build
MAKEDIR		:= $(dir $(realpath $(firstword $(MAKEFILE_LIST))))
SCRIPTDIR	:= $(MAKEDIR)/script
M		?= $(BUILD)/milestones
AIABVALUES	?= $(MAKEDIR)/omec.yaml
RESOURCEDIR	:= $(MAKEDIR)/resources

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
install_docker_helm: $(M)/install_docker_helm
install: $(M)/install

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


$(M)/pull_images: | $(M)/install_docker_helm
	./script/pull_images.sh
	touch $@

# Install Docker CE
## Set up the repository:
### Install packages to allow apt to use a repository over HTTPS
$(M)/install_docker_helm: | $(M)
	sudo ./script/install_docker_helm.sh
	sudo usermod -aG docker $$USER
	touch $@
	echo "Run newgrp docker and re-run make cmd"
	exit 0

$(M)/install_k3s: | $(M)/install_docker_helm $(M)/pull_images
	curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=$(K3S_VERSION) INSTALL_K3S_EXEC="--write-kubeconfig-mode=600 --flannel-backend=none --disable-network-policy --disable=traefik --cluster-cidr=10.42.0.0/16 --kube-apiserver-arg service-node-port-range=2000-36767" sh -s - --docker
	mkdir -p $(HOME)/.kube
	sudo cp -f /etc/rancher/k3s/k3s.yaml $(HOME)/.kube/config
	sudo chown $(shell id -u):$(shell id -g) $(HOME)/.kube/config
	export KUBECONFIG=$(HOME)/.kube/config; \
	kubectl apply -f $(RESOURCEDIR)/calico-tigera-operator.yaml; \
	kubectl apply -f $(RESOURCEDIR)/calico-custom-resources.yaml; \
	kubectl apply -f $(RESOURCEDIR)/multus-daemonset.yml
	sleep 15s;
	kubectl wait pod -n kube-system --for=condition=Ready --all
	touch $@

# UE images includes kernel module, ue_ip.ko
# which should be built in the exactly same kernel version of the host machine
$(BUILD)/openairinterface: | $(M)/install_docker_helm
	mkdir -p $(BUILD)
	cd $(BUILD); git clone https://github.com/opencord/openairinterface.git

$(M)/ue-image: | $(M)/install_k3s $(BUILD)/openairinterface
	cd $(BUILD)/openairinterface; \
	sudo docker build . --target lte-uesoftmodem \
		--build-arg build_base=omecproject/oai-base:1.1.0 \
		--file Dockerfile.ue \
		--tag omecproject/lte-uesoftmodem:1.1.0
	touch $@

$(M)/oaisim: | $(M)/ue-image  $(M)/deploy_omec
	sudo ip addr add 127.0.0.2/8 dev lo || true
	$(eval mme_iface=$(shell ip -4 route list default | awk -F 'dev' '{ print $$2; exit }' | awk '{ print $$1 }'))
	helm upgrade --install --namespace $(MODEL_NAME) oaisim helm-charts/oaisim -f $(AIABVALUES) \
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


/opt/cni/bin: | $(M)/install_k3s
	echo "Copy cni plugins"
	sudo cp $(RESOURCEDIR)/net-plugins/* /opt/cni/bin/
	sudo chmod +x /opt/cni/bin/*
	touch $@

# TODO: need to connect ONOS
$(M)/fabric: | $(M)/install_k3s /opt/cni/bin
	sudo apt install -y openvswitch-switch
	sudo ovs-vsctl --may-exist add-br br-s1u-net
	sudo ovs-vsctl --may-exist add-port br-s1u-net s1u-enb -- set Interface s1u-enb type=internal
	sudo ip addr add 11.1.1.111/24 dev s1u-enb  || true
	sudo ip link set s1u-enb up
	kubectl apply -f $(RESOURCEDIR)/router.yaml
	kubectl wait pod -n default --for=condition=Ready -l app=router --timeout=300s
	kubectl -n default exec router ip route add 16.0.0.0/8 via 13.1.1.110 || true
	kubectl delete net-attach-def sgi-net
	touch $@


$(M)/deploy_omec: | $(M)/install /opt/cni/bin $(M)/fabric $(M)/build_omec
	echo "Adding Model $(MODEL_NAME)"
	juju add-model $(MODEL_NAME)
	echo "deploying net-attach-def "
	kubectl apply -f $(RESOURCEDIR)/ovs-network.yaml --namespace $(MODEL_NAME) || true
	helm repo add incubator https://charts.helm.sh/incubator
	helm install cassandra incubator/cassandra --version "0.13.1" --values $(RESOURCEDIR)/cassandra_values.yaml -n $(MODEL_NAME)
	juju deploy ./bundle.yaml --trust
	kubectl wait pod -n $(MODEL_NAME) --for=condition=Ready -l app.kubernetes.io/name=spgwc --timeout=300s

$(M)/build_omec: | $(M)/build-hss $(M)/build-mme $(M)/build-spgwc $(M)/build-spgwu
	echo "Omec chart build done"
	touch $@

$(M)/build-hss: | $(M)
	echo "bundling hss charm"
	cd charm/hss && charmcraft pack -v
	touch $@
$(M)/build-mme: | $(M)
	echo "bundling mme charm"
	cd charm/mme && charmcraft pack -v
	touch $@
$(M)/build-spgwc: $(M)
	echo "bundling spgwc charm"
	cd charm/spgwc && charmcraft pack -v
	touch $@
$(M)/build-spgwu: $(M)
	echo "bundling spgwu charm"
	cd charm/spgwu && charmcraft pack -v
	touch $@

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

set-nodeport-range:
	sed -r '/^--service-node-port-range=.*$$/d' -i  /var/snap/microk8s/current/args/kube-apiserver && sed -r '1 i\--service-node-port-range=2000-36767' -i  /var/snap/microk8s/current/args/kube-apiserver
	microk8s stop
	microk8s start
	
reset-omec:
	juju remove-application spgwu || true
	juju remove-application spgwc || true
	juju remove-application mme || true
	juju remove-application hss || true
	#juju remove-application cassandra-k8s || true
	helm del cassandra -n $(MODEL_NAME) || true
	kubectl delete -f $(RESOURCEDIR)/ovs-network.yaml -n $(MODEL_NAME) || true
	juju destroy-model $(MODEL_NAME) --destroy-storage -y || true
	cd $(M); rm -f oaisim deploy_omec fabric


clean-oaisim:
	helm del oaisim -n $(MODEL_NAME) || true
	kubectl delete job ue-setup-if -n $(MODEL_NAME) || true
	kubectl delete job ue-teardown-if -n $(MODEL_NAME) || true
	cd $(M) && rm -rf oaisim || true

clean-omec-build: | clean-oaisim
	cd charm/hss && charmcraft clean
	cd charm/mme && charmcraft clean
	cd charm/spgwc && charmcraft clean
	cd charm/spgwu && charmcraft clean
	cd $(M) && rm -rf build-mme build-hss build-spgwc build-spgwu build_omec || true
