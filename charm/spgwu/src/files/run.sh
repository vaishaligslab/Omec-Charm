#!/bin/bash
#
# Copyright 2019-present Open Networking Foundation
# Copyright 2019 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -ex
mkdir -p /opt/dp/config
cd /opt/dp/config
cp /etc/dp/config/{cdr.cfg,dp.cfg,log.json,static_arp.cfg} .
S1U_DEVNAME=s1u-net-veth
SGI_DEVNAME=sgi-net-veth

#S1U_DEVNAME=s1u-net
#SGI_DEVNAME=sgi-net

WB_IPv4=$(ip -4 addr show dev ${S1U_DEVNAME} | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
EB_IPv4=$(ip -4 addr show dev ${SGI_DEVNAME} | grep -oP '(?<=inet\s)\d+(\.\d+){3}')
WB_MAC=$(ip addr show dev ${S1U_DEVNAME} | awk '$1=="link/ether"{print $2}')
EB_MAC=$(ip addr show dev ${SGI_DEVNAME} | awk '$1=="link/ether"{print $2}')

sed -i "s/DP_ADDR/$POD_IP/g" dp.cfg
sed -i "s/S1U_IP/$WB_IPv4/g" dp.cfg
sed -i "s/SGI_IP/$EB_IPv4/g" dp.cfg
sed -i "s/S1U_MAC/$WB_MAC/g" dp.cfg
sed -i "s/SGI_MAC/$EB_MAC/g" dp.cfg
sed -i "s/S1U_IFACE/$S1U_DEVNAME/g" dp.cfg
sed -i "s/SGI_IFACE/$SGI_DEVNAME/g" dp.cfg

#export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/ngic-rtc/third_party/libpfcp/lib
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib
#Set NUMA memory
MEMORY=7168

CORES="-c $(taskset -p $$ | awk '{print $NF}')"
EAL_ARGS="${CORES} --no-huge -m ${MEMORY} --no-pci --vdev eth_af_packet0,iface=s1u-net --vdev eth_af_packet1,iface=sgi-net"


echo "#!/bin/bash " > run.sh
echo "export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib" >> run.sh
echo "ngic_dataplane $EAL_ARGS" >> run.sh
chmod +x run.sh

#while true; do sleep 10000; done
ngic_dataplane $EAL_ARGS
