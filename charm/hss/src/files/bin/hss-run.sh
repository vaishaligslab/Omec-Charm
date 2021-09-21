#!/bin/bash

# Copyright 2019-present Open Networking Foundation
#
# SPDX-License-Identifier: LicenseRef-ONF-Member-Only-1.0

set -ex

CONF_DIR="/opt/c3po/hss/conf"
LOGS_DIR="/opt/c3po/hss/logs"
mkdir -p $CONF_DIR $LOGS_DIR

cp /etc/hss/conf/{acl.conf,hss.json,hss.conf,oss.json} $CONF_DIR
cat $CONF_DIR/{hss.json,hss.conf}

cd $CONF_DIR
make_certs.sh hss NAMESPACE.svc.cluster.local

cd ..
hss -j $CONF_DIR/hss.json
