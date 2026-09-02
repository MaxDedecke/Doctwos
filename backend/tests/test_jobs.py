from api import jobs as jobs_api
from models.database import DiagnosticsRun, JobCenterDismissal, KnowledgeSource, LinkBuilderRun, Project


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
    assert sent_tasks[0][0] == ("process_knowledge_source",)
    assert sent_tasks[0][1]["args"] == [source.id]
    assert sent_tasks[0][1]["kwargs"]["trace_id"]

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


def test_job_list_can_be_scoped_to_a_project(client, db_session, test_project, test_team):
    """The selected project view must not leak jobs from other projects."""
    other_project = Project(name="Other job project", team_id=test_team)
    db_session.add(other_project)
    db_session.commit()
    db_session.refresh(other_project)
    source_current = KnowledgeSource(
        name="Current project source", type="Git", project_id=test_project,
        team_id=test_team, sync_status="pending",
    )
    source_other = KnowledgeSource(
        name="Other project source", type="Git", project_id=other_project.id,
        team_id=test_team, sync_status="pending",
    )
    link_current = LinkBuilderRun(task_type="entity_links", project_id=test_project, status="pending")
    link_other = LinkBuilderRun(task_type="entity_links", project_id=other_project.id, status="pending")
    db_session.add_all([source_current, source_other, link_current, link_other])
    db_session.commit()

    try:
        response = client.get(f"/jobs?project_id={test_project}")
        assert response.status_code == 200, response.text
        keys = {job["key"] for job in response.json()["jobs"]}
        assert f"source:{source_current.id}" in keys
        assert f"link_builder:{link_current.id}" in keys
        assert f"source:{source_other.id}" not in keys
        assert f"link_builder:{link_other.id}" not in keys
        assert not any(job["kind"] == "diagnostics" for job in response.json()["jobs"])
    finally:
        db_session.query(JobCenterDismissal).filter(
            JobCenterDismissal.kind == "source",
            JobCenterDismissal.job_id.in_([source_current.id, source_other.id]),
        ).delete(synchronize_session=False)
        db_session.delete(source_current)
        db_session.delete(source_other)
        db_session.delete(link_current)
        db_session.delete(link_other)
        db_session.delete(other_project)
        db_session.commit()


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
    assert sent_tasks[0][0] == ("generate_diagnostics_bundle",)
    assert sent_tasks[0][1]["args"] == [created.id]
    assert sent_tasks[0][1]["kwargs"]["trace_id"]
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


def test_admin_can_remove_failed_diagnostics_job(client, db_session):
    run = DiagnosticsRun(status="failed", error_message="bundle failed")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    response = client.delete(f"/jobs/diagnostics/{run.id}")

    assert response.status_code == 200
    listed = client.get("/jobs")
    assert all(job["key"] != f"diagnostics:{run.id}" for job in listed.json()["jobs"])
    db_session.query(JobCenterDismissal).filter(
        JobCenterDismissal.kind == "diagnostics",
        JobCenterDismissal.job_id == run.id,
    ).delete(synchronize_session=False)
    db_session.delete(run)
    db_session.commit()


def test_admin_can_stop_running_diagnostics_job(client, db_session, monkeypatch):
    run = DiagnosticsRun(status="pending", celery_task_id="celery-task-123")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    revoked = []
    monkeypatch.setattr(
        jobs_api.celery_app.control,
        "revoke",
        lambda *args, **kwargs: revoked.append((args, kwargs)),
    )

    response = client.post(f"/jobs/diagnostics/{run.id}/stop")

    assert response.status_code == 200
    db_session.refresh(run)
    assert run.status == "cancelled"
    assert run.progress_message == "Vom Administrator abgebrochen"
    assert revoked == [(
        ("celery-task-123",),
        {"terminate": True, "signal": "SIGTERM"},
    )]
    db_session.delete(run)
    db_session.commit()
