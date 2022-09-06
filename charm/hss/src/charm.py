#!/usr/bin/env python3
# Copyright 2021 root
# See LICENSE file for licensing details.


"""HSS is the main database of the current generation's cellular  communications systems."""

import glob
import logging
import os

from ops.charm import CharmBase, InstallEvent, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, Container

from files import loadfile
from kubernetes_service import K8sServicePatch, PatchFailed

logger = logging.getLogger(__name__)


class HssCharm(CharmBase):
    """Charm the service."""

    _s6a_port = 3868  # port to listen on for the web interface and API
    _config_port = 8080  # port for HA-communication between multiple instances of alertmanager
    _prometheus_port = 9089

    def __init__(self, *args):
        """Observes install and pebble ready events."""
        super().__init__(*args)
        self.framework.observe(self.on.hss_pebble_ready, self._on_hss_pebble_ready)
        self.framework.observe(self.on.install, self._on_install)

    def _on_hss_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Event triggerred on Pebble Ready."""
        pebble_layer = {
            "summary": "hss layer",
            "description": "pebble config layer for hss",
            "services": {
                "hss": {
                    "override": "replace",
                    "summary": "hss",
                    "command": """/bin/bash -xc "/bin/Cass_Provisioning.sh" """,
                    "startup": "enabled",
                }
            },
        }

        container = self.unit.get_container("hss")
        script_path = "/etc/hss/conf/"
        self._push_file_to_container(container, "src/files/*.conf", script_path, 0o755)
        self._push_file_to_container(container, "src/files/*.json", script_path, 0o755)
        self._push_file_to_container(container, "src/files/bin/*.*", "/bin/", 0o755)

        container.add_layer("hss", pebble_layer, combine=True)
        if not container.get_service("hss").is_running():
            container.start("hss")
            logger.info("hss service started")
        self.unit.status = ActiveStatus()

    def _push_file_to_container(
        self, container: Container, src_path: str, dst_path: str, file_permission: int
    ) -> None:
        pass
        for file_path in glob.glob(src_path):
            file_data = loadfile(file_path, self.namespace)
            file_name = os.path.basename(file_path)
            container.push(
                dst_path + file_name, file_data, make_dirs=True, permissions=file_permission
            )

    def _patch_k8s_service(self) -> None:
        """Fix the Kubernetes service that was setup by Juju with correct port numbers."""
        if self.config["s6aPort"]:
            self._s6a_port = int(self.config["s6aPort"])
        if self.config["promExporterPort"]:
            self._prometheus_port = int(self.config["promExporterPort"])

        if self.unit.is_leader():
            service_ports = [
                ("s6a", self._s6a_port, self._s6a_port),
                ("config-port", self._config_port, self._config_port),
                ("prometheus-exporter", self._prometheus_port, self._prometheus_port),
            ]
            try:
                K8sServicePatch.set_ports(self.app.name, service_ports)
            except PatchFailed as e:
                logger.error("Unable to patch the Kubernetes service: %s", str(e))
            else:
                logger.info("Successfully patched the Kubernetes service")

    def _on_install(self, event: InstallEvent) -> None:
        """Event handler for InstallEvent during which we will update the K8s service."""
        self._patch_k8s_service()

    @property
    def namespace(self) -> str:
        """Kubernetes namespace."""
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r") as f:
            return f.read().strip()


if __name__ == "__main__":
    main(HssCharm)
