#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#

import os
import re
from copy import deepcopy
from typing import Any

import yaml
from airbyte_api_client.model.airbyte_catalog import AirbyteCatalog
from airbyte_api_client.model.airbyte_stream import AirbyteStream
from airbyte_api_client.model.airbyte_stream_and_configuration import AirbyteStreamAndConfiguration
from airbyte_api_client.model.airbyte_stream_configuration import AirbyteStreamConfiguration
from airbyte_api_client.model.connection_schedule import ConnectionSchedule
from airbyte_api_client.model.connection_status import ConnectionStatus
from airbyte_api_client.model.destination_sync_mode import DestinationSyncMode
from airbyte_api_client.model.namespace_definition_type import NamespaceDefinitionType
from airbyte_api_client.model.resource_requirements import ResourceRequirements
from airbyte_api_client.model.sync_mode import SyncMode

ENV_VAR_MATCHER_PATTERN = re.compile(r".*\$\{([^}^{]+)\}.*")


def env_var_replacer(loader: yaml.Loader, node: yaml.Node) -> Any:
    """Convert a YAML node to a Python object, expanding variable.

    Args:
        loader (yaml.Loader): Not used
        node (yaml.Node): Yaml node to convert to python object

    Returns:
        Any: Python object with expanded vars.
    """
    return os.path.expandvars(node.value)


class EnvVarLoader(yaml.SafeLoader):
    pass


# All yaml nodes matching the regex will be tagged as !environment_variable.
EnvVarLoader.add_implicit_resolver("!environment_variable", ENV_VAR_MATCHER_PATTERN, None)

# All yaml nodes tagged as !environment_variable will be constructed with the env_var_replacer callback.
EnvVarLoader.add_constructor("!environment_variable", env_var_replacer)


class ConnectionConfiguration:
    def __init__(
        self,
        source_id,
        destination_id,
        status,
        name,
        namespace_definition,
        namespace_format,
        prefix,
        resource_requirements,
        schedule,
        sync_catalog,
    ) -> None:
        self.name = name
        self.source_id = source_id
        self.destination_id = destination_id
        self.sync_catalog = self.create_configured_catalog(sync_catalog)
        self.namespace_definition = NamespaceDefinitionType(namespace_definition)
        self.namespace_format = namespace_format
        self.prefix = prefix
        self.schedule = ConnectionSchedule(**schedule)
        self.resource_requirements = ResourceRequirements(**resource_requirements)
        self.status = ConnectionStatus(status)

    @staticmethod
    def create_configured_catalog(sync_catalog):

        streams_and_configurations = []
        for stream in deepcopy(sync_catalog)["streams"]:
            stream["stream"]["supported_sync_modes"] = [SyncMode(sm) for sm in stream["stream"]["supported_sync_modes"]]
            stream["config"]["sync_mode"] = SyncMode(stream["config"]["sync_mode"])
            stream["config"]["destination_sync_mode"] = DestinationSyncMode(stream["config"]["destination_sync_mode"])

            streams_and_configurations.append(
                AirbyteStreamAndConfiguration(
                    stream=AirbyteStream(**stream["stream"]), config=AirbyteStreamConfiguration(**stream["config"])
                )
            )
        return AirbyteCatalog(streams_and_configurations)

    def to_dict(self, filtered_out_keys=None):
        as_dict = {
            "name": self.name,
            "source_id": self.source_id,
            "destination_id": self.destination_id,
            "sync_catalog": self.sync_catalog,
            "namespace_definition": self.namespace_definition,
            "namespace_format": self.namespace_format,
            "prefix": self.prefix,
            "schedule": self.schedule,
            "resource_requirements": self.resource_requirements,
            "status": self.status,
        }
        if filtered_out_keys is None:
            return as_dict
        else:
            return {k: v for k, v in as_dict.items() if k not in filtered_out_keys}

    @property
    def for_create(self):
        return self.to_dict()

    @property
    def for_update(self):
        return self.to_dict(filtered_out_keys=["source_id", "destination_id"])
