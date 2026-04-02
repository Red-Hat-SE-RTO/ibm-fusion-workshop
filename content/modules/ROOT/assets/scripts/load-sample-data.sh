#!/usr/bin/env bash
set -euo pipefail

# ── Pre-flight ──────────────────────────────────────────────────────────────
: "${AWS_ACCESS_KEY_ID:?Set AWS_ACCESS_KEY_ID from your ObjectBucketClaim secret}"
: "${AWS_SECRET_ACCESS_KEY:?Set AWS_SECRET_ACCESS_KEY from your ObjectBucketClaim secret}"
: "${BUCKET_NAME:?Set BUCKET_NAME from your ObjectBucketClaim}"
: "${S3_ENDPOINT:?Set S3_ENDPOINT (e.g. https://s3-openshift-storage.<domain>)}"

command -v aws >/dev/null 2>&1 || {
  echo "Installing AWS CLI…"
  pip install --quiet --user awscli
  export PATH="$HOME/.local/bin:$PATH"
}

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
AWS="aws --endpoint-url $S3_ENDPOINT --no-verify-ssl"

echo "▸ Staging sample data in $WORK"

# ── 1. Red Hat & IBM documentation (PDFs) ───────────────────────────────────
mkdir -p "$WORK/docs/redhat" "$WORK/docs/ibm"

REDHAT_DOCS=(
  "https://access.redhat.com/documentation/en-us/openshift_container_platform/4.18/pdf/architecture/openshift_container_platform-4.18-architecture-en-us.pdf"
  "https://access.redhat.com/documentation/en-us/openshift_container_platform/4.18/pdf/storage/openshift_container_platform-4.18-storage-en-us.pdf"
  "https://access.redhat.com/documentation/en-us/openshift_container_platform/4.18/pdf/networking/openshift_container_platform-4.18-networking-en-us.pdf"
)

for url in "${REDHAT_DOCS[@]}"; do
  fname=$(basename "$url")
  echo "  ↓ $fname"
  curl -sLk -o "$WORK/docs/redhat/$fname" "$url" 2>/dev/null || echo "  ⚠ skipped (not reachable)"
done

IBM_DOCS=(
  "https://www.ibm.com/docs/en/fusion-software/2.12.0?topic=overview-product"
  "https://www.ibm.com/docs/en/fusion-software/2.12.0?topic=services-data-cataloging"
)

for url in "${IBM_DOCS[@]}"; do
  slug=$(echo "$url" | sed 's|.*/||; s|[^a-zA-Z0-9]|_|g')
  echo "  ↓ ibm-fusion-${slug}.html"
  curl -sLk -o "$WORK/docs/ibm/ibm-fusion-${slug}.html" "$url" 2>/dev/null || echo "  ⚠ skipped"
done

# ── 2. Sample YAML manifests ────────────────────────────────────────────────
mkdir -p "$WORK/manifests"

cat > "$WORK/manifests/storageclass-ceph-rbd.yaml" <<'YAML'
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ocs-storagecluster-ceph-rbd
provisioner: openshift-storage.rbd.csi.ceph.com
parameters:
  clusterID: openshift-storage
  pool: ocs-storagecluster-cephblockpool
reclaimPolicy: Delete
volumeBindingMode: Immediate
YAML

cat > "$WORK/manifests/storageclass-cephfs.yaml" <<'YAML'
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: ocs-storagecluster-cephfs
provisioner: openshift-storage.cephfs.csi.ceph.com
parameters:
  clusterID: openshift-storage
  fsName: ocs-storagecluster-cephfilesystem
reclaimPolicy: Delete
volumeBindingMode: Immediate
YAML

cat > "$WORK/manifests/pvc-example.yaml" <<'YAML'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-vol-01
spec:
  accessModes: [ReadWriteOnce]
  resources:
    requests:
      storage: 50Gi
  storageClassName: ocs-storagecluster-ceph-rbd
YAML

cat > "$WORK/manifests/backup-policy.yaml" <<'YAML'
apiVersion: data-protection.isf.ibm.com/v1alpha1
kind: BackupPolicy
metadata:
  name: daily-gold
  namespace: ibm-spectrum-fusion-ns
spec:
  recipe: recipe-minio-backup
  schedule: "0 2 * * *"
  retentionPolicy:
    maxBackups: 7
YAML

cat > "$WORK/manifests/fusionserviceinstance-dcs.yaml" <<'YAML'
apiVersion: service.isf.ibm.com/v1
kind: FusionServiceInstance
metadata:
  name: data-cataloging
  namespace: ibm-spectrum-fusion-ns
spec:
  serviceDefinition: data-cataloging-service-definition
  doInstall: true
  parameters:
    - name: namespace
      value: "ibm-data-cataloging"
    - name: rwx_storage_class
      value: "ocs-storagecluster-cephfs"
YAML

for i in $(seq 1 8); do
  cat > "$WORK/manifests/deployment-app-${i}.yaml" <<YAML
apiVersion: apps/v1
kind: Deployment
metadata:
  name: workload-app-${i}
  labels:
    app: workload-${i}
    tier: $([ $((i % 2)) -eq 0 ] && echo "frontend" || echo "backend")
spec:
  replicas: $((i % 3 + 1))
  selector:
    matchLabels:
      app: workload-${i}
  template:
    metadata:
      labels:
        app: workload-${i}
    spec:
      containers:
        - name: app
          image: registry.redhat.io/ubi9/ubi-minimal:latest
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
YAML
done

# ── 3. Synthetic CSV data ───────────────────────────────────────────────────
mkdir -p "$WORK/data/csv"

python3 -c "
import random
print('timestamp,node,cpu_pct,mem_used_gb,mem_total_gb,disk_io_mbps,network_rx_mbps')
for h in range(24):
    for node in ['worker-1','worker-2','worker-3','osd-1','osd-2','osd-3']:
        print(f'2026-03-31T{h:02d}:00:00Z,{node},{random.uniform(10,90):.1f},{random.uniform(4,32):.1f},32.0,{random.uniform(0,50):.1f},{random.uniform(0,10):.1f}')
" > "$WORK/data/csv/cluster-metrics-2026-03-31.csv"

python3 -c "
import random
print('pv_name,capacity_gi,access_mode,storage_class,status,namespace,claim')
for i in range(1,41):
    sc = 'ocs-storagecluster-cephfs' if i%3==0 else 'ocs-storagecluster-ceph-rbd'
    am = 'RWX' if i%4==0 else 'RWO'
    ns = f'workshop-user{i%5+1}'
    print(f'pvc-{i:04d},{random.randint(10,500)},{am},{sc},Bound,{ns},data-vol-{i:04d}')
" > "$WORK/data/csv/pv-inventory.csv"

python3 -c "
import random
depts = ['Engineering','Sales','Marketing','Finance','Legal','HR','Security']
classes = ['Public','Internal','Confidential','Restricted']
print('customer_id,name,email,department,data_classification,last_access')
for i in range(1,61):
    print(f'CUST-{i:04d},User {i},user{i}@example.com,{random.choice(depts)},{random.choice(classes)},2026-03-{random.randint(1,28):02d}T{random.randint(0,23):02d}:00:00Z')
" > "$WORK/data/csv/customer-directory.csv"

# ── 4. Synthetic JSON data ──────────────────────────────────────────────────
mkdir -p "$WORK/data/json"

python3 -c "
import json, random, datetime
records = []
for i in range(25):
    records.append({
        'id': f'EVT-{i+1:04d}',
        'type': random.choice(['ScaleUp','ScaleDown','FailOver','Rebalance','Backup','Restore']),
        'source': random.choice(['ceph-mgr','fusion-operator','odf-console','noobaa-core']),
        'severity': random.choice(['info','warning','critical']),
        'timestamp': (datetime.datetime(2026,3,31) - datetime.timedelta(hours=random.randint(0,168))).isoformat()+'Z',
        'message': f'Storage event {i+1} processed successfully'
    })
print(json.dumps(records, indent=2))
" > "$WORK/data/json/storage-events.json"

python3 -c "
import json, random
pools = []
for name in ['cephblockpool','cephfilesystem-data0','cephfilesystem-metadata0','.rgw.root','default.rgw.log']:
    pools.append({
        'name': name,
        'stored_bytes': random.randint(10**9, 10**12),
        'objects': random.randint(1000, 500000),
        'utilization_pct': round(random.uniform(15, 85), 1),
        'pg_count': random.choice([64,128,256,512])
    })
print(json.dumps({'cluster':'ocs-storagecluster','pools':pools}, indent=2))
" > "$WORK/data/json/ceph-pool-stats.json"

python3 -c "
import json, random
configs = {
    'backupSchedules': [
        {'name': 'daily-gold',   'cron': '0 2 * * *',  'retention': 7, 'enabled': True},
        {'name': 'weekly-silver','cron': '0 3 * * 0',  'retention': 4, 'enabled': True},
        {'name': 'monthly-archive','cron': '0 4 1 * *','retention': 12,'enabled': False}
    ],
    'replicationPolicies': [
        {'source': 'us-east-2', 'target': 'us-west-2', 'interval_min': 15, 'enabled': True},
        {'source': 'us-east-2', 'target': 'eu-west-1', 'interval_min': 60, 'enabled': False}
    ]
}
print(json.dumps(configs, indent=2))
" > "$WORK/data/json/data-protection-config.json"

# ── 5. Synthetic log files ──────────────────────────────────────────────────
mkdir -p "$WORK/logs"

python3 -c "
import random, datetime
levels = ['INFO','INFO','INFO','WARN','ERROR','DEBUG']
components = ['ceph-osd.0','ceph-osd.1','ceph-osd.2','ceph-mon.a','ceph-mgr','rook-operator']
for i in range(200):
    ts = (datetime.datetime(2026,3,31,23,59,59) - datetime.timedelta(seconds=random.randint(0,86400))).strftime('%Y-%m-%dT%H:%M:%SZ')
    lvl = random.choice(levels)
    comp = random.choice(components)
    msgs = [
        'Health check passed', 'PG count adjusted', 'OSD heartbeat received',
        'Slow request detected', 'Scrub completed', 'Recovery in progress',
        'Client connection established', 'Pool rebalance triggered',
        'Deep scrub started on pg 3.2a', 'Mon election finished'
    ]
    print(f'{ts} [{lvl}] {comp}: {random.choice(msgs)}')
" > "$WORK/logs/ceph-cluster-2026-03-31.log"

python3 -c "
import random, datetime
for i in range(150):
    ts = (datetime.datetime(2026,3,31,23,59,59) - datetime.timedelta(seconds=random.randint(0,86400))).strftime('%Y-%m-%dT%H:%M:%SZ')
    lvl = random.choice(['INFO','INFO','WARN','ERROR'])
    ns = random.choice(['ibm-spectrum-fusion-ns','ibm-data-cataloging','openshift-storage','workshop-user1'])
    msgs = [
        'Reconciliation completed', 'Resource updated', 'Watch event received',
        'Operator version check passed', 'CRD schema validated',
        'Service instance status: Running', 'Backup job scheduled',
        'Connection health check: OK', 'License validated'
    ]
    print(f'{ts} [{lvl}] namespace={ns}: {random.choice(msgs)}')
" > "$WORK/logs/fusion-operator-2026-03-31.log"

python3 -c "
import random, datetime
for i in range(100):
    ts = (datetime.datetime(2026,3,31,23,59,59) - datetime.timedelta(seconds=random.randint(0,86400))).strftime('%Y-%m-%dT%H:%M:%SZ')
    method = random.choice(['GET','POST','PUT','DELETE'])
    paths = ['/api/v1/pods','/api/v1/namespaces','/apis/storage.k8s.io/v1/storageclasses',
             '/api/v1/persistentvolumes','/apis/apps/v1/deployments']
    code = random.choices([200,201,204,400,403,404,500], weights=[50,15,10,5,5,10,5])[0]
    print(f'{ts} {method} {random.choice(paths)} {code} user=system:serviceaccount:openshift-storage:rook-ceph-operator latency={random.randint(1,500)}ms')
" > "$WORK/logs/api-audit-2026-03-31.log"

# ── 6. Upload everything ───────────────────────────────────────────────────
echo "▸ Uploading to s3://${BUCKET_NAME}"
$AWS s3 sync "$WORK/" "s3://${BUCKET_NAME}/" --quiet 2>/dev/null

COUNT=$($AWS s3 ls "s3://${BUCKET_NAME}/" --recursive 2>/dev/null | wc -l)
echo "✓ Uploaded ${COUNT} files to s3://${BUCKET_NAME}"
echo "  Bucket is ready for DCS scanning."
