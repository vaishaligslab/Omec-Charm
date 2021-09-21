# OMEC Charm

Open Mobiled Evolved Core (OMEC) is opensource EPC (4G) Core
Consisten of MME,HSS,SPGWC and SPGWU components

## Enable Multus

make multus

##  Build OMEC  charm

make build

##  Deploy OMEC charm

make deploy

Note : 
- Juju Model named "development" needs to be deployed (TODO remove this dependancy)


## Build or deploy individual components e.g. spgwu
make build-<component-name>
make deploy-<component-name>

e.g.

make build-spgwu
make deploy-spgwu


## Cleanup omec applications

make cleanup





