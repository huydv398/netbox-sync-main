# -*- coding: utf-8 -*-
#  Copyright (c) 2020 - 2026 Ricardo Bartels. All rights reserved.
#
#  netbox-sync.py
#
#  This work is licensed under the terms of the MIT license.
#  For a copy, see file LICENSE.txt included in this
#  repository or visit: <https://opensource.org/licenses/MIT>.

from module.config import source_config_section_name
from module.config.base import ConfigBase
from module.config.option import ConfigOption
from module.sources.common.config import *

class DellECSConfig(ConfigBase):

    section_name = source_config_section_name
    source_name = None
    source_name_example = "my-ecs-example"

    def __init__(self):
        self.options = [
            ConfigOption(**config_option_enabled_definition),

            ConfigOption(**{**config_option_type_definition, "config_example": "dell_ecs"}),

            ConfigOption("host_fqdn",
                         str,
                         description="host name / IP address of the Dell ECS management API",
                         config_example="ecs.example.com",
                         mandatory=True),

            ConfigOption("port",
                         int,
                         description="TCP port to connect to",
                         default_value=4443),

            ConfigOption("username",
                         str,
                         description="username to use to authenticate with ECS API",
                         config_example="ecs-admin",
                         mandatory=True),

            ConfigOption("password",
                         str,
                         description="password to use to authenticate with ECS API",
                         config_example="super-secret",
                         sensitive=True,
                         mandatory=True),

            ConfigOption("validate_tls_certs",
                         bool,
                         description="Enforces TLS certificate validation.",
                         default_value=False),
        ]