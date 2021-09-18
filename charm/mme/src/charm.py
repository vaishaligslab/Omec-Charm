#!/usr/bin/env python3
# Copyright 2021 charmjuju
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

from cryptography import x509
from kubernetes import kubernetes
from ops.charm import CharmBase, InstallEvent, RemoveEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.pebble import ConnectionError

import resources

scriptPath = "/opt/mme/scripts/"
configPath = "/opt/mme/config/"


logger = logging.getLogger(__name__)

# Reduce the log output from the Kubernetes library
logging.getLogger("kubernetes").setLevel(logging.INFO)

class MmeCharm(CharmBase):
    """Charm the service."""

    _authed = False
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
       # self.framework.observe(self.on.mme_pebble_ready, self._on_mme_pebble_ready)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.remove, self._on_remove)

    def _on_install(self, event: InstallEvent) -> None:
        """Handle the install event, create Kubernetes resources"""
        if not self._k8s_auth():
            event.defer()
            return
        self.unit.status = MaintenanceStatus("creating k8s resources")
        # Create the Kubernetes resources needed for the mme
        r = resources.MmeResources(self)
        r.apply()

    def _on_remove(self, event: RemoveEvent) -> None:
        """Cleanup Kubernetes resources"""
        # Authenticate with the Kubernetes API
        if not self._k8s_auth():
            event.defer()
            return
        # Remove created Kubernetes resources
        r = resources.MmeResources(self)
        r.delete()

    def _on_config_changed(self, event) -> None:
        # Defer the config-changed event if we do not have sufficient privileges
        if not self._k8s_auth():
            event.defer()
            return

        # Default StatefulSet needs patching for extra volume mounts. Ensure that
        # the StatefulSet is patched on each invocation.
        if not self._statefulset_patched:
            self._patch_stateful_set()
            self.unit.status = MaintenanceStatus("waiting for changes to apply")

        try:
            # Configure and start the mme interface
            self._config_mme()
            # Configure and start the s1ap interface
            self._config_s1ap()
            # Configure and start the s6a interface
            self._config_s6a()
            # Configure and start the s11 interface
            self._config_s11()
        except ConnectionError:
            logger.info("pebble socket not available, deferring config-changed")
            event.defer()
            return

        self.unit.status = ActiveStatus()

    # def _push_file_to_container(self, container, srcPath, dstPath, filePermission):
    #     for filePath in glob.glob(srcPath):
    #         print("Loading file name:" + filePath)
    #         fileData = resources.MmeResources(self).loadfile(filePath)
    #         fileName = os.path.basename(filePath)
    #         container.push(dstPath + fileName, fileData, make_dirs=True, permissions=filePermission)

    # def _update_mme_and_run(self):
    #     self.unit.status = MaintenanceStatus('Configuring mme-app')

    #     # Define an initial Pebble layer configuration
    #     pebble_layer = {
    #         "summary": "mme-app layer",
    #         "description": "pebble config layer for mme-app",
    #         "services": {
    #             "mme": {
    #                 "override": "replace",
    #                 "summary": "mme",
    #                 "command": """/bin/bash -c "while true; do echo 'Running mme-app'; sleep 10; done" """,
    #                 "startup": "enabled",
    #                 "environment": {"thing": self.model.config["thing"]},
    #             }
    #         },
    #     }

    #     container = self.unit.get_container("mme")

    #     self._push_file_to_container(container, "src/files/scripts/*.*", scriptPath, 0o755)
    #     self._push_file_to_container(container, "src/files/config/*.*", configPath, 0o644)
    #     # Add intial Pebble config layer using the Pebble API
    #     container.add_layer("mme", pebble_layer, combine=True)

    #     if container.get_service("mme").is_running():
    #         container.stop("mme")
    #     container.start("mme")

    #     self.unit.status = ActiveStatus()

    # def _on_mme_pebble_ready(self, event):
    #     self._update_mme_and_run()

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

    @property
    def _statefulset_patched(self) -> bool:
        """Slightly naive check to see if the StatefulSet has already been patched"""
        # Get an API client
        apps_api = kubernetes.client.AppsV1Api(kubernetes.client.ApiClient())
        # Get the StatefulSet for the deployed application
        s = apps_api.read_namespaced_stateful_set(name=self.app.name, namespace=self.namespace)
        # Create a volume mount that we expect to be present after patching the StatefulSet
        expected = kubernetes.client.V1VolumeMount(mount_path="/opt/mme/config/shared", name="shared-data")
        return expected in s.spec.template.spec.containers[1].volume_mounts

    def _patch_stateful_set(self) -> None:
        """Patch the StatefulSet to include specific ServiceAccount and Secret mounts"""
        self.unit.status = MaintenanceStatus("patching StatefulSet for additional k8s permissions")
        # Get an API client
        api = kubernetes.client.AppsV1Api(kubernetes.client.ApiClient())
        r = resources.MmeResources(self)
        # Read the StatefulSet we're deployed into
        s = api.read_namespaced_stateful_set(name=self.app.name, namespace=self.namespace)
        # Add ServiceName to the specs
        #s.spec.service_name = "mme-headless"
        # Add the required volume mounts to the mme container spec
        s.spec.template.spec.containers[1].volume_mounts.extend(r.mme_volume_mounts)
        # Add the required volume mounts to the s1ap container spec
        s.spec.template.spec.containers[2].volume_mounts.extend(r.s1ap_volume_mounts)
        # Add the required volume mounts to the s6a container spec
        s.spec.template.spec.containers[3].volume_mounts.extend(r.s6a_volume_mounts)
        # Add the required volume mounts to the s11 container spec
        s.spec.template.spec.containers[4].volume_mounts.extend(r.s11_volume_mounts)
        # Add additional init containers required for mme
        s.spec.template.spec.init_containers.extend(r.add_mme_init_containers)
        # Add resource limit to each container
        length = len(s.spec.template.spec.containers)
        itr = 1

        while itr < length:
            s.spec.template.spec.containers[itr].resources = kubernetes.client.V1ResourceRequirements(
                limits = {
                    'cpu': '0.2',
                    'memory': '200Mi'
                },
                requests = {
                    'cpu': '0.2',
                    'memory': '200Mi'
                }
            )
            itr += 1
        # Add the required volumes to the StatefulSet spec
        s.spec.template.spec.volumes.extend(r.mme_volumes)

        # Patch the StatefulSet with our modified object
        api.patch_namespaced_stateful_set(name=self.app.name, namespace=self.namespace, body=s)
        logger.info("Patched StatefulSet to include additional volumes and mounts")

    def _config_mme(self) -> dict:
        """Configure Pebble to start the mme interface container"""
        # Define a simple layer
        # Define an initial Pebble layer configuration
        layer = {
            "summary": "mme-app layer",
            "description": "pebble config layer for mme-app",
            "services": {
                "mme": {
                    "override": "replace",
                    "summary": "mme-app",
                    "command": """/bin/bash -xc "/opt/mme/scripts/mme-run.sh mme-app" """,
                    "startup": "enabled",
                    "environment": {
                        "thing": self.model.config["thing"],
                        "POD_IP": f"{self.pod_ip}",
                        "MMERUNENV": "container",
                    },
                }
            },
        }

        # Add a Pebble config layer to the mme container
        container = self.unit.get_container("mme")
        container.add_layer("mme", layer, combine=True)
        # Check if the mme service is already running and start it if not
        if not container.get_service("mme").is_running():
            container.start("mme")
            logger.info("mme service started")

    def _config_s1ap(self) -> dict:
        """Configure Pebble to start the s1ap interface container"""
        # Define a simple layer
        # Define an initial Pebble layer configuration
        layer = {
            "summary": "mme-s1ap layer",
            "description": "pebble config layer for mme-s1ap",
            "services": {
                "s1ap": {
                    "override": "replace",
                    "summary": "mme-s1ap",
                    "command": """/bin/bash -xc "/opt/mme/scripts/mme-run.sh s1ap-app" """,
                    "startup": "enabled",
                    "environment": {
                        "thing": self.model.config["thing"],
                        "POD_IP": f"{self.pod_ip}",
                        "MMERUNENV": "container",
                    },
                }
            },
        }

        # Add a Pebble config layer to the s1ap container
        container = self.unit.get_container("s1ap")
        container.add_layer("s1ap", layer, combine=True)
        # Check if the s1ap service is already running and start it if not
        if not container.get_service("s1ap").is_running():
            container.start("s1ap")
            logger.info("s1ap service started")

    def _config_s6a(self) -> dict:
        """Configure Pebble to start the s6a interface container"""
        # Define a simple layer
        # Define an initial Pebble layer configuration
        layer = {
            "summary": "mme-s6a layer",
            "description": "pebble config layer for mme-s6a",
            "services": {
                "s6a": {
                    "override": "replace",
                    "summary": "mme-s6a",
                    "command": """/bin/bash -xc "/opt/mme/scripts/mme-run.sh s6a-app" """,
                    "startup": "enabled",
                    "environment": {
                        "MMERUNENV": "container",
                    },
                }
            },
        }

        # Add a Pebble config layer to the s6a container
        container = self.unit.get_container("s6a")
        container.add_layer("s6a", layer, combine=True)
        # Check if the s6a service is already running and start it if not
        if not container.get_service("s6a").is_running():
            container.start("s6a")
            logger.info("s6a service started")

    def _config_s11(self) -> dict:
        """Configure Pebble to start the s11 interface container"""
        # Define a simple layer
        # Define an initial Pebble layer configuration
        layer = {
            "summary": "mme-s11 layer",
            "description": "pebble config layer for mme-s11",
            "services": {
                "s11": {
                    "override": "replace",
                    "summary": "mme-s11",
                    "command": """/bin/bash -xc "/opt/mme/scripts/mme-run.sh s11-app" """,
                    "startup": "enabled",
                    "environment": {
                        "MMERUNENV": "container",
                    },
                }
            },
        }

        # Add a Pebble config layer to the s11 container
        container = self.unit.get_container("s11")
        container.add_layer("s11", layer, combine=True)
        # Check if the s11 service is already running and start it if not
        if not container.get_service("s11").is_running():
            container.start("s11")
            logger.info("s11 service started")

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


if __name__ == "__main__":
    main(MmeCharm)
