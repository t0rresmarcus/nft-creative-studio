import io
import json
import zipfile

from PIL import Image


def test_projects_are_private(client):
    owner = client.post("/api/auth/register", json={"name": "Ada", "email": "ada@example.com", "password": "studio-pass"}).json()
    other = client.post("/api/auth/register", json={"name": "Bea", "email": "bea@example.com", "password": "studio-pass"}).json()
    created = client.post(
        "/api/projects",
        headers={"Authorization": f"Bearer {owner['token']}"},
        json={"name": "Private", "project_type": "photo", "canvas_width": 128, "canvas_height": 128},
    )
    assert created.status_code == 200, created.text
    project_id = created.json()["id"]
    hidden = client.get(f"/api/projects/{project_id}", headers={"Authorization": f"Bearer {other['token']}"})
    assert hidden.status_code == 404


def test_collection_plan_render_and_zip(client):
    registered = client.post("/api/auth/register", json={"name": "Ada", "email": "ada2@example.com", "password": "studio-pass"}).json()
    headers = {"Authorization": f"Bearer {registered['token']}"}
    project = client.post(
        "/api/projects",
        headers=headers,
        json={"name": "Drop", "project_type": "generative", "canvas_width": 96, "canvas_height": 96, "license": "cc0"},
    ).json()
    sample = client.post(f"/api/projects/{project['id']}/traits/sample", headers=headers)
    assert sample.status_code == 200, sample.text
    assert len(sample.json()["categories"]) == 4
    collection = client.post(
        f"/api/projects/{project['id']}/collections",
        headers=headers,
        json={"name": "Signal", "supply": 6, "seed": 4, "mode": "weighted", "symbol": "SIG"},
    ).json()
    planned = client.post(f"/api/collections/{collection['id']}/plan", headers=headers)
    assert planned.status_code == 200, planned.text
    assert planned.json()["report"]["unique"] == 6
    rendered = client.post(f"/api/collections/{collection['id']}/render", headers=headers)
    assert rendered.status_code == 200, rendered.text
    assert rendered.json()["status"] == "succeeded", rendered.json()
    detail = client.get(f"/api/collections/{collection['id']}", headers=headers).json()
    assert all(item["image_url"] for item in detail["items"])
    assert detail["items"][0]["metadata"]["name"] == "Signal #1"
    exported = client.post(f"/api/collections/{collection['id']}/export", headers=headers)
    assert exported.status_code == 200, exported.text
    archive = zipfile.ZipFile(io.BytesIO(exported.content))
    names = set(archive.namelist())
    assert "images/1.png" in names
    assert "metadata/1.json" in names
    assert "metadata.csv" in names
    assert "provenance.json" in names
    metadata = json.loads(archive.read("metadata/1.json"))
    assert metadata["attributes"]
    report = client.get(f"/api/collections/{collection['id']}/report", headers=headers).json()
    assert report["status"] == "pass"


def test_editor_saves_a_new_version(client):
    registered = client.post("/api/auth/register", json={"name": "Ada", "email": "ada3@example.com", "password": "studio-pass"}).json()
    headers = {"Authorization": f"Bearer {registered['token']}"}
    project = client.post("/api/projects", headers=headers, json={"name": "Edits", "canvas_width": 64, "canvas_height": 64}).json()
    image = Image.new("RGB", (32, 24), (180, 40, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    uploaded = client.post(
        f"/api/projects/{project['id']}/assets",
        headers=headers,
        files=[("files", ("portrait.png", buffer.getvalue(), "image/png"))],
    )
    assert uploaded.status_code == 200, uploaded.text
    asset_id = uploaded.json()[0]["id"]
    rendered = client.post(
        f"/api/assets/{asset_id}/render",
        headers=headers,
        json={"operations": [{"type": "resize", "params": {"width": 16, "height": 16, "fit": "cover"}}, {"type": "brightness", "params": {"factor": 1.2}}]},
    )
    assert rendered.status_code == 200, rendered.text
    assert rendered.json()["width"] == 16
    history = client.get(f"/api/assets/{asset_id}/history", headers=headers).json()
    assert history["versions"]


def test_batch_resize_is_reproducible(client):
    registered = client.post("/api/auth/register", json={"name": "Ada", "email": "ada4@example.com", "password": "studio-pass"}).json()
    headers = {"Authorization": f"Bearer {registered['token']}"}
    project = client.post("/api/projects", headers=headers, json={"name": "Batch", "canvas_width": 64, "canvas_height": 64}).json()
    image = Image.new("RGB", (40, 40), (10, 20, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    uploaded = client.post(
        f"/api/projects/{project['id']}/assets",
        headers=headers,
        files=[("files", ("shot.png", buffer.getvalue(), "image/png"))],
    ).json()
    workflow = client.post(
        f"/api/projects/{project['id']}/workflows",
        headers=headers,
        json={
            "name": "Square",
            "operations": [
                {"type": "resize", "params": {"width": 24, "height": 24, "fit": "exact"}},
                {"type": "rename", "params": {"pattern": "{project}-{index}"}},
            ],
        },
    ).json()
    job = client.post(f"/api/workflows/{workflow['id']}/run", headers=headers, json={"asset_ids": [uploaded[0]["id"]], "seed": 9, "dry_run": True})
    assert job.status_code == 200, job.text
    assert job.json()["status"] == "succeeded"
    assert job.json()["result"]["outputs"][0]["name"].endswith(".png")
