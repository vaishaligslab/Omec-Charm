# Copyright 2021 Canonical
# See LICENSE file for licensing details.
import logging
import glob
import os

from kubernetes import kubernetes

logger = logging.getLogger(__name__)


class SpgwcResources:
    """Class to handle the creation and deletion of those Kubernetes resources
    required by the MME, but not automatically handled by Juju"""

    def __init__(self, charm):
        self.model = charm.model
        self.app = charm.app
        self.config = charm.config
        self.namespace = charm.namespace
        # Setup some Kubernetes API clients we'll need
        kcl = kubernetes.client.ApiClient()
        self.apps_api = kubernetes.client.AppsV1Api(kcl)
        self.core_api = kubernetes.client.CoreV1Api(kcl)
        self.auth_api = kubernetes.client.RbacAuthorizationV1Api(kcl)

        self.script_path = "src/files/scripts/*.*"
        self.config_path = "src/files/config/*.*"

    def apply(self) -> None:
        """Create the required Kubernetes resources for the dashboard"""

        # Create Kubernetes Services
        for service in self._services:
            s = self.core_api.list_namespaced_service(
                namespace=service["namespace"],
                field_selector=f"metadata.name={service['body'].metadata.name}",
            )
            if not s.items:
                self.core_api.create_namespaced_service(**service)
            else:
                logger.info(
                    "service '%s' in namespace '%s' exists, patching",
                    service["body"].metadata.name,
                    service["namespace"],
                )
                self.core_api.patch_namespaced_service(
                    name=service["body"].metadata.name, **service
                )


        logger.info("Created additional Kubernetes resources")

    def delete(self) -> None:
        """Delete all of the Kubernetes resources created by the apply method""" 
        # Delete Kubernetes services
        for service in self._services:
            self.core_api.delete_namespaced_service(
                namespace=service["namespace"], name=service["body"].metadata.name
            )
        logger.info("Deleted additional Kubernetes resources")

    @property
    def add_spgwc_init_containers(self) -> dict:
        """Returns the addtional init_container required for spgwc"""
        return [
            kubernetes.client.V1Container(
                name  = "spgwc-dep-check",
                image = "quay.io/stackanetes/kubernetes-entrypoint:v0.3.1",
                image_pull_policy = "IfNotPresent",
                security_context = kubernetes.client.V1SecurityContext(
                    allow_privilege_escalation = False,
                    read_only_root_filesystem = False,
                    run_as_user = 0,
                ),
                env = [
                    kubernetes.client.V1EnvVar(
                        name = "NAMESPACE",
                        value_from = kubernetes.client.V1EnvVarSource(
                            field_ref = kubernetes.client.V1ObjectFieldSelector(
                                field_path = "metadata.namespace",
                                api_version = "v1"
                            ),
                        ),
                    ),
                    kubernetes.client.V1EnvVar(
                        name = "POD_NAME",
                        value_from = kubernetes.client.V1EnvVarSource(
                            field_ref = kubernetes.client.V1ObjectFieldSelector(
                                field_path = "metadata.name",
                                api_version = "v1"
                            ),
                        ),
                    ),
                    kubernetes.client.V1EnvVar(
                        name = "PATH",
                        value = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/",
                    ),
                    kubernetes.client.V1EnvVar(
                        name = "COMMAND",
                        value = "echo done",
                    ),
                    kubernetes.client.V1EnvVar(
                        name = "DEPENDENCY_POD_JSON",
                        value = '[{"labels": {"app.kubernetes.io/name": "mme"}, "requireSameNode": false}]',
                    ),
                ],
                command = ["kubernetes-entrypoint"],
            ),
        ]

    @property
    def spgwc_add_env(self) -> dict:
        """ TODO: Need to add MEM_LIMIT ENV""" 
        """Returns the additional env for the spgwc containers"""
        return [
            kubernetes.client.V1EnvVar(
                name = "MME_ADDR",
                value_from = kubernetes.client.V1EnvVarSource(
                    config_map_key_ref = kubernetes.client.V1ConfigMapKeySelector(
                        key = "IP",
                        name = "mme-ip",
                    ),
                ),
            ),
            kubernetes.client.V1EnvVar(
                name = "POD_IP",
                value_from = kubernetes.client.V1EnvVarSource(
                    field_ref = kubernetes.client.V1ObjectFieldSelector(field_path="status.podIP"),
                ),
            ),
            kubernetes.client.V1EnvVar(
                name = "MEM_LIMIT",
                value_from = kubernetes.client.V1EnvVarSource(
                    resource_field_ref = kubernetes.client.V1ResourceFieldSelector(
                        container_name="spgwc",
                        resource="limits.memory",
                        divisor="1Mi",
                    ),
                ),
            ),
        ]

    @property
    def add_container_resource_limit(self, containers):
        #Length of list containers
        length = len(containers)
        itr = 1

        while itr < length:
            containers[itr].resources = kubernetes.client.V1ResourceRequirements(
                limits = {
                    'cpu': '0.2',
                    'memory': '200Mi'
                },
                requests = {
                    'cpu': '0.2',
                    'memory': '200Mi'
                }
            )

    @property
    def _services(self) -> list:
        """Return a list of Kubernetes services needed by the mme"""
        # Note that this service is actually created by Juju, we are patching
        # it here to include the correct port mapping
        # TODO: Update when support improves in Juju

        return [
            {
                "namespace": self.namespace,
                "body": kubernetes.client.V1Service(
                    api_version="v1",
                    metadata=kubernetes.client.V1ObjectMeta(
                        namespace=self.namespace,
                        name="spgwc-cp-comm",
                        labels={"app.kubernetes.io/name": self.app.name},
                    ),
                    spec=kubernetes.client.V1ServiceSpec(
                        ports=[
                            kubernetes.client.V1ServicePort(
                                name="cp-comm",
                                port=8085,
                                protocol="UDP",
                            ),
                        ],
                        selector={"app.kubernetes.io/name": self.app.name},
                    ),
                ),
            },
            {
                "namespace": self.namespace,
                "body": kubernetes.client.V1Service(
                    api_version="v1",
                    metadata=kubernetes.client.V1ObjectMeta(
                        namespace=self.namespace,
                        name="spgwc-s11",
                        labels={"app.kubernetes.io/name": self.app.name},
                    ),
                    spec=kubernetes.client.V1ServiceSpec(
                        ports=[
                            kubernetes.client.V1ServicePort(
                                name="s11",
                                port=2123,
                                protocol="UDP",
                                node_port=32124,
                            ),
                        ],
                        selector={"app.kubernetes.io/name": self.app.name},
                        type="NodePort",
                    ),
                ),
            },
        ]

    def loadfile(self, file_name):
        """Read the file content and return content data"""

        sed_command = "sed -i 's/NAMESPACE/{1}/' {0}".format(file_name, self.namespace)
        os.system(sed_command)

        with open(file_name, 'r') as f:
            data = f.read()
            f.close()
            return data


    def _get_config_data(self, files_path):
        """Return the dictionary of file contnent and name needed by mme"""
        dicts = {}
        for file_path in glob.glob(files_path):
            file_data = self.loadfile(file_path)
            file_name = os.path.basename(file_path)
            dicts[file_name] = file_data
        return dicts
