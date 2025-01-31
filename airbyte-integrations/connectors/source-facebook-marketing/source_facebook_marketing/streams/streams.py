#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#

import base64
import logging
from itertools import chain
from typing import Any, Iterable, List, Mapping, Optional

import pendulum
import requests
from airbyte_cdk.models import SyncMode
from cached_property import cached_property
from facebook_business.adobjects.abstractobject import AbstractObject

from .base_insight_streams import AdsInsights
from .base_streams import FBMarketingIncrementalStream, FBMarketingReversedIncrementalStream, FBMarketingStream

logger = logging.getLogger("airbyte")


def fetch_thumbnail_data_url(url: str) -> Optional[str]:
    """Request thumbnail image and return it embedded into the data-link"""
    try:
        response = requests.get(url)
        if response.status_code == requests.status_codes.codes.OK:
            _type = response.headers["content-type"]
            data = base64.b64encode(response.content)
            return f"data:{_type};base64,{data.decode('ascii')}"
        else:
            logger.warning(f"Got {repr(response)} while requesting thumbnail image.")
    except requests.exceptions.RequestException as exc:
        logger.warning(f"Got {str(exc)} while requesting thumbnail image.")
    return None


class AdCreatives(FBMarketingStream):
    """AdCreative is append only stream
    doc: https://developers.facebook.com/docs/marketing-api/reference/ad-creative
    """

    entity_prefix = "adcreative"
    enable_deleted = False

    def __init__(self, fetch_thumbnail_images: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._fetch_thumbnail_images = fetch_thumbnail_images

    @cached_property
    def fields(self) -> List[str]:
        """Remove "thumbnail_data_url" field because it is computed field and it's not a field that we can request from Facebook"""
        return [f for f in super().fields if f != "thumbnail_data_url"]

    def read_records(
        self,
        sync_mode: SyncMode,
        cursor_field: List[str] = None,
        stream_slice: Mapping[str, Any] = None,
        stream_state: Mapping[str, Any] = None,
    ) -> Iterable[Mapping[str, Any]]:
        """Read with super method and append thumbnail_data_url if enabled"""
        for record in super().read_records(sync_mode, cursor_field, stream_slice, stream_state):
            if self._fetch_thumbnail_images:
                record["thumbnail_data_url"] = fetch_thumbnail_data_url(record.get("thumbnail_url"))
            yield record

    def list_objects(self, params: Mapping[str, Any]) -> Iterable:
        objects = []
        for account in self._api.accounts:
            objects = chain(objects, account.get_ad_creatives(params=params))
        return objects


class Ads(FBMarketingIncrementalStream):
    """doc: https://developers.facebook.com/docs/marketing-api/reference/adgroup"""

    entity_prefix = "ad"

    def list_objects(self, params: Mapping[str, Any]) -> Iterable:
        objects = []
        for account in self._api.accounts:
            objects = chain(objects, account.get_ads(params=params))
        return objects


class AdSets(FBMarketingIncrementalStream):
    """doc: https://developers.facebook.com/docs/marketing-api/reference/ad-campaign"""

    entity_prefix = "adset"

    def list_objects(self, params: Mapping[str, Any]) -> Iterable:
        objects = []
        for account in self._api.accounts:
            objects = chain(objects, account.get_ad_sets(params=params))
        return objects


class Campaigns(FBMarketingIncrementalStream):
    """doc: https://developers.facebook.com/docs/marketing-api/reference/ad-campaign-group"""

    entity_prefix = "campaign"
    primary_key = ["id"]

    def list_objects(self, params: Mapping[str, Any]) -> Iterable:
        objects = []
        for account in self._api.accounts:
            objects = chain(objects, account.get_campaigns(params=params))
        return objects


class Activities(FBMarketingIncrementalStream):
    """doc: https://developers.facebook.com/docs/marketing-api/reference/ad-activity"""

    entity_prefix = "activity"
    cursor_field = "event_time"
    primary_key = ["actor_id", "object_id", "event_time"]

    def list_objects(self, fields: List[str], params: Mapping[str, Any]) -> Iterable:
        objects = []
        for account in self._api.accounts:
            objects = chain(objects, account.get_activities(fields=fields, params=params))
        return objects

    def read_records(
        self,
        sync_mode: SyncMode,
        cursor_field: List[str] = None,
        stream_slice: Mapping[str, Any] = None,
        stream_state: Mapping[str, Any] = None,
    ) -> Iterable[Mapping[str, Any]]:
        """Main read method used by CDK"""
        loaded_records_iter = self.list_objects(fields=self.fields, params=self.request_params(stream_state=stream_state))

        for record in loaded_records_iter:
            if isinstance(record, AbstractObject):
                yield record.export_all_data()  # convert FB object to dict
            else:
                yield record  # execute_in_batch will emmit dicts

    def _state_filter(self, stream_state: Mapping[str, Any]) -> Mapping[str, Any]:
        """Additional filters associated with state if any set"""
        state_value = stream_state.get(self.cursor_field)
        since = self._start_date if not state_value else pendulum.parse(state_value)

        potentially_new_records_in_the_past = self._include_deleted and not stream_state.get("include_deleted", False)
        if potentially_new_records_in_the_past:
            self.logger.info(f"Ignoring bookmark for {self.name} because of enabled `include_deleted` option")
            since = self._start_date

        return {"since": since.int_timestamp}


class Videos(FBMarketingIncrementalStream):
    """See: https://developers.facebook.com/docs/marketing-api/reference/video"""

    entity_prefix = "video"

    def list_objects(self, params: Mapping[str, Any]) -> Iterable:
        objects = []
        for account in self._api.accounts:
            objects = chain(objects, account.get_ad_videos(params=params))
        return objects


class AdAccount(FBMarketingStream):
    """See: https://developers.facebook.com/docs/marketing-api/reference/ad-account"""

    use_batch = False
    enable_deleted = False

    def list_objects(self, params: Mapping[str, Any]) -> Iterable:
        """noop in case of AdAccount"""
        return self._api.accounts


class Images(FBMarketingReversedIncrementalStream):
    """See: https://developers.facebook.com/docs/marketing-api/reference/ad-image"""

    def list_objects(self, params: Mapping[str, Any]) -> Iterable:
        objects = []
        for account in self._api.accounts:
            objects = chain(objects, account.get_ad_images(params=params, fields=self.fields))
        return objects


class AdsInsightsAgeAndGender(AdsInsights):
    breakdowns = ["age", "gender"]


class AdsInsightsCountry(AdsInsights):
    breakdowns = ["country"]


class AdsInsightsRegion(AdsInsights):
    breakdowns = ["region"]


class AdsInsightsDma(AdsInsights):
    breakdowns = ["dma"]


class AdsInsightsPlatformAndDevice(AdsInsights):
    breakdowns = ["publisher_platform", "platform_position", "impression_device"]
    # FB Async Job fails for unknown reason if we set other breakdowns
    # my guess: it fails because of very large cardinality of result set (Eugene K)
    action_breakdowns = ["action_type"]


class AdsInsightsActionType(AdsInsights):
    breakdowns = []
    action_breakdowns = ["action_type"]
