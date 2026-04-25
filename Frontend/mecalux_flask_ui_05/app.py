from __future__ import annotations

import json

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    stream_with_context,
    url_for,
)
from flask_socketio import SocketIO, join_room

from mock_api.case_parser import parse_csv_case, parse_json_case, parse_zip_cases
from services import api_client
from websocket_mock.progress import run_fake_job


app = Flask(__name__)
app.config["SECRET_KEY"] = "hackupc-mecalux-dev"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 3600
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


@app.context_processor
def inject_backend_mode():
    return {
        "backend_mode": "mock" if api_client.using_mock_backend() else "real",
        "backend_url": api_client.BACKEND_URL,
    }


@app.get("/")
def dashboard():
    return render_template("dashboard.html", projects=api_client.list_projects())


@app.post("/projects")
def new_project():
    name = request.form.get("name", "")
    project = api_client.create_project(name)
    return redirect(url_for("editor", project_id=project["id"]))


@app.post("/projects/<project_id>/delete")
def delete_project(project_id: str):
    api_client.delete_project(project_id)
    return redirect(url_for("dashboard"))


@app.post("/projects/upload-case")
def upload_case():
    """Import public challenge-style cases into the local Flask UI store."""

    created = []

    zip_file = request.files.get("case_zip")
    if zip_file and zip_file.filename:
        for name, layout in parse_zip_cases(zip_file):
            created.append(
                api_client.import_project(name, layout, status="uploaded zip")
            )

    json_file = request.files.get("case_json")
    if json_file and json_file.filename:
        name, layout = parse_json_case(json_file)
        created.append(
            api_client.import_project(name, layout, status="uploaded json")
        )

    csv_files = {
        "warehouse.csv": request.files.get("warehouse_csv"),
        "obstacles.csv": request.files.get("obstacles_csv"),
        "ceiling.csv": request.files.get("ceiling_csv"),
        "types_of_bays.csv": request.files.get("types_of_bays_csv"),
    }
    if csv_files["warehouse.csv"] and csv_files["warehouse.csv"].filename:
        name = request.form.get("case_name") or "Uploaded CSV case"
        parsed_name, layout = parse_csv_case(name, csv_files)
        created.append(
            api_client.import_project(parsed_name, layout, status="uploaded csv")
        )

    if created:
        destination = request.form.get("next")
        if destination == "jobs":
            return redirect(url_for("optimization_page", project_id=created[0]["id"]))
        return redirect(url_for("editor", project_id=created[0]["id"]))

    return redirect(url_for("dashboard"))


@app.get("/projects/<project_id>/editor")
def editor(project_id: str):
    layout = api_client.get_layout(project_id)
    if layout is None:
        return "Project not found", 404
    return render_template("editor.html", project_id=project_id, layout=layout)


@app.get("/projects/<project_id>/jobs")
def optimization_page(project_id: str):
    layout = api_client.get_layout(project_id)
    if layout is None:
        return "Project not found", 404
    return render_template("job.html", project_id=project_id, layout=layout)


@app.post("/api/layouts/<project_id>")
def save_layout(project_id: str):
    payload = request.get_json(force=True) or {}
    return jsonify(api_client.save_layout(project_id, payload))


@app.post("/api/jobs")
def api_create_job():
    payload = request.get_json(silent=True) or {}
    project_id = payload.get("project_id")
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400

    layout = payload.get("layout")
    if isinstance(layout, dict):
        api_client.save_layout(str(project_id), layout)

    try:
        job = api_client.create_job(project_id)
    except api_client.ApiClientError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    if api_client.using_mock_backend():
        socketio.start_background_task(run_fake_job, socketio, job["id"])

    return jsonify(job), 201


@app.get("/api/jobs/<job_id>")
def api_get_job(job_id: str):
    try:
        job = api_client.get_job(job_id)
    except api_client.ApiClientError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    if job is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.get("/api/jobs/<job_id>/result")
def api_get_result(job_id: str):
    try:
        result = api_client.get_result(job_id)
    except api_client.ApiClientError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    if result is None:
        return jsonify({"error": "Result not ready"}), 404
    return jsonify(result)


@app.get("/api/jobs/<job_id>/stream")
def api_stream_job(job_id: str):
    if api_client.using_mock_backend():
        return jsonify({"error": "SSE stream is only used in real mode"}), 400

    try:
        backend_stream = api_client.open_job_stream(job_id)
    except api_client.ApiClientError as exc:
        return jsonify({"error": exc.message}), exc.status_code

    @stream_with_context
    def generate():
        try:
            for line in backend_stream.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                raw_payload = line[5:].strip()
                if not raw_payload:
                    continue
                try:
                    payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    yield f"data: {raw_payload}\n\n"
                    continue
                normalized = api_client.normalize_stream_event(job_id, payload)
                yield f"data: {json.dumps(normalized)}\n\n"
        finally:
            backend_stream.close()

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/score")
def api_score():
    payload = request.get_json(force=True) or {}
    layout = _layout_from_payload(payload)
    if layout is None:
        return jsonify({"error": "Layout payload or project_id is required"}), 400

    try:
        result = api_client.score_layout(layout)
    except api_client.ApiClientError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)


@app.post("/api/validate")
def api_validate():
    payload = request.get_json(force=True) or {}
    layout = _layout_from_payload(payload)
    if layout is None:
        return jsonify({"error": "Layout payload or project_id is required"}), 400

    try:
        result = api_client.validate_layout(layout)
    except api_client.ApiClientError as exc:
        return jsonify({"error": exc.message}), exc.status_code
    return jsonify(result)


def _layout_from_payload(payload: dict[str, object]) -> dict[str, object] | None:
    """Resolve the layout used by score and validate bridge endpoints."""

    layout = payload.get("layout")
    if isinstance(layout, dict):
        return layout

    project_id = payload.get("project_id")
    if not project_id:
        return None

    stored = api_client.get_layout(str(project_id))
    if stored is None:
        return None

    if isinstance(payload.get("shelves"), list):
        stored["shelves"] = payload["shelves"]
    if isinstance(payload.get("bayTypes"), list):
        stored["bayTypes"] = payload["bayTypes"]
    return stored


@socketio.on("join_job")
def on_join_job(data):
    job_id = data.get("job_id")
    if not job_id:
        return
    join_room(job_id)
    job = api_client.get_job(job_id)
    if job:
        socketio.emit("job_update", job, room=job_id)


if __name__ == "__main__":
    socketio.run(
        app,
        debug=True,
        host="0.0.0.0",
        port=5000,
        allow_unsafe_werkzeug=True,
    )
