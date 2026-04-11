from __future__ import annotations

from kubernetes import client, config
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException


class KubeflowClient:
    def __init__(self, namespace: str, group: str, version: str, plural: str, in_cluster: bool = False, kubeconfig: str | None = None) -> None:
        self.namespace = namespace
        self.group = group
        self.version = version
        self.plural = plural
        self.available = True
        try:
            self._api_client = self._build_api_client(in_cluster=in_cluster, kubeconfig=kubeconfig)
            self._custom_api = client.CustomObjectsApi(self._api_client)
        except Exception:
            self.available = False
            self._api_client = None
            self._custom_api = None

    def _build_api_client(self, in_cluster: bool, kubeconfig: str | None) -> ApiClient:
        if in_cluster:
            config.load_incluster_config()
        else:
            config.load_kube_config(config_file=kubeconfig)
        return client.ApiClient()

    async def submit_pytorch_job(self, job_name: str, image: str, command: list[str] | None = None) -> str:
        if not self.available or self._custom_api is None:
            raise RuntimeError("kubeflow client unavailable")
        container_spec: dict = {
            "name": "pytorch",
            "image": image,
        }
        if command:
            container_spec["command"] = command
        else:
            container_spec["command"] = ["python", "-c", "print('train')"]
        body = {
            "apiVersion": f"{self.group}/{self.version}",
            "kind": "PyTorchJob",
            "metadata": {"name": job_name, "namespace": self.namespace},
            "spec": {
                "pytorchReplicaSpecs": {
                    "Master": {
                        "replicas": 1,
                        "restartPolicy": "Never",
                        "template": {
                            "spec": {
                                "containers": [
                                    container_spec
                                ]
                            }
                        },
                    }
                }
            },
        }
        self._custom_api.create_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural,
            body=body,
        )
        return job_name

    async def get_job_phase(self, job_name: str) -> str:
        if not self.available or self._custom_api is None:
            raise RuntimeError("kubeflow client unavailable")
        obj = self._custom_api.get_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=self.namespace,
            plural=self.plural,
            name=job_name,
        )
        conditions = obj.get("status", {}).get("conditions", [])
        if not conditions:
            return "Running"
        return conditions[-1].get("type", "Running")

    async def delete_job(self, job_name: str) -> bool:
        if not self.available or self._custom_api is None:
            return False
        try:
            self._custom_api.delete_namespaced_custom_object(
                group=self.group,
                version=self.version,
                namespace=self.namespace,
                plural=self.plural,
                name=job_name,
            )
            return True
        except ApiException:
            return False

    async def get_job_logs(self, job_name: str) -> str:
        if not self.available or self._api_client is None:
            raise RuntimeError("kubeflow client unavailable")
        core_api = client.CoreV1Api(self._api_client)
        pods = core_api.list_namespaced_pod(
            namespace=self.namespace,
            label_selector=f"training.kubeflow.org/job-name={job_name}",
        )
        if not pods.items:
            return ""
        pod_name = pods.items[0].metadata.name
        return core_api.read_namespaced_pod_log(
            name=pod_name,
            namespace=self.namespace,
        )
