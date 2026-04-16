# NetBox-Sync

A tool to synchronize inventory data from external sources into a NetBox instance.

## Supported sources

* VMware vCenter Server
* [bb-ricardo/check_redfish](https://github.com/bb-Ricardo/check_redfish) inventory files
<<<<<<<<< Temporary merge branch 1
=========
* Dell ECS (using NetBox Custom Objects plugin)
>>>>>>>>> Temporary merge branch 2

**IMPORTANT: READ INSTRUCTIONS CAREFULLY BEFORE RUNNING THIS PROGRAM**

## Thanks
A BIG thank-you goes out to [Raymond Beaudoin](https://github.com/synackray) for creating
[vcenter-netbox-sync](https://github.com/synackray/vcenter-netbox-sync) which served as source of a lot
of ideas for this project.

## Principles

> copied from [Raymond Beaudoin](https://github.com/synackray)

The [NetBox documentation](https://netbox.readthedocs.io/en/stable/#serve-as-a-source-of-truth) makes it clear
the tool is intended to act as a "Source of Truth". The automated import of live network state is
strongly discouraged. While this is sound logic we've aimed to provide a middle-ground
solution for those who desire the functionality.

All objects collected from vCenter have a "lifecycle". Upon import, for supported object types,
they are tagged `NetBox-synced` to note their origin and distinguish them from other objects.
Using this tagging system also allows for the orphaning of objects which are no longer detected in vCenter.
This ensures stale objects are removed from NetBox keeping an accurate current state.

## Requirements

### Software

* Python 3.6 or newer
* `packaging`
* `urllib3==2.2.1`
* `wheel`
* `requests==2.31.0`
* `pyvmomi==8.0.2.0.1`
* `aiodns==3.0.0`
* `pyyaml==6.0.1`

### Environment
* NetBox >= 2.9
#### Source: VMWare (if used)
* VMWare vCenter >= 6.0
#### Source: check_redfish (if used)
* check_redfish >= 1.2.0
<<<<<<<<< Temporary merge branch 1
=========
#### Source: Dell ECS (if used)
* Dell ECS Management API access
* NetBox Custom Objects plugin installed and configured with models for namespaces, buckets, users
>>>>>>>>> Temporary merge branch 2

# Installing
* here we assume we install in ```/opt```

## RedHat based OS
* on RedHat/CentOS 7 you need to install python3.6 and pip from EPEL first
* on RedHat/CentOS 8 systems the package name changed to `python3-pip`
```shell
yum install python36-pip
```

### Ubuntu

```shell
apt-get update && apt-get install python3-venv
```

### Clone and install dependencies

```shell
cd /opt
git clone https://github.com/bb-Ricardo/netbox-sync.git
cd netbox-sync
python3 -m venv .venv
. .venv/bin/activate
pip3 install --upgrade pip
pip3 install wheel
pip3 install -r requirements.txt
```

If you need Python 3.6 compatibility, install dependencies from `requirements_3.6.txt` instead.

### VMware tag support

If you want vCenter tag synchronization, install the VMware automation SDK:

```shell
pip install --upgrade git+https://github.com/vmware/vsphere-automation-sdk-python.git
```

## Configuration

Configuration can be provided via config files, environment variables, or both. Environment variables override config file values.

### Config files

Supported config file formats:

* INI
* YAML

Multiple config files may be specified on the command line. Later files overwrite earlier values.

Example:

```bash
/opt/netbox-sync/netbox-sync.py -c common.ini all-sources.yaml additional-config.yaml
```

Generate example config files with:

```bash
/opt/netbox-sync/netbox-sync.py -g -c settings-example.ini
/opt/netbox-sync/netbox-sync.py -g -c settings-example.yaml
```

### Environment variables

The env var prefix is `NBS`.

The general pattern is:

```bash
NBS_<SECTION>_<OPTION_NAME>=value
```

Example:

```yaml
common:
  log_level: DEBUG2
netbox:
  host_fqdn: netbox-host.example.com
  prune_enabled: true
```

```bash
NBS_COMMON_LOG_LEVEL="DEBUG2"
NBS_NETBOX_HOST_FQDN="netbox-host.example.com"
NBS_NETBOX_PRUNE_ENABLED="true"
```

Source definitions require an index and `_NAME` to associate environment variables with a source.

Example:

```ini
[source/example-vcenter]
enabled = True
type = vmware
host_fqdn = vcenter.example.com
username = vcenter-readonly
```

```bash
NBS_SOURCE_1_NAME="example-vcenter"
NBS_SOURCE_1_PASSWORD="super-secret-and-not-saved-to-the-config-file"
NBS_SOURCE_1_CUSTOM_DNS_SERVERS="10.0.23.23,10.0.42.42"
```

## Usage

Run the script with `-h` to display available options.

```bash
python netbox-sync.py -h
```

Example options include:

* `-c`, `--config` : specify one or more config files
* `-g`, `--generate_config` : generate default config examples
* `-l`, `--log_level` : set log level (`DEBUG3`, `DEBUG2`, `DEBUG`, `INFO`, `WARNING`, `ERROR`)
* `-n`, `--dry_run` : perform a test run without modifying NetBox
* `-p`, `--purge` : remove synced objects created by this script

### Recommended testing

Use `-n` for a dry run before making changes in NetBox.
Set `-l DEBUG2` for detailed logging during initial validation.

## Cron job example

To run the sync regularly, add a cron entry:

```cron
23 */2 * * * /opt/netbox-sync/.venv/bin/python3 /opt/netbox-sync/netbox-sync.py >/dev/null 2>&1
```

## Docker

Build the container locally:

```shell
docker build -t bbricardo/netbox-sync:latest .
```

Run the container with a mounted config file:

```shell
docker run --rm -it -v $(pwd)/settings.ini:/app/settings.ini bbricardo/netbox-sync:latest
```

## Kubernetes

Use the provided `k8s-netbox-sync-cronjob.yaml` manifest as a starting point. Create a ConfigMap for settings and a Secret for credentials, then deploy the cron job to your cluster.

## Acknowledgments

Thanks to [Raymond Beaudoin](https://github.com/synackray) for the original `vcenter-netbox-sync` project and inspiration.

    type: vmware
    host_fqdn: vcenter.example.com
    permitted_subnets: 172.16.0.0/12, 10.0.0.0/8, 192.168.0.0/16, fd00::/8
    cluster_site_relation: Cluster_NYC = New York, Cluster_FFM.* = Frankfurt, Datacenter_TOKIO/.* = Tokio
```

secrets example saved as `secrets.yaml`
```yaml
netbox:
  api_token: XYZXYZXYZXYZXYZXYZXYZXYZ
source:
  my-vcenter-example:
    username: vcenter-readonly
    password: super-secret
```

Create resource in your k8s cluster
 ```shell
kubectl create configmap netbox-sync-config --from-file=settings.yaml
kubectl create secret generic netbox-sync-secrets --from-file=secrets.yaml
kubectl apply -f k8s-netbox-sync-cronjob.yaml
 ```

# How it works
**READ CAREFULLY**

## Basic structure
The program operates mainly like this
1. parsing and validating config
2. instantiating all sources and setting up connection to NetBox
3. read current data from NetBox
4. read data from all sources and add/update objects in memory
5. Update data in NetBox based on data from sources
6. Prune old objects

## NetBox connection
Request all current NetBox objects. Use caching whenever possible.
Objects must provide "last_updated" attribute to support caching for this object type.

Actually perform the request and retry x times if request times out.
Program will exit if all retries failed!

## Supported sources
Check out the documentations for the different sources
* [vmware](https://github.com/bb-Ricardo/netbox-sync/blob/main/docs/source_vmware.md)
* [check_redfish](https://github.com/bb-Ricardo/netbox-sync/blob/main/docs/source_check_redfish.md)
* Dell ECS (custom implementation using NetBox Custom Objects plugin)
=======

If you have multiple vCenter instances or check_redfish folders just add another source with the same type
in the **same** file.

Example:
```ini
[source/vcenter-BLN]

enabled = True
host_fqdn = vcenter1.berlin.example.com

[source/vcenter-NYC]

enabled = True
host_fqdn = vcenter2.new-york.example.com

[source/redfish-hardware]

type = check_redfish
inventory_file_path = /opt/redfish_inventory
<<<<<<< HEAD

[source/ecs-prod]

enabled = True
type = dell_ecs
host_fqdn = ecs.example.com
port = 4443
username = ecs-admin
password = super-secret
validate_tls_certs = False
=======
```

If different sources overwrite the same attribute for ex. a host then the order of the sources should be considered.
The last source in order from top to bottom will prevail.

## Pruning
Prune objects in NetBox if they are no longer present in any source.
First they will be marked as Orphaned and after X (config option) days they will be
deleted from NetBox.

Objects subjected to pruning:
* devices
* VMs
* device interfaces
* VM interfaces
* IP addresses

All other objects created (i.e.: VLANs, cluster, manufacturers) will keep the
source tag but will not be deleted. Theses are "shared" objects might be used
by different NetBox objects

# License
>You can check out the full license [here](https://github.com/bb-Ricardo/netbox-sync/blob/main/LICENSE.txt)

This project is licensed under the terms of the **MIT** license.
<<<<<<< HEAD

=======
>>>>>>> cd90f89f571da0de99fe6f23bf81f271dc77fd6b
