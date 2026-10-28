from dataclasses import replace

from fakes import AtomicSharedState, PDF, dossier_drive
from litman_harness.dossier.models import Resource
from litman_harness.dossier.service import ExpedienteService
from litman_harness.plans import PlanStore


def test_status_reports_drift_without_writes(tmp_path):
    drive = dossier_drive()
    service = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    service.apply_incorporation(service.preview_incorporation('root', ['source']).id)
    state = service.load_state(drive.resources['root'])
    manifest = state.manifest
    manifest.originals[0]['copied_from'] = 'lost-source'
    manifest.summary = {'items': [{'key': 'objeto', 'value': 'x', 'source_file_id': 'lost-source'}],
                        'based_on_analyses': []}
    manifest.analyses = [{'operation_id': 'a', 'status': 'published', 'folder_id': manifest.folders['initial'],
                          'artifacts': [{'file_id': 'artifact', 'name': 'old.pdf'}]}]
    drive.add(Resource('artifact', 'new.pdf', PDF, '1', drive_id='shared', parents=('root',)), b'a')
    drive.resources['source'] = replace(drive.resources['source'], name='changed.pdf', md5_checksum='changed')
    drive.contents[manifest.context_file_id] = b'external edit'
    drive.contents[state.manifest_file.id] = manifest.serialize().encode()
    before = (list(drive.created), list(drive.moved))
    result = service.status('root')
    codes = {(entry['code'], entry.get('id')) for entry in result['drift']}
    assert {('original_name_changed', 'source'), ('original_content_changed', 'source'),
            ('artifact_name_changed', 'artifact'), ('artifact_misplaced', 'artifact'),
            ('summary_source_unavailable', 'lost-source'), ('context_changed', manifest.context_file_id)} <= codes
    assert (drive.created, drive.moved) == before
    assert result['writes'] is False


def test_status_reports_missing_published_artifact(tmp_path):
    drive = dossier_drive()
    service = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    service.apply_incorporation(service.preview_incorporation('root', ['source']).id)
    state = service.load_state(drive.resources['root'])
    state.manifest.analyses = [{'operation_id': 'a', 'status': 'published', 'artifacts': [{'file_id': 'lost'}]}]
    drive.contents[state.manifest_file.id] = state.manifest.serialize().encode()
    result = service.status('root')
    assert any(x['kind'] == 'artifact' and x['id'] == 'lost' for x in result['missing_resources'])
    assert any(x['code'] == 'resource_unavailable' and x['id'] == 'lost' for x in result['drift'])


def test_truncated_inventory_is_explicit(monkeypatch, tmp_path):
    from litman_harness.dossier import service as service_module
    from litman_harness.dossier.tree import walk_tree

    drive = dossier_drive()
    service = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    service.apply_incorporation(service.preview_incorporation('root', ['source']).id)
    monkeypatch.setattr(service_module, 'walk_tree', lambda drive, root, children: walk_tree(drive, root, children, limit=1))
    result = service.status('root')
    assert result['tree_truncated'] and not result['candidate_scan_complete']
    assert any(x['code'] == 'candidate_scan_incomplete' for x in result['drift'])
    assert not any(x['code'] == 'resource_unavailable' for x in result['drift'])


def test_moved_original_is_reported(tmp_path):
    drive = dossier_drive()
    drive.resources['source'] = replace(drive.resources['source'], capabilities={'canMoveItemWithinDrive': True})
    service = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    service.apply_incorporation(service.preview_incorporation('root', ['source']).id)
    drive.resources['source'] = replace(drive.resources['source'], parents=('root',))
    result = service.status('root')
    assert any(x['code'] == 'original_misplaced' and x['id'] == 'source' for x in result['drift'])
    drive.resources['source'] = replace(drive.resources['source'], parents=('unavailable-parent',))
    result = service.status('root')
    assert any(x['code'] == 'resource_unavailable' and x['id'] == 'source' for x in result['drift'])


def test_status_propagates_transient_drive_errors(tmp_path, monkeypatch):
    import pytest
    from litman_harness.errors import HarnessError

    drive = dossier_drive()
    service = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    service.apply_incorporation(service.preview_incorporation('root', ['source']).id)
    state = service.load_state(drive.resources['root'])
    state.manifest.summary = {'items': [{'key': 'objeto', 'value': 'x', 'source_file_id': 'copied-source'}],
                              'based_on_analyses': []}
    drive.contents[state.manifest_file.id] = state.manifest.serialize().encode()
    original_get = drive.get

    def failing_get(identifier):
        if identifier == 'copied-source':
            raise HarnessError('drive_error', 'temporary', details={'http_status': 503})
        return original_get(identifier)

    monkeypatch.setattr(drive, 'get', failing_get)
    with pytest.raises(HarnessError, match='temporary'):
        service.status('root')
    monkeypatch.setattr(drive, 'get', original_get)
    original_download = drive.download

    def failing_download(identifier, path):
        if identifier == state.manifest.context_file_id:
            raise HarnessError('drive_error', 'temporary', details={'http_status': 503})
        return original_download(identifier, path)

    monkeypatch.setattr(drive, 'download', failing_download)
    with pytest.raises(HarnessError, match='temporary'):
        service.status('root')


def test_v2_retirement_preserves_history_and_excludes_active_sources():
    from litman_harness.dossier.manifest import Manifest
    from litman_harness.dossier.recommendation import recommend
    from litman_harness.dossier.context import render_context

    manifest = Manifest.new(Resource('root', 'Tender', 'folder', '1'))
    manifest.originals = [{'file_id': 'a', 'observed_name': 'A', 'md5_checksum': 'hash'}]
    manifest.summary = {'items': [{'key': 'objeto', 'value': 'X', 'source_file_id': 'a'}], 'based_on_analyses': []}
    manifest.upgrade()
    manifest.originals[0]['status'] = 'retired'
    restored = Manifest.parse(manifest.serialize())
    assert restored.originals[0]['file_id'] == 'a'
    assert not restored.active_originals()
    assert 'a' not in restored.summary_sources()
    assert ('original', 'a') not in restored.references()
    assert recommend(folder_id='root', state='adopted', manifest=restored)['kind'] == 'incorporate'
    context = render_context(restored, 'Tender')
    assert 'retirad' in context and 'open?id=a' not in context


def test_reconciliation_retire_reactivate_and_rename(tmp_path):
    from litman_harness.dossier.reconciliation import ReconciliationService
    drive = dossier_drive()
    drive.resources['source'] = replace(drive.resources['source'], capabilities={'canRename': True})
    dossier = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    dossier.apply_incorporation(dossier.preview_incorporation('root', ['source']).id)
    service = ReconciliationService(dossier)
    plan = service.preview('root', [{'op': 'retire_original', 'file_id': 'source'}])
    result = service.apply(plan.id)
    assert result['manifest']['originals'][0]['status'] == 'retired'
    plan = service.preview('root', [{'op': 'reactivate_original', 'file_id': 'source'}])
    assert service.apply(plan.id)['manifest']['originals'][0]['status'] == 'active'
    plan = service.preview('root', [{'op': 'rename_managed', 'file_id': 'source', 'new_name': 'new.pdf'}])
    result = service.apply(plan.id)
    assert result['manifest']['originals'][0]['observed_name'] == 'new.pdf'
    assert drive.get('source').name == 'new.pdf'


def test_reconciliation_conflicts_on_changed_name(tmp_path):
    from litman_harness.dossier.reconciliation import ReconciliationService
    drive = dossier_drive()
    dossier = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    dossier.apply_incorporation(dossier.preview_incorporation('root', ['source']).id)
    service = ReconciliationService(dossier)
    plan = service.preview('root', [{'op': 'adopt_current_name', 'file_id': 'source'}])
    drive.resources['source'] = replace(drive.resources['source'], name='other.pdf')
    assert service.apply(plan.id)['status'] == 'conflict'


def test_reconciliation_placement_and_artifact_return(tmp_path):
    from litman_harness.dossier.reconciliation import ReconciliationService
    drive = dossier_drive()
    dossier = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    dossier.apply_incorporation(dossier.preview_incorporation('root', ['source']).id)
    state = dossier.load_state(drive.get('root'))
    manifest = state.manifest
    original_folder = manifest.folders['originals']
    initial = manifest.folders['initial']
    for identifier in (original_folder, initial):
        drive.resources[identifier] = replace(drive.get(identifier), capabilities={'canAddChildren': True})
    drive.resources['source'] = replace(drive.get('source'), capabilities={'canMoveItemWithinDrive': True})
    drive.add(Resource('artifact', 'result.pdf', PDF, '1', drive_id='shared', parents=('root',),
                       capabilities={'canMoveItemWithinDrive': True}), b'result')
    manifest.analyses = [{'operation_id': 'a', 'status': 'published', 'folder_id': initial,
                          'artifacts': [{'file_id': 'artifact', 'name': 'result.pdf'}]}]
    drive.contents[state.manifest_file.id] = manifest.serialize().encode()
    service = ReconciliationService(dossier)
    plan = service.preview('root', [{'op': 'place_original', 'file_id': 'source'},
                                    {'op': 'return_artifact', 'file_id': 'artifact'}])
    assert service.apply(plan.id)['status'] == 'succeeded'
    assert drive.get('source').parents == (original_folder,)
    assert drive.get('artifact').parents == (initial,)


def test_reconciliation_adopts_current_artifact_name(tmp_path):
    from litman_harness.dossier.reconciliation import ReconciliationService
    drive = dossier_drive()
    dossier = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    dossier.apply_incorporation(dossier.preview_incorporation('root', ['source']).id)
    state = dossier.load_state(drive.get('root'))
    state.manifest.analyses = [{'operation_id': 'a', 'status': 'published',
                                'artifacts': [{'file_id': 'artifact', 'name': 'old.pdf'}]}]
    drive.add(Resource('artifact', 'new.pdf', PDF, '1', drive_id='shared', parents=('root',)), b'file')
    drive.contents[state.manifest_file.id] = state.manifest.serialize().encode()
    service = ReconciliationService(dossier)
    result = service.apply(service.preview('root', [{'op': 'adopt_current_name', 'file_id': 'artifact'}]).id)
    assert result['manifest']['analyses'][0]['artifacts'][0]['name'] == 'new.pdf'


def test_reconciliation_rechecks_capabilities_before_any_write(tmp_path):
    from litman_harness.dossier.reconciliation import ReconciliationService
    drive = dossier_drive()
    drive.resources['source'] = replace(drive.get('source'), capabilities={'canRename': True})
    dossier = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    dossier.apply_incorporation(dossier.preview_incorporation('root', ['source']).id)
    state = dossier.load_state(drive.get('root'))
    folder = state.manifest.folders['originals']
    drive.resources[folder] = replace(drive.get(folder), capabilities={'canAddChildren': True})
    drive.add(Resource('artifact', 'result.pdf', PDF, '1', drive_id='shared', parents=('root',),
                       capabilities={'canMoveItemWithinDrive': True}), b'result')
    state.manifest.analyses = [{'operation_id': 'a', 'status': 'published', 'folder_id': folder,
                                'artifacts': [{'file_id': 'artifact', 'name': 'result.pdf'}]}]
    drive.contents[state.manifest_file.id] = state.manifest.serialize().encode()
    service = ReconciliationService(dossier)
    plan = service.preview('root', [{'op': 'rename_managed', 'file_id': 'source', 'new_name': 'renamed.pdf'},
                                    {'op': 'return_artifact', 'file_id': 'artifact'}])
    drive.resources['artifact'] = replace(drive.get('artifact'), capabilities={})
    result = service.apply(plan.id)
    assert result['status'] == 'conflict' and not result['writes']
    assert drive.get('source').name == 'pliego.pdf'


def test_reconciliation_disappeared_resource_is_conflict(tmp_path):
    from litman_harness.dossier.reconciliation import ReconciliationService
    drive = dossier_drive()
    dossier = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    dossier.apply_incorporation(dossier.preview_incorporation('root', ['source']).id)
    service = ReconciliationService(dossier)
    plan = service.preview('root', [{'op': 'adopt_current_name', 'file_id': 'source'}])
    del drive.resources['source']
    assert service.apply(plan.id)['status'] == 'conflict'


def test_reconciliation_resume_after_rename_response_lost(tmp_path, monkeypatch):
    import pytest
    from litman_harness.errors import HarnessError
    from litman_harness.dossier.reconciliation import ReconciliationService
    drive = dossier_drive()
    drive.resources['source'] = replace(drive.get('source'), capabilities={'canRename': True})
    dossier = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    dossier.apply_incorporation(dossier.preview_incorporation('root', ['source']).id)
    service = ReconciliationService(dossier)
    plan = service.preview('root', [{'op': 'rename_managed', 'file_id': 'source', 'new_name': 'new.pdf'}])
    rename = drive.rename
    def interrupted(identifier, name):
        rename(identifier, name)
        raise RuntimeError('response lost')
    monkeypatch.setattr(drive, 'rename', interrupted)
    with pytest.raises(HarnessError) as exc:
        service.apply(plan.id)
    assert exc.value.code == 'operation_interrupted'
    monkeypatch.setattr(drive, 'rename', rename)
    result = service.apply(plan.id)
    assert result['status'] == 'succeeded'
    assert result['manifest']['originals'][0]['observed_name'] == 'new.pdf'


def test_in_place_reconciliation_does_not_require_destination_write_permission(tmp_path):
    from litman_harness.dossier.reconciliation import ReconciliationService

    drive = dossier_drive()
    dossier = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    dossier.apply_incorporation(dossier.preview_incorporation('root', ['source']).id)
    state = dossier.load_state(drive.get('root'))
    folder_id = state.manifest.folders['originals']
    drive.resources[folder_id] = replace(drive.get(folder_id), capabilities={})
    service = ReconciliationService(dossier)
    plan = service.preview('root', [{'op': 'place_original', 'file_id': 'source'}])
    assert plan.actions[0].metadata['strategy'] == 'in_place'
    result = service.apply(plan.id)
    assert result['status'] == 'succeeded'
    assert result['manifest']['originals'][0]['placement'] == 'in_place'
    assert drive.get('source').parents == ('root',)


def test_concurrent_manifest_after_rename_can_be_reconciled_with_new_plan(tmp_path, monkeypatch):
    from litman_harness.dossier.manifest import Manifest
    from litman_harness.dossier.reconciliation import ReconciliationService

    drive = dossier_drive()
    drive.resources['source'] = replace(drive.get('source'), capabilities={'canRename': True})
    shared = AtomicSharedState(drive)
    dossier = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), shared)
    dossier.apply_incorporation(dossier.preview_incorporation('root', ['source']).id)
    state = dossier.load_state(drive.get('root'))
    service = ReconciliationService(dossier)
    plan = service.preview('root', [{'op': 'rename_managed', 'file_id': 'source', 'new_name': 'new.pdf'}])
    rename = drive.rename
    def concurrent_rename(identifier, name):
        result = rename(identifier, name)
        manifest = Manifest.parse(drive.contents[state.manifest_file.id].decode())
        manifest.workflow_phase = 'analisis_inicial'
        drive.write_text(state.manifest_file.id, manifest.serialize())
        return result
    monkeypatch.setattr(drive, 'rename', concurrent_rename)
    result = service.apply(plan.id)
    assert result['status'] == 'conflict' and result['writes']
    assert result['conflict']['recovery']['operations'] == [{'op': 'adopt_current_name', 'file_id': 'source'}]
    monkeypatch.setattr(drive, 'rename', rename)
    repair = service.preview('root', result['conflict']['recovery']['operations'])
    result = service.apply(repair.id)
    assert result['status'] == 'succeeded'
    assert result['manifest']['workflow_phase'] == 'analisis_inicial'
    assert result['manifest']['originals'][0]['observed_name'] == 'new.pdf'


def test_concurrent_manifest_after_artifact_move_can_be_reconciled(tmp_path, monkeypatch):
    from litman_harness.dossier.manifest import Manifest
    from litman_harness.dossier.reconciliation import ReconciliationService

    drive = dossier_drive()
    shared = AtomicSharedState(drive)
    dossier = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), shared)
    dossier.apply_incorporation(dossier.preview_incorporation('root', ['source']).id)
    state = dossier.load_state(drive.get('root'))
    folder_id = state.manifest.folders['initial']
    drive.resources[folder_id] = replace(drive.get(folder_id), capabilities={'canAddChildren': True})
    drive.add(Resource('artifact', 'result.pdf', PDF, '1', drive_id='shared', parents=('root',),
                       capabilities={'canMoveItemWithinDrive': True}), b'result')
    state.manifest.analyses = [{'operation_id': 'a', 'status': 'published', 'folder_id': folder_id,
                                'artifacts': [{'file_id': 'artifact', 'name': 'result.pdf'}]}]
    drive.write_text(state.manifest_file.id, state.manifest.serialize())
    service = ReconciliationService(dossier)
    plan = service.preview('root', [{'op': 'return_artifact', 'file_id': 'artifact'}])
    move = drive.move
    def concurrent_move(identifier, parent, parents):
        result = move(identifier, parent, parents)
        manifest = Manifest.parse(drive.contents[state.manifest_file.id].decode())
        manifest.workflow_phase = 'analisis_inicial'
        drive.write_text(state.manifest_file.id, manifest.serialize())
        return result
    monkeypatch.setattr(drive, 'move', concurrent_move)
    result = service.apply(plan.id)
    assert result['status'] == 'conflict' and result['writes']
    assert result['conflict']['recovery']['operations'] == [{'op': 'return_artifact', 'file_id': 'artifact'}]
    monkeypatch.setattr(drive, 'move', move)
    repair = service.preview('root', result['conflict']['recovery']['operations'])
    result = service.apply(repair.id)
    assert result['status'] == 'succeeded'
    assert result['manifest']['workflow_phase'] == 'analisis_inicial'
    assert drive.get('artifact').parents == (folder_id,)


def test_concurrent_manifest_after_copied_placement_adopts_the_copy_without_duplicating_it(tmp_path, monkeypatch):
    from litman_harness.dossier.manifest import Manifest
    from litman_harness.dossier.reconciliation import ReconciliationService

    drive = dossier_drive()
    shared = AtomicSharedState(drive)
    dossier = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), shared)
    dossier.apply_incorporation(dossier.preview_incorporation('root', ['source']).id)
    state = dossier.load_state(drive.get('root'))
    folder_id = state.manifest.folders['originals']
    drive.resources['source'] = replace(drive.get('source'), capabilities={'canCopy': True})
    drive.resources[folder_id] = replace(drive.get(folder_id), capabilities={'canAddChildren': True})
    service = ReconciliationService(dossier)
    plan = service.preview('root', [{'op': 'place_original', 'file_id': 'source'}])
    assert plan.actions[0].metadata['strategy'] == 'copy'
    copy = drive.copy
    def concurrent_copy(file_id, name, parent_id, operation_id, action_id):
        result = copy(file_id, name, parent_id, operation_id, action_id)
        manifest = Manifest.parse(drive.contents[state.manifest_file.id].decode())
        manifest.workflow_phase = 'analisis_inicial'
        drive.write_text(state.manifest_file.id, manifest.serialize())
        return result
    monkeypatch.setattr(drive, 'copy', concurrent_copy)
    before = list(drive.created)
    result = service.apply(plan.id)
    assert result['status'] == 'conflict' and result['writes']
    new_copies = [identifier for identifier in drive.created if identifier not in before]
    assert len(new_copies) == 1
    copy_id = new_copies[0]
    assert result['conflict']['recovery']['operations'] == [
        {'op': 'adopt_copy', 'file_id': 'source', 'copy_file_id': copy_id}]
    repair = service.preview('root', result['conflict']['recovery']['operations'])
    result = service.apply(repair.id)
    assert result['status'] == 'succeeded'
    assert result['manifest']['workflow_phase'] == 'analisis_inicial'
    assert result['manifest']['originals'][0]['file_id'] == copy_id
    assert result['manifest']['originals'][0]['copied_from'] == 'source'
    assert result['manifest']['originals'][0]['provenance'] == 'copied'
    assert [identifier for identifier in drive.created if identifier not in before] == new_copies
