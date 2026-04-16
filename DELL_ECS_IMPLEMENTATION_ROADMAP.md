# Dell ECS Source - Implementation Roadmap

Hướng dẫn chi tiết để cải thiện Dell ECS source theo VMware pattern.

## Quick Start

### 1. Nhìn lại hiện tại (Current State)

**File**: `module/sources/dell_ecs/connection.py`

**Vấn đề hiện tại:**
```python
def apply(self):
    namespaces = self.get_namespaces()
    for ns in namespaces:
        self.add_namespace(ns)
    
    buckets = self.get_buckets()
    for bucket in buckets:
        self.add_bucket(bucket)
    
    users = self.get_users()
    for user in users:
        self.add_user(user)
```

❌ **Hạn chế:**
- Hardcoded loop không dễ mở rộng
- Không có filtering
- Không có caching
- Không có proper error handling
- Không xử lý parent-child relationships tốt

---

### 2. Bước 1: Thêm Object Mapping (5 phút)

```python
def apply(self):
    """Apply Dell ECS data to NetBox inventory"""
    log.info(f"Query data from Dell ECS: '{self.settings['host_fqdn']}'")

    # Define object mapping - dễ mở rộng
    object_mapping = {
        "namespace": {
            "api_handler": self.get_namespaces,
            "item_handler": self.add_namespace,
        },
        "bucket": {
            "api_handler": self.get_buckets,
            "item_handler": self.add_bucket,
        },
        "user": {
            "api_handler": self.get_users,
            "item_handler": self.add_user,
        }
    }

    # Iterate over object types
    for object_type, handlers in object_mapping.items():
        log.debug(f"Processing {object_type}s from Dell ECS")
        
        try:
            items = handlers["api_handler"]()
        except Exception as e:
            log.error(f"Failed to get {object_type}s: {e}")
            continue
        
        if items is None:
            continue
        
        log.debug(f"Found {len(items)} {object_type}(s)")
        
        for item in items:
            try:
                handlers["item_handler"](item)
            except Exception as e:
                log.error(f"Error processing {object_type}: {e}")
```

✅ **Lợi ích:**
- Dễ thêm object types mới (chỉ cần thêm 1 entry vào mapping)
- Consistent error handling
- Better logging

---

### 3. Bước 2: Thêm Caching (5 phút)

```python
def __init__(self, name=None):
    # ... existing code ...
    
    # Add caching lists
    self.processed_namespaces = []
    self.processed_buckets = []
    self.processed_users = []

def add_namespace(self, ns_data):
    ns_name = grab(ns_data, 'name')
    
    if not ns_name:
        return
    
    # Check cache
    if ns_name in self.processed_namespaces:
        log.debug2(f"Namespace '{ns_name}' already processed, skipping")
        return
    
    self.processed_namespaces.append(ns_name)
    
    # ... rest of code ...
```

✅ **Lợi ích:**
- Tránh xử lý lại cùng object nhiều lần
- Performance improvement

---

### 4. Bước 3: Improve Parent-Child Handling (10 phút)

**Current:**
```python
def add_bucket(self, bucket_data):
    bucket_name = bucket_data.get('name')
    ns_name = bucket_data.get('namespace')
    
    namespace = self.inventory.get_by_data(NBNamespace, data={'name': ns_name})
    if namespace is None:
        namespace = self.inventory.add_object(NBNamespace, data={'name': ns_name}, source=self)
```

**Improved:**
```python
def add_bucket(self, bucket_data):
    bucket_name = grab(bucket_data, 'name')
    ns_name = grab(bucket_data, 'namespace')
    
    if not bucket_name or not ns_name:
        log.warning(f"Bucket missing name or namespace")
        return
    
    # Find parent namespace
    namespace = self.inventory.get_by_data(NBNamespace, data={'name': ns_name})
    
    if namespace is None:
        # Smart creation
        log.debug2(f"Namespace '{ns_name}' not found, creating...")
        ns_data = {
            'name': ns_name,
            'slug': ns_name.lower().replace(' ', '-'),
            'description': f"Dell ECS Namespace: {ns_name}"
        }
        namespace = self.inventory.add_object(NBNamespace, data=ns_data, source=self)
    
    if namespace is None:
        log.error(f"Failed to create namespace '{ns_name}'")
        return
    
    # Build complete bucket data
    bucket_data_dict = {
        'name': bucket_name,
        'namespace': namespace,
        'size': grab(bucket_data, 'size', 0),
        'used': grab(bucket_data, 'used', 0),
        'vpool': grab(bucket_data, 'vpool'),
        'replication_group': grab(bucket_data, 'replication_group'),
        'owner': grab(bucket_data, 'owner'),
        'description': f"Dell ECS Bucket: {bucket_name}"
    }
    
    # Find by both name and parent
    existing = self.inventory.get_by_data(NBBucket, data={
        'name': bucket_name,
        'namespace': namespace
    })
    
    if existing is not None:
        existing.update(data=bucket_data_dict, source=self)
    else:
        self.inventory.add_object(NBBucket, data=bucket_data_dict, source=self)
```

✅ **Lợi ích:**
- Better error handling
- Auto-create parent if needed
- Find objects using parent reference (not just name)

---

### 5. Bước 4: Add Filtering Support (10 phút)

**Update `module/sources/dell_ecs/config.py`:**

```python
class DellECSConfig(ConfigBase):
    
    def initialize_settings(self):
        # ... existing settings ...
        
        # Add filtering
        self.add_config_setting(
            key="namespace_include_filter",
            description="Comma-separated include filter for namespaces",
            setting_value_type=str,
            env_var=f"NBS_SOURCE_{self.source_name_normalized}_NAMESPACE_INCLUDE_FILTER",
        )
        
        self.add_config_setting(
            key="namespace_exclude_filter",
            description="Comma-separated exclude filter for namespaces",
            setting_value_type=str,
            env_var=f"NBS_SOURCE_{self.source_name_normalized}_NAMESPACE_EXCLUDE_FILTER",
        )
        
        # Similar for bucket_include_filter, bucket_exclude_filter, etc.
```

**Update `add_namespace` method:**

```python
def add_namespace(self, ns_data):
    ns_name = grab(ns_data, 'name')
    
    if not ns_name:
        return
    
    # Add filtering
    if not self.passes_filter(ns_name,
                             grab(self.settings, "namespace_include_filter"),
                             grab(self.settings, "namespace_exclude_filter")):
        log.debug2(f"Namespace '{ns_name}' filtered out")
        return
    
    # ... rest of code ...
```

✅ **Lợi ích:**
- Flexible filtering configuration
- Can include/exclude objects dynamically

---

### 6. Bước 5: Improve Error Handling (15 phút)

**Current get_buckets():**
```python
def get_buckets(self):
    if not self.token:
        return []

    url = f"https://{self.settings['host_fqdn']}:{self.settings['port']}/object/buckets"
    # ...
    response = requests.get(url, headers=headers, ...)
    # No timeout, no error handling
```

**Improved:**
```python
def get_buckets(self) -> Optional[List[Dict]]:
    """Fetch buckets from ECS API with proper error handling"""
    
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
        log.error(f"Invalid JSON response: {e}")

    return None
```

✅ **Lợi ích:**
- Timeout handling
- Network error handling
- JSON parsing error handling
- Type hints for better IDE support

---

## Implementation Guide

### Phase 1: Quick Wins (30 minutes)

**Priority: High | Effort: Low | Impact: High**

1. ✅ Add Object Mapping (Step 1)
2. ✅ Add Caching (Step 2)
3. ✅ Improve API error handling (Step 5 - simplified)

**Files to modify:**
- `module/sources/dell_ecs/connection.py`

### Phase 2: Enhancement (1-2 hours)

**Priority: High | Effort: Medium | Impact: High**

1. ✅ Improve parent-child handling (Step 3)
2. ✅ Add filtering support (Step 4)
3. ✅ Add comprehensive error handling (Step 5 - full)
4. ✅ Add better logging

**Files to modify:**
- `module/sources/dell_ecs/connection.py`
- `module/sources/dell_ecs/config.py`

### Phase 3: Advanced (2-4 hours)

**Priority: Medium | Effort: High | Impact: Medium**

1. Add type hints throughout
2. Add metrics/telemetry
3. Add connection pooling
4. Add incremental sync capability
5. Add unit tests

---

## Testing Checklist

```markdown
### Basic Functionality
- [ ] Source initializes successfully
- [ ] Can authenticate with ECS
- [ ] Can retrieve namespaces
- [ ] Can retrieve buckets
- [ ] Can retrieve users
- [ ] Objects are added to NetBox inventory

### Filtering
- [ ] namespace_include_filter works
- [ ] namespace_exclude_filter works
- [ ] bucket_include_filter works
- [ ] bucket_exclude_filter works

### Caching
- [ ] Reprocessing same object is skipped
- [ ] Cache is cleared on new run

### Error Handling
- [ ] Timeout is caught and logged
- [ ] Network error is caught and logged
- [ ] Invalid JSON is caught and logged
- [ ] Missing parent is handled gracefully

### Parent-Child Relationships
- [ ] Namespace is created if not found
- [ ] Bucket finds correct namespace
- [ ] Bucket-namespace relationship is maintained

### Dry-run & Pruning
- [ ] Dry-run works correctly
- [ ] Orphaned objects are tagged
- [ ] Orphaned objects are deleted after prune_delay_in_days
```

---

## Configuration Example

```ini
[source/dell-ecs-prod]
enabled = True
type = dell_ecs
host_fqdn = ecs.example.com
port = 4443
username = admin
password = ${ECS_PASSWORD}

# Optional: Filtering
namespace_include_filter = prod-*, staging-*
namespace_exclude_filter = test-*, backup-*
bucket_include_filter = *
bucket_exclude_filter = archive-*
user_include_filter = *
user_exclude_filter = backup-*

# Optional: Connection settings
validate_tls_certs = True
connection_timeout = 30
```

---

## Expected Improvements

### Code Quality
- **Before**: ~50 lines of simple loop
- **After**: ~300 lines of robust, extensible code
- **Readability**: ⬆️ Better structure and comments
- **Maintainability**: ⬆️ Easy to add new object types
- **Testability**: ⬆️ Smaller, focused methods

### Features
- **Filtering**: ✅ Include/exclude patterns
- **Caching**: ✅ Avoid reprocessing
- **Error handling**: ✅ Graceful degradation
- **Logging**: ✅ DEBUG2 levels
- **Parent-child**: ✅ Smart relationship handling

### Performance
- **Skip reprocessing**: ⬆️ ~30-50% faster for large datasets
- **Better API usage**: ⬆️ Early termination on errors
- **Timeout handling**: ⬆️ Prevent hanging

---

## Migration Path

### If you want to refactor existing code:

1. **Create new file** as backup:
   ```
   module/sources/dell_ecs/connection_backup.py
   ```

2. **Update existing file** step by step:
   - Step 1: Add Object Mapping
   - Test with `netbox-sync.py -n` (dry-run)
   - Step 2: Add Caching
   - Test again
   - Continue with other steps

3. **Keep backwards compatibility**:
   - Existing configuration should work
   - Add new config options but make them optional

---

## Further Reading

See `ARCHITECTURE_GUIDE.md` for:
- Detailed explanation of VMware pattern
- How NetBox tagging works
- How orphaned object pruning works
- Flow diagrams and examples
