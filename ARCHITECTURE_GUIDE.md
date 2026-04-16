# NetBox-Sync Architecture Guide: VMware to Dell ECS

## Giới thiệu

Document này giải thích kiến trúc của netbox-sync, cách mà VMware source hoạt động, và cách áp dụng kiến trúc này để xây dựng Dell ECS source hiệu quả hơn.

---

## 1. Kiến trúc chung của netbox-sync

### 1.1 Flow chính (Main Flow)

```
main() 
  ├─ Config Parser: Đọc config từ file/env vars
  ├─ Create NetBox Handler: Kết nối đến NetBox
  ├─ Initialize Sources: Khởi tạo các source handlers (VMware, check_redfish, Dell ECS, v.v.)
  ├─ Query Current Data: Lấy dữ liệu hiện tại từ NetBox (query dependent objects)
  ├─ Resolve Relations: Giải quyết các relations giữa các objects
  ├─ Initialize Basic Data: Khởi tạo dữ liệu cơ bản (tags, manufacturers, v.v.)
  ├─ MAIN LOOP - For each source:
  │   └─ source.apply(): Lấy dữ liệu từ source và áp dụng vào inventory
  ├─ Tag all the things: Tagging objects dựa trên source tags
  ├─ Update Instance: Cập nhật tất cả objects vào NetBox
  ├─ Prune Data: Xóa orphaned objects nếu cần
  └─ Finish: Đóng kết nối
```

### 1.2 Các thành phần chính

- **SourceBase**: Base class cho tất cả sources
- **NetBoxHandler**: Quản lý kết nối đến NetBox, xử lý tagging và pruning
- **NetBoxInventory**: Lưu trữ các objects và quản lý relations
- **NBObject**: Base class cho tất cả NetBox objects (NBDevice, NBVM, NBIPAddress, v.v.)

---

## 2. Cách hoạt động của VMware Source (Best Practice)

### 2.1 Cấu trúc của VMware Source

```
module/sources/vmware/
├── config.py         # Xử lý config settings cho VMware
└── connection.py     # VMWareHandler class - logic chính
```

### 2.2 Chu trình hoạt động của VMWareHandler

```python
class VMWareHandler(SourceBase):
    dependent_netbox_objects = [
        # Liệt kê tất cả NetBox objects cần lấy từ NetBox
        NBTag, NBManufacturer, NBDeviceType, ..., NBMACAddress
    ]
    
    def __init__(self):
        # 1. Khởi tạo config
        # 2. Kết nối đến vCenter
        # 3. set_source_tag()
    
    def apply(self):
        # Main logic - gọi từ netbox-sync.py
        # 1. Tạo mapping: object_type -> view_handler
        # 2. Iterate qua tất cả object types
        # 3. Cho mỗi object, gọi handler method tương ứng
```

### 2.3 Phương pháp xử lý Objects

#### Step 1: Object Mapping (Tạo mapping giữa VMware objects và handlers)

```python
object_mapping = {
    "datacenter": {
        "view_type": vim.Datacenter,
        "view_handler": self.add_datacenter
    },
    "cluster": {
        "view_type": vim.ClusterComputeResource,
        "view_handler": self.add_cluster
    },
    "virtual machine": {
        "view_type": vim.VirtualMachine,
        "view_handler": self.add_virtual_machine
    },
    # ... more types
}
```

#### Step 2: Iterate and Process

```python
for view_name, view_details in object_mapping.items():
    # Lấy container view từ vCenter
    container_view = self.session.viewManager.CreateContainerView(
        container=self.session.rootFolder,
        type=[view_details.get("view_type")],
        recursive=True
    )
    
    # Xử lý từng object
    for obj in container_view.view:
        view_details.get("view_handler")(obj)  # Gọi handler
```

#### Step 3: Handler Method Pattern

Mỗi handler method (e.g., `add_virtual_machine`) làm như sau:

```python
def add_virtual_machine(self, obj):
    # 1. PARSING - Trích xuất thông tin từ object
    name = get_string_or_none(grab(obj, "name"))
    vm_uuid = grab(obj, "config.instanceUuid")
    status = "active" if grab(obj, "runtime.powerState") == "poweredOn" else "offline"
    
    # 2. FILTERING - Lọc dựa trên các điều kiện
    if vm_uuid in self.processed_vm_uuid:
        return  # Skip nếu đã xử lý
    
    if self.passes_filter(name, ...):
        return  # Skip nếu không pass filter
    
    # 3. GATHERING DATA - Lấy thêm dữ liệu liên quan
    platform = grab(obj, "config.guestFullName")
    cluster_object = self.get_parent_object_by_class(...)
    parent_host = self.get_parent_object_by_class(...)
    
    # 4. BUILDING DATA DICT - Tạo dict dữ liệu cho NetBox object
    vm_data = {
        "name": name,
        "status": status,
        "cluster": cluster_object,
        "cpu_count": grab(obj, "config.hardware.numCPU"),
        "memory": grab(obj, "config.hardware.memoryMB"),
        # ... more fields
    }
    
    # 5. ADD/UPDATE TO INVENTORY
    # Cách 1: Tìm object trong inventory dựa trên identifiers
    existing_vm = self.inventory.get_by_data(NBVM, data={"name": name, "cluster": cluster_object})
    
    # Cách 2: Nếu tìm thấy, update; nếu không, thêm mới
    if existing_vm is not None:
        existing_vm.update(data=vm_data, source=self)
    else:
        self.inventory.add_object(NBVM, data=vm_data, source=self)
```

### 2.4 Các điểm quan trọng

1. **Caching**: VMware source duy trì cache để tránh xử lý lại cùng một object
2. **Parent-child relationships**: Trích xuất thông tin từ parent objects (e.g., cluster từ VM)
3. **Filtering**: Cho phép include/exclude objects dựa trên patterns
4. **Data enrichment**: Lấy thêm dữ liệu từ configuration (e.g., guest tools info)
5. **Error handling**: Graceful handling khi không tìm thấy parent objects
6. **Source tracking**: Đánh dấu object `source=self` để biết object này từ source nào

---

## 3. Hiện tại Dell ECS Source (Simplified Version)

Current implementation của Dell ECS source khá đơn giản:

```python
def apply(self):
    # 1. Lấy namespaces từ ECS API
    namespaces = self.get_namespaces()
    for ns in namespaces:
        self.add_namespace(ns)
    
    # 2. Lấy buckets
    buckets = self.get_buckets()
    for bucket in buckets:
        self.add_bucket(bucket)
    
    # 3. Lấy users
    users = self.get_users()
    for user in users:
        self.add_user(user)
```

**Hạn chế hiện tại:**
- Chỉ xử lý 3 types: Namespace, Bucket, User
- Không có filtering mechanism
- Không có parent-child relationship mapping
- Không có caching mechanism
- Không có error handling khi parent objects không tìm thấy

---

## 4. Cách áp dụng kiến trúc VMware cho Dell ECS

### 4.1 Nâng cấp Dell ECS Source để tuân theo VMware pattern

#### Bước 1: Mở rộng `dependent_netbox_objects`

```python
class DellECSHandler(SourceBase):
    # Thêm tất cả objects cần lấy từ NetBox
    dependent_netbox_objects = [
        NBTag,
        NBNamespace,
        NBBucket,
        NBUser,
        # Có thể thêm những objects khác nếu cần:
        NBSite,        # để map ECS cluster
        NBCustomField, # cho custom attributes
        # v.v.
    ]
```

#### Bước 2: Tạo Object Mapping

```python
def apply(self):
    """
    Apply Dell ECS data to NetBox inventory using VMware pattern
    """
    log.info(f"Applying Dell ECS data from source '{self.name}'")
    
    # Object mapping similar to VMware
    object_mapping = {
        "namespace": {
            "api_handler": self.get_namespaces,
            "item_handler": self.add_namespace
        },
        "bucket": {
            "api_handler": self.get_buckets,
            "item_handler": self.add_bucket
        },
        "replication_group": {
            "api_handler": self.get_replication_groups,
            "item_handler": self.add_replication_group
        },
        "user": {
            "api_handler": self.get_users,
            "item_handler": self.add_user
        }
    }
    
    # Iterate like VMware
    for object_type, handlers in object_mapping.items():
        log.debug(f"Processing {object_type}s from Dell ECS")
        
        try:
            items = handlers["api_handler"]()
        except Exception as e:
            log.error(f"Failed to get {object_type}s from Dell ECS: {e}")
            continue
        
        if items is None:
            log.debug(f"No {object_type}s found")
            continue
        
        log.debug(f"Found {len(items)} {object_type}(s)")
        
        for item in items:
            try:
                handlers["item_handler"](item)
            except Exception as e:
                log.error(f"Error processing {object_type}: {e}")
```

#### Bước 3: Cải thiện Handler Methods

Giả sử bạn muốn xử lý Bucket với parent-child relationship:

```python
def add_bucket(self, bucket_data):
    """
    Add bucket as NetBox custom object with proper parent/child handling
    """
    bucket_name = bucket_data.get('name')
    ns_name = bucket_data.get('namespace')
    
    if not bucket_name or not ns_name:
        log.warning(f"Bucket missing name or namespace: {bucket_data}")
        return
    
    # 1. FILTERING (optional)
    if not self.passes_filter(bucket_name, self.settings.bucket_include_filter, 
                              self.settings.bucket_exclude_filter):
        log.debug2(f"Bucket '{bucket_name}' filtered out")
        return
    
    # 2. GATHERING DATA - tìm parent namespace
    namespace = self.inventory.get_by_data(NBNamespace, data={'name': ns_name})
    
    if namespace is None:
        # Nếu parent không tìm thấy, tạo nó trước
        log.debug2(f"Namespace '{ns_name}' not found in inventory, creating...")
        ns_data = {'name': ns_name, 'slug': ns_name.lower().replace(' ', '-')}
        namespace = self.inventory.add_object(NBNamespace, data=ns_data, source=self)
    
    # 3. BUILDING DATA DICT
    bucket_data_dict = {
        'name': bucket_name,
        'namespace': namespace,
        'size': bucket_data.get('size', 0),
        'used': bucket_data.get('used', 0),
        'vpool': bucket_data.get('vpool'),
        'replication_group': bucket_data.get('replication_group'),
        'owner': bucket_data.get('owner'),
        'description': f"Dell ECS Bucket: {bucket_name}"
    }
    
    # 4. ADD/UPDATE TO INVENTORY
    # Tìm existing bucket dựa trên name và namespace
    existing_bucket = self.inventory.get_by_data(NBBucket, data={
        'name': bucket_name,
        'namespace': namespace
    })
    
    if existing_bucket is not None:
        log.debug2(f"Bucket '{bucket_name}' already exists, updating...")
        existing_bucket.update(data=bucket_data_dict, source=self)
    else:
        log.debug2(f"Creating new bucket '{bucket_name}'")
        self.inventory.add_object(NBBucket, data=bucket_data_dict, source=self)
```

#### Bước 4: Thêm Caching (optional nhưng khuyến cáo)

```python
def __init__(self, name=None):
    # ... existing code ...
    
    # Thêm caching để tránh xử lý lại cùng một object
    self.processed_namespaces = []
    self.processed_buckets = []
    self.processed_users = []

def add_namespace(self, ns_data):
    ns_name = ns_data.get('name')
    
    if ns_name in self.processed_namespaces:
        log.debug2(f"Namespace '{ns_name}' already processed, skipping")
        return
    
    self.processed_namespaces.append(ns_name)
    
    # ... rest of the code ...
```

#### Bước 5: Thêm Error Handling và Logging

```python
def get_buckets(self):
    """
    Fetch buckets from ECS with proper error handling
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
            timeout=30
        )
        
        if response.status_code != 200:
            log.error(f"Failed to get buckets from ECS: {response.status_code} {response.text}")
            return None
        
        buckets = response.json().get('buckets', [])
        log.debug(f"Successfully fetched {len(buckets)} buckets from ECS")
        return buckets
        
    except requests.exceptions.Timeout:
        log.error("Timeout while fetching buckets from ECS")
        return None
    except requests.exceptions.RequestException as e:
        log.error(f"Error fetching buckets from ECS: {e}")
        return None
    except ValueError as e:
        log.error(f"Invalid JSON response from ECS buckets endpoint: {e}")
        return None
```

---

## 5. Tóm tắt các điểm khác biệt

| Khía cạnh | VMware Pattern | Dell ECS (Hiện tại) | Dell ECS (Cải thiện) |
|-----------|---|---|---|
| **Object Mapping** | ✅ Rõ ràng, dễ mở rộng | ❌ Hardcoded loop | ✅ Object mapping dict |
| **Filtering** | ✅ Config-driven filters | ❌ Không có | ✅ Config-driven filters |
| **Caching** | ✅ `processed_vm_names` | ❌ Không có | ✅ Thêm caching dicts |
| **Parent-child** | ✅ Smart lookup | ⚠️ Tạo nếu không tìm thấy | ✅ Smart lookup + auto-create |
| **Error handling** | ✅ Comprehensive | ⚠️ Cơ bản | ✅ Try-catch blocks |
| **Logging** | ✅ DEBUG2 levels | ❌ Minimal | ✅ Chi tiết logging |
| **Scalability** | ✅ Dễ thêm object types | ⚠️ Phải sửa apply() | ✅ Chỉ thêm mapping entry |

---

## 6. Implementation Recommendations

### Phase 1: Quick Wins (Low effort, high impact)
1. Thêm Object Mapping structure
2. Thêm Caching mechanism
3. Thêm proper error handling

### Phase 2: Enhancement (Medium effort, high impact)
1. Thêm filtering config options
2. Thêm DEBUG2 logging
3. Thêm parent-child relationship smarts
4. Thêm timeout handling

### Phase 3: Advanced (Higher effort, future-proof)
1. Thêm metrics/telemetry
2. Thêm connection pooling
3. Thêm multi-threaded processing
4. Thêm incremental sync (chỉ sync changes)

---

## 7. Ví dụ Configuration

```ini
[source/dell-ecs-prod]
enabled = True
type = dell_ecs
host_fqdn = ecs.example.com
port = 4443
username = admin
password = secret

; Optional: Filtering
namespace_include_filter = prod-*, staging-*
namespace_exclude_filter = test-*
bucket_include_filter = *
bucket_exclude_filter = backup-*

; Optional: Validation
validate_tls_certs = True
connection_timeout = 30
```

---

## 8. Đọc thêm

- **source_base.py**: Base class và common methods
- **vmware/connection.py**: Full VMware implementation cho reference
- **netbox/inventory.py**: Cách hoạt động của inventory system
- **netbox/connection.py**: NetBox handler và tagging logic
