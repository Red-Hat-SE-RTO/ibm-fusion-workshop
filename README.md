# Modern Hybrid Infrastructure: IBM Storage Fusion & OpenShift Data Foundation

[![Build and Deploy to GitHub Pages](https://github.com/Red-Hat-SE-RTO/ibm-fusion-workshop/actions/workflows/gh-pages.yml/badge.svg)](https://github.com/Red-Hat-SE-RTO/ibm-fusion-workshop/actions/workflows/gh-pages.yml)

**[View the Workshop Content](https://red-hat-se-rto.github.io/ibm-fusion-workshop)**

A 2-hour hands-on workshop deployed on OpenShift via ArgoCD GitOps, following the
[Field-Sourced Content Template](https://github.com/rhpds/field-sourced-content-template)
Helm App of Apps pattern.

## Workshop Overview

| Module | Duration | Type | Topic |
|--------|----------|------|-------|
| 0 | 30 min | Presentation/Demo | Installation & Architecture |
| 1 | 15 min | Guided Tour | Architecture Tour & Storage Provisioning |
| 2 | 30 min | Hands-on Lab | OpenShift Virtualization & RWX Live Migration |
| 3 | 25 min | Hands-on Lab | Modern Data Protection (CBT & Backups) |
| 4 | 20 min | Hands-on Lab / Presentation | AI-Driven Data Cataloging with MCP |
| 5 | 10 min | Presentation | The 4.20+ Horizon: AI & Autonomic Operations |

## Architecture

```
GitHub Repository
  │
  └─► ArgoCD (App of Apps)
        ├─► workshop-infra ────► Per-user Namespaces + RBAC
        ├─► showroom-user1 ────► Showroom Pod (showroom-deployer chart)
        ├─► showroom-user2 ────► Showroom Pod (showroom-deployer chart)
        └─► showroom-userN ────► Showroom Pod (showroom-deployer chart)
```

Each user gets their own [Showroom](https://github.com/rhpds/showroom-deployer)
instance deployed via the official `showroom-single-pod` Helm chart with
per-user `user_data` attributes injected through ArgoCD.

## Prerequisites

- Pre-provisioned RHDP environment: **OpenShift Container Platform with IBM Fusion** (AWS)
- Must be provisioned **90 minutes prior** to session start
- OpenShift GitOps (ArgoCD) operator installed on the cluster
- `oc` and `helm` CLI tools available

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/Red-Hat-SE-RTO/ibm-fusion-workshop.git
cd ibm-fusion-workshop
```

Edit `values.yaml`:
- Set `deployer.domain` to your cluster's apps domain
- Set `gitops.repoUrl` and `components.showroom.content.repoUrl` to your GitHub repo URL
- Set `workshop.openshift_console_url` and `workshop.fusion_ui_url` for your cluster
- Add/remove entries under `users:` for the number of participants

### 2. Push to GitHub

```bash
git add -A && git commit -m "Configure workshop for my cluster"
git push origin main
```

### 3. Deploy via ArgoCD

```bash
oc login --token=<token> --server=<api-url>

helm template workshop . | oc apply -f -
```

This creates the root ArgoCD Applications which automatically sync:
- `workshop-infra` -- per-user namespaces and RBAC
- `showroom-<user>` -- one Showroom lab guide per user (via showroom-deployer chart)

### 4. Verify

```bash
# Check ArgoCD applications
oc get applications -n openshift-gitops

# Check showroom pods
oc get pods -n showroom-user1

# Get showroom route
oc get route -n showroom-user1
```

## Repository Structure

```
ibm-fusion-workshop/
├── Chart.yaml                    # Master Helm chart
├── values.yaml                   # Central configuration
├── templates/
│   ├── _helpers.tpl
│   └── applications.yaml         # ArgoCD App of Apps (infra + per-user showroom)
├── components/
│   └── workshop-infra/           # Per-user namespaces and RBAC
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│           ├── namespaces.yaml
│           ├── rbac.yaml
│           └── network-policies.yaml
├── content/                      # Showroom Antora lab guide
│   ├── antora.yml
│   └── modules/ROOT/
│       ├── nav.adoc
│       ├── assets/images/
│       ├── examples/
│       ├── partials/
│       └── pages/
│           ├── index.adoc
│           ├── module-00-installation.adoc
│           ├── module-01-architecture.adoc
│           ├── module-02-virtualization.adoc
│           ├── module-03-data-protection.adoc
│           ├── module-04-data-cataloging.adoc
│           ├── module-05-horizon.adoc
│           ├── references.adoc
│           └── conclusion.adoc
└── README.md
```

## Scaling Users

Add or remove users in `values.yaml`:

```yaml
users:
  - user1
  - user2
  - user3
  # ...add as many as needed
```

Each user gets:
- A dedicated namespace (`workshop-<user>`) with admin RBAC
- KubeVirt admin role for VM operations
- A Showroom lab guide instance at `https://showroom-<user>.<apps-domain>`

## AgnosticD Variable Mapping

This workshop uses the Field-Sourced Content Helm path. For integration with
AgnosticD directly, the following mapping applies:

| Helm Value | AgnosticD Variable | Description |
|------------|-------------------|-------------|
| `components.showroom.content.repoUrl` | `ocp4_workload_showroom_content_git_repo` | Lab content git repo |
| `components.showroom.content.repoRef` | `ocp4_workload_showroom_content_git_repo_ref` | Git branch/tag |
| `components.showroom.chartVersion` | `ocp4_workload_showroom_deployer_chart_version` | Showroom chart version |
| `deployer.domain` | `cluster_domain` (auto-injected) | Cluster apps domain |

## Technology Stack

| Component | Version |
|-----------|---------|
| Red Hat OpenShift Container Platform | 4.18 |
| OpenShift Data Foundation (ODF) | 4.18 |
| IBM Storage Fusion | 2.10+ |
| OpenShift Virtualization | 4.18 |
| Showroom Deployer | ^2.0.0 |

## External References

### Product Documentation
- [IBM Storage Fusion 2.10 Docs](https://www.ibm.com/docs/en/storage-fusion/2.10)
- [OpenShift Data Foundation 4.18 Docs](https://docs.redhat.com/en/documentation/red_hat_openshift_data_foundation/4.18)
- [OpenShift Container Platform 4.18 Docs](https://docs.redhat.com/en/documentation/openshift_container_platform/4.18)

### Storage & Data Services
- [Ceph Architecture](https://docs.ceph.com/en/latest/architecture/)
- [Ceph RBD Documentation](https://docs.ceph.com/en/latest/rbd/)
- [Multicloud Object Gateway (NooBaa)](https://www.noobaa.io/)

### Virtualization
- [OpenShift Virtualization Docs](https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/html/virtualization)
- [KubeVirt Project](https://kubevirt.io/)

### Data Protection
- [IBM Fusion Data Protection](https://www.ibm.com/docs/en/storage-fusion/2.10?topic=overview-data-protection)
- [Change Block Tracking](https://www.ibm.com/docs/en/storage-fusion/2.10?topic=backup-change-block-tracking)
- [Ceph rbd-diff API](https://docs.ceph.com/en/latest/rbd/rbd-snapshot/#differential-backups)

### Data Cataloging & AI
- [IBM Fusion Data Cataloging Service](https://www.ibm.com/docs/en/fusion-software/2.12.0?topic=services-data-cataloging)
- [DCS MCP Server Documentation](https://www.ibm.com/docs/en/fusion-software/2.12.0?topic=autotagging-data-cataloging-mcp-server)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [Red Hat OpenShift Lightspeed](https://docs.redhat.com/en/documentation/red_hat_openshift_lightspeed/)
- [Exploring your Catalog with Natural Language through MCP (IBM Community)](https://community.ibm.com/community/user/blogs/paul-llamas-virgen/2026/03/06/exploring-your-fusion-data-catalog-with-nlp)

### Forward-Looking
- [Kubernetes Descheduler](https://github.com/kubernetes-sigs/descheduler)
- [Kubernetes Gateway API](https://gateway-api.sigs.k8s.io/)
- [IBM Content-Aware Storage](https://www.ibm.com/products/storage-fusion)

### Workshop Infrastructure
- [Showroom Deployer](https://github.com/rhpds/showroom-deployer)
- [Showroom Content Template](https://github.com/rhpds/showroom_template_default)
- [Field-Sourced Content Template](https://github.com/rhpds/field-sourced-content-template)
- [Red Hat Demo Platform](https://demo.redhat.com/)
- [Antora Documentation](https://docs.antora.org/)
- [Operator Lifecycle Manager](https://olm.operatorframework.io/)
