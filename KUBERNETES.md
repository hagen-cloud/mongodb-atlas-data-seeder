# Kubernetes execution

Last reviewed: 2026-10-07.

## Objective and prerequisites

Run the seeder as a parallel Indexed Job on a Kubernetes cluster supporting Indexed Jobs. The supplied manifests use a ConfigMap and an existing Kubernetes Secret; no specific managed Kubernetes product or secret manager is required.

Before applying, verify cluster access, non-production database authorization, network/DNS reachability, image availability, connection and storage budgets, and run cleanup ownership. Decide how your environment provisions the URI Secret and, if necessary, image pull credentials. The existing node selector and toleration require nodes prepared for the generic `workload=data-seeder` label/taint; configure these for your environment.

## Supplied manifests

| File | Purpose |
|---|---|
| `k8s/configmap.example.yaml` | Embedded config and bulk template mounted under `/etc/seeder`. |
| `k8s/secret.example.yaml` | URI shape only; never apply it as a working credential. |
| `k8s/job.yaml` | Indexed Job with explicit resource limits and container security settings. |

Namespace, ResourceQuota, LimitRange, NetworkPolicy, secret-store integration, and node-pool provisioning are not supplied. Prepare the applicable controls through your platform before running this high-volume workload. They must not be assumed from this guide.

## Prepare local deployment inputs

1. Copy `k8s/job.yaml` to ignored `k8s/local-job.yaml` and replace the deliberately invalid registry image with the immutable image you built.
2. Copy `k8s/configmap.example.yaml` to ignored `k8s/local-configmap.yaml` and review target volume and concurrency. The supplied example retains a 3TB target and five worker processes per pod; the Job retains five pods and six CPUs per pod. Scale down for a small test.
3. Keep Job `completions`, `parallelism`, and `SEEDER_SHARD_TOTAL` equal. `JOB_COMPLETION_INDEX` is supplied by Kubernetes.
4. Provision namespace `mongo-seeder` if needed and a Secret named `mongo-seeder-uri` with key `uri`, using your approved secret source. The Job consumes it through `secretKeyRef`.

If a local Secret manifest is necessary, use ignored `k8s/secret.yaml`, apply it privately, and remove the local credential file when no longer needed. Kubernetes Secret values are not confidential merely because the object is a Secret; apply platform access and encryption controls. Do not paste the URI into shell command arguments or publish resolved manifests.

## Apply and observe

After the prerequisites are satisfied:

```bash
kubectl apply -f k8s/local-configmap.yaml
kubectl apply -f k8s/local-job.yaml
kubectl -n mongo-seeder get job mongo-seeder
kubectl -n mongo-seeder get pods
kubectl -n mongo-seeder logs -f job/mongo-seeder --all-containers --prefix
```

Expected lifecycle: startup, periodic measurements, target reached, and final size. Observe database and node health separately. If monitoring stops reporting or the target is wrong, terminate the Job; the existing monitor does not signal writers on an unhandled measurement failure.

The Job retains a 24-hour deadline, one-hour TTL after completion, retry/backoff, non-root UID, read-only root filesystem, dropped capabilities, and writable `/tmp`. CPU limits still apply even when requests equal limits. These settings do not guarantee isolation from other workloads without the platform controls you provision.

## Validation and recovery

Validate config and templates with the CLI dry-run before deployment. Unit tests parse the embedded ConfigMap and check shard dimensions; they do not certify Kubernetes scheduling, network policies, secrets, or admission compatibility. No real Kubernetes deployment is required for repository verification.

To stop only this test:

```bash
kubectl -n mongo-seeder delete job mongo-seeder
```

Delete only the test ConfigMap/Secret you created when no longer required. Remove the namespace only if it was created solely for this disposable test and contains no other workload. Removing the Job or namespace does not remove data already written to MongoDB; verify and clean up only the test databases separately.

## References

- [Indexed parallel processing](https://kubernetes.io/docs/tasks/job/indexed-parallel-processing-static/)
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Resource management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
