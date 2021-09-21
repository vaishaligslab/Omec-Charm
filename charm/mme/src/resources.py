# Copyright 2021 Canonical
# See LICENSE file for licensing details.
import logging
import glob
import os

from kubernetes import kubernetes

logger = logging.getLogger(__name__)


class MmeResources:
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
        # Create required Kubernetes Service Accounts
        for sa in self._service_accounts:
            svc_accounts = self.core_api.list_namespaced_service_account(
                namespace=sa["namespace"],
                field_selector=f"metadata.name={sa['body'].metadata.name}",
            )
            if not svc_accounts.items:
                self.core_api.create_namespaced_service_account(**sa)
            else:
                logger.info(
                    "service account '%s' in namespace '%s' exists, patching",
                    sa["body"].metadata.name,
                    sa["namespace"],
                )
                self.core_api.patch_namespaced_service_account(name=sa["body"].metadata.name, **sa)

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

        # Create Kubernetes ConfigMaps
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

        # Create Kubernetes Roles
        for role in self._roles:
            r = self.auth_api.list_namespaced_role(
                namespace=role["namespace"],
                field_selector=f"metadata.name={role['body'].metadata.name}",
            )
            if not r.items:
                self.auth_api.create_namespaced_role(**role)
            else:
                logger.info(
                    "role '%s' in namespace '%s' exists, patching",
                    role["body"].metadata.name,
                    role["namespace"],
                )
                self.auth_api.patch_namespaced_role(name=role["body"].metadata.name, **role)

        # Create Kubernetes Role Bindings
        for rb in self._rolebindings:
            r = self.auth_api.list_namespaced_role_binding(
                namespace=rb["namespace"],
                field_selector=f"metadata.name={rb['body'].metadata.name}",
            )
            if not r.items:
                self.auth_api.create_namespaced_role_binding(**rb)
            else:
                logger.info(
                    "role binding '%s' in namespace '%s' exists, patching",
                    rb["body"].metadata.name,
                    rb["namespace"],
                )
                self.auth_api.patch_namespaced_role_binding(name=rb["body"].metadata.name, **rb)

        logger.info("Created additional Kubernetes resources")

    def delete(self) -> None:
        """Delete all of the Kubernetes resources created by the apply method"""
        # Delete service accounts
        for sa in self._service_accounts:
            self.core_api.delete_namespaced_service_account(
                namespace=sa["namespace"], name=sa["body"].metadata.name
            )
        # Delete Kubernetes services
        for service in self._services:
            self.core_api.delete_namespaced_service(
                namespace=service["namespace"], name=service["body"].metadata.name
            )
        # Delete Kubernetes configmaps
        for cm in self._configmaps:
            self.core_api.delete_namespaced_config_map(
                namespace=cm["namespace"], name=cm["body"].metadata.name
            )
        # Delete Kubernetes roles
        for role in self._roles:
            self.auth_api.delete_namespaced_role(
                namespace=role["namespace"], name=role["body"].metadata.name
            )
        # Delete Kubernetes role bindings
        for rb in self._rolebindings:
            self.auth_api.delete_namespaced_role_binding(
                namespace=rb["namespace"], name=rb["body"].metadata.name
            )

        logger.info("Deleted additional Kubernetes resources")

    @property
    def add_mme_init_containers(self) -> dict:
        """Returns the addtional init_containers required for mme"""
        return [
            kubernetes.client.V1Container(
                name  = "mme-configmap-mme-ip",
                command = ["/opt/mme/scripts/mme-ip.sh"],
                image = "docker.io/omecproject/pod-init:1.0.0",
                image_pull_policy = "IfNotPresent",
                volume_mounts = [
                    kubernetes.client.V1VolumeMount(
                        mount_path = "/opt/mme/scripts/mme-ip.sh",
                        sub_path = "mme-ip.sh",
                        name = "scripts",
                    ),
                ],
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
                        name = "POD_IP",
                        value_from = kubernetes.client.V1EnvVarSource(
                            field_ref = kubernetes.client.V1ObjectFieldSelector(field_path="status.podIP"),
                        ),
                    ),
                ],
            ),
            kubernetes.client.V1Container(
                name  = "mme-load-sctp-module",
                command = ["bash", "-xc"],
                args = ["if chroot /mnt/host-rootfs modinfo nf_conntrack_proto_sctp > /dev/null 2>&1; then chroot /mnt/host-rootfs modprobe nf_conntrack_proto_sctp; fi; chroot /mnt/host-rootfs modprobe tipc"],
                image = "docker.io/omecproject/pod-init:1.0.0",
                image_pull_policy = "IfNotPresent",
                security_context = kubernetes.client.V1SecurityContext(
                    privileged = True,
                    run_as_user = 0,
                ),
                volume_mounts = self._sctp_module_volume_mounts,
            ),
            kubernetes.client.V1Container(
                name  = "mme-dep-check",
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
                        value = '[{"labels": {"app.kubernetes.io/name": "hss"}, "requireSameNode": false}]',
                    ),
                ],
                command = ["kubernetes-entrypoint"],
            ),
            kubernetes.client.V1Container(
                name  = "mme-init",
                command = ["/opt/mme/scripts/mme-init.sh"],
                image = "amitinfo2k/nucleus-mme:9f86f87",
                image_pull_policy = "IfNotPresent",
                env = [
                    kubernetes.client.V1EnvVar(
                        name = "POD_IP",
                        value_from = kubernetes.client.V1EnvVarSource(
                            field_ref = kubernetes.client.V1ObjectFieldSelector(field_path="status.podIP"),
                        ),
                    ),
                ],
                volume_mounts = self._mme_init_volume_mounts,
            ),
        ]

    @property
    def mme_volumes(self) -> dict:
        """Returns the additional volumes required by the mme"""
        return [
            kubernetes.client.V1Volume(
                name="scripts",
                config_map=kubernetes.client.V1ConfigMapVolumeSource(
                    name="mme-scripts",
                    default_mode=493,
                ),
            ),
            kubernetes.client.V1Volume(
                name="configs",
                config_map=kubernetes.client.V1ConfigMapVolumeSource(
                    name="mme-configs",
                    default_mode=420,
                ),
            ),
            kubernetes.client.V1Volume(
                name="shared-data",
                empty_dir=kubernetes.client.V1EmptyDirVolumeSource(),
            ),
            kubernetes.client.V1Volume(
                name="shared-app",
                empty_dir=kubernetes.client.V1EmptyDirVolumeSource(),
            ),
            kubernetes.client.V1Volume(
                name="host-rootfs",
                host_path=kubernetes.client.V1HostPathVolumeSource(path="/"),
            ),
        ]

    @property
    def mme_volume_mounts(self) -> dict:
        """Returns the additional volume mounts for the mme-app containers"""
        return [
            kubernetes.client.V1VolumeMount(
                mount_path="/opt/mme/config/shared",
                name="shared-data",
            ),
            kubernetes.client.V1VolumeMount(
                name="shared-app",
                mount_path="/tmp",
            ),
            kubernetes.client.V1VolumeMount(
                name="scripts",
                mount_path="/opt/mme/scripts",
            ),
            kubernetes.client.V1VolumeMount(
                name="configs",
                mount_path="/opt/mme/config",
            ),
        ]

    @property
    def _sctp_module_volume_mounts(self) -> dict:
        """Returns the additional volume mounts for the sctp-module init_container"""
        return [
            kubernetes.client.V1VolumeMount(
                mount_path="/mnt/host-rootfs",
                name="host-rootfs",
            ),
        ]

    @property
    def _mme_init_volume_mounts(self) -> dict:
        """Returns the additional volume mounts for the mme-init init_container"""
        return [
            kubernetes.client.V1VolumeMount(
                mount_path="/opt/mme/config/shared",
                name="shared-data",
            ),
            kubernetes.client.V1VolumeMount(
                name="scripts",
                mount_path="/opt/mme/scripts",
            ),
            kubernetes.client.V1VolumeMount(
                name="configs",
                mount_path="/opt/mme/config",
            ),
        ]

    @property
    def s1ap_volume_mounts(self) -> dict:
        """Returns the additional volume mounts for the s1ap containers"""
        return [
            kubernetes.client.V1VolumeMount(
                mount_path="/opt/mme/config/shared",
                name="shared-data",
            ),
            kubernetes.client.V1VolumeMount(
                name="shared-app",
                mount_path="/tmp",
            ),
            kubernetes.client.V1VolumeMount(
                name="scripts",
                mount_path="/opt/mme/scripts",
            ),
            kubernetes.client.V1VolumeMount(
                name="configs",
                mount_path="/opt/mme/config",
            ),
        ]

    @property
    def s6a_volume_mounts(self) -> dict:
        """Returns the additional volume mounts for the s6a containers"""
        return [
            kubernetes.client.V1VolumeMount(
                mount_path="/opt/mme/config/shared",
                name="shared-data",
            ),
            kubernetes.client.V1VolumeMount(
                name="shared-app",
                mount_path="/tmp",
            ),
            kubernetes.client.V1VolumeMount(
                name="scripts",
                mount_path="/opt/mme/scripts",
            ),
        ]

    @property
    def s11_volume_mounts(self) -> dict:
        """Returns the additional volume mounts for the s11 containers"""
        return [
            kubernetes.client.V1VolumeMount(
                mount_path="/opt/mme/config/shared",
                name="shared-data",
            ),
            kubernetes.client.V1VolumeMount(
                name="shared-app",
                mount_path="/tmp",
            ),
            kubernetes.client.V1VolumeMount(
                name="scripts",
                mount_path="/opt/mme/scripts",
            ),
        ]

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
                        name=self.app.name,
                        labels={"app.kubernetes.io/name": self.app.name},
                    ),
                    spec=kubernetes.client.V1ServiceSpec(
                        ports=[
                            kubernetes.client.V1ServicePort(
                                name="s11",
                                port=2123,
                                protocol="UDP",
                            ),
                            kubernetes.client.V1ServicePort(
                                name="s6a",
                                port=3868,
                                protocol="TCP",
                            ),
                            kubernetes.client.V1ServicePort(
                                name="s1ap",
                                port=36412,
                                protocol="SCTP",
                            ),
                            kubernetes.client.V1ServicePort(
                                name="prometheus-exporter",
                                port=3081,
                                protocol="TCP",
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
                        name="mme-headless",
                        labels={"app.kubernetes.io/name": self.app.name},
                    ),
                    spec=kubernetes.client.V1ServiceSpec(
                        ports=[
                            kubernetes.client.V1ServicePort(
                                name="s11",
                                port=2123,
                                protocol="UDP",
                            ),
                            kubernetes.client.V1ServicePort(
                                name="s6a",
                                port=3868,
                                protocol="TCP",
                            ),
                            kubernetes.client.V1ServicePort(
                                name="s1ap",
                                port=36412,
                                protocol="SCTP",
                            ),
                        ],
                        selector={"app.kubernetes.io/name": self.app.name},
                        cluster_ip="None",
                    ),
                ),
            },
            {
                "namespace": self.namespace,
                "body": kubernetes.client.V1Service(
                    api_version="v1",
                    metadata=kubernetes.client.V1ObjectMeta(
                        namespace=self.namespace,
                        name="mme-external",
                        labels={"app.kubernetes.io/name": self.app.name},
                    ),
                    spec=kubernetes.client.V1ServiceSpec(
                        ports=[
                            kubernetes.client.V1ServicePort(
                                name="s1ap",
                                port=36412,
                                protocol="SCTP",
                                node_port=36412,
                            ),
                        ],
                        selector={"app.kubernetes.io/name": self.app.name},
                        type="NodePort",
                    ),
                ),
            },
        ]

    def _loadfile(self, file_name):
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
            file_data = self._loadfile(file_path)
            file_name = os.path.basename(file_path)
            dicts[file_name] = file_data
        return dicts

    @property
    def _configmaps(self) -> list:
        """Return a list of ConfigMaps needed by the mme"""
        dict_script = self._get_config_data(self.script_path)
        dict_config = self._get_config_data(self.config_path)
        return [
            {
                "namespace": self.namespace,
                "body": kubernetes.client.V1ConfigMap(
                    api_version="v1",
                    metadata=kubernetes.client.V1ObjectMeta(
                        namespace=self.namespace,
                        name="mme-scripts",
                        labels={
                            "app.kubernetes.io/name": self.app.name,
                            "app": self.app.name
                        },
                    ),
                    data=dict_script,
                ),
            },
            {
                "namespace": self.namespace,
                "body": kubernetes.client.V1ConfigMap(
                    api_version="v1",
                    metadata=kubernetes.client.V1ObjectMeta(
                        namespace=self.namespace,
                        name="mme-configs",
                        labels={
                            "app.kubernetes.io/name": self.app.name,
                            "app": self.app.name
                        },
                    ),
                    data=dict_config,
                ),
            },
            {
                "namespace": self.namespace,
                "body": kubernetes.client.V1ConfigMap(
                    api_version="v1",
                    metadata=kubernetes.client.V1ObjectMeta(
                        namespace=self.namespace,
                        name="mme-ip",
                        labels={
                            "app.kubernetes.io/name": self.app.name,
                            "app": "spgwc",
                        },
                    ),
                ),
            }
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
