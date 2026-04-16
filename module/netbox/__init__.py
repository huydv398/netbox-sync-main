# -*- coding: utf-8 -*-
#  Copyright (c) 2020 - 2026 Ricardo Bartels. All rights reserved.
#
#  netbox-sync.py
#
#  This work is licensed under the terms of the MIT license.
#  For a copy, see file LICENSE.txt included in this
#  repository or visit: <https://opensource.org/licenses/MIT>.

from module.netbox.object_classes import (
    NetBoxInterfaceType,
    NetBoxObject,
    NBObjectList,
    NBCustomField,
    NBTag,
    NBTagList,
    NBTenant,
    NBSite,
    NBSiteGroup,
    NBVRF,
    NBVLAN,
    NBVLANList,
    NBVLANGroup,
    NBPrefix,
    NBManufacturer,
    NBDeviceType,
    NBPlatform,
    NBClusterType,
    NBClusterGroup,
    NBDeviceRole,
    NBCluster,
    NBDevice,
    NBVM,
    NBVMInterface,
    NBVirtualDisk,
    NBInterface,
    NBIPAddress,
    NBMACAddress,
    NBFHRPGroupItem,
    NBInventoryItem,
<<<<<<< HEAD
    NBPowerPort,
    NBNamespace,
    NBBucket,
    NBUser
=======
    NBPowerPort
>>>>>>> cd90f89f571da0de99fe6f23bf81f271dc77fd6b
)

primary_tag_name = "NetBox-synced"
