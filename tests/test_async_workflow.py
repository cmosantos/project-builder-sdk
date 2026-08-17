import inspect

from project_builder.workflow import (
    executar_qa,
    executar_repair,
    run_project,
    run_project_async,
)


def test_workflow_agentic_usa_um_unico_event_loop():
    assert inspect.iscoroutinefunction(run_project_async)
    assert inspect.iscoroutinefunction(executar_qa)
    assert inspect.iscoroutinefunction(executar_repair)
    assert not inspect.iscoroutinefunction(run_project)
