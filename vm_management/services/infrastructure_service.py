"""Infrastructure service for the VM management service"""

import hashlib
import logging
import uuid
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from mako.lookup import TemplateLookup
from mako.template import Template
from msfwk.context import current_config
from msfwk.utils.config import read_config
from msfwk.utils.user import get_current_user
from pydantic import BaseModel
from yaml import SafeLoader, load

from vm_management.exceptions import InfrastructureError
from vm_management.models import ServerCreationPayload
from vm_management.utils import generate_sha512_hash

logger = logging.getLogger("application")

if TYPE_CHECKING:
    from msfwk.models import DespUser

k8s_config.load_incluster_config()


class TerraformConfig(BaseModel):
    """Configuration for terraform operations"""

    openstack_keypair_name: str
    openstack_network_port_id: str
    job_template_name: str = "terraform-job-template.tpl"
    create_external_volume: bool
    external_volume_size: int


class AnsibleConfig(BaseModel):
    """Configuration for ansible operations"""

    playbook_template_name: str = "ansible-playbook-template.tpl"
    playbook_name: str = "ansible_playbook.yaml"
    job_template_name: str = "ansible-job-template.tpl"


class InfrastructureConfig(BaseModel):
    """Configuration for infrastructure operations"""

    environment: str
    vm_management_host: str
    namespace: str
    job_template_path: str = "job-template"
    terraform_config: TerraformConfig
    ansible_config: AnsibleConfig


class InfrastructureService:
    """Service for managing infrastructure operations (Terraform, Ansible, K8s)"""

    def __init__(self, config: InfrastructureConfig) -> None:
        self.config = config
        self.k8s_batch_api = k8s_client.BatchV1Api()
        self.k8s_core_api = k8s_client.CoreV1Api()

    async def create_server_with_terraform(
        self, server_id: uuid.UUID, server_creation_payload: ServerCreationPayload, transaction_id: str = ""
    ) -> None:
        """Create server infrastructure using terraform

        Args:
            server_id: Server ID in the database
            server_creation_payload: Server creation payload
            transaction_id: Transaction ID
        """
        logger.info("Creating server infrastructure for server %s", server_id)
        await self._run_terraform_job(
            server_id=server_id, server_creation_payload=server_creation_payload, transaction_id=transaction_id
        )

    def _render_template(self, context: dict[str, Any], file_folder: str, file_name: str) -> str:
        """Render a mako template

        Args:
            context: Template context
            file_folder: Folder containing the template
            file_name: Template file name

        Returns:
            str: Rendered template
        """
        try:
            lookup = TemplateLookup(
                directories=[f"./{file_folder}"], default_filters=["h"], input_encoding="utf-8", output_encoding="utf-8"
            )
            content = Template(filename=f"./{file_folder}/{file_name}", lookup=lookup).render(**context)  # noqa: S702 (fixed with the template lookup)

            sha256_hash = hashlib.sha256()
            sha256_hash.update(content.encode("utf-8"))
            hash_hex = sha256_hash.hexdigest()
            logger.debug("Generated content:\n%s\nSHA256: %s", content, hash_hex)

            return content
        except Exception as e:
            logger.exception("Failed to render template %s", file_name)
            msg = f"Failed to render template: {e}"
            raise InfrastructureError(msg)

    def _create_k8s_configmap(self, name: str, data: dict[str, str]) -> None:
        """Create a Kubernetes ConfigMap

        Args:
            name: ConfigMap name
            data: ConfigMap data
        """
        try:
            configmap = k8s_client.V1ConfigMap(
                metadata=k8s_client.V1ObjectMeta(name=name),
                data=data,
            )

            self.k8s_core_api.create_namespaced_config_map(
                namespace=self.config.namespace,
                body=configmap,
            )
        except Exception as e:
            logger.exception("Failed to create ConfigMap %s", name)
            msg = f"Failed to create ConfigMap: {e}"
            raise InfrastructureError(msg)

    async def _run_terraform_job(
        self, server_id: uuid.UUID, server_creation_payload: ServerCreationPayload, transaction_id: str
    ) -> str:
        """Run terraform job in kubernetes to create a server

        Args:
            server_id: Server ID
            server_creation_payload: Server creation payload
            transaction_id: Transaction ID

        Returns:
            str: Job UUID
        """
        try:
            job_uuid = str(uuid.uuid4())

            job_name = f"{server_creation_payload.username}-{job_uuid}"
            server_name = f"{server_creation_payload.username}-{job_uuid}"

            create_volume = self.config.terraform_config.create_external_volume
            volume_size = self.config.terraform_config.external_volume_size

            password = generate_sha512_hash(server_creation_payload.password)

            # Prepare terraform variables
            job_template_vars = {
                "job_name": job_name,
                "env_variables": {
                    "DB_SERVER_ID": server_id,
                    "VM_MANAGEMENT_HOST": self.config.vm_management_host,
                    "TRANSACTION_ID": transaction_id,
                    "TF_VAR_server_name": server_name,
                    "TF_VAR_image_name": server_creation_payload.image_name,
                    "TF_VAR_flavor_name": server_creation_payload.flavor_name,
                    "TF_VAR_key_pair_name": self.config.terraform_config.openstack_keypair_name,
                    "TF_VAR_ssh_public_key": server_creation_payload.ssh_public_key,
                    "TF_VAR_username": server_creation_payload.username,
                    "TF_VAR_password": password,
                    "TF_VAR_network_port_id": self.config.terraform_config.openstack_network_port_id,
                    "TF_VAR_environment": self.config.environment,
                    "TF_VAR_create_volume": str(create_volume).lower(),
                    "TF_VAR_volume_size": volume_size,
                },
            }

            # Render the job template
            output = self._render_template(
                job_template_vars,
                self.config.job_template_path,
                self.config.terraform_config.job_template_name,
            )
            job_manifest = load(output, Loader=SafeLoader)

            # Create the Kubernetes job
            self.k8s_batch_api.create_namespaced_job(
                namespace=self.config.namespace,
                body=job_manifest,
            )

            logger.info("Created Terraform job for creating server %s", server_id)
            return job_uuid

        except Exception as e:
            logger.exception("Failed to run Terraform job")
            msg = f"Failed to run Terraform job: {e}"
            raise InfrastructureError(msg)

    async def run_ansible_setup(
        self, server_id: uuid.UUID, server_ip: str, project: dict[str, Any], transaction_id: str
    ) -> None:
        """Run ansible setup on a server

        Args:
            server_id: Server ID
            server_ip: Server IP address
            project: Project information (from project management)
            transaction_id: Transaction ID
        """
        try:
            job_uuid = str(uuid.uuid4())
            configmap_name = f"ansible-config-{job_uuid}"
            repository_group = current_config.get().get("services").get("project-management").get("repository_group")

            # Create HTTPS URL from git URL
            https_url = (
                project["repository"]["url"]
                .replace("git@", "https://")
                .replace(f":{repository_group}", f"/{repository_group}")
                .replace("https://", f"https://{project['profile']['username']}:{project['repository']['token']}@")
            )

            user: DespUser = get_current_user()
            if user is None:
                user_email = f"{project['profile']['username']}@desp.com"
            else:
                user_email = user.profile.email
                if user_email is None:
                    user_email = f"{project['profile']['username']}@desp.com"

            # Prepare ansible context
            context = {
                "hosts": server_ip,
                "apps": project["applications"],
                "username": project["profile"]["username"],
                "token": project["repository"]["url"],
                "url": https_url,
                "email": user_email,
                "projectName": project["name"],
                "projectId": project["id"],
                "projectProfileId": project["profile"]["id"],
            }

            # Render the ansible playbook
            playbook_content = self._render_template(
                context, self.config.job_template_path, self.config.ansible_config.playbook_template_name
            )

            logger.debug("Generated Ansible playbook:\n%s", playbook_content)

            # Create ConfigMap with the playbook
            self._create_k8s_configmap(configmap_name, {self.config.ansible_config.playbook_name: playbook_content})

            # Create and run the ansible job
            await self._run_ansible_job(job_uuid, configmap_name, server_ip, server_id, transaction_id)

            logger.info("Created Ansible job for server %s at %s", server_id, server_ip)

        except Exception as e:
            logger.exception("Failed to run Ansible setup")
            msg = f"Failed to run Ansible setup: {e}"
            raise InfrastructureError(msg)

    async def _run_ansible_job(
        self, job_uuid: str, config_map_name: str, server_ip: str, server_id: uuid.UUID, transaction_id: str
    ) -> None:
        """Create and run a Kubernetes job for Ansible

        Args:
            config_map_name: Name of the ConfigMap containing the ansible playbook
            server_ip: Server IP address
            server_id: Server ID
            transaction_id: Transaction ID
        """
        try:
            job_name = f"ansible-job-{job_uuid}"

            # Prepare job context
            job_context = {
                "VM_MANAGEMENT_HOST": self.config.vm_management_host,
                "DB_SERVER_ID": server_id,
                "ANSIBLE_JOB_NAME": job_name,
                "SERVER_IP": server_ip,
                "CONFIG_MAP_NAME": config_map_name,
                "TRANSACTION_ID": transaction_id,
                "EXECUTION_ENV": self.config.environment,
            }

            # Render the job template
            output = self._render_template(
                job_context, self.config.job_template_path, self.config.ansible_config.job_template_name
            )
            job_manifest = load(output, Loader=SafeLoader)

            # Create the Kubernetes job
            self.k8s_batch_api.create_namespaced_job(
                namespace=self.config.namespace,
                body=job_manifest,
            )

            logger.info("Created Ansible job %s for server %s", job_name, server_id)

        except Exception as e:
            logger.exception("Failed to create Ansible job")
            msg = f"Failed to create Ansible job: {e}"
            raise InfrastructureError(msg)


async def get_infrastructure_config() -> InfrastructureConfig:
    """Returns infrastructure terraforma and ansible configuration"""
    config = read_config().get("services").get("vm-management")

    environment = read_config().get("general").get("application_environment")

    terraform_config = TerraformConfig(
        openstack_keypair_name=config.get("openstack_key_pair_name"),
        openstack_network_port_id=config.get("openstack_network_port_id"),
        create_external_volume=config.get("create_external_volume"),
        external_volume_size=config.get("external_volume_size"),
    )

    return InfrastructureConfig(
        vm_management_host=config.get("host"),
        environment=environment,
        terraform_config=terraform_config,
        ansible_config=AnsibleConfig(),
        namespace=config.get("namespace_job_terraform"),
    )


async def get_infrastructure_service(
    infrastructure_config: Annotated[InfrastructureConfig, Depends(get_infrastructure_config)],
) -> InfrastructureService:
    """Get infrastructure service instance

    Args:
        infrastructure_config: Infrastructure configuration

    Returns:
        InfrastructureService: Infrastructure service instance
    """
    return InfrastructureService(infrastructure_config)
