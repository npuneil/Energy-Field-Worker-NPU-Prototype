"""
Zava Energy – On-Device AI for Field Operations
================================================
A Flask application showcasing on-device AI capabilities using
Microsoft Foundry Local on Copilot+ PCs with NPU acceleration.

Tabs:
  1. Field Inspection AI  – Upload field photos, get AI hazard/condition assessment
  2. Operations Assistant – Chat about safety procedures, regulations, field ops
  3. Document Analyzer    – Paste/upload permits, inspection reports, SOPs for AI analysis
  4. NPU Dashboard        – Live NPU status, cost savings, offline proof
"""

import os
import sys
import json
import time
import uuid
import base64
import subprocess
import traceback
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

from flask import (
    Flask, render_template, request, jsonify, send_from_directory
)
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# Foundry Local bootstrap  (NPU pre-loaded via HTTP, CPU via HTTP fallback)
# ---------------------------------------------------------------------------
foundry_ok = False
model_id = None
foundry_service_url = None       # e.g. "http://127.0.0.1:51902"
npu_alias = None                 # CLI alias for NPU inference, e.g. "phi-3.5-mini"
use_npu = False                  # True when NPU model is available

# NPU aliases to try – first cached match wins
# qwen2.5-1.5b is preferred: its NPU variant works via HTTP after pre-loading.
# phi-3.5-mini crashes the Foundry HTTP service on NPU inference.
NPU_ALIAS_PREFERENCE = [
    "qwen2.5-1.5b",
    "phi-3-mini-4k",
    "phi-3-mini-128k",
    "qwen2.5-7b",
]

# CPU model IDs to try via HTTP – first match wins
CPU_MODEL_PREFERENCE = [
    "Phi-4-mini-instruct-generic-cpu",
    "Phi-3.5-mini-instruct-generic-cpu",
    "qwen2.5-0.5b-instruct-generic-cpu",
]


def _discover_foundry_port() -> str | None:
    """Parse `foundry service status` to get the running service URL."""
    try:
        result = subprocess.run(
            ["foundry", "service", "status"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            if "http://" in line:
                import re
                m = re.search(r"(https?://[\d.]+:\d+)", line)
                if m:
                    return m.group(1)
    except Exception as exc:
        print(f"[STARTUP] foundry CLI not available: {exc}")
    return None


def _detect_npu_alias() -> str | None:
    """Find the best cached NPU model alias via `foundry model list`."""
    try:
        result = subprocess.run(
            ["foundry", "model", "list"],
            capture_output=True, text=True, timeout=15,
        )
        # Parse lines that contain 'NPU' to find cached NPU model aliases
        npu_aliases = set()
        current_alias = None
        for line in result.stdout.splitlines():
            parts = line.split()
            if not parts:
                continue
            # Lines starting with an alias look like:
            # "phi-3.5-mini    NPU    chat    2.78 GB    MIT    phi-3.5-mini-instruct-qnn-npu:2"
            # Continuation lines (same alias, different device) look like:
            # "                CPU    chat    2.53 GB    ..."
            if parts[0] and not parts[0].startswith("-") and not parts[0].startswith("Alias"):
                # First token might be an alias or a device specifier
                if parts[0] in ("CPU", "NPU", "GPU", "Auto"):
                    # continuation line for current_alias
                    if parts[0] == "NPU" and current_alias:
                        npu_aliases.add(current_alias)
                else:
                    current_alias = parts[0]
                    if len(parts) > 1 and parts[1] == "NPU":
                        npu_aliases.add(current_alias)

        for pref in NPU_ALIAS_PREFERENCE:
            if pref in npu_aliases:
                return pref
        # Return any NPU alias if none matched preference
        return next(iter(npu_aliases), None)
    except Exception as exc:
        print(f"[STARTUP] Could not detect NPU models: {exc}")
        return None


def _foundry_get(path: str, timeout: int = 10):
    """GET helper returning parsed JSON, or None on failure."""
    try:
        resp = urllib.request.urlopen(f"{foundry_service_url}{path}", timeout=timeout)
        return json.loads(resp.read())
    except Exception:
        return None


def _foundry_post(path: str, body: dict, timeout: int = 120):
    """POST helper returning parsed JSON, or None on failure."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{foundry_service_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())


def init_foundry():
    """Discover running Foundry Local service – prefer NPU (pre-loaded via HTTP), fall back to CPU."""
    global foundry_ok, model_id, foundry_service_url, npu_alias, use_npu

    foundry_ok = False
    model_id = None
    foundry_service_url = None
    npu_alias = None
    use_npu = False

    # --- 1. Ensure Foundry HTTP service is running ---------------------------
    service_url = _discover_foundry_port()
    if not service_url:
        try:
            subprocess.run(["foundry", "service", "start"],
                           capture_output=True, text=True, timeout=30)
            service_url = _discover_foundry_port()
        except Exception:
            pass

    if not service_url:
        print("[STARTUP] Foundry Local service not running. UI-preview mode.")
        return

    foundry_service_url = service_url
    print(f"[STARTUP] Foundry Local HTTP service at {service_url}")

    # --- 2. Check if an NPU model is already available in the HTTP service ----
    models_data = _foundry_get("/v1/models")
    if models_data and "data" in models_data:
        available_ids = [m["id"] for m in models_data["data"]]
        print(f"[STARTUP] Available HTTP models: {available_ids}")
        npu_ids = [mid for mid in available_ids
                   if "npu" in mid.lower() or "qnn" in mid.lower()]

        # Pick best NPU model matching our preference order
        for pref in NPU_ALIAS_PREFERENCE:
            pref_clean = pref.replace("-", "")
            for mid in npu_ids:
                if pref_clean in mid.replace("-", "").lower():
                    model_id = mid
                    npu_alias = pref
                    break
            if model_id:
                break

        if model_id:
            use_npu = True
            foundry_ok = True
            print(f"[STARTUP] NPU model already in service: {model_id}")
            print(f"[STARTUP] Running on: NPU (QNN) via HTTP service")
            return

    # --- 3. Try to pre-load an NPU model into the service --------------------
    detected = _detect_npu_alias()
    if detected:
        print(f"[STARTUP] Pre-loading NPU model '{detected}' via foundry model load ...")
        try:
            result = subprocess.run(
                ["foundry", "model", "load", detected, "--device", "NPU"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                import time as _time
                _time.sleep(2)
                models_data = _foundry_get("/v1/models")
                if models_data and "data" in models_data:
                    npu_ids = [m["id"] for m in models_data["data"]
                               if "npu" in m["id"].lower() or "qnn" in m["id"].lower()]
                    best = None
                    for mid in npu_ids:
                        if detected.replace("-", "") in mid.replace("-", "").lower():
                            best = mid
                            break
                    if not best and npu_ids:
                        best = npu_ids[0]
                    if best:
                        model_id = best
                        npu_alias = detected
                        use_npu = True
                        foundry_ok = True
                        print(f"[STARTUP] NPU model ready via HTTP: {model_id}")
                        return
            else:
                print(f"[STARTUP] foundry model load failed (rc={result.returncode}): {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print("[STARTUP] foundry model load timed out (120s)")
        except Exception as exc:
            print(f"[STARTUP] foundry model load error: {exc}")

    # --- 4. Fall back to CPU via HTTP service ---------------------------------
    models_data = _foundry_get("/v1/models")
    if not models_data or "data" not in models_data:
        print("[STARTUP] Could not list models. UI-preview mode.")
        foundry_service_url = None
        return

    available_ids = [m["id"] for m in models_data["data"]]

    for pref in CPU_MODEL_PREFERENCE:
        pref_lower = pref.lower()
        for mid in available_ids:
            if mid.lower().startswith(pref_lower):
                model_id = mid
                break
        if model_id:
            break

    if not model_id and available_ids:
        cpu_models = [m for m in available_ids if "cpu" in m.lower()]
        model_id = cpu_models[0] if cpu_models else available_ids[0]

    if not model_id:
        print("[STARTUP] No models available. UI-preview mode.")
        foundry_service_url = None
        return

    foundry_ok = True
    print(f"[STARTUP] Selected CPU model: {model_id}")
    print(f"[STARTUP] Running on: CPU (HTTP service)")

init_foundry()

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
inference_log: list[dict] = []

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _run_inference(system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> dict:
    """Run a chat completion via Foundry HTTP service (NPU or CPU). Log metrics."""
    global foundry_service_url, model_id
    if not foundry_ok or not foundry_service_url or not model_id:
        return {
            "text": "[Demo mode – Foundry Local not connected. Install & start Foundry Local to enable on-device AI.]",
            "tokens": 0,
            "latency_ms": 0,
            "cloud_cost_saved": "$0.00",
        }

    body = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
    }

    hardware = "NPU" if use_npu else "CPU"
    t0 = time.perf_counter()
    try:
        result = _foundry_post("/v1/chat/completions", body, timeout=120)
    except Exception as exc:
        print(f"[INFERENCE] HTTP call failed ({hardware}): {exc}")
        return {
            "text": f"[Error: Could not reach Foundry Local – {exc}]",
            "tokens": 0, "latency_ms": 0, "cloud_cost_saved": "$0.00",
        }

    elapsed_ms = round((time.perf_counter() - t0) * 1000)

    # Extract response text
    text = ""
    choices = result.get("choices", [])
    if choices:
        choice = choices[0]
        msg = choice.get("message") or choice.get("delta") or {}
        text = msg.get("content", "")

    usage = result.get("usage") or {}
    total_tokens = usage.get("total_tokens", 0)
    if not total_tokens:
        total_tokens = _estimate_tokens(system_prompt + user_prompt) + _estimate_tokens(text)

    est_cost = round(total_tokens * 0.00001, 6)

    entry = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.now().isoformat(),
        "tokens": total_tokens,
        "latency_ms": elapsed_ms,
        "cloud_cost_saved": f"${est_cost:.4f}",
        "hardware": hardware,
    }
    inference_log.append(entry)

    return {
        "text": text,
        "tokens": total_tokens,
        "latency_ms": elapsed_ms,
        "cloud_cost_saved": f"${est_cost:.4f}",
        "hardware": hardware,
    }

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify({
        "foundry_connected": foundry_ok,
        "model": model_id or "N/A",
        "endpoint": foundry_service_url or ("Foundry CLI (in-process)" if use_npu else "N/A"),
        "mode": "on-device NPU" if use_npu else ("on-device CPU" if foundry_ok else "UI preview (no AI)"),
        "hardware": "NPU (QNN)" if use_npu else ("CPU" if foundry_ok else "none"),
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Operations Assistant – energy field operations chat."""
    data = request.get_json(force=True)
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    system = (
        "You are Zava Energy's AI field operations assistant. Be concise and professional. "
        "Answer questions about pipeline safety, facility inspections, regulatory compliance, "
        "field procedures, equipment maintenance, environmental protocols, and energy operations. "
        "Reference relevant safety standards (CSA Z662, OPR-99, AER directives) where appropriate."
    )
    result = _run_inference(system, user_msg, max_tokens=256)
    return jsonify(result)


@app.route("/api/assess-inspection", methods=["POST"])
def api_assess_inspection():
    """Field Inspection AI – analyse field condition report."""
    data = request.get_json(force=True)
    description = data.get("description", "").strip()
    inspection_type = data.get("inspection_type", "pipeline")

    if not description:
        return jsonify({"error": "No field description provided"}), 400

    system = (
        "You are a Zava Energy field inspection analyst specializing in energy infrastructure. "
        "Assess this field inspection report. Reply with: "
        "Risk Level (Low/Medium/High/Critical), Recommended Action, "
        "2 Immediate Next Steps, Regulatory Consideration, "
        "Priority (Routine/Scheduled/Urgent/Emergency). Be brief and actionable."
    )
    desc_truncated = description[:600]
    user_prompt = f"{inspection_type} inspection: {desc_truncated}"
    result = _run_inference(system, user_prompt, max_tokens=350)
    return jsonify(result)


@app.route("/api/analyze-document", methods=["POST"])
def api_analyze_document():
    """Document Analyzer – summarise/extract from pasted text."""
    data = request.get_json(force=True)
    doc_text = data.get("text", "").strip()
    task = data.get("task", "summarize")

    if not doc_text:
        return jsonify({"error": "No document text provided"}), 400

    task_prompts = {
        "summarize": (
            "Summarize this energy operations document in 3-5 bullet points. "
            "Focus on: safety requirements, operational limits, compliance deadlines, key actions."
        ),
        "extract": (
            "Extract key data: permit number, facility/pipeline ID, operator, "
            "dates, pressure limits, flow rates, inspection intervals, conditions. "
            "Return as a structured list."
        ),
        "review": (
            "Review this energy operations document for potential issues: safety gaps, "
            "regulatory non-compliance, missing inspections, environmental concerns, "
            "or items requiring immediate field action. Provide a brief risk assessment."
        ),
    }

    system = "Zava Energy operations document analyst. " + task_prompts.get(task, task_prompts["summarize"])
    doc_truncated = doc_text[:1500]
    result = _run_inference(system, doc_truncated, max_tokens=350)
    return jsonify(result)


@app.route("/api/metrics")
def api_metrics():
    total_tokens = sum(e["tokens"] for e in inference_log)
    total_cost = sum(float(e["cloud_cost_saved"].replace("$", "")) for e in inference_log)
    avg_latency = (
        round(sum(e["latency_ms"] for e in inference_log) / len(inference_log))
        if inference_log else 0
    )
    return jsonify({
        "total_inferences": len(inference_log),
        "total_tokens": total_tokens,
        "total_cloud_cost_saved": f"${total_cost:.4f}",
        "avg_latency_ms": avg_latency,
        "log": inference_log[-20:],
    })


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)


@app.route("/api/upload-image", methods=["POST"])
def upload_image():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "Empty file"}), 400
    if not _allowed_file(f.filename):
        return jsonify({"error": "File type not allowed"}), 400

    fname = secure_filename(f"{uuid.uuid4().hex[:8]}_{f.filename}")
    f.save(str(UPLOAD_DIR / fname))
    return jsonify({"filename": fname, "url": f"/uploads/{fname}"})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Zava Energy – On-Device AI for Field Operations")
    print("  Powered by Microsoft Surface + Foundry Local")
    print("=" * 60)
    print(f"  Model loading may take a moment on first run...")
    print(f"  Once ready, open \u2192 http://localhost:5000\n")
    app.run(host="127.0.0.1", port=5000, debug=False)
