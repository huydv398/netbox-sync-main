# -*- coding: utf-8 -*-
#  Copyright (c) 2020 - 2026 Ricardo Bartels. All rights reserved.
#
#  netbox-sync.py
#
#  This work is licensed under the terms of the MIT license.
#  For a copy, see file LICENSE.txt included in this
#  repository or visit: <https://opensource.org/licenses/MIT>.

"""
IMPROVED Dell ECS Handler - Following VMware Source Pattern

This is an example of how to refactor Dell ECS source to follow
the VMware source architecture for better maintainability and scalability.

Key improvements:
1. Object mapping for easy expansion
2. Proper parent-child relationship handling
3. Caching to avoid reprocessing
4. Comprehensive error handling
5. Better logging
6. Filtering support
"""

import requests
import urllib3
from typing import Optional, Dict, List, Any

from module.sources.common.source_base import SourceBase
from module.sources.dell_ecs.config import DellECSConfig
from module.common.logging import get_logger
from module.common.misc import grab
from module.netbox.inventory import NetBoxInventory
from module.netbox import *

log = get_logger()


class DellECSHandlerImproved(SourceBase):
    """
    Improved Dell ECS source handler following VMware pattern.
    
    This implementation includes:
    - Object mapping for easy expansion
    - Parent-child relationship handling
    - Caching mechanism
    - Comprehensive error handling
    - Better logging and filtering
    """

    # Define all NetBox objects that need to be queried from NetBox
    dependent_netbox_objects = [
        NBTag,
        NBNamespace,
        NBBucket,
        NBUser,
        NBCustomField,
        NBSite,
    ]

    source_type = "dell_ecs"
    recursion_level = 0

    # Session management
    session = None
    token = None

    # Caching mechanisms (to avoid reprocessing same objects)
    processed_namespaces: List[str] = []
    processed_buckets: List[str] = []
    processed_users: List[str] = []
    processed_replication_groups: List[str] = []

    # Cache for quick lookups
    namespace_cache: Dict[str, Any] = {}
    replication_group_cache: Dict[str, Any] = {}

    def __init__(self, name=None):
        if name is None:
            raise ValueError(f"Invalid value for attribute 'name': '{name}'.")

        self.inventory = NetBoxInventory()
        self.name = name
        
        # Initialize caching lists
        self.processed_namespaces = []
        self.processed_buckets = []
        self.processed_users = []
        self.processed_replication_groups = []
        self.namespace_cache = {}
        self.replication_group_cache = {}

        # Parse settings
        settings_handler = DellECSConfig()
        settings_handler.source_name = name
        self.settings = settings_handler.parse_config()

        if not self.settings:
            log.error(f"Config for source '{name}' could not be parsed. Skipping.")
            return

        self.set_source_tag()

        # Connect to ECS
        if not self.connect():
            log.error(f"Failed to connect to Dell ECS '{name}'.")
            return

        self.init_successful = True
        log.info(f"Successfully initialized Dell ECS source '{name}'.")

    def connect(self) -> bool:
        """
        Authenticate with Dell ECS API and get token
        
        Returns
        -------
        bool
            True if connection successful, False otherwise
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
            response = requests.post(
                url, 
                json=payload, 
                headers=headers, 
                verify=self.settings.get('validate_tls_certs', False),
                timeout=self.settings.get('connection_timeout', 30)
            )
            
            if response.status_code == 200:
                self.token = response.headers.get('X-SDS-AUTH-TOKEN')
                if self.token:
                    log.info(f"Successfully authenticated with Dell ECS '{self.name}'.")
                    return True
                else:
                    log.error(f"No token received from Dell ECS '{self.name}'.")
            else:
                log.error(f"Authentication failed for Dell ECS '{self.name}': "
                         f"{response.status_code} {response.text}")
        except requests.exceptions.Timeout:
            log.error(f"Connection timeout to Dell ECS '{self.name}'")
        except requests.exceptions.RequestException as e:
            log.error(f"Error connecting to Dell ECS '{self.name}': {e}")

        return False

    def apply(self):
        """
        Main method following VMware pattern.
        
        This uses object mapping to make it easy to add new object types.
        """
        log.info(f"Query data from Dell ECS: '{self.settings['host_fqdn']}'")

        # Define object mapping similar to VMware
        # This makes it very easy to add new object types in the future
        object_mapping = {
            "namespace": {
                "api_handler": self.get_namespaces,
                "item_handler": self.add_namespace,
                "include_filter": grab(self.settings, "namespace_include_filter"),
                "exclude_filter": grab(self.settings, "namespace_exclude_filter"),
            },
            "replication_group": {
                "api_handler": self.get_replication_groups,
                "item_handler": self.add_replication_group,
                "include_filter": grab(self.settings, "replication_group_include_filter"),
                "exclude_filter": grab(self.settings, "replication_group_exclude_filter"),
            },
            "bucket": {
                "api_handler": self.get_buckets,
                "item_handler": self.add_bucket,
                "include_filter": grab(self.settings, "bucket_include_filter"),
                "exclude_filter": grab(self.settings, "bucket_exclude_filter"),
            },
            "user": {
                "api_handler": self.get_users,
                "item_handler": self.add_user,
                "include_filter": grab(self.settings, "user_include_filter"),
                "exclude_filter": grab(self.settings, "user_exclude_filter"),
            }
        }

        # Iterate over object types and process them
        for object_type, handlers in object_mapping.items():
            log.debug(f"Processing {object_type}s from Dell ECS")

            # Call API handler to get items
            try:
                items = handlers["api_handler"]()
            except Exception as e:
                log.error(f"Failed to get {object_type}s from Dell ECS: {e}")
                continue

            if items is None:
                log.debug(f"No {object_type}s found")
                continue

            log.debug(f"Retrieved '{len(items)}' {object_type}(s) from Dell ECS")

            # Process each item
            for item in items:
                try:
                    handlers["item_handler"](item)
                except Exception as e:
                    log.error(f"Error processing {object_type} '{grab(item, 'name')}': {e}")
                    continue

    # ==================== API Methods ====================
    # These methods retrieve data from Dell ECS API with proper error handling

    def get_namespaces(self) -> Optional[List[Dict]]:
        """
        Fetch namespaces from ECS API
        
        Returns
        -------
        Optional[List[Dict]]
            List of namespace dictionaries or None if failed
        """
        if not self.token:
            log.error("No valid ECS token. Cannot fetch namespaces.")
            return None

        url = f"https://{self.settings['host_fqdn']}:{self.settings['port']}/object/namespaces"
        headers = {'X-SDS-AUTH-TOKEN': self.token}

        try:
            response = requests.get(
                url,
                headers=headers,
                verify=self.settings.get('validate_tls_certs', False),
                timeout=self.settings.get('connection_timeout', 30)
            )

            if response.status_code != 200:
                log.error(f"Failed to get namespaces from ECS: "
                         f"{response.status_code} {response.text}")
                return None

            namespaces = response.json().get('namespaces', [])
            log.debug(f"Successfully fetched {len(namespaces)} namespaces from ECS")
            return namespaces

        except requests.exceptions.Timeout:
            log.error("Timeout while fetching namespaces from ECS")
        except requests.exceptions.RequestException as e:
            log.error(f"Error fetching namespaces from ECS: {e}")
        except ValueError as e:
            log.error(f"Invalid JSON response from ECS namespaces endpoint: {e}")

        return None

    def get_replication_groups(self) -> Optional[List[Dict]]:
        """
        Fetch replication groups from ECS API
        
        Returns
        -------
        Optional[List[Dict]]
            List of replication group dictionaries or None if failed
        """
        if not self.token:
            return None

        url = f"https://{self.settings['host_fqdn']}:{self.settings['port']}/object/replication-groups"
        headers = {'X-SDS-AUTH-TOKEN': self.token}

        try:
            response = requests.get(
                url,
                headers=headers,
                verify=self.settings.get('validate_tls_certs', False),
                timeout=self.settings.get('connection_timeout', 30)
            )

            if response.status_code != 200:
                log.warning(f"Failed to get replication groups from ECS: {response.status_code}")
                return None

            rg_list = response.json().get('replication_groups', [])
            log.debug(f"Successfully fetched {len(rg_list)} replication group(s) from ECS")
            return rg_list

        except Exception as e:
            log.debug(f"Error fetching replication groups from ECS: {e}")

        return None

    def get_buckets(self) -> Optional[List[Dict]]:
        """
        Fetch buckets from ECS API
        
        Returns
        -------
        Optional[List[Dict]]
            List of bucket dictionaries or None if failed
        """
        if not self.token:
            log.error("No valid ECS token. Cannot fetch buckets.")
            return None

        url = f"https://{self.settings['host_fqdn']}:{self.settings['port']}/object/buckets"
        headers = {'X-SDS-AUTH-TOKEN': self.token}

        try:
            response = requests.get(
                url,
                headers=headers,
                verify=self.settings.get('validate_tls_certs', False),
                timeout=self.settings.get('connection_timeout', 30)
            )

            if response.status_code != 200:
                log.error(f"Failed to get buckets from ECS: {response.status_code} {response.text}")
                return None

            buckets = response.json().get('buckets', [])
            log.debug(f"Successfully fetched {len(buckets)} bucket(s) from ECS")
            return buckets

        except requests.exceptions.Timeout:
            log.error("Timeout while fetching buckets from ECS")
        except requests.exceptions.RequestException as e:
            log.error(f"Error fetching buckets from ECS: {e}")
        except ValueError as e:
            log.error(f"Invalid JSON response from ECS buckets endpoint: {e}")

        return None

    def get_users(self) -> Optional[List[Dict]]:
        """
        Fetch users from ECS API
        
        Returns
        -------
        Optional[List[Dict]]
            List of user dictionaries or None if failed
        """
        if not self.token:
            log.error("No valid ECS token. Cannot fetch users.")
            return None

        url = f"https://{self.settings['host_fqdn']}:{self.settings['port']}/object/users"
        headers = {'X-SDS-AUTH-TOKEN': self.token}

        try:
            response = requests.get(
                url,
                headers=headers,
                verify=self.settings.get('validate_tls_certs', False),
                timeout=self.settings.get('connection_timeout', 30)
            )

            if response.status_code != 200:
                log.error(f"Failed to get users from ECS: {response.status_code} {response.text}")
                return None

            users = response.json().get('users', [])
            log.debug(f"Successfully fetched {len(users)} user(s) from ECS")
            return users

        except requests.exceptions.Timeout:
            log.error("Timeout while fetching users from ECS")
        except requests.exceptions.RequestException as e:
            log.error(f"Error fetching users from ECS: {e}")
        except ValueError as e:
            log.error(f"Invalid JSON response from ECS users endpoint: {e}")

        return None

    # ==================== Handler Methods ====================
    # These methods process individual items and add/update them to NetBox inventory

    def add_namespace(self, ns_data: Dict) -> None:
        """
        Add or update namespace in NetBox inventory
        
        Implements the VMware pattern:
        1. Parsing - extract name
        2. Filtering - check against include/exclude filters
        3. Caching - avoid reprocessing
        4. Building data dict
        5. Add/update to inventory
        
        Parameters
        ----------
        ns_data : Dict
            Namespace data from ECS API
        """
        # 1. PARSING
        ns_name = grab(ns_data, 'name')

        if not ns_name:
            log.warning(f"Namespace missing name: {ns_data}")
            return

        # 2. FILTERING (following VMware pattern)
        if not self.passes_filter(ns_name, 
                                 grab(self.settings, "namespace_include_filter"),
                                 grab(self.settings, "namespace_exclude_filter")):
            log.debug2(f"Namespace '{ns_name}' filtered out")
            return

        # 3. CACHING - avoid reprocessing
        if ns_name in self.processed_namespaces:
            log.debug2(f"Namespace '{ns_name}' already processed, skipping")
            return

        self.processed_namespaces.append(ns_name)
        log.debug(f"Processing namespace '{ns_name}'")

        # 4. BUILDING DATA DICT
        namespace_data = {
            'name': ns_name,
            'slug': ns_name.lower().replace(' ', '-'),
            'description': f"Dell ECS Namespace: {ns_name}",
            'ns_id': grab(ns_data, 'id'),
            'retention_days': grab(ns_data, 'retention_days', 0),
            'compliance_enabled': grab(ns_data, 'compliance_enabled', False),
        }

        # Cache the namespace for later reference
        self.namespace_cache[ns_name] = namespace_data

        # 5. ADD/UPDATE TO INVENTORY
        existing_ns = self.inventory.get_by_data(NBNamespace, data={'name': ns_name})

        if existing_ns is not None:
            log.debug2(f"Namespace '{ns_name}' already exists, updating")
            existing_ns.update(data=namespace_data, source=self)
        else:
            log.debug2(f"Creating new namespace '{ns_name}'")
            self.inventory.add_object(NBNamespace, data=namespace_data, source=self)

    def add_replication_group(self, rg_data: Dict) -> None:
        """
        Add or update replication group in NetBox inventory
        
        Parameters
        ----------
        rg_data : Dict
            Replication group data from ECS API
        """
        # 1. PARSING
        rg_name = grab(rg_data, 'name')

        if not rg_name:
            log.warning(f"Replication group missing name")
            return

        # 2. FILTERING
        if not self.passes_filter(rg_name,
                                 grab(self.settings, "replication_group_include_filter"),
                                 grab(self.settings, "replication_group_exclude_filter")):
            log.debug2(f"Replication group '{rg_name}' filtered out")
            return

        # 3. CACHING
        if rg_name in self.processed_replication_groups:
            return

        self.processed_replication_groups.append(rg_name)

        # 4. BUILDING DATA DICT
        rg_data_dict = {
            'name': rg_name,
            'slug': rg_name.lower().replace(' ', '-'),
            'description': f"Dell ECS Replication Group: {rg_name}",
            'replication_group_id': grab(rg_data, 'id'),
        }

        self.replication_group_cache[rg_name] = rg_data_dict

        log.debug2(f"Processing replication group '{rg_name}'")

    def add_bucket(self, bucket_data: Dict) -> None:
        """
        Add or update bucket in NetBox inventory with parent namespace reference
        
        Implements parent-child relationship handling (following VMware pattern):
        - Find parent namespace in inventory
        - If not found, create it
        - Create bucket with reference to namespace
        
        Parameters
        ----------
        bucket_data : Dict
            Bucket data from ECS API
        """
        # 1. PARSING
        bucket_name = grab(bucket_data, 'name')
        ns_name = grab(bucket_data, 'namespace')

        if not bucket_name or not ns_name:
            log.warning(f"Bucket missing name or namespace: {bucket_data}")
            return

        # 2. FILTERING
        if not self.passes_filter(bucket_name,
                                 grab(self.settings, "bucket_include_filter"),
                                 grab(self.settings, "bucket_exclude_filter")):
            log.debug2(f"Bucket '{bucket_name}' filtered out")
            return

        # 3. CACHING
        bucket_cache_key = f"{ns_name}/{bucket_name}"
        if bucket_cache_key in self.processed_buckets:
            log.debug2(f"Bucket '{bucket_cache_key}' already processed, skipping")
            return

        self.processed_buckets.append(bucket_cache_key)
        log.debug(f"Processing bucket '{bucket_cache_key}'")

        # 4. HANDLING PARENT-CHILD RELATIONSHIP
        # Following VMware pattern: find parent object, create if not found
        namespace = self.inventory.get_by_data(NBNamespace, data={'name': ns_name})

        if namespace is None:
            # Parent not found - create it
            log.debug2(f"Namespace '{ns_name}' not found in inventory, creating...")
            ns_data = {
                'name': ns_name,
                'slug': ns_name.lower().replace(' ', '-'),
                'description': f"Dell ECS Namespace: {ns_name}"
            }
            namespace = self.inventory.add_object(NBNamespace, data=ns_data, source=self)

        if namespace is None:
            # Still failed to create namespace, can't proceed with bucket
            log.error(f"Failed to find or create namespace '{ns_name}' for bucket '{bucket_name}'")
            return

        # 5. BUILDING DATA DICT
        bucket_data_dict = {
            'name': bucket_name,
            'namespace': namespace,
            'bucket_id': grab(bucket_data, 'id'),
            'size': grab(bucket_data, 'size', 0),
            'used': grab(bucket_data, 'used', 0),
            'owner': grab(bucket_data, 'owner'),
            'replication_group': grab(bucket_data, 'replication_group'),
            'vpool': grab(bucket_data, 'vpool'),
            'versioning_enabled': grab(bucket_data, 'versioning_enabled', False),
            'encryption_enabled': grab(bucket_data, 'encryption_enabled', False),
            'compliance_enabled': grab(bucket_data, 'compliance_enabled', False),
            'description': f"Dell ECS Bucket: {bucket_name} (Namespace: {ns_name})"
        }

        # 6. ADD/UPDATE TO INVENTORY
        # Find using both name and parent namespace
        existing_bucket = self.inventory.get_by_data(NBBucket, data={
            'name': bucket_name,
            'namespace': namespace
        })

        if existing_bucket is not None:
            log.debug2(f"Bucket '{bucket_cache_key}' already exists, updating")
            existing_bucket.update(data=bucket_data_dict, source=self)
        else:
            log.debug2(f"Creating new bucket '{bucket_cache_key}'")
            self.inventory.add_object(NBBucket, data=bucket_data_dict, source=self)

    def add_user(self, user_data: Dict) -> None:
        """
        Add or update user in NetBox inventory
        
        Parameters
        ----------
        user_data : Dict
            User data from ECS API
        """
        # 1. PARSING
        username = grab(user_data, 'username')

        if not username:
            log.warning(f"User missing username: {user_data}")
            return

        # 2. FILTERING
        if not self.passes_filter(username,
                                 grab(self.settings, "user_include_filter"),
                                 grab(self.settings, "user_exclude_filter")):
            log.debug2(f"User '{username}' filtered out")
            return

        # 3. CACHING
        if username in self.processed_users:
            log.debug2(f"User '{username}' already processed, skipping")
            return

        self.processed_users.append(username)
        log.debug(f"Processing user '{username}'")

        # 4. BUILDING DATA DICT
        user_data_dict = {
            'username': username,
            'email': grab(user_data, 'email', ''),
            'full_name': grab(user_data, 'full_name', username),
            'user_id': grab(user_data, 'id'),
            'user_type': grab(user_data, 'type', 'local'),
            'active': grab(user_data, 'active', True),
            'description': f"Dell ECS User: {username}"
        }

        # 5. ADD/UPDATE TO INVENTORY
        existing_user = self.inventory.get_by_data(NBUser, data={'username': username})

        if existing_user is not None:
            log.debug2(f"User '{username}' already exists, updating")
            existing_user.update(data=user_data_dict, source=self)
        else:
            log.debug2(f"Creating new user '{username}'")
            self.inventory.add_object(NBUser, data=user_data_dict, source=self)

    def passes_filter(self, name: str, include_filter: Optional[str] = None,
                     exclude_filter: Optional[str] = None) -> bool:
        """
        Check if name passes include/exclude filters (following SourceBase pattern)
        
        Parameters
        ----------
        name : str
            Name to check
        include_filter : Optional[str]
            Comma-separated include patterns
        exclude_filter : Optional[str]
            Comma-separated exclude patterns
            
        Returns
        -------
        bool
            True if name passes filters, False otherwise
        """
        # This uses the SourceBase.passes_filter method
        # You may need to import it from SourceBase
        return super().passes_filter(name, include_filter, exclude_filter)

    def finish(self):
        """
        Cleanup after processing (close connections, etc.)
        """
        if self.session is not None:
            try:
                self.session.close()
            except Exception as e:
                log.debug(f"Error closing ECS session: {e}")
        
        log.debug(f"Dell ECS source '{self.name}' finished")
