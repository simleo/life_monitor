# Copyright (c) 2020-2021 CRS4
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import json
import logging

import pytest
from lifemonitor.api.services import LifeMonitor
from lifemonitor.auth.models import User
from tests import utils
from tests.conftest_helpers import enable_auto_login
from tests.conftest_types import ClientAuthenticationMethod

logger = logging.getLogger()


@pytest.mark.parametrize("client_auth_method", [
    ClientAuthenticationMethod.NOAUTH,
], indirect=True)
@pytest.mark.parametrize("user1", [True], indirect=True)
def test_user_subscribe_not_authorized(app_client, client_auth_method, user1, user1_auth, valid_workflow):
    workflow = utils.pick_workflow(user1, valid_workflow)
    r = app_client.post(
        utils.build_workflow_path(workflow, include_version=False, subpath='subscribe'), headers=user1_auth
    )
    assert r.status_code == 401, "Anonymous users should not be able to use the subscription API"


@pytest.mark.parametrize("client_auth_method", [
    ClientAuthenticationMethod.NOAUTH,
], indirect=True)
@pytest.mark.parametrize("user1", [True], indirect=True)
def test_user_unsubscribe_not_authorized(app_client, client_auth_method, user1, user1_auth, valid_workflow):
    workflow = utils.pick_workflow(user1, valid_workflow)
    r = app_client.post(
        utils.build_workflow_path(workflow, include_version=False, subpath='unsubscribe'), headers=user1_auth
    )
    assert r.status_code == 401, "Anonymous users should not be able to use the subscription API"


@pytest.mark.parametrize("client_auth_method", [
    #    ClientAuthenticationMethod.BASIC,
    ClientAuthenticationMethod.API_KEY,
    ClientAuthenticationMethod.AUTHORIZATION_CODE,
    ClientAuthenticationMethod.REGISTRY_CODE_FLOW
], indirect=True)
@pytest.mark.parametrize("user1", [True], indirect=True)
def test_user_subscribe_workflow(app_client, client_auth_method, user1, user1_auth, valid_workflow):
    workflow = utils.pick_workflow(user1, valid_workflow)
    logger.debug("User1 Auth Headers: %r", user1_auth)
    enable_auto_login(user1['user'])
    r = app_client.post(
        utils.build_workflow_path(workflow, include_version=False, subpath='subscribe'), headers=user1_auth
    )
    assert r.status_code == 204, f"Error when subscribing to the workflow {workflow}"


@pytest.mark.parametrize("client_auth_method", [
    #    ClientAuthenticationMethod.BASIC,
    ClientAuthenticationMethod.API_KEY,
    ClientAuthenticationMethod.AUTHORIZATION_CODE,
    ClientAuthenticationMethod.REGISTRY_CODE_FLOW
], indirect=True)
@pytest.mark.parametrize("user1", [True], indirect=True)
def test_user_unsubscribe_workflow(app_client, client_auth_method, user1, user1_auth, valid_workflow, lm: LifeMonitor):
    wdata = utils.pick_workflow(user1, valid_workflow)
    user: User = user1['user']
    enable_auto_login(user)
    # register a subscription
    workflow = lm.get_workflow(wdata['uuid'])
    assert workflow, "Invalid workflow"
    lm.subscribe_user_resource(user, workflow)
    assert len(user.subscriptions) == 1, "Invalid number of subscriptions"

    # try to delete the subscription via API
    r = app_client.post(
        utils.build_workflow_path(workflow, include_version=False, subpath='unsubscribe'), headers=user1_auth
    )
    assert r.status_code == 204, f"Error when unsubscribing to the workflow {workflow}"


@pytest.mark.parametrize("client_auth_method", [
    #    ClientAuthenticationMethod.BASIC,
    ClientAuthenticationMethod.API_KEY,
    ClientAuthenticationMethod.AUTHORIZATION_CODE,
    ClientAuthenticationMethod.REGISTRY_CODE_FLOW
], indirect=True)
@pytest.mark.parametrize("user1", [True], indirect=True)
def test_user_subscriptions(app_client, client_auth_method, user1, user1_auth, valid_workflow, lm: LifeMonitor):
    wdata = utils.pick_workflow(user1, valid_workflow)
    user: User = user1['user']
    enable_auto_login(user)
    # register a subscription
    workflow = lm.get_workflow(wdata['uuid'])
    assert workflow, "Invalid workflow"
    lm.subscribe_user_resource(user, workflow)
    assert len(user.subscriptions) == 1, "Invalid number of subscriptions"

    # get subscriptions of the current user
    r = app_client.get(
        '/users/current/subscriptions', headers=user1_auth
    )
    assert r.status_code == 200, "Error when trying to get user subscriptions"
    data = json.loads(r.data.decode())
    logger.info(data)
    assert "items" in data, "Invalid data format"
    assert len(data['items']) == 1, "Unexpected number of subscriptions"
    logger.info("The actual subscription: %r", data['items'][0])


@pytest.mark.parametrize("client_auth_method", [
    #    ClientAuthenticationMethod.BASIC,
    ClientAuthenticationMethod.API_KEY,
    ClientAuthenticationMethod.AUTHORIZATION_CODE,
    ClientAuthenticationMethod.REGISTRY_CODE_FLOW
], indirect=True)
@pytest.mark.parametrize("user1", [True], indirect=True)
def test_subscribed_workflow_by_user(app_client, client_auth_method,
                                     user1, user1_auth, user2, user2_auth, lm: LifeMonitor):
    user2_obj: User = user2['user']

    # get subscriptions of the user2
    r = app_client.get(
        '/users/current/subscriptions', headers=user2_auth)
    assert r.status_code == 200, "Error when trying to get user subscriptions"
    data = json.loads(r.data.decode())
    logger.info(data)
    assert len(data['items']) == 0, "Unexpected number of subscriptions for user2"

    # user2 subscribes to the workflow 'sort-and-change-case-travis'
    valid_workflow = 'sort-and-change-case-travis'
    wdata = utils.pick_workflow(user1, valid_workflow)

    # get workflows of user2
    r = app_client.get(
        '/users/current/workflows?subscriptions=true', headers=user2_auth
    )
    assert r.status_code == 200, "Error when trying to get user subscriptions"
    assert r.status_code == 200, "Error when trying to get user subscriptions"
    user2_workflows = json.loads(r.data.decode())['items']
    for i in user2_workflows:
        assert i['name'] != valid_workflow, f"'{valid_workflow}' should not in user2 workflow list"
    assert len(user2_workflows) == 2, "Unexpected number of workflows for user2"

    # user2 subscribes to 'sort-and-change-case-travis' workflow
    workflow = lm.get_workflow(wdata['uuid'])
    assert workflow, "Invalid workflow"
    lm.subscribe_user_resource(user2_obj, workflow)
    assert len(user2_obj.subscriptions) == 1, "Invalid number of subscriptions"

    # check again subscriptions of the user2
    r = app_client.get(
        '/users/current/subscriptions', headers=user2_auth)
    assert r.status_code == 200, "Error when trying to get user subscriptions"
    data = json.loads(r.data.decode())
    logger.info(data)
    assert len(data['items']) == 1, "Unexpected number of subscriptions for user2"

    # get workflows of user1
    r = app_client.get(
        '/users/current/workflows', headers=user1_auth
    )
    assert r.status_code == 200, "Error when trying to get user subscriptions"
    assert r.status_code == 200, "Error when trying to get user subscriptions"
    user1_workflows = json.loads(r.data.decode())
    assert 'items' in user1_workflows, "Invalid response format"
    for w in user1_workflows['items']:
        logger.info("Workflow %r", w['name'])

    # get workflows of user2 - include subscribed workflows
    r = app_client.get(
        '/users/current/workflows?subscriptions=true', headers=user2_auth
    )
    assert r.status_code == 200, "Error when trying to get user subscriptions"
    rj = json.loads(r.data.decode())
    assert 'items' in rj, "Invalid response format"
    user2_workflows = rj['items']
    for w in user2_workflows:
        logger.info("Workflow %r", w['name'])
    assert len(user2_workflows) == 3, "Unexpected number of workflows for user2"
    assert list(filter(lambda x: x['name'] == valid_workflow, user2_workflows)), "Subscribed workflow not found"

    # get workflows of user2 - do not include subscribed workflows
    r = app_client.get(
        '/users/current/workflows?subscriptions=false', headers=user2_auth
    )
    assert r.status_code == 200, "Error when trying to get user subscriptions"
    rj = json.loads(r.data.decode())
    assert 'items' in rj, "Invalid response format"
    user2_workflows = rj['items']
    assert len(user2_workflows) == 2, "Unexpected number of workflows for user2"
    assert list(filter(lambda x: x['name'] != valid_workflow, user2_workflows)), "Subscribed workflow should be included"
