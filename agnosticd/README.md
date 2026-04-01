# AgnosticD v2 Deployment

Deploy the IBM Storage Fusion & ODF Workshop using AgnosticD v2.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| AgnosticD v2 | Cloned and set up (`agd setup`) |
| Base cluster | OCP 4.18+ with IBM Storage Fusion 2.12+ and ODF |
| ArgoCD | OpenShift GitOps operator installed |
| OpenAI key | API key for OpenShift Lightspeed (Module 4) |

## Quick Start

### 1. Copy the vars file

```bash
cp agnosticd/vars/ibm-fusion-workshop.yml ~/Development/agnosticd-v2-vars/
```

### 2. Create the OpenAI API key secret

Before deploying (or after the `openshift-lightspeed` namespace exists):

```bash
oc create namespace openshift-lightspeed 2>/dev/null || true
oc create secret generic openai-api-key \
  -n openshift-lightspeed \
  --from-literal=api-key='<YOUR_OPENAI_API_KEY>'
```

### 3. Deploy

```bash
cd ~/Development/agnosticd-v2
./bin/agd provision -g myfusion -c ibm-fusion-workshop -a sandbox1234
```

This provisions the base OCP cluster and runs the `ocp4_workload_field_content`
workload, which creates an ArgoCD Application pointing to this repository.
ArgoCD then deploys all components:

- RHACM (sync-wave 0)
- Workshop infrastructure, DCS, Lightspeed (sync-wave 1)
- Showroom lab guides per user (sync-wave 2)

### 4. Verify

```bash
oc get applications -n openshift-gitops
oc get pods -n ibm-data-cataloging
oc get csv -n openshift-lightspeed
```

## Manual Deployment (without AgnosticD)

If you already have a cluster, deploy directly with Helm:

```bash
git clone https://github.com/Red-Hat-SE-RTO/ibm-fusion-workshop.git
cd ibm-fusion-workshop

# Edit values.yaml for your cluster
vim values.yaml

# Create the OpenAI API key secret
oc create namespace openshift-lightspeed 2>/dev/null || true
oc create secret generic openai-api-key \
  -n openshift-lightspeed \
  --from-literal=api-key='<YOUR_OPENAI_API_KEY>'

# Deploy via ArgoCD
helm template workshop . | oc apply -f -
```

## Variable Mapping

| Helm Value | AgnosticD Variable | Description |
|------------|-------------------|-------------|
| `components.showroom.content.repoUrl` | `ocp4_workload_field_content_gitops_repo_url` | Workshop git repo |
| `components.showroom.content.repoRef` | `ocp4_workload_field_content_gitops_repo_ref` | Git branch/tag |
| `deployer.domain` | `cluster_domain` (auto-injected) | Cluster apps domain |

## Disabling Components

Set any component to `enabled: false` in `values.yaml` to skip it:

```yaml
components:
  dcs:
    enabled: false      # Skip DCS if Fusion < 2.12
  lightspeed:
    enabled: false      # Skip Lightspeed if no API key
```
