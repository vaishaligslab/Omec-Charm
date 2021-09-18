# Copyright 2021 Canonical
# See LICENSE file for licensing details.
import logging
import glob
import os

from kubernetes import kubernetes

logger = logging.getLogger(__name__)


class SpgwuResources:
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

        self.script_path = "src/files/Script/*.*"
        #self.config_path = "src/files/config/*.*"
        self.runscriptPath = "src/files/*.*"
        self.configPath = "src/files/Config/*.*"

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

        for cm in self._configmaps:
            s = self.core_api.list_namespaced_config_map(
                namespace=cm["namespace"],
                field_selector=f"metadata.name={cm['body'].metadata.name}",
            )
            if not s.items:
                self.core_api.create_namespaced_config_map(**cm)
            else:
                logger.info(
                    "configmap '%s' in namespace '%s' exists, patching",
                    cm["body"].metadata.name,
                    cm["namespace"],
                )
                self.core_api.patch_namespaced_config_map(name=cm["body"].metadata.name, **cm)



    def delete(self) -> None:
        """Delete all of the Kubernetes resources created by the apply method"""
        #Delete Kubernetes services
        for service in self._services:
            self.core_api.delete_namespaced_service(
                namespace=service["namespace"], name=service["body"].metadata.name
            )

        logger.info("Deleted additional Kubernetes resources")

        #Delete Kubernetes configmaps
        for cm in self._configmaps:
           self.core_api.delete_namespaced_config_map(
               namespace=cm["namespace"], name=cm["body"].metadata.name
           )

    @property
    def add_spgwu_init_containers(self) -> dict:
        """Returns the addtional init_containers required for mme"""
        return [
            kubernetes.client.V1Container(
                name  = "spgwu-iptables-init",
                command = ["/opt/dp/scripts/setup-af-iface.sh"],
                image = "docker.io/omecproject/pod-init:1.0.0",
                image_pull_policy = "IfNotPresent",
                security_context = kubernetes.client.V1SecurityContext(
                    capabilities=kubernetes.client.V1Capabilities(add=["NET_ADMIN"])
    
                ),
                 volume_mounts = [
                    kubernetes.client.V1VolumeMount(
                        mount_path = "/opt/dp/scripts/setup-af-iface.sh",
                        sub_path = "setup-af-iface.sh",
                        name = "dp-script",
                    ),
                ],
            ),
        ]

#    @property
#    def spgwu_volume_mounts(self) -> dict:
#        """Returns the additional volume mounts for the mme-app containers"""
#        return [
#            kubernetes.client.V1VolumeMount(
#                mount_path="/abc/",
#                name="dp-script",
#            ),
#            kubernetes.client.V1VolumeMount(
#                name="dp-config",
#                mount_path="/etc/dp/config",
#            ),
#        ]'''


    @property
    def _service_accounts(self) -> list:
        """Return a dictionary containing parameters for the mme svc account"""
        return [
            {
                "namespace": self.namespace,
                "body": kubernetes.client.V1ServiceAccount(
                    api_version="v1",
                    metadata=kubernetes.client.V1ObjectMeta(
                        namespace=self.namespace,
                        name="mme",
                        labels={"app.kubernetes.io/name": self.app.name},
                    ),
                ),
            }
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
                        name="spgwu-dp-comm",
                        labels={"app.kubernetes.io/name": self.app.name},
                    ),
                    spec=kubernetes.client.V1ServiceSpec(
                        ports=[
                            kubernetes.client.V1ServicePort(
                                name="dp-comm",
                                port=8085,
                                protocol="UDP",
                                node_port=30020,
                            ),
                        ],
                        selector={"app.kubernetes.io/name": self.app.name},
                        type="NodePort",
                    ),
                ),
            },
        ]

    def loadfile(self, file_name):
        '''Read the file content and return content data'''
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

    @property
    def _configmaps(self) -> list:
        """Return a list of ConfigMaps needed by the mme"""
        dict_script = self._get_config_data(self.script_path)
        dict_config = self._get_config_data(self.configPath)
        dict_runscript=self._get_config_data(self.runscriptPath)
        return [
            {
                "namespace": self.namespace,
                "body": kubernetes.client.V1ConfigMap(
                    api_version="v1",
                    metadata=kubernetes.client.V1ObjectMeta(
                        namespace=self.namespace,
                        name="spgwu",
                        labels={
                            "app.kubernetes.io/name": self.app.name,
                            "app": self.app.name
                        },
                    ),
                    data=dict_script,

                ),
            },
           
         ]

    @property
    def _roles(self) -> list:
        """Return a list of Roles required by the mme"""
        return [
            {
                "namespace": self.namespace,
                "body": kubernetes.client.V1Role(
                    api_version="rbac.authorization.k8s.io/v1",
                    metadata=kubernetes.client.V1ObjectMeta(
                        namespace=self.namespace,
                        name="mme",
                        labels={"app.kubernetes.io/name": self.app.name},
                    ),
                    rules=[
                        # Allow mme to get, update, delete, list and patch the resources
                        kubernetes.client.V1PolicyRule(
                            api_groups=["", "extensions", "batch", "apps"],
                            resources=["statefulsets", "daemonsets", "jobs", "pods", "services", "endpoints", "configmaps"],
                            verbs=["get", "update", "delete", "list", "patch"],
                        ),
                    ],
                ),
            }
        ]

    @property
    def _rolebindings(self) -> list:
        """Return a list of Role Bindings required by the mme"""
        return [
            {
                "namespace": self.namespace,
                "body": kubernetes.client.V1RoleBinding(
                    api_version="rbac.authorization.k8s.io/v1",
                    metadata=kubernetes.client.V1ObjectMeta(
                        namespace=self.namespace,
                        name="mme",
                        labels={"app.kubernetes.io/name": self.app.name},
                    ),
                    role_ref=kubernetes.client.V1RoleRef(
                        api_group="rbac.authorization.k8s.io",
                        kind="Role",
                        name="mme",
                    ),
                    subjects=[
                        kubernetes.client.V1Subject(
                            kind="ServiceAccount",
                            name="mme",
                            namespace=self.namespace,
                        )
                    ],
                ),
            }
        ]

    @property
    def spgwu_volumes(self) -> dict:
        """Returns the additional volumes required by the mme"""
        return [
            kubernetes.client.V1Volume(
                name="dp-script",
                config_map=kubernetes.client.V1ConfigMapVolumeSource(
                    name="spgwu",
                    default_mode=493,
                ),
            ),
        ]
