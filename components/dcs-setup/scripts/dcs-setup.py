#!/usr/bin/env python3
"""
DCS Data Ingestion Setup
========================
Runs inside the ibm-data-cataloging namespace as a Kubernetes Job.

1. Creates an ObjectBucketClaim and waits for it to bind
2. Generates diverse sample data and uploads to S3
3. Authenticates with DCS auth service
4. Registers the S3 bucket as a DCS connection via connmgr API
5. Triggers a scan and monitors indexing progress
6. Falls back to direct DB2 insertion if Kafka indexing stalls
"""

import datetime
import io
import json
import logging
import os
import random
import sys
import time
import urllib3
import warnings

import boto3
import requests
from botocore.config import Config as BotoConfig
from kubernetes import client, config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dcs-setup")

# ── Configuration from environment ──────────────────────────────────────────

DCS_NS = os.environ.get("DCS_NAMESPACE", "ibm-data-cataloging")
USER_NS = os.environ.get("USER_NAMESPACE", "workshop-user1")
CONN_NAME = os.environ.get("CONNECTION_NAME", "workshop-sample-data")
CLUSTER_NAME = os.environ.get("CLUSTER_NAME", "ocp-workshop")
BUCKET_PREFIX = os.environ.get("BUCKET_PREFIX", "dcs-sample-data")
S3_HOST = os.environ.get("S3_HOST", "")
STORAGE_CLASS = os.environ.get("STORAGE_CLASS_NOOBAA", "openshift-storage.noobaa.io")
DCS_ADMIN_USER = os.environ.get("DCS_ADMIN_USER", "sdadmin")
DCS_ADMIN_PASSWORD_SECRET = os.environ.get("DCS_ADMIN_PASSWORD_SECRET", "keystone")
DCS_ADMIN_PASSWORD_KEY = os.environ.get("DCS_ADMIN_PASSWORD_KEY", "password")

SCAN_POLL_INTERVAL = 10
SCAN_TIMEOUT = 300
FALLBACK_AFTER = 120


# ── Kubernetes helpers ──────────────────────────────────────────────────────

def k8s_clients():
    config.load_incluster_config()
    return client.CoreV1Api(), client.CustomObjectsApi()


def get_secret_value(core_v1, namespace, secret_name, key):
    import base64
    secret = core_v1.read_namespaced_secret(secret_name, namespace)
    return base64.b64decode(secret.data[key]).decode()


# ── Step 1: Create ObjectBucketClaim ────────────────────────────────────────

def ensure_obc(custom_api, core_v1):
    obc_name = BUCKET_PREFIX
    group = "objectbucket.io"
    version = "v1alpha1"
    plural = "objectbucketclaims"

    try:
        obc = custom_api.get_namespaced_custom_object(group, version, USER_NS, plural, obc_name)
        log.info("OBC %s already exists in %s (status: %s)", obc_name, USER_NS,
                 obc.get("status", {}).get("phase", "unknown"))
    except client.exceptions.ApiException as e:
        if e.status != 404:
            raise
        log.info("Creating OBC %s in %s", obc_name, USER_NS)
        body = {
            "apiVersion": f"{group}/{version}",
            "kind": "ObjectBucketClaim",
            "metadata": {"name": obc_name, "namespace": USER_NS},
            "spec": {
                "generateBucketName": obc_name,
                "storageClassName": STORAGE_CLASS,
            },
        }
        custom_api.create_namespaced_custom_object(group, version, USER_NS, plural, body)

    log.info("Waiting for OBC to become Bound...")
    for _ in range(60):
        obc = custom_api.get_namespaced_custom_object(group, version, USER_NS, plural, obc_name)
        phase = obc.get("status", {}).get("phase", "")
        if phase == "Bound":
            break
        time.sleep(5)
    else:
        raise RuntimeError("OBC did not become Bound within 5 minutes")

    bucket_name = obc["spec"].get("bucketName", "")
    log.info("OBC bound. Bucket name: %s", bucket_name)

    access_key = get_secret_value(core_v1, USER_NS, obc_name, "AWS_ACCESS_KEY_ID")
    secret_key = get_secret_value(core_v1, USER_NS, obc_name, "AWS_SECRET_ACCESS_KEY")
    return bucket_name, access_key, secret_key


# ── Step 2: Generate and upload sample data ─────────────────────────────────

def build_sample_files():
    """Return a dict of {object_key: bytes_content}."""
    files = {}

    # YAML manifests
    files["manifests/storageclass-ceph-rbd.yaml"] = b"""\
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
"""
    files["manifests/storageclass-cephfs.yaml"] = b"""\
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
"""
    files["manifests/pvc-example.yaml"] = b"""\
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
"""
    files["manifests/backup-policy.yaml"] = b"""\
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
"""
    files["manifests/fusionserviceinstance-dcs.yaml"] = b"""\
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
"""

    for i in range(1, 9):
        tier = "frontend" if i % 2 == 0 else "backend"
        replicas = i % 3 + 1
        files[f"manifests/deployment-app-{i}.yaml"] = f"""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: workload-app-{i}
  labels:
    app: workload-{i}
    tier: {tier}
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: workload-{i}
  template:
    metadata:
      labels:
        app: workload-{i}
    spec:
      containers:
        - name: app
          image: registry.redhat.io/ubi9/ubi-minimal:latest
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
""".encode()

    # CSV data
    rows = ["timestamp,node,cpu_pct,mem_used_gb,mem_total_gb,disk_io_mbps,network_rx_mbps"]
    for h in range(24):
        for node in ["worker-1", "worker-2", "worker-3", "osd-1", "osd-2", "osd-3"]:
            rows.append(
                f"2026-03-31T{h:02d}:00:00Z,{node},"
                f"{random.uniform(10,90):.1f},{random.uniform(4,32):.1f},32.0,"
                f"{random.uniform(0,50):.1f},{random.uniform(0,10):.1f}"
            )
    files["data/csv/cluster-metrics-2026-03-31.csv"] = "\n".join(rows).encode()

    rows = ["pv_name,capacity_gi,access_mode,storage_class,status,namespace,claim"]
    for i in range(1, 41):
        sc = "ocs-storagecluster-cephfs" if i % 3 == 0 else "ocs-storagecluster-ceph-rbd"
        am = "RWX" if i % 4 == 0 else "RWO"
        ns = f"workshop-user{i % 5 + 1}"
        rows.append(f"pvc-{i:04d},{random.randint(10,500)},{am},{sc},Bound,{ns},data-vol-{i:04d}")
    files["data/csv/pv-inventory.csv"] = "\n".join(rows).encode()

    rows = ["customer_id,name,email,department,data_classification,last_access"]
    depts = ["Engineering", "Sales", "Marketing", "Finance", "Legal", "HR", "Security"]
    classes = ["Public", "Internal", "Confidential", "Restricted"]
    for i in range(1, 61):
        rows.append(
            f"CUST-{i:04d},User {i},user{i}@example.com,"
            f"{random.choice(depts)},{random.choice(classes)},"
            f"2026-03-{random.randint(1,28):02d}T{random.randint(0,23):02d}:00:00Z"
        )
    files["data/csv/customer-directory.csv"] = "\n".join(rows).encode()

    # JSON data
    events = []
    for i in range(25):
        events.append({
            "id": f"EVT-{i+1:04d}",
            "type": random.choice(["ScaleUp", "ScaleDown", "FailOver", "Rebalance", "Backup", "Restore"]),
            "source": random.choice(["ceph-mgr", "fusion-operator", "odf-console", "noobaa-core"]),
            "severity": random.choice(["info", "warning", "critical"]),
            "timestamp": (datetime.datetime(2026, 3, 31) - datetime.timedelta(hours=random.randint(0, 168))).isoformat() + "Z",
            "message": f"Storage event {i+1} processed successfully",
        })
    files["data/json/storage-events.json"] = json.dumps(events, indent=2).encode()

    pools = []
    for name in ["cephblockpool", "cephfilesystem-data0", "cephfilesystem-metadata0", ".rgw.root", "default.rgw.log"]:
        pools.append({
            "name": name,
            "stored_bytes": random.randint(10**9, 10**12),
            "objects": random.randint(1000, 500000),
            "utilization_pct": round(random.uniform(15, 85), 1),
            "pg_count": random.choice([64, 128, 256, 512]),
        })
    files["data/json/ceph-pool-stats.json"] = json.dumps({"cluster": "ocs-storagecluster", "pools": pools}, indent=2).encode()

    configs = {
        "backupSchedules": [
            {"name": "daily-gold",   "cron": "0 2 * * *",  "retention": 7, "enabled": True},
            {"name": "weekly-silver","cron": "0 3 * * 0",  "retention": 4, "enabled": True},
            {"name": "monthly-archive","cron": "0 4 1 * *","retention": 12,"enabled": False},
        ],
        "replicationPolicies": [
            {"source": "us-east-2", "target": "us-west-2", "interval_min": 15, "enabled": True},
            {"source": "us-east-2", "target": "eu-west-1", "interval_min": 60, "enabled": False},
        ],
    }
    files["data/json/data-protection-config.json"] = json.dumps(configs, indent=2).encode()

    # Log files
    levels = ["INFO", "INFO", "INFO", "WARN", "ERROR", "DEBUG"]
    components = ["ceph-osd.0", "ceph-osd.1", "ceph-osd.2", "ceph-mon.a", "ceph-mgr", "rook-operator"]
    msgs = [
        "Health check passed", "PG count adjusted", "OSD heartbeat received",
        "Slow request detected", "Scrub completed", "Recovery in progress",
        "Client connection established", "Pool rebalance triggered",
        "Deep scrub started on pg 3.2a", "Mon election finished",
    ]
    lines = []
    for _ in range(200):
        ts = (datetime.datetime(2026, 3, 31, 23, 59, 59) - datetime.timedelta(seconds=random.randint(0, 86400))).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append(f"{ts} [{random.choice(levels)}] {random.choice(components)}: {random.choice(msgs)}")
    files["logs/ceph-cluster-2026-03-31.log"] = "\n".join(lines).encode()

    lines = []
    for _ in range(150):
        ts = (datetime.datetime(2026, 3, 31, 23, 59, 59) - datetime.timedelta(seconds=random.randint(0, 86400))).strftime("%Y-%m-%dT%H:%M:%SZ")
        ns = random.choice(["ibm-spectrum-fusion-ns", "ibm-data-cataloging", "openshift-storage", "workshop-user1"])
        op_msgs = [
            "Reconciliation completed", "Resource updated", "Watch event received",
            "Operator version check passed", "CRD schema validated",
            "Service instance status: Running", "Backup job scheduled",
            "Connection health check: OK", "License validated",
        ]
        lines.append(f"{ts} [{random.choice(['INFO','INFO','WARN','ERROR'])}] namespace={ns}: {random.choice(op_msgs)}")
    files["logs/fusion-operator-2026-03-31.log"] = "\n".join(lines).encode()

    lines = []
    for _ in range(100):
        ts = (datetime.datetime(2026, 3, 31, 23, 59, 59) - datetime.timedelta(seconds=random.randint(0, 86400))).strftime("%Y-%m-%dT%H:%M:%SZ")
        method = random.choice(["GET", "POST", "PUT", "DELETE"])
        paths = ["/api/v1/pods", "/api/v1/namespaces", "/apis/storage.k8s.io/v1/storageclasses",
                 "/api/v1/persistentvolumes", "/apis/apps/v1/deployments"]
        code = random.choices([200, 201, 204, 400, 403, 404, 500], weights=[50, 15, 10, 5, 5, 10, 5])[0]
        lines.append(
            f"{ts} {method} {random.choice(paths)} {code} "
            f"user=system:serviceaccount:openshift-storage:rook-ceph-operator latency={random.randint(1,500)}ms"
        )
    files["logs/api-audit-2026-03-31.log"] = "\n".join(lines).encode()

    return files


def download_docs():
    """Download Red Hat and IBM documentation for catalog diversity."""
    docs = {}
    urls = {
        "docs/redhat/openshift_container_platform-4.18-storage-en-us.pdf":
            "https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/pdf/storage/openshift_container_platform-4.18-storage-en-us.pdf",
        "docs/redhat/openshift_container_platform-4.18-architecture-en-us.pdf":
            "https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/pdf/architecture/openshift_container_platform-4.18-architecture-en-us.pdf",
        "docs/redhat/openshift_container_platform-4.18-networking-en-us.pdf":
            "https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/pdf/networking/openshift_container_platform-4.18-networking-en-us.pdf",
        "docs/redhat/openshift_container_platform-4.18-backup_and_restore-en-us.pdf":
            "https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/pdf/backup_and_restore/openshift_container_platform-4.18-backup_and_restore-en-us.pdf",
    }
    for key, url in urls.items():
        try:
            resp = requests.get(url, timeout=60, verify=False)
            if resp.status_code == 200 and len(resp.content) > 100:
                docs[key] = resp.content
                log.info("Downloaded %s (%d bytes)", key, len(resp.content))
            else:
                log.warning("Skipping %s (status %d, length %d)", key, resp.status_code, len(resp.content))
        except Exception as e:
            log.warning("Failed to download %s: %s", key, e)
    return docs


def upload_to_s3(bucket_name, access_key, secret_key, files):
    endpoint_url = f"https://{S3_HOST}"
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        verify=False,
        config=BotoConfig(signature_version="s3v4"),
    )

    for key, data in files.items():
        s3.put_object(Bucket=bucket_name, Key=key, Body=data)
    log.info("Uploaded %d files to s3://%s", len(files), bucket_name)
    return s3


# ── Step 3: DCS auth ───────────────────────────────────────────────────────

def get_dcs_token(core_v1):
    password = get_secret_value(core_v1, DCS_NS, DCS_ADMIN_PASSWORD_SECRET, DCS_ADMIN_PASSWORD_KEY)
    resp = requests.get(
        f"http://auth.{DCS_NS}.svc:80/auth/v1/token",
        auth=(DCS_ADMIN_USER, password),
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.headers.get("X-Auth-Token", "")
    if not token:
        raise RuntimeError("DCS auth returned 200 but no X-Auth-Token header")
    log.info("Obtained DCS auth token")
    return token


# ── Step 4: Register S3 connection ──────────────────────────────────────────

def register_connection(token, bucket_name, access_key, secret_key):
    url = f"http://connmgr.{DCS_NS}.svc:80/connmgr/v1/connections"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    existing = [c["name"] for c in resp.json()]
    if CONN_NAME in existing:
        log.info("Connection %s already exists -- skipping creation", CONN_NAME)
        return

    payload = {
        "name": CONN_NAME,
        "platform": "S3",
        "host": S3_HOST,
        "datasource": bucket_name,
        "cluster": CLUSTER_NAME,
        "additional_info": {
            "access_key": access_key,
            "secret_key": secret_key,
            "verify_certificates": False,
        },
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code == 201:
        log.info("Connection %s created successfully", CONN_NAME)
    else:
        raise RuntimeError(f"Failed to create connection: {resp.status_code} {resp.text}")


# ── Step 5: Trigger scan and monitor ────────────────────────────────────────

def get_connection_total(token):
    """Return total_records for the connection from connmgr."""
    url = f"http://connmgr.{DCS_NS}.svc:80/connmgr/v1/connections"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        for c in resp.json():
            if c["name"] == CONN_NAME:
                return c.get("total_records", 0)
    except Exception:
        pass
    return 0


def trigger_and_monitor_scan(token):
    headers = {"Authorization": f"Bearer {token}"}
    scan_url = f"http://connmgr.{DCS_NS}.svc:80/connmgr/v1/scan/{CONN_NAME}"

    total = get_connection_total(token)
    if total > 0:
        log.info("Catalog already has %d records -- skipping scan", total)
        return True

    resp = requests.post(scan_url, headers=headers, timeout=30)
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"status": resp.text}
    log.info("Scan trigger response: %s", body.get("status", body))

    started = time.time()
    while time.time() - started < SCAN_TIMEOUT:
        time.sleep(SCAN_POLL_INTERVAL)

        try:
            resp = requests.get(scan_url, headers=headers, timeout=15)
            data = resp.json()
        except Exception:
            data = {}

        indexed = data.get("indexed_records", 0)
        scanned = data.get("scanned_records", 0)
        status = data.get("status", "unknown")
        total = get_connection_total(token)

        log.info("Scan: status=%s scanned=%d indexed=%d | connection total=%d",
                 status, scanned, indexed, total)

        if total > 0:
            log.info("Catalog populated: %d total records", total)
            return True

        elapsed = time.time() - started
        if elapsed > FALLBACK_AFTER and total == 0:
            if scanned > 0 or "No scan" in status or "Complete" in status:
                log.warning("Indexing stalled after %.0fs -- will use DB2 fallback", elapsed)
                return False

    log.warning("Scan monitoring timed out after %ds", SCAN_TIMEOUT)
    return False


# ── Step 6: DB2 direct fallback ─────────────────────────────────────────────

def db2_fallback(token, bucket_name, s3_client):
    """Insert catalog records directly into METAOCEAN via DB2 CLI exec."""
    log.info("Starting DB2 direct insertion fallback")

    objects = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket_name):
        for obj in page.get("Contents", []):
            objects.append(obj)

    if not objects:
        log.error("No objects found in bucket %s -- nothing to insert", bucket_name)
        return

    db2_cli_fallback(bucket_name, objects)


def db2_cli_fallback(bucket_name, objects):
    """Exec into the DB2 pod and run INSERT statements using db2 batch mode."""
    v1 = client.CoreV1Api()
    from kubernetes.stream import stream

    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    sql_lines = ["connect to BLUDB;"]
    for obj in objects:
        key = obj["Key"]
        size = obj.get("Size", 0)
        parts = key.rsplit("/", 1)
        path = parts[0] if len(parts) > 1 else ""
        filename = parts[-1]
        ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        fkey = f"{CLUSTER_NAME}:{bucket_name}:{key}"

        sql_lines.append(
            f"INSERT INTO BLUADMIN.METAOCEAN "
            f"(DATASOURCE, PLATFORM, CLUSTER, PATH, FILENAME, FILETYPE, SIZE, "
            f"INSERTTIME, UPDATEDTIME, SCANGEN, FKEY, OPERATION, INGESTTYPE, STATE) "
            f"VALUES ('{bucket_name}', 'S3', '{CLUSTER_NAME}', "
            f"'/{path}', '{filename}', '{ext}', {size}, "
            f"'{now}', '{now}', 1, '{fkey}', 'ADD', 'SCAN', 'normal');"
        )

    db2_pod = None
    pods = v1.list_namespaced_pod(DCS_NS)
    for pod in pods.items:
        if pod.metadata.name.startswith("c-isd-db2u-") and pod.status.phase == "Running":
            db2_pod = pod.metadata.name
            break

    if not db2_pod:
        log.error("No running DB2 pod found -- cannot perform CLI fallback")
        return

    batch_input = "\n".join(sql_lines)
    cmd = ["su", "-", "db2inst1", "-c", f"printf '{batch_input}' | db2 -t"]

    log.info("Executing %d INSERT statements via DB2 CLI on pod %s", len(objects), db2_pod)
    try:
        result = stream(
            v1.connect_get_namespaced_pod_exec,
            db2_pod, DCS_NS,
            command=cmd,
            container="db2u",
            stderr=True, stdout=True, stdin=False, tty=False,
        )
        successes = result.count("DB20000I")
        failures = result.count("SQLSTATE=")
        log.info("DB2 CLI fallback: %d successes, %d failures (output length: %d)",
                 successes, failures, len(result))
        if failures > 0:
            log.warning("Some DB2 inserts failed -- check output: %s", result[-500:])
    except Exception as e:
        log.error("DB2 CLI fallback failed: %s", e)


# ── Step 7: Verify catalog population ───────────────────────────────────────

def verify_catalog(token):
    total = get_connection_total(token)
    if total > 0:
        log.info("Final catalog state: total_records=%d", total)
        return True
    log.warning("Final catalog state: total_records=0")
    return False


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    log.info("=== DCS Data Ingestion Setup ===")
    log.info("DCS namespace: %s | User namespace: %s | Connection: %s", DCS_NS, USER_NS, CONN_NAME)

    core_v1, custom_api = k8s_clients()

    # Step 1: OBC
    log.info("--- Step 1: ObjectBucketClaim ---")
    bucket_name, access_key, secret_key = ensure_obc(custom_api, core_v1)

    # Step 2: Generate + upload
    log.info("--- Step 2: Generate and upload sample data ---")
    sample_files = build_sample_files()
    doc_files = download_docs()
    sample_files.update(doc_files)
    s3_client = upload_to_s3(bucket_name, access_key, secret_key, sample_files)

    # Step 3: Auth
    log.info("--- Step 3: DCS authentication ---")
    token = get_dcs_token(core_v1)

    # Step 4: Register connection
    log.info("--- Step 4: Register S3 connection ---")
    register_connection(token, bucket_name, access_key, secret_key)

    # Step 5: Scan + monitor
    log.info("--- Step 5: Trigger scan and monitor ---")
    indexed_ok = trigger_and_monitor_scan(token)

    # Step 6: Fallback if needed
    if not indexed_ok:
        log.info("--- Step 6: DB2 fallback insertion ---")
        token = get_dcs_token(core_v1)
        db2_fallback(token, bucket_name, s3_client)

    # Step 7: Verify
    log.info("--- Step 7: Verify catalog ---")
    token = get_dcs_token(core_v1)
    if verify_catalog(token):
        log.info("=== DCS setup completed successfully ===")
    else:
        log.warning("=== Catalog verification inconclusive -- check DCS console ===")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("DCS setup failed")
        sys.exit(1)
