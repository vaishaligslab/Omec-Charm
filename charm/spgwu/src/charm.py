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
import datetime
import logging
import os
import glob
from ipaddress import IPv4Address
from pathlib import Path
from subprocess import check_output
from typing import Optional

#from cryptography import x509
from kubernetes import kubernetes

import logging

from ops.charm import CharmBase,  InstallEvent, RemoveEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

import resources
from pathlib import Path
from files import *

logger = logging.getLogger(__name__)


class SpgwuCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()
    _authed = False

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.spgwu_pebble_ready, self._on_spgwu_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.fortune_action, self._on_fortune_action)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.remove, self._on_remove)

        #self._stored.set_default(things=[])

    def _on_spgwu_pebble_ready(self, event):
        """Define and start a workload using the Pebble API.

        TEMPLATE-TODO: change this example to suit your needs.
        You'll need to specify the right entrypoint and environment
        configuration for your specific workload. Tip: you can see the
        standard entrypoint of an existing container using docker inspect

        Learn more about Pebble layers at https://github.com/canonical/pebble
        """
        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
        # Define an initial Pebble layer configuration
        pebble_layer = {
            "summary": "spgwu layer",
            "description": "pebble config layer for spgwu",
            "services": {
                "spgwu": {
                    "override": "replace",
                    "summary": "spgwu",
                    "command": """/bin/bash -xc "ip a;  /opt/dp/scripts/run.sh;" """,
                    #"command": """/bin/bash -xc "while true; do echo 'Running spgwu'; sleep 10; done" """,
                    "startup": "enabled",
                    "environment": {
                        "POD_IP": f"{self.pod_ip}",
                        },
                }
            },
        }
        scriptPath = "/opt/dp/scripts/"
        configPath = "/etc/dp/config/"
        container = self.unit.get_container("spgwu")
        self._push_file_to_container(container, "src/files/run.sh", scriptPath, 0o755)
        self._push_file_to_container(container, "src/files/Config/*.*", configPath, 0o755)
        # Add intial Pebble config layer using the Pebble API
        container.add_layer("spgwu", pebble_layer, combine=True)
        # Autostart any services that were defined with startup: enabled
        container.autostart()
        # Learn more about statuses in the SDK docs:
        # https://juju.is/docs/sdk/constructs#heading--statuses
        self.unit.status = ActiveStatus()

    def _on_config_changed(self, event) -> None:
        """Just an example to show how to deal with changed configuration.

        TEMPLATE-TODO: change this example to suit your needs.
        If you don't need to handle config, you can remove this method,
        the hook created in __init__.py for it, the corresponding test,
        and the config.py file.

        Learn more about config at https://juju.is/docs/sdk/config
        """

        if not self._k8s_auth():
            event.defer()
            return

        # Default StatefulSet needs patching for extra volume mounts. Ensure that
        # the StatefulSet is patched on each invocation.
    #if not self._statefulset_patched:"""
        self._patch_stateful_set()
        self.unit.status = MaintenanceStatus("waiting for changes to apply")

        self.unit.status = ActiveStatus()


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


    def _patch_stateful_set(self) -> None:
        """Patch the StatefulSet to include specific ServiceAccount and Secret mounts"""
        self.unit.status = MaintenanceStatus("patching StatefulSet for additional k8s permissions")
        # Get an API client
        api = kubernetes.client.AppsV1Api(kubernetes.client.ApiClient())
        r = resources.SpgwuResources(self)
        # Read the StatefulSet we're deployed into
        s = api.read_namespaced_stateful_set(name=self.app.name, namespace=self.namespace)
        # Add the required volume mounts to the spgwu container spec
        s.spec.template.spec.init_containers.extend(r.add_spgwu_init_containers)

        #s.spec.template.spec.containers[1].volume_mounts.extend(r.spgwu_volume_mounts)
        s.spec.template.spec.volumes.extend(r.spgwu_volumes)
        s.spec.template.metadata.annotations = {
            "k8s.v1.cni.cncf.io/networks": '''[
                {
                    "name": "s1u-net",
                    "interface": "s1u-net",
                    "ips": ["11.1.1.110/24"]
                },
                {
                    "name": "sgi-net",
                    "interface": "sgi-net",
                    "ips": ["13.1.1.110/24"]
                }
            ]''',
        }

        # Patch the StatefulSet with our modified object
        api.patch_namespaced_stateful_set(name=self.app.name, namespace=self.namespace, body=s)
        logger.info("Patched StatefulSet to include additional volumes and mounts")

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
        r = resources.SpgwuResources(self)
        r.apply()

    def _push_file_to_container(self, container, srcPath, dstPath, filePermission):
        for filePath in glob.glob(srcPath):
            print("Loading file name:" + filePath)
            fileData = loadfile(filePath)
            fileName = os.path.basename(filePath)
            container.push(dstPath + fileName, fileData, make_dirs=True, permissions=filePermission)

    def _on_remove(self, event: RemoveEvent) -> None:
        """Cleanup Kubernetes resources"""
        # Authenticate with the Kubernetes API
        if not self._k8s_auth():
            event.defer()
            return
        # Remove created Kubernetes resources
        r = resources.SpgwuResources(self)
        r.delete()

if __name__ == "__main__":
    main(SpgwuCharm)
