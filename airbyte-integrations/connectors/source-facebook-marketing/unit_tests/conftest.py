#
# Copyright (c) 2021 Airbyte, Inc., all rights reserved.
#

import pendulum
from facebook_business import FacebookAdsApi, FacebookSession
from pytest import fixture
from source_facebook_marketing.api import API

FB_API_VERSION = FacebookAdsApi.API_VERSION


@fixture(autouse=True)
def time_sleep_mock(mocker):
    time_mock = mocker.patch("time.sleep")
    yield time_mock


@fixture(scope="session", name="account_id")
def account_id_fixture():
    return "unknown_account"


@fixture(scope="session", name="some_config")
def some_config_fixture(account_id):
    return {"start_date": "2021-01-23T00:00:00Z", "access_token": "unknown_token"}


@fixture(autouse=True)
def mock_default_sleep_interval(mocker):
    mocker.patch("source_facebook_marketing.streams.common.DEFAULT_SLEEP_INTERVAL", return_value=pendulum.duration(seconds=5))


@fixture(autouse=True)
def mock_accounts(mocker, account_id):
    mock_account = mocker.Mock()
    mock_account.account_id = account_id
    mocker.patch("facebook_business.adobjects.user.User.get_ad_accounts", return_value=[mock_account])


@fixture(name="fb_account_response")
def fb_account_response_fixture(account_id):
    return {
        "json": {
            "data": [
                {
                    "account_id": account_id,
                    "id": f"act_{account_id}",
                }
            ],
            "paging": {"cursors": {"before": "MjM4NDYzMDYyMTcyNTAwNzEZD", "after": "MjM4NDYzMDYyMTcyNTAwNzEZD"}},
        },
        "status_code": 200,
    }


@fixture(name="api")
def api_fixture(some_config, requests_mock, fb_account_response, account_id):
    api = API(access_token=some_config["access_token"])

    requests_mock.register_uri("GET", FacebookSession.GRAPH + f"/{FB_API_VERSION}/me/adaccounts", [fb_account_response])
    requests_mock.register_uri("GET", FacebookSession.GRAPH + f"/{FB_API_VERSION}/act_{account_id}/", [fb_account_response])
    return api
