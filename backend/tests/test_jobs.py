from api import jobs as jobs_api
from models.database import DiagnosticsRun, JobCenterDismissal, KnowledgeSource


def test_admin_can_restart_failed_source_and_keep_job_visible(client, db_session, test_project, test_team, monkeypatch):
    source = KnowledgeSource(
        name="Restartable source",
        type="Git",
        project_id=test_project,
        team_id=test_team,
        sync_status="error",
        progress=42,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    sent_tasks = []
    monkeypatch.setattr(
        jobs_api.celery_app,
        "send_task",
        lambda *args, **kwargs: sent_tasks.append((args, kwargs)),
    )

    response = client.post(f"/jobs/source/{source.id}/start")

    assert response.status_code == 200
    db_session.refresh(source)
    assert source.sync_status == "pending"
    assert source.progress == 0
    assert sent_tasks == [(("process_knowledge_source",), {"args": [source.id], "kwargs": {"trace_id": "-"}})]

    listed = client.get("/jobs")
    assert listed.status_code == 200
    listed_source = next(job for job in listed.json()["jobs"] if job["key"] == f"source:{source.id}")
    assert listed_source["status"] == "pending"
    assert listed_source["can_start"] is False
    db_session.delete(source)
    db_session.commit()


def test_non_admin_cannot_start_job(member_client):
    response = member_client.post("/jobs/source/999999/start")

    assert response.status_code == 403


def test_admin_can_restart_failed_diagnostics_run(client, db_session, monkeypatch):
    run = DiagnosticsRun(status="failed")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    sent_tasks = []
    monkeypatch.setattr(
        jobs_api.celery_app,
        "send_task",
        lambda *args, **kwargs: sent_tasks.append((args, kwargs)),
    )

    response = client.post(f"/jobs/diagnostics/{run.id}/start")

    assert response.status_code == 200
    created = db_session.query(DiagnosticsRun).order_by(DiagnosticsRun.id.desc()).first()
    assert created.id != run.id
    assert created.status == "pending"
    assert sent_tasks == [(("generate_diagnostics_bundle",), {"args": [created.id], "kwargs": {"trace_id": "-"}})]
    db_session.delete(created)
    db_session.delete(run)
    db_session.commit()


def test_admin_can_remove_completed_source_job_without_deleting_source(client, db_session, test_project, test_team):
    source = KnowledgeSource(
        name="Dismissable source",
        type="Git",
        project_id=test_project,
        team_id=test_team,
        sync_status="completed",
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    response = client.delete(f"/jobs/source/{source.id}")

    assert response.status_code == 200
    assert db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).first() is not None
    listed = client.get("/jobs")
    assert all(job["key"] != f"source:{source.id}" for job in listed.json()["jobs"])
    db_session.query(JobCenterDismissal).filter(
        JobCenterDismissal.kind == "source",
        JobCenterDismissal.job_id == source.id,
    ).delete(synchronize_session=False)
    db_session.delete(source)
    db_session.commit()
