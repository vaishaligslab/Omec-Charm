SHELL = bash -o pipefail

.PHONY: build

build: build-hss build-mme build-spgwc

build-hss:
	echo "bundling hss charm"
	cd charm/hss && charmcraft pack -v
build-mme:
	echo "bundling mme charm"
	cd charm/mme && charmcraft pack -v
build-spgwc:
	echo "bundling spgwc charm"
	cd charm/spgwc && charmcraft pack -v

deploy: deploy-hss deploy-mme deploy-spgwc

deploy-hss:
	juju add-model development
	juju deploy cassandra-k8s
	echo "deploying hss charm"
	cd charm/hss && juju deploy ./hss_ubuntu-20.04-amd64.charm --resource hss-image=vaishalinicky/cqlshimage:v5  --debug
deploy-mme:
	echo "deploying mme charm"
	cd charm/mme && juju deploy ./mme_ubuntu-20.04-amd64.charm --resource mme-image=amitinfo2k/nucleus-mme:9f86f87 --debug
deploy-spgwc:
	echo "deploying spgwc charm"
	cd charm/spgwc && juju deploy ./spgwc_ubuntu-20.04-amd64.charm --resource spgwc-image=amitinfo2k/ngic-cp:1.9.0 --debug
deploy-spgwu:
	echo "deploying dp charm"
	cd charm/spgwu && juju deploy ./spgwu_ubuntu-20.04-amd64.charm --resource spgwu-image=amitinfo2k/ngic-dp:1.9.0 --debug

cleanup:
	juju remove-application spgwc
	juju remove-application mme
	juju remove-application hss
	juju remove-application cassandra-k8s
	juju destroy-model development --destroy-storage -y


