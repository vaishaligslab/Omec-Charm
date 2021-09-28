SHELL = bash -o pipefail

.PHONY: build

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


deploy: deploy-deps deploy-spgwu deploy-hss deploy-mme deploy-spgwc

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


