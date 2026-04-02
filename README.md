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
| 5 | 15 min | Presentation | The 4.21 Horizon: AI & Autonomic Operations |

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
| IBM Storage Fusion | 2.12 |
| OpenShift Virtualization | 4.18 |
| Showroom Deployer | ^2.0.0 |

## External References

### Product Documentation
- [IBM Storage Fusion 2.12 Docs](https://www.ibm.com/docs/en/storage-fusion/2.12)
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
- [IBM Fusion Data Protection](https://www.ibm.com/docs/en/storage-fusion/2.12?topic=overview-data-protection)
- [Change Block Tracking](https://www.ibm.com/docs/en/storage-fusion/2.12?topic=backup-change-block-tracking)
- [Ceph rbd-diff API](https://docs.ceph.com/en/latest/rbd/rbd-snapshot/#differential-backups)

### Data Cataloging & AI
- [IBM Fusion Data Cataloging Service](https://www.ibm.com/docs/en/fusion-software/2.12.0?topic=services-data-cataloging)
- [DCS MCP Server Documentation](https://www.ibm.com/docs/en/fusion-software/2.12.0?topic=autotagging-data-cataloging-mcp-server)
- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [Red Hat OpenShift Lightspeed](https://docs.redhat.com/en/documentation/red_hat_openshift_lightspeed/)
- [Exploring your Catalog with Natural Language through MCP (IBM Community)](https://community.ibm.com/community/user/blogs/paul-llamas-virgen/2026/03/06/exploring-your-fusion-data-catalog-with-nlp)

### OpenShift 4.21 & The Horizon (Module 5)

**Autonomic Virtualization**
- [Dynamic VM CPU Workload Rebalancing with Load Aware Descheduler](https://developers.redhat.com/blog/2025/06/03/dynamic-vm-cpu-workload-rebalancing-load-aware-descheduler)
- [Load Aware Rebalancing with OpenShift Virtualization](https://developers.redhat.com/blog/2024/12/19/load-aware-rebalancing-openshift-virtualization)
- [Enabling Descheduler Evictions on VMs (OKD 4.21)](https://docs.okd.io/4.21/virt/managing_vms/advanced_vm_management/virt-enabling-descheduler-evictions.html)
- [Descheduler PSI Evaluation Repository](https://github.com/openshift-virtualization/descheduler-psi-evaluation)
- [PSI - Pressure Stall Information (Linux Kernel)](https://docs.kernel.org/accounting/psi.html)
- [Cross-Cluster Live Migration (OKD 4.21)](https://docs.okd.io/4.21/virt/live_migration/virt-enabling-cclm-for-vms.html)
- [What's New in OpenShift Virtualization 4.21](https://redhat.com/en/blog/whats-new-red-hat-openshift-virtualization-421)

**AI Inference: Gateway API Inference Extension & llm-d**
- [Gateway API Inference Extension (Official Docs)](https://gateway-api-inference-extension.sigs.k8s.io/)
- [Gateway API Inference Extension (GitHub)](https://github.com/kubernetes-sigs/gateway-api-inference-extension)
- [Introducing Gateway API Inference Extension (Kubernetes Blog)](https://kubernetes.io/blog/2025/06/05/introducing-gateway-api-inference-extension)
- [Deep Dive into GIE (CNCF)](https://www.cncf.io/blog/2025/04/21/deep-dive-into-the-gateway-api-inference-extension/)
- [OpenShift 4.20: Accelerating Virtualization and AI](https://www.redhat.com/en/blog/red-hat-openshift-42-what-you-need-to-know)
- [Run Model-as-a-Service for Multiple LLMs on OpenShift](https://developers.redhat.com/articles/2026/03/24/run-model-service-multiple-llms-openshift)
- [llm-d (Official Site)](https://llm-d.ai/)
- [llm-d (GitHub)](https://github.com/llm-d/llm-d)
- [Welcome llm-d to the CNCF](https://www.cncf.io/blog/2026/03/24/welcome-llm-d-to-the-cncf-evolving-kubernetes-into-sota-ai-infrastructure/)

**IBM Content-Aware Storage**
- [Content-Aware Storage for the Generative AI Era (IBM Research)](https://www.research.ibm.com/blog/content-aware-storage-generative-ai)
- [IBM Fusion CAS: Making Data Better, Faster and Stronger](https://community.ibm.com/community/user/blogs/shu-mookerjee/2025/04/09/ibm-fusion-content-aware-storage)
- [IBM CAS for RAG AI Workflows (NAND Research)](https://nand-research.com/research-note-ibm-content-aware-storage-for-rag-ai-workflows/)
- [IBM Fusion CAS vs State-of-the-Art RAG Benchmarks](https://community.ibm.com/community/user/blogs/venkata-vamsikrishna-meduri/2026/02/08/evaluating-qa-accuracy-of-ibm-fusion-cas)
- [IBM Fusion for Red Hat AI](https://community.ibm.com/community/user/blogs/matthew-kelm/2026/02/23/unlocking-data-inference-speed-ibmfusionredhatai)
- [Building Enterprise LLMOps on Fusion HCI with OpenShift AI](https://community.ibm.com/community/user/blogs/purnanand-kumar/2026/02/06/building-enterprise-llmops-on-ibm-fusion-hci)

**GPU Scheduling & AI Training**
- [Dynamic Resource Allocation Goes GA in OpenShift 4.21](https://developers.redhat.com/articles/2026/03/25/dynamic-resource-allocation-goes-ga-red-hat-openshift-421-smarter-gpu)
- [AI Workloads (OCP 4.21 Docs)](https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/html-single/ai_workloads/index)
- [Improve GPU Utilization with Kueue in OpenShift AI](https://developers.redhat.com/articles/2025/05/22/improve-gpu-utilization-kueue-openshift-ai)

**Platform Release Notes**
- [OpenShift 4.21 Release Notes](https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/html/release_notes/ocp-4-21-release-notes)
- [OpenShift 4.21: Smarter Scaling, Faster Migration, AI-Powered Efficiency](https://redhat.com/en/blog/red-hat-openshift-421-smarter-scaling-faster-migration-and-ai-powered-efficiency)
- [OpenShift Virtualization 4.21 Release Notes](https://docs.redhat.com/en/documentation/openshift_container_platform/4.21/html/virtualization/release-notes)

### Workshop Infrastructure
- [Showroom Deployer](https://github.com/rhpds/showroom-deployer)
- [Showroom Content Template](https://github.com/rhpds/showroom_template_default)
- [Field-Sourced Content Template](https://github.com/rhpds/field-sourced-content-template)
- [Red Hat Demo Platform](https://demo.redhat.com/)
- [Antora Documentation](https://docs.antora.org/)
- [Operator Lifecycle Manager](https://olm.operatorframework.io/)
