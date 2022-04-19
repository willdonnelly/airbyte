#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#

from copy import deepcopy

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


class AirbyteConnectionConfiguration:
    def __init__(self, raw_configuration) -> None:
        self.sync_catalog = self.create_configured_catalog(raw_configuration["sync_catalog"])
        self.namespace_definition = NamespaceDefinitionType(raw_configuration["namespace_definition"])
        self.namespace_format = raw_configuration["namespace_format"]
        self.prefix = raw_configuration["prefix"]
        self.schedule = ConnectionSchedule(**raw_configuration["schedule"])
        self.resource_requirements = ResourceRequirements(**raw_configuration["resource_requirements"])
        self.status = ConnectionStatus(raw_configuration["status"])

    def to_dict(self):
        return {
            "sync_catalog": self.sync_catalog,
            "namespace_definition": self.namespace_definition,
            "namespace_format": self.namespace_format,
            "prefix": self.prefix,
            "schedule": self.schedule,
            "resource_requirements": self.resource_requirements,
            "status": self.status,
        }

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
