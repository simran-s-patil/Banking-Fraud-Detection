
"""Automated tests for investigation services."""

import pytest

from backend.investigation_service import (
    create_investigation,
    get_investigation_by_id,
    get_investigations,
    update_investigation,
)


@pytest.mark.parametrize("alert_id", [0, -1, True, "1"])
def test_invalid_alert_id_for_creation(alert_id):
    with pytest.raises(ValueError):
        create_investigation(alert_id, "Test Investigator")


@pytest.mark.parametrize("name", ["", "   ", None, 123])
def test_invalid_investigator_name(name):
    with pytest.raises(ValueError):
        create_investigation(1, name)


def test_investigator_name_too_long():
    with pytest.raises(ValueError):
        create_investigation(1, "A" * 101)


def test_invalid_notes_type_for_creation():
    with pytest.raises(ValueError):
        create_investigation(1, "Test Investigator", 123)


@pytest.mark.parametrize("investigation_id", [0, -1, True, "1"])
def test_invalid_investigation_id_for_retrieval(investigation_id):
    with pytest.raises(ValueError):
        get_investigation_by_id(investigation_id)


@pytest.mark.parametrize("limit", [0, -1, 501, True, 1.5])
def test_invalid_investigation_limit(limit):
    with pytest.raises(ValueError):
        get_investigations(limit=limit)


def test_invalid_resolution_status_filter():
    with pytest.raises(ValueError):
        get_investigations(resolution_status="DONE")


def test_invalid_outcome_filter():
    with pytest.raises(ValueError):
        get_investigations(outcome="MAYBE")


@pytest.mark.parametrize("investigation_id", [0, -1, True, "1"])
def test_invalid_investigation_id_for_update(investigation_id):
    with pytest.raises(ValueError):
        update_investigation(investigation_id, notes="Test")


def test_invalid_notes_for_update():
    with pytest.raises(ValueError):
        update_investigation(1, notes=123)


def test_invalid_outcome_for_update():
    with pytest.raises(ValueError):
        update_investigation(1, outcome="MAYBE")


def test_invalid_resolution_status_for_update():
    with pytest.raises(ValueError):
        update_investigation(1, resolution_status="DONE")


def test_empty_investigation_update():
    with pytest.raises(ValueError):
        update_investigation(1)
