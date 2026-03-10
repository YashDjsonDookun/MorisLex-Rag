# MORISLEX-RAG — Problems and Fixes

**Obsidian:** **01 - Projects/MorisLex Rag**. Index: [[index]]. Engine: [[01 - Projects/MorisLex Engine/problems-and-fixes|Engine problems and fixes]].

Record of issues encountered in deployment and operations, and how they were fixed.

---

## 1. Ollama: "client connection closed before server finished loading" / 499

**Symptom:** Ollama logs show model loading (e.g. `load_tensors: CPU model buffer size = 1834.82 MiB`), then `"client connection closed before server finished loading, aborting load"` and `Load failed ... context canceled`. A request to `POST /v1/chat/completions` returns **499** after ~7s.

**Cause:** The first request to Ollama triggers model load (1–3 min on CPU). The client that triggered the load had a short read timeout (~7s). When it closed the connection, Ollama aborted the load. The client was either (1) the deploy warm-up using `ollama run` (CLI has short timeout) or (2) the retrieval pod calling Ollama with a timeout that was not applied as a long **read** timeout.

**Fixes applied:**

- **Warm-up:** No longer use `kubectl exec ... ollama run`. Warm-up now uses a **temporary port-forward** from the deploy host and **curl** with `--max-time 600` to `POST /v1/chat/completions`, so the connection stays open for the whole first load.
- **Retrieval → Ollama client:** In `app/llm/client_ollama.py`, use **`httpx.Timeout(600.0, connect=60.0)`** and pass it to the OpenAI client so the **read** timeout is 600s. This prevents the retrieval pod from closing the connection while the model is loading.

**References:** `deploy.sh` (`warm_up_ollama_in_cluster`), `app/llm/client_ollama.py`.

---

## 2. Retrieval pod: CrashLoopBackOff (exit code 1)

**Symptom:** Retrieval pod restarts repeatedly; `kubectl describe pod` shows `State: Waiting, Reason: CrashLoopBackOff`, `Last State: Terminated, Reason: Error, Exit Code: 1`. No logs or immediate crash after start.

**Cause:** **Uvicorn with `workers=2`** was enabled so one worker could serve `/health` while the other was blocked on a long Ollama request. With multiple workers, uvicorn **forks** the process. In the container (Rancher Desktop / Lima), **sentence-transformers** and **Chroma** (or other ML/vector libs) are not always fork-safe; the child process can crash on startup (exit 1). Works locally (single process or different fork behaviour).

**Fix:** Reverted to **single worker** in `app/services/retrieval_service.py`. Kept the more tolerant **probes** (longer `timeoutSeconds`, higher `failureThreshold`) so the single worker is not restarted too aggressively when blocked on Ollama.

**References:** `app/services/retrieval_service.py`, `k8s/base/retrieval-deployment.yaml`.

---

## 3. Retrieval pod: "often disconnects" / liveness restarts

**Symptom:** Retrieval pod restarts or becomes NotReady during long Chat requests; user sees connection errors or "pod may be restarting".

**Cause:** Single uvicorn worker blocked on a long Ollama request (1–3 min). **Liveness probe** (`GET /health`) could not get a response in time (default 1s timeout), so Kubernetes restarted the pod.

**Fixes applied:**

- **Liveness:** `timeoutSeconds: 10`, `failureThreshold: 6`, `initialDelaySeconds: 15` so the pod is not killed on a few slow health checks.
- **Readiness:** `timeoutSeconds: 5`, `failureThreshold: 3`.
- **terminationGracePeriodSeconds: 25** so the old replica exits faster during rollout.

**References:** `k8s/base/retrieval-deployment.yaml`.

---

## 4. Retrieval rollout: "1 old replicas are pending termination" / timeout

**Symptom:** `kubectl rollout status deployment/morislex-rag-retrieval` times out; message says "1 old replicas are pending termination".

**Cause:** New retrieval pod was Ready, but the **old** pod took a long time to terminate (default 30s grace). Deploy script only waited 120s for the full rollout, so it often hit the timeout.

**Fixes applied:**

- **Retrieval rollout timeout** in `deploy.sh` increased from 120s to **180s**.
- **terminationGracePeriodSeconds: 25** on the retrieval pod so the old pod is killed sooner if it does not exit cleanly.
- Timeout message updated to suggest `kubectl describe pod` for diagnostics.

**References:** `deploy.sh`, `k8s/base/retrieval-deployment.yaml`.

---

## 5. Ollama pod: Pending (never scheduled)

**Symptom:** `kubectl get pods -n morislex-rag -l component=ollama` shows `0/1 Pending`. `kubectl logs` shows nothing (no container running).

**Cause:** **Insufficient resources** on the node. Ollama had `requests.memory: 4Gi`; on Rancher Desktop with 4–6Gi total for the VM, the scheduler could not place the pod.

**Fixes applied:**

- **Ollama resources** in `k8s/base/ollama-deployment.yaml`: `requests.memory: 2Gi`, `limits.memory: 6Gi` so the pod can schedule on smaller nodes. qwen2.5:3b still fits; if the node has more RAM and you see OOM, increase again.
- **Deploy warning** when Ollama rollout times out: instruct user to run `kubectl describe pod -n morislex-rag -l component=ollama` and check **Events** (e.g. "Insufficient memory").

**References:** `k8s/base/ollama-deployment.yaml`, `deploy.sh`.

---

## 6. How to access the Streamlit UI after deploy

**Symptom:** User is unsure how to open the app after `./deploy.sh`.

**Answer:**

- If the deploy script is **still running**: open **http://localhost:8502** (it holds the port-forward).
- If the script was **stopped**: run `kubectl port-forward -n morislex-rag svc/morislex-rag-ui 8502:8502` and open http://localhost:8502.
- If a **LoadBalancer** is used: use the URL printed by deploy (e.g. http://192.168.64.2:8502).

**References:** [[ARCHITECTURE-RAG]], [[DEPLOYMENT-RUNBOOK]], `deploy.sh`.

---

## 7. Checklist for future similar issues

- **Pod Pending** → `kubectl describe pod ...` and read **Events** (scheduling, PVC, resources).
- **Pod CrashLoopBackOff** → `kubectl logs ... --tail=100` or `--previous` for the exception/traceback.
- **Ollama 499 / load aborted** → Ensure client (retrieval or warm-up) uses a **long read timeout** (e.g. 600s) and does not close the connection during model load.
- **Retrieval restarts under load** → Keep **single worker**; rely on **probe tuning** (timeoutSeconds, failureThreshold) so long Ollama requests do not cause liveness failure.
