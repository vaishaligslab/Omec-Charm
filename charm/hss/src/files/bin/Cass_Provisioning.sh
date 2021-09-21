#!/bin/bash
echo "Executing Script"
imsi=208014567891200
msisdn=1122334455
apn="apn1"
opc="d4416644f6154936193433dd20a0ace0"
sqn=96
cassandra_ip="cassandra-k8s"
mmeidentity="mme.NAMESPACE.svc.cluster.local"
no_of_users=1
mmerealm="NAMESPACE.svc.cluster.local"
key="465b5ce8b199b49faa5f0a2ee238a6bc"
isdn=19136246000
id=1
unreachability=1

until cqlsh $cassandra_ip 9042 --file /opt/c3po/hssdb/oai_db.cql;
  do echo "Provisioning HSSDB";
  sleep 2;
done

echo "hello"

/bin/data_provisioning_users.sh $imsi $msisdn $apn $key $no_of_users $cassandra_ip $opc $mmeidentity $mmerealm

echo "This script has just run another script."

/bin/data_provisioning_mme.sh $id $isdn $mmeidentity $mmerealm $unreachability $cassandra_ip

echo "done with Cassendra Provisioning"
echo "started hss process"

/bin/hss-run.sh

