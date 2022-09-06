# Copyright 2021 root
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, call, patch

from ops import testing
from ops.model import ActiveStatus

from charm import HssCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = testing.Harness(HssCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("kubernetes_service.K8sServicePatch.set_ports")
    def test_given_unit_is_leader_when_on_install_then_k8s_service_is_patches(
        self, patch_set_ports
    ):
        event = Mock()
        self.harness.set_leader(is_leader=True)

        self.harness.charm._on_install(event=event)

        patch_set_ports.assert_called_with(
            "omec-hss",
            [
                ("s6a", 3868, 3868),
                ("config-port", 8080, 8080),
                ("prometheus-exporter", 9080, 9080),
            ],
        )

    @patch("charm.loadfile")
    @patch("charm.HssCharm.namespace", new_callable=PropertyMock)
    def test_given_namespace_when_pebble_ready_then_status_is_active(
        self, namespace_patch, patch_load_file
    ):
        patch_load_file.return_value = "whatever loaded file content"
        namespace = "whatever namespace"
        namespace_patch.return_value = namespace

        self.harness.container_pebble_ready(container_name="hss")

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    @patch("charm.loadfile")
    @patch("ops.model.Container.push")
    @patch("charm.HssCharm.namespace", new_callable=PropertyMock)
    def test_given_when_pebble_ready_then_files_are_pushed(
        self, namespace_patch, container_push_patch, patch_loadfile
    ):
        loaded_file = "whatever file content"
        patch_loadfile.return_value = loaded_file
        namespace = "whatever namespace"
        namespace_patch.return_value = namespace

        self.harness.container_pebble_ready(container_name="hss")

        calls = [
            call("/etc/hss/conf/hss.conf", loaded_file, make_dirs=True, permissions=493),
            call("/etc/hss/conf/acl.conf", loaded_file, make_dirs=True, permissions=493),
            call("/etc/hss/conf/oss.json", loaded_file, make_dirs=True, permissions=493),
            call("/etc/hss/conf/hss.json", loaded_file, make_dirs=True, permissions=493),
            call("/bin/data_provisioning_mme.sh", loaded_file, make_dirs=True, permissions=493),
            call("/bin/make_certs.sh", loaded_file, make_dirs=True, permissions=493),
            call("/bin/Cass_Provisioning.sh", loaded_file, make_dirs=True, permissions=493),
            call("/bin/oai_db.cql", loaded_file, make_dirs=True, permissions=493),
            call("/bin/hss-run.sh", loaded_file, make_dirs=True, permissions=493),
            call("/bin/data_provisioning_users.sh", loaded_file, make_dirs=True, permissions=493),
        ]
        container_push_patch.assert_has_calls(calls=calls)
