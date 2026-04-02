# AgnosticD v2 Deployment

Deploy the IBM Storage Fusion & ODF Workshop using AgnosticD v2.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| RHDP environment | Order [OpenShift Container Platform with IBM Fusion](https://catalog.demo.redhat.com/catalog?item=babylon-catalog-prod/sandboxes-gpte.ocp4-demo-ibm-fusion.prod) from the Red Hat Demo Platform |
| AgnosticD v2 | Cloned and set up per the [AgnosticD v2 Setup Guide](https://github.com/agnosticd/agnosticd-v2/blob/main/docs/setup.adoc) |
| ArgoCD | OpenShift GitOps operator installed (included in the RHDP environment) |
| OpenAI key | API key for OpenShift Lightspeed (Module 4) |

## Quick Start

### 1. Set up AgnosticD v2 (one-time)

Follow the [AgnosticD v2 Setup Guide](https://github.com/agnosticd/agnosticd-v2/blob/main/docs/setup.adoc) to clone the repo and run `./bin/agd setup`.

### 2. Copy the vars file

```bash
cp agnosticd/vars/ibm-fusion-workshop.yml ~/Development/agnosticd-v2-vars/
```

### 3. Create the OpenAI API key secret

Before deploying (or after the `openshift-lightspeed` namespace exists):

```bash
oc create namespace openshift-lightspeed 2>/dev/null || true
oc create secret generic openai-api-key \
  -n openshift-lightspeed \
  --from-literal=api-key='<YOUR_OPENAI_API_KEY>'
```

### 4. Deploy

Replace `sandbox1234` with your RHDP sandbox account number:

```bash
cd ~/Development/agnosticd-v2
./bin/agd provision -g myfusion -c ibm-fusion-workshop -a sandbox1234
```

This provisions the base OCP cluster and runs the `ocp4_workload_field_content`
workload, which creates an ArgoCD Application pointing to this repository.
ArgoCD then deploys all components:

- Machineset, RHACM (sync-wave 0)
- Workshop infrastructure, DCS, Lightspeed (sync-wave 1)
- DCS setup, Showroom lab guides per user (sync-wave 2)

### 5. Verify

```bash
oc get applications -n openshift-gitops
oc get pods -n ibm-data-cataloging
oc get csv -n openshift-lightspeed

# Check showroom for user1
oc get route -n showroom-user1
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
