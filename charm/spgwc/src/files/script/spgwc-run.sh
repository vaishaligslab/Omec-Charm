#!/bin/bash
#
# Copyright 2019-present Open Networking Foundation
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

set -xe
mkdir -p /opt/cp/config
cd /opt/cp/config
cp /etc/cp/config/{adc_rules.cfg,cp.cfg,log.json,meter_profile.cfg,pcc_rules.cfg,sdf_rules.cfg,rules_ipv4.cfg,rules_ipv6.cfg,static_arp.cfg} .

UPF_IP=$(curl -k -H "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"   https://kubernetes.default.svc:443/api/v1/namespaces/{NAMESPACE}/endpoints/spgwu-dp-comm | jq -r '.subsets[].addresses[].ip')

export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib

sed -i "s/CP_ADDR/$POD_IP/g" cp.cfg
sed -i "s/DP_ADDR/$UPF_IP/g" cp.cfg

APP_PATH="./build"
APP="ngic_controlplane"
LOG_LEVEL=0

#Set NUMA memory
MEMORY=2048

#Set corelist here
CORELIST="0-1"

CORES="-c $(taskset -p $$ | awk '{print $NF}')"
EAL_ARGS="${CORES} --no-huge -m ${MEMORY} --no-pci"

#NOW=$(date +"%Y-%m-%d_%H-%M")
#FILE="logs/cp_$NOW.log"

ARGS="$EAL_ARGS --file-prefix cp -- -z $LOG_LEVEL"

echo "#!/bin/bash" > run.sh
echo "export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib" > run.sh
echo "ngic_controlplane $ARGS" >> run.sh
chmod +x run.sh

#while true; do sleep 10000; done

ngic_controlplane $ARGS

