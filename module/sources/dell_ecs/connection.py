# -*- coding: utf-8 -*-
#  Copyright (c) 2020 - 2026 Ricardo Bartels. All rights reserved.
#
#  netbox-sync.py
#
#  This work is licensed under the terms of the MIT license.
#  For a copy, see file LICENSE.txt included in this
#  repository or visit: <https://opensource.org/licenses/MIT>.

import requests
import urllib3
from module.sources.common.source_base import SourceBase
from module.sources.dell_ecs.config import DellECSConfig
from module.common.logging import get_logger
from module.netbox.inventory import NetBoxInventory
from module.netbox import *

log = get_logger()

class DellECSHandler(SourceBase):
    """
    Source class to import data from Dell ECS and add/update NetBox objects based on gathered information
    """

    dependent_netbox_objects = [
        NBTag,
        NBNamespace,
        NBBucket,
        NBUser,
        NBCustomField,  # For additional fields
    ]

    source_type = "dell_ecs"

    def __init__(self, name=None):
        if name is None:
            raise ValueError(f"Invalid value for attribute 'name': '{name}'.")

        self.inventory = NetBoxInventory()
        self.name = name
        self.session = None
        self.token = None

        # parse settings
        settings_handler = DellECSConfig()
        settings_handler.source_name = name
        self.settings = settings_handler.parse_config()

        if not self.settings:
            log.error(f"Config for source '{name}' could not be parsed. Skipping.")
            return

        self.set_source_tag()

        # connect to ECS
        if not self.connect():
            log.error(f"Failed to connect to Dell ECS '{name}'.")
            return

        self.init_successful = True
        log.info(f"Successfully initialized Dell ECS source '{name}'.")

    def connect(self):
        """
        Authenticate with Dell ECS API and get token
        """
        url = f"https://{self.settings['host_fqdn']}:{self.settings['port']}/login"
        payload = {
            "username": self.settings['username'],
            "password": self.settings['password']
        }
        headers = {'Content-Type': 'application/json'}

        if not self.settings.get('validate_tls_certs', False):
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        try:
            response = requests.post(url, json=payload, headers=headers, verify=self.settings.get('validate_tls_certs', False))
            if response.status_code == 200:
                self.token = response.headers.get('X-SDS-AUTH-TOKEN')
                if self.token:
                    log.info(f"Successfully authenticated with Dell ECS '{self.name}'.")
                    return True
                else:
                    log.error(f"No token received from Dell ECS '{self.name}'.")
            else:
                log.error(f"Authentication failed for Dell ECS '{self.name}': {response.status_code} {response.text}")
        except Exception as e:
            log.error(f"Error connecting to Dell ECS '{self.name}': {e}")

        return False

    def get_namespaces(self):
        """
        Fetch namespaces from ECS
        """
        if not self.token:
            return []

        url = f"https://{self.settings['host_fqdn']}:{self.settings['port']}/object/namespaces"
        headers = {'X-SDS-AUTH-TOKEN': self.token}

        try:
            response = requests.get(url, headers=headers, verify=self.settings.get('validate_tls_certs', False))
            if response.status_code == 200:
                return response.json()
            else:
                log.error(f"Failed to get namespaces: {response.status_code} {response.text}")
        except Exception as e:
            log.error(f"Error fetching namespaces: {e}")

        return []

    def get_buckets(self):
        """
        Fetch buckets from ECS
        """
        if not self.token:
            return []

        url = f"https://{self.settings['host_fqdn']}:{self.settings['port']}/object/bucket"
        headers = {'X-SDS-AUTH-TOKEN': self.token}

        try:
            response = requests.get(url, headers=headers, verify=self.settings.get('validate_tls_certs', False))
            if response.status_code == 200:
                return response.json()
            else:
                log.error(f"Failed to get buckets: {response.status_code} {response.text}")
        except Exception as e:
            log.error(f"Error fetching buckets: {e}")

        return []

    def get_users(self):
        """
        Fetch users from ECS
        """
        if not self.token:
            return []

        url = f"https://{self.settings['host_fqdn']}:{self.settings['port']}/object/user"
        headers = {'X-SDS-AUTH-TOKEN': self.token}

        try:
            response = requests.get(url, headers=headers, verify=self.settings.get('validate_tls_certs', False))
            if response.status_code == 200:
                return response.json()
            else:
                log.error(f"Failed to get users: {response.status_code} {response.text}")
        except Exception as e:
            log.error(f"Error fetching users: {e}")

        return []

    def apply(self):
        """
        Apply the Dell ECS data to NetBox inventory
        """
        log.info(f"Applying Dell ECS data from source '{self.name}'")

        # Get namespaces and add as custom objects
        namespaces = self.get_namespaces()
        for ns in namespaces:
            self.add_namespace(ns)

        # Get buckets and add as custom objects
        buckets = self.get_buckets()
        for bucket in buckets:
            self.add_bucket(bucket)

        # Get users
        users = self.get_users()
        for user in users:
            self.add_user(user)

    def add_namespace(self, ns_data):
        """
        Add namespace as NetBox custom object
        """
        ns_name = ns_data.get('name')
        if not ns_name:
            return

        namespace_data = {
            'name': ns_name,
            'slug': ns_name.lower().replace(' ', '-'),
            'description': f"Dell ECS Namespace: {ns_name}"
        }

        namespace = self.inventory.get_by_data(NBNamespace, data={'name': ns_name})
        if namespace is None:
            self.inventory.add_object(NBNamespace, data=namespace_data, source=self)
        else:
            namespace.update(data=namespace_data, source=self)

    def add_bucket(self, bucket_data):
        """
        Add bucket as NetBox custom object
        """
        bucket_name = bucket_data.get('name')
        ns_name = bucket_data.get('namespace')
        if not bucket_name or not ns_name:
            return

        # Find or create namespace
        namespace = self.inventory.get_by_data(NBNamespace, data={'name': ns_name})
        if namespace is None:
            namespace = self.inventory.add_object(NBNamespace, data={'name': ns_name}, source=self)

        bucket_data_dict = {
            'name': bucket_name,
            'namespace': namespace,
            'size': bucket_data.get('size', 0),
            'description': f"Bucket in namespace {ns_name}"
        }

        bucket = self.inventory.get_by_data(NBBucket, data={'name': bucket_name})
        if bucket is None:
            self.inventory.add_object(NBBucket, data=bucket_data_dict, source=self)
        else:
            bucket.update(data=bucket_data_dict, source=self)

    def add_user(self, user_data):
        """
        Add user as NetBox custom object
        """
        username = user_data.get('username')
        if not username:
            return

        user_data_dict = {
            'username': username,
            'email': user_data.get('email', ''),
            'permissions': user_data.get('permissions', []),
            'description': f"Dell ECS User: {username}"
        }

        user = self.inventory.get_by_data(NBUser, data={'username': username})
        if user is None:
            self.inventory.add_object(NBUser, data=user_data_dict, source=self)
        else:
            user.update(data=user_data_dict, source=self)