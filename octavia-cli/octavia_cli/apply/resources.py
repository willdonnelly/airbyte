#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#

import abc
import os
import time
from pathlib import Path
from typing import Callable, Optional, Union

import airbyte_api_client
import yaml
from airbyte_api_client.api import connection_api, destination_api, source_api
from airbyte_api_client.model.airbyte_catalog import AirbyteCatalog
from airbyte_api_client.model.connection_create import ConnectionCreate
from airbyte_api_client.model.connection_id_request_body import ConnectionIdRequestBody
from airbyte_api_client.model.connection_read import ConnectionRead
from airbyte_api_client.model.connection_update import ConnectionUpdate
from airbyte_api_client.model.destination_create import DestinationCreate
from airbyte_api_client.model.destination_id_request_body import DestinationIdRequestBody
from airbyte_api_client.model.destination_read import DestinationRead
from airbyte_api_client.model.destination_update import DestinationUpdate
from airbyte_api_client.model.source_create import SourceCreate
from airbyte_api_client.model.source_discover_schema_request_body import SourceDiscoverSchemaRequestBody
from airbyte_api_client.model.source_id_request_body import SourceIdRequestBody
from airbyte_api_client.model.source_read import SourceRead
from airbyte_api_client.model.source_update import SourceUpdate
from click import ClickException

from .configuration_serializers import AirbyteConnectionConfiguration
from .diff_helpers import compute_diff, hash_config
from .yaml_loaders import EnvVarLoader


class DuplicateResourceError(ClickException):
    pass


class NonExistingResourceError(ClickException):
    pass


class InvalidConfigurationError(ClickException):
    pass


class ResourceState:
    def __init__(self, configuration_path: str, resource_id: str, generation_timestamp: int, configuration_hash: str):
        """This constructor is meant to be private. Construction shall be made with create or from_file class methods.

        Args:
            configuration_path (str): Path to the configuration this state relates to.
            resource_id (str): Id of the resource the state relates to.
            generation_timestamp (int): State generation timestamp.
            configuration_hash (str): Hash of the loaded configuration file.
        """
        self.configuration_path = configuration_path
        self.resource_id = resource_id
        self.generation_timestamp = generation_timestamp
        self.configuration_hash = configuration_hash
        self.path = os.path.join(os.path.dirname(self.configuration_path), "state.yaml")

    def as_dict(self):
        return {
            "resource_id": self.resource_id,
            "generation_timestamp": self.generation_timestamp,
            "configuration_path": self.configuration_path,
            "configuration_hash": self.configuration_hash,
        }

    def _save(self) -> None:
        """Save the state as a YAML file."""
        with open(self.path, "w") as state_file:
            yaml.dump(self.as_dict(), state_file)

    @classmethod
    def create(cls, configuration_path: str, configuration_hash: str, resource_id: str) -> "ResourceState":
        """Create a state for a resource configuration.

        Args:
            configuration_path (str): Path to the YAML file defining the resource.
            configuration_hash (str): Hash of the loaded configuration fie.
            resource_id (str): UUID of the resource.

        Returns:
            ResourceState: state representing the resource.
        """
        generation_timestamp = int(time.time())
        state = ResourceState(configuration_path, resource_id, generation_timestamp, configuration_hash)
        state._save()
        return state

    @classmethod
    def from_file(cls, file_path: str) -> "ResourceState":
        """Deserialize a state from a YAML path.

        Args:
            file_path (str): Path to the YAML state.

        Returns:
            ResourceState: state deserialized from YAML.
        """
        with open(file_path, "r") as f:
            raw_state = yaml.safe_load(f)
        return ResourceState(
            raw_state["configuration_path"],
            raw_state["resource_id"],
            raw_state["generation_timestamp"],
            raw_state["configuration_hash"],
        )


class BaseResource(abc.ABC):
    APPLY_PRIORITY = 0  # Priority of the resource during the apply. 0 means the resource is top priority.
    ConfigurationSerializer = (
        None  # Declare a configuration serializer class if extra validation can be implemented on the raw configuration.
    )

    @property
    @abc.abstractmethod
    def api(
        self,
    ):  # pragma: no cover
        pass

    @property
    @abc.abstractmethod
    def create_function_name(
        self,
    ):  # pragma: no cover
        pass

    @property
    @abc.abstractmethod
    def create_payload(
        self,
    ):  # pragma: no cover
        pass

    @property
    @abc.abstractmethod
    def update_payload(
        self,
    ):  # pragma: no cover
        pass

    @property
    @abc.abstractmethod
    def update_function_name(
        self,
    ):  # pragma: no cover
        pass

    @property
    @abc.abstractmethod
    def get_function_name(
        self,
    ):  # pragma: no cover
        pass

    @property
    @abc.abstractmethod
    def get_payload(
        self,
    ):  # pragma: no cover
        pass

    @property
    @abc.abstractmethod
    def resource_id_field(
        self,
    ):  # pragma: no cover
        pass

    @property
    @abc.abstractmethod
    def ResourceIdRequestBody(
        self,
    ):  # pragma: no cover
        pass

    @property
    @abc.abstractmethod
    def resource_type(
        self,
    ):  # pragma: no cover
        pass

    def __init__(
        self, api_client: airbyte_api_client.ApiClient, workspace_id: str, raw_configuration: dict, configuration_path: str
    ) -> None:
        """Create a BaseResource object.

        Args:
            api_client (airbyte_api_client.ApiClient): the Airbyte API client.
            workspace_id (str): the workspace id.
            raw_configuration (dict): The local configuration describing the resource.
            configuration_path (str): The path to the local configuration describing the resource with YAML.
        """
        self._create_fn = getattr(self.api, self.create_function_name)
        self._update_fn = getattr(self.api, self.update_function_name)
        self._get_fn = getattr(self.api, self.get_function_name)

        self.configuration_path = configuration_path
        self.configuration_hash = hash_config(raw_configuration)
        self.raw_configuration = raw_configuration
        self.configuration = (
            self.ConfigurationSerializer(raw_configuration["configuration"])
            if self.ConfigurationSerializer is not None
            else raw_configuration["configuration"]
        )
        self.state = self._get_state_from_file(configuration_path)

        self.api_instance = self.api(api_client)
        self.workspace_id = workspace_id
        self.resource_name = raw_configuration["resource_name"]

        self.local_file_changed = True if self.state is None else self.configuration_hash != self.state.configuration_hash

    @property
    def remote_resource(self):
        return self._get_remote_resource() if self.state else None

    def _get_remote_comparable_configuration(
        self,
    ) -> Union[SourceRead, DestinationRead, dict]:  # pragma: no cover
        """Get the object to which local configuration will be compared to.

        Raises:
            NonExistingResourceError: Raised if the remote resource does not exists.

        Returns:
            Union[SourceRead, DestinationRead, dict]: The comparable configuration
        """
        if not self.was_created:
            raise NonExistingResourceError("Can't find a comparable configuration as the remote resource does not exists.")
        else:
            return self.remote_resource

    def _get_local_comparable_configuration(
        self,
    ) -> dict:  # pragma: no cover
        """Get the object to which remote configuration will be compared to.

        Returns:
            dict: The comparable configuration
        """
        return self.raw_configuration["configuration"]

    @property
    def was_created(self):
        return True if self.remote_resource else False

    def _get_remote_resource(self) -> Union[SourceRead, DestinationRead, ConnectionRead]:
        """Run search of a resources on the remote Airbyte instance.

        Returns:
            Union[SourceReadList, DestinationReadList, ConnectionReadList]: Search results
        """
        return self._get_fn(self.api_instance, self.get_payload)

    @staticmethod
    def _get_state_from_file(configuration_file: str) -> Optional[ResourceState]:
        """Retrieve a state object from a local YAML file if it exists.

        Returns:
            Optional[ResourceState]: the deserialized resource state if YAML file found.
        """
        expected_state_path = Path(os.path.join(os.path.dirname(configuration_file), "state.yaml"))
        if expected_state_path.is_file():
            return ResourceState.from_file(expected_state_path)

    def get_diff_with_remote_resource(self) -> str:
        """Compute the diff between current resource and the remote resource.

        Raises:
            NonExistingResourceError: Raised if the remote resource does not exist.

        Returns:
            str: The prettyfied diff.
        """
        if not self.was_created:
            raise NonExistingResourceError("Cannot compute diff with a non existing remote resource.")
        local_config = self._get_local_comparable_configuration()
        remote_config = self._get_remote_comparable_configuration()
        diff = compute_diff(remote_config, local_config)
        return diff.pretty()

    def _create_or_update(
        self,
        operation_fn: Callable,
        payload: Union[SourceCreate, SourceUpdate, DestinationCreate, DestinationUpdate, ConnectionCreate, ConnectionUpdate],
    ) -> Union[SourceRead, DestinationRead]:
        """Wrapper to trigger create or update of remote resource.

                Args:
                    operation_fn (Callable): The API function to run.
                    payload (Union[SourceCreate, SourceUpdate, DestinationCreate, DestinationUpdate]): The payload to send to create or update the resource.
        .
                Raises:
                    InvalidConfigurationError: Raised if the create or update payload is invalid.
                    ApiException: Raised in case of other API errors.

                Returns:
                    Union[SourceRead, DestinationRead, ConnectionRead]: The created or updated resource.
        """
        try:
            result = operation_fn(self.api_instance, payload)
            return result, ResourceState.create(self.configuration_path, self.configuration_hash, result[self.resource_id_field])
        except airbyte_api_client.ApiException as api_error:
            if api_error.status == 422:
                # This  API response error is really verbose, but it embodies all the details about why the config is not valid.
                # TODO alafanechere: try to parse it and display it in a more readable way.
                raise InvalidConfigurationError(api_error.body)
            else:
                raise api_error

    def create(self) -> Union[SourceRead, DestinationRead, ConnectionRead]:
        """Public function to create the resource on the remote Airbyte instance.

        Returns:
            Union[SourceRead, DestinationRead, ConnectionRead]: The created resource.
        """
        return self._create_or_update(self._create_fn, self.create_payload)

    def update(self) -> Union[SourceRead, DestinationRead, ConnectionRead]:
        """Public function to update the resource on the remote Airbyte instance.

        Returns:
            Union[SourceRead, DestinationRead, ConnectionRead]: The updated resource.
        """
        return self._create_or_update(self._update_fn, self.update_payload)

    @property
    def resource_id(self) -> Optional[str]:
        """Exposes the resource UUID of the remote resource

        Returns:
            str: Remote resource's UUID
        """
        return self.state.resource_id if self.state is not None else None

    @property
    def resource_id_request_body(self) -> Union[SourceIdRequestBody, DestinationIdRequestBody]:
        """Creates SourceIdRequestBody or DestinationIdRequestBody from resource id.

        Raises:
            NonExistingResourceError: raised if the resource id is None.

        Returns:
            Union[SourceIdRequestBody, DestinationIdRequestBody]: The model instance.
        """
        if self.resource_id is None:
            raise NonExistingResourceError("The resource id could not be retrieved, the remote resource is not existing.")
        return self.ResourceIdRequestBody(self.resource_id)


class SourceAndDestination(BaseResource):
    @property
    def definition_id(self):
        return self.raw_configuration["definition_id"]

    @property
    def definition_image(self):
        return self.raw_configuration["definition_image"]

    @property
    def definition_version(self):
        return self.raw_configuration["definition_version"]

    def _get_remote_comparable_configuration(self) -> dict:
        comparable_configuration = super()._get_remote_comparable_configuration()
        return comparable_configuration.connection_configuration


class Source(SourceAndDestination):

    api = source_api.SourceApi
    create_function_name = "create_source"
    resource_id_field = "source_id"
    ResourceIdRequestBody = SourceIdRequestBody
    get_function_name = "get_source"
    update_function_name = "update_source"
    resource_type = "source"

    @property
    def create_payload(self):
        return SourceCreate(self.definition_id, self.configuration, self.workspace_id, self.resource_name)

    @property
    def get_payload(self):
        if self.state is not None:
            return SourceIdRequestBody(self.state.resource_id)

    @property
    def update_payload(self):
        return SourceUpdate(
            source_id=self.resource_id,
            connection_configuration=self.configuration,
            name=self.resource_name,
        )

    @property
    def source_discover_schema_request_body(self) -> SourceDiscoverSchemaRequestBody:
        """Creates SourceDiscoverSchemaRequestBody from resource id.

        Raises:
            NonExistingResourceError: raised if the resource id is None.

        Returns:
            SourceDiscoverSchemaRequestBody: The SourceDiscoverSchemaRequestBody model instance.
        """
        if self.resource_id is None:
            raise NonExistingResourceError("The resource id could not be retrieved, the remote resource is not existing.")
        return SourceDiscoverSchemaRequestBody(self.resource_id)

    @property
    def catalog(self) -> AirbyteCatalog:
        """Retrieves the source's Airbyte catalog.

        Returns:
            AirbyteCatalog: The catalog issued by schema discovery.
        """
        schema = self.api_instance.discover_schema_for_source(self.source_discover_schema_request_body)
        return schema.catalog


class Destination(SourceAndDestination):
    api = destination_api.DestinationApi
    create_function_name = "create_destination"
    resource_id_field = "destination_id"
    ResourceIdRequestBody = DestinationIdRequestBody
    get_function_name = "get_destination"
    update_function_name = "update_destination"
    resource_type = "destination"

    @property
    def create_payload(self) -> DestinationCreate:
        """Defines the payload to create the remote resource.

        Returns:
            DestinationCreate: The DestinationCreate model instance
        """
        return DestinationCreate(self.workspace_id, self.resource_name, self.definition_id, self.configuration)

    @property
    def get_payload(self) -> DestinationRead:
        """Defines the payload to search the remote resource. Search by resource name if no state found, otherwise search by resource id found in the state.
        Returns:
            DestinationSearch: The DestinationSearch model instance
        """
        if self.state is not None:
            return DestinationIdRequestBody(self.state.resource_id)

    @property
    def update_payload(self) -> DestinationUpdate:
        """Defines the payload to update a remote resource.

        Returns:
            DestinationUpdate: The DestinationUpdate model instance.
        """
        return DestinationUpdate(
            destination_id=self.resource_id,
            connection_configuration=self.configuration,
            name=self.resource_name,
        )


class Connection(BaseResource):
    APPLY_PRIORITY = 1  # Set to 1 to create connection after source or destination.
    ConfigurationSerializer = AirbyteConnectionConfiguration
    api = connection_api.ConnectionApi
    create_function_name = "create_connection"
    resource_id_field = "connection_id"
    ResourceIdRequestBody = ConnectionIdRequestBody
    get_function_name = "get_connection"
    update_function_name = "update_connection"
    resource_type = "connection"

    @property
    def source_id(self):
        return self.raw_configuration["source_id"]

    @property
    def destination_id(self):
        return self.raw_configuration["destination_id"]

    @property
    def create_payload(self) -> ConnectionCreate:
        """Defines the payload to create the remote connection.

        Returns:
            ConnectionCreate: The ConnectionCreate model instance
        """
        return ConnectionCreate(
            name=self.resource_name, source_id=self.source_id, destination_id=self.destination_id, **self.configuration.to_dict()
        )

    @property
    def get_payload(self) -> ConnectionRead:
        """Defines the payload to search the remote resource. Search by resource name if no state found, otherwise search by resource id found in the state.
        Returns:
            DestinationSearch: The DestinationSearch model instance
        """
        if self.state is not None:
            return ConnectionIdRequestBody(self.state.resource_id)

    @property
    def update_payload(self) -> ConnectionUpdate:
        """Defines the payload to update a remote connection.

        Returns:
            ConnectionUpdate: The DestinationUpdate model instance.
        """
        return ConnectionUpdate(connection_id=self.resource_id, **self.configuration.to_dict())

    def create(self) -> dict:
        return self._create_or_update(self._create_fn, self.create_payload)

    def update(self) -> dict:
        return self._create_or_update(self._update_fn, self.update_payload)

    def _get_remote_comparable_configuration(self) -> dict:
        keys_to_filter_out = [
            "source_id",
            "name",
            "destination_id",
            "connection_id",
            "operation_ids",
        ]  # We do not allow local edition of these keys
        comparable_configuration = super()._get_remote_comparable_configuration()
        return {k: v for k, v in comparable_configuration.to_dict().items() if k not in keys_to_filter_out}


def factory(api_client: airbyte_api_client.ApiClient, workspace_id: str, configuration_path: str) -> Union[Source, Destination, Connection]:
    """Create resource object according to the definition type field in their YAML configuration.

    Args:
        api_client (airbyte_api_client.ApiClient): The Airbyte API client.
        workspace_id (str): The current workspace id.
        configuration_path (str): Path to the YAML file with the configuration.

    Raises:
        NotImplementedError: Raised if the definition type found in the YAML is not a supported resource.

    Returns:
        Union[Source, Destination, Connection]: The resource object created from the YAML config.
    """
    with open(configuration_path, "r") as f:
        raw_configuration = yaml.load(f, EnvVarLoader)
    if raw_configuration["definition_type"] == "source":
        return Source(api_client, workspace_id, raw_configuration, configuration_path)
    if raw_configuration["definition_type"] == "destination":
        return Destination(api_client, workspace_id, raw_configuration, configuration_path)
    if raw_configuration["definition_type"] == "connection":
        return Connection(api_client, workspace_id, raw_configuration, configuration_path)
    else:
        raise NotImplementedError(f"Resource {raw_configuration['definition_type']} was not yet implemented")
