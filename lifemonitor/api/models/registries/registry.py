from __future__ import annotations

import logging
import uuid as _uuid
from typing import Union, List
from abc import ABC, abstractmethod
from authlib.integrations.base_client import RemoteApp
from sqlalchemy.dialects.postgresql import UUID
from lifemonitor.db import db
from lifemonitor.auth.models import User
from sqlalchemy.ext.associationproxy import association_proxy
from lifemonitor.auth.oauth2.client.services import oauth2_registry

from lifemonitor.common import (EntityNotFoundException)
from lifemonitor.utils import download_url, to_camel_case
from lifemonitor.auth.oauth2.client.models import OAuthIdentity


import lifemonitor.api.models as models

# set module level logger
logger = logging.getLogger(__name__)




class WorkflowRegistryClient(ABC):

    def __init__(self, registry: WorkflowRegistry):
        self._registry = registry
        try:
            self._oauth2client: RemoteApp = getattr(oauth2_registry, self.registry.name)
        except AttributeError:
            raise RuntimeError(f"Unable to find a OAuth2 client for the {self.registry.name} service")

    @property
    def registry(self):
        return self._registry

    def _get_access_token(self, user_id):
        # get the access token related with the user of this client registry
        return OAuthIdentity.find_by_user_id(user_id, self.registry.name).token

    def _get(self, user, *args, **kwargs):
        # update token
        self._oauth2client.token = self._get_access_token(user.id)
        return self._oauth2client.get(*args, **kwargs)

    def download_url(self, url, user, target_path=None):
        return download_url(url, target_path,
                            authorization=f'Bearer {self._get_access_token(user.id)["access_token"]}')

    def get_external_id(self, uuid, version, user: User) -> str:
        """ Return CSV of uuid and version"""
        return ",".join([str(uuid), str(version)])

    @abstractmethod
    def build_ro_link(self, w: models.Workflow) -> str:
        pass

    @abstractmethod
    def get_workflows_metadata(self, user, details=False):
        pass

    @abstractmethod
    def get_workflow_metadata(self, user, w: Union[models.Workflow, str]):
        pass

    @abstractmethod
    def filter_by_user(workflows: list, user: User):
        pass


class WorkflowRegistry(db.Model):

    uuid = db.Column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    uri = db.Column(db.Text, unique=True)
    type = db.Column(db.String, nullable=False)
    _client_id = db.Column(db.Integer, db.ForeignKey('client.id', ondelete='CASCADE'))
    _server_id = db.Column(db.Integer, db.ForeignKey('oauth2_identity_provider.id', ondelete='CASCADE'))
    client_credentials = db.relationship("Client", uselist=False, cascade="all, delete")
    server_credentials = db.relationship("OAuth2IdentityProvider", uselist=False, cascade="all, delete")
    registered_workflows = db.relationship("Workflow",
                                           back_populates="workflow_registry", cascade="all, delete")
    client_id = association_proxy('client_credentials', 'client_id')
    name = association_proxy('server_credentials', 'name')
    # _uri = association_proxy('server_credentials', 'api_base_url')

    _client = None

    __mapper_args__ = {
        'polymorphic_identity': 'workflow_registry',
        'polymorphic_on': type,
    }

    def __init__(self, client_credentials, server_credentials):
        self.__instance = self
        self.uri = server_credentials.api_base_url
        self.client_credentials = client_credentials
        self.server_credentials = server_credentials
        self._client = None

    @property
    def name(self):
        return self.server_credentials.name

    @name.setter
    def name(self, value):
        self.server_credentials.name = value

    @property
    def client(self) -> WorkflowRegistryClient:
        if self._client is None:
            return models.registries.get_registry_client_class(self.type)(self)
        return self._client

    def build_ro_link(self, w: models.Workflow) -> str:
        return self.client.build_ro_link(w)

    def download_url(self, url, user, target_path=None):
        return self.client.download_url(url, user, target_path=target_path)

    @property
    def users(self) -> List[User]:
        return self.get_users()

    def get_user(self, user_id) -> User:
        for u in self.users:
            logger.debug(f"Checking {u.id} {user_id}")
            if u.id == user_id:
                return u
        raise EntityNotFoundException(User, entity_id=user_id)

    def get_users(self) -> List[User]:
        try:
            return [i.user for i in OAuthIdentity.query
                    .filter(OAuthIdentity.provider == self.server_credentials).all()]
        except Exception as e:
            raise EntityNotFoundException(e)

    def add_workflow(self, workflow_uuid, workflow_version,
                     workflow_submitter: User,
                     roc_link, roc_metadata=None,
                     external_id=None, name=None):
        if external_id is None:
            try:
                external_id = self.client.get_external_id(
                    workflow_uuid, workflow_version, workflow_submitter)
            except Exception as e:
                logger.exception(e)

        return models.Workflow(workflow_uuid, workflow_version, workflow_submitter, roc_link,
                               registry=self,
                               roc_metadata=roc_metadata,
                               external_id=external_id, name=name)

    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()

    def get_workflow(self, uuid, version=None):
        try:
            if not version:
                return models.Workflow.query.with_parent(self)\
                    .filter(models.Workflow.uuid == uuid).order_by(models.Workflow.version.desc()).first()
            return models.Workflow.query.with_parent(self)\
                .filter(models.Workflow.uuid == uuid).filter(models.Workflow.version == version).first()
        except Exception as e:
            raise EntityNotFoundException(e)

    def get_workflow_versions(self, uuid):
        try:
            workflows = models.Workflow.query.with_parent(self)\
                .filter(models.Workflow.uuid == uuid).order_by(models.Workflow.version.desc())
            return {w.version: w for w in workflows}
        except Exception as e:
            raise EntityNotFoundException(e)

    def get_user_workflows(self, user: User):
        return self.client.filter_by_user(self.registered_workflows, user)

    @classmethod
    def all(cls):
        return cls.query.all()

    @classmethod
    def find_by_id(cls, uuid) -> WorkflowRegistry:
        try:
            return cls.query.get(uuid)
        except Exception as e:
            raise EntityNotFoundException(WorkflowRegistry, entity_id=uuid, exception=e)

    @classmethod
    def find_by_name(cls, name):
        try:
            return cls.query.filter(WorkflowRegistry.server_credentials.has(name=name)).one()
        except Exception as e:
            raise EntityNotFoundException(WorkflowRegistry, entity_id=name, exception=e)

    @classmethod
    def find_by_uri(cls, uri):
        try:
            return cls.query.filter(WorkflowRegistry.uri == uri).one()
        except Exception as e:
            raise EntityNotFoundException(WorkflowRegistry, entity_id=uri, exception=e)

    @classmethod
    def find_by_client_id(cls, client_id):
        try:
            return cls.query.filter_by(client_id=client_id).first()
        except Exception as e:
            raise EntityNotFoundException(WorkflowRegistry, entity_id=client_id, exception=e)

    @staticmethod
    def new_instance(registry_type, client_credentials, server_credentials):
        return models.registries.get_registry_class(registry_type)(client_credentials,
                                                            server_credentials)
