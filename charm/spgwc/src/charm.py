#!/usr/bin/env python3
# Copyright 2021 root
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""
from files import *
import logging
import os
from typing import Optional
from subprocess import check_output
from ipaddress import IPv4Address
import datetime
from cryptography import x509
import glob
from ops.charm import CharmBase, InstallEvent, RemoveEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from kubernetes import kubernetes
from pathlib import Path
import resources

logger = logging.getLogger(__name__)


class SpgwcCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()
    _authed = False

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.spgwc_pebble_ready, self._on_spgwc_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.fortune_action, self._on_fortune_action)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.remove, self._on_remove)
        self._stored.set_default(things=[])

    def _on_spgwc_pebble_ready(self, event):
        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
        # Define an initial Pebble layer configuration
        pebble_layer = {
            "summary": "spgwc layer",
            "description": "pebble config layer for httpbin",
            "services": {
                "spgwc": {
                    "override": "replace",
                    "summary": "spgwc",
                    "command": """/bin/bash -xc "/opt/cp/scripts/spgwc-run.sh" """,
                    "startup": "enabled",
                }
            },
        }
        scriptPath = "/opt/cp/scripts/"
        configPath = "/etc/cp/config/"
        self._push_file_to_container(container, "src/files/script/*.*", scriptPath, 0o755)
        self._push_file_to_container(container, "src/files/config/*.*", configPath, 0o755)

        # Add intial Pebble config layer using the Pebble API
        container.add_layer("spgwc", pebble_layer, combine=True)
        # Autostart any services that were defined with startup: enabled
        container.autostart()
        # Learn more about statuses in the SDK docs:
        # https://juju.is/docs/sdk/constructs#heading--statuses
        self.unit.status = ActiveStatus()

    def _on_config_changed(self, event) -> None:
        # Defer the config-changed event if we do not have sufficient privileges
        if not self._k8s_auth():
            event.defer()
            return

        # Default StatefulSet needs patching for inicontainers and extra volumes. Ensure that
        # the StatefulSet is patched on each invocation.
        if not self._statefulset_patched:
            self._patch_stateful_set()
            self.unit.status = MaintenanceStatus("waiting for changes to apply")
        self.unit.status = ActiveStatus()

    @property
    def _statefulset_patched(self) -> bool:
        """Slightly naive check to see if the StatefulSet has already been patched"""
        # Get an API client
        apps_api = kubernetes.client.AppsV1Api(kubernetes.client.ApiClient())
        # Get the StatefulSet for the deployed application
        s = apps_api.read_namespaced_stateful_set(name=self.app.name, namespace=self.namespace)
        # Create a volume mount that we expect to be present after patching the StatefulSet
        expected = kubernetes.client.V1EnvVar(
                name = "MME_ADDR",
                value_from = kubernetes.client.V1EnvVarSource(
                    config_map_key_ref = kubernetes.client.V1ConfigMapKeySelector(
                        key = "IP",
                        name = "mme-ip",
                    ),
                ),
            )
        return expected in s.spec.template.spec.containers[1].env

    def _patch_stateful_set(self) -> None:
        """Patch the StatefulSet to include specific ServiceAccount and Secret mounts"""
        self.unit.status = MaintenanceStatus("patching StatefulSet for additional k8s permissions")
        # Get an API client
        api = kubernetes.client.AppsV1Api(kubernetes.client.ApiClient())
        r = resources.SpgwcResources(self)
        # Read the StatefulSet we're deployed into
        s = api.read_namespaced_stateful_set(name=self.app.name, namespace=self.namespace)
        # Add ServiceName to the statefulset spec
        #s.spec.service_name = "spgwc-headless"
        # Add the required volume mounts to the mme container spec
        s.spec.template.spec.containers[1].env.extend(r.spgwc_add_env)
        # Add additional init containers required for mme
        s.spec.template.spec.init_containers.extend(r.add_spgwc_init_containers)
        # Add resource limit to each container
        #containers = s.spec.template.spec.containers
        s.spec.template.spec.containers[1].resources = kubernetes.client.V1ResourceRequirements(
                limits = {
                    "cpu": "2",
                    "memory": "2Gi"
                },
                requests = {
                    "cpu": "2",
                    "memory": "2Gi"
                }
            )
        s.spec.template.spec.containers[1].stdin = True
        s.spec.template.spec.containers[1].tty = True
        # Patch the StatefulSet with our modified object
        api.patch_namespaced_stateful_set(name=self.app.name, namespace=self.namespace, body=s)
        logger.info("Patched StatefulSet to include additional volumes and mounts")

    def _on_fortune_action(self, event):
        """Just an example to show how to receive actions.

        TEMPLATE-TODO: change this example to suit your needs.
        If you don't need to handle actions, you can remove this method,
        the hook created in __init__.py for it, the corresponding test,
        and the actions.py file.

        Learn more about actions at https://juju.is/docs/sdk/actions
        """
        fail = event.params["fail"]
        if fail:
            event.fail(fail)
        else:
            event.set_results({"fortune": "A bug in the code is worth two in the documentation."})


    def _push_file_to_container(self, container, srcPath, dstPath, filePermission):
        for filePath in glob.glob(srcPath):
            print("Loading file name:" + filePath)
            fileData = loadfile(filePath)
            fileName = os.path.basename(filePath)
            container.push(dstPath + fileName, fileData, make_dirs=True, permissions=filePermission)

    '''def _patch_k8s_service(self):
        """Fix the Kubernetes service that was setup by Juju with correct port numbers."""
        if self.unit.is_leader():
            service_ports = [
                (f"s6a", self._s6a_port, self._s6a_port),
                (f"config-port", self._config_port, self._config_port),
                (f"prometheus-exporter", self._prometheus_port, self._prometheus_port),
            ]
            try:
                K8sServicePatch.set_ports(self.app.name, service_ports)
            except PatchFailed as e:
                logger.error("Unable to patch the Kubernetes service: %s", str(e))
            else:
                logger.info("Successfully patched the Kubernetes service")'''
    def _k8s_auth(self) -> bool:
        """Authenticate to kubernetes."""
        if self._authed:
            return True
        # Remove os.environ.update when lp:1892255 is FIX_RELEASED.
        os.environ.update(
            dict(
                e.split("=")
                for e in Path("/proc/1/environ").read_text().split("\x00")
                if "KUBERNETES_SERVICE" in e
            )
        )
        # Authenticate against the Kubernetes API using a mounted ServiceAccount token
        kubernetes.config.load_incluster_config()
        # Test the service account we've got for sufficient perms
        auth_api = kubernetes.client.RbacAuthorizationV1Api(kubernetes.client.ApiClient())

        try:
            auth_api.list_cluster_role()
        except kubernetes.client.exceptions.ApiException as e:
            if e.status == 403:
                # If we can't read a cluster role, we don't have enough permissions
                self.unit.status = BlockedStatus("Run juju trust on this application to continue")
                return False
            else:
                raise e

        self._authed = True
        return True
    @property
    def namespace(self) -> str:
        with open("/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r") as f:
            return f.read().strip()

    @property
    def pod_ip(self) -> Optional[IPv4Address]:
        return IPv4Address(check_output(["unit-get", "private-address"]).decode().strip())

    def _on_install(self, event: InstallEvent) -> None:
        """Event handler for InstallEvent during which we will update the K8s service."""
        
        """Handle the install event, create Kubernetes resources"""
        if not self._k8s_auth():
            event.defer()
            return
        self.unit.status = MaintenanceStatus("creating k8s resources")
        # Create the Kubernetes resources needed for the spgwc
        r = resources.SpgwcResources(self)
        r.apply()

    def _on_remove(self, event: RemoveEvent) -> None:
        """Cleanup Kubernetes resources"""
        # Authenticate with the Kubernetes API
        if not self._k8s_auth():
            event.defer()
            return
        # Remove created Kubernetes resources
        r = resources.SpgwcResources(self)
        r.delete()


    '''def _on_upgrade_charm(self, _):
        """Event handler for replica's UpgradeCharmEvent."""
        # Ensure that older deployments of Alertmanager run the logic to patch the K8s service
        self._patch_k8s_service()

       # update config hash
        self._stored.config_hash = (
            ""
            if not self.container.can_connect()
            else sha256(yaml.safe_dump(yaml.safe_load(self.container.pull(self._config_path))))
        )

        # After upgrade (refresh), the unit ip address is not guaranteed to remain the same, and
        # the config may need update. Calling the common hook to update.
        self._common_exit_hook()'''



if __name__ == "__main__":
    main(SpgwcCharm)
