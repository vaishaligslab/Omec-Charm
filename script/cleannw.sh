#!/bin/bash

sudo ovs-vsctl del-port br-s1u-net s1u-net 
sudo ovs-vsctl del-port br-sgi-net sgi-net 
kubectl delete -n development -f ovs-network.yaml
sudo ovs-vsctl show
