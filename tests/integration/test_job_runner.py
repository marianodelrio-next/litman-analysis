from __future__ import annotations
import json, subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from litman_analysis.config import Settings
from litman_analysis.domain.jobs import JobRequest, JobType, MaterializedCase, StorageKind
from litman_analysis.execution import ContainerJobLauncher, JobRunner

def job(tmp_path, ik=StorageKind.LOCAL, ok=StorageKind.LOCAL, jt=JobType.ASSESSMENT):
    source=tmp_path/"source"; source.mkdir(exist_ok=True); (source/"pliego.md").write_text("# Pliego")
    return JobRequest("job-1",jt,ik,ok,str(source) if ik is StorageKind.LOCAL else "drive-source",str(tmp_path/"published") if ok is StorageKind.LOCAL else "drive-target",{"generation":{"artifacts":["technical-proposal"]}})

class Source:
    def __init__(self,drive=False,fail=False): self.drive,self.fail=drive,fail
    def materialize(self,request,workspace):
        if self.fail: raise RuntimeError("materialization failed")
        case=workspace/"case"; case.mkdir(); (case/"pliego.md").write_text("# Drive")
        meta={"pliego.md":{"document_id":"drive-file-123","filename":"Pliego original.md","mime_type":"text/markdown"}} if self.drive else {}
        return MaterializedCase(request.job_id,case,meta)
class Publisher:
    def __init__(self,fail=None): self.calls=[]; self.fail=fail
    def publish(self,request,run):
        self.calls.append((request,run))
        if self.fail: raise RuntimeError(self.fail)
        return (SimpleNamespace(name="output/result.json",uri="test",checksum="hash"),)
class Pipeline:
    calls=[]; valid=True
    def __init__(self,settings,provider): self.settings=settings
    def execute(self,case,*,case_id,bundle,generation=None):
        type(self).calls.append(bundle); stage="detailed-analysis" if generation else "assessment"
        run=self.settings.runs_dir/case_id/stage/"run"; output=run/"output"; output.mkdir(parents=True)
        (output/"validation.json").write_text(json.dumps({"valid":self.valid})); (output/"result.json").write_text("{}")
        if generation is None:
            (output/"ficha_oportunidad.pdf").write_bytes(b"pdf")
        if generation is not None:
            (output/"dossier.json").write_text("{}"); (output/"proposal.docx").write_bytes(b"docx")
            (output/"generation_manifest.json").write_text(json.dumps({"documents":["output/proposal.docx"],"artifacts":[{"id":"technical-proposal"}]}))
        return run,{}
def make_runner(tmp_path,source=None,publisher=None,pipeline=Pipeline):
    settings=Settings(project_root=tmp_path,runs_root=tmp_path/"runs",workspace_root=tmp_path/"work",home_dir=tmp_path/"home",codex_home_dir=tmp_path/"codex",codex_preflight=False,google_credentials_file=tmp_path/"credentials.json")
    return JobRunner(settings,local_source=source or Source(),local_publisher=publisher or Publisher(),drive_service_factory=lambda _:object(),drive_source_factory=lambda *_:source or Source(True),drive_publisher_factory=lambda _:publisher or Publisher(),authentication_factory=lambda **_:object(),provider_factory=lambda **_:object(),assessment_factory=pipeline,detailed_factory=pipeline)

@pytest.mark.parametrize("route",[
    (StorageKind.LOCAL,StorageKind.LOCAL),
    (StorageKind.LOCAL,StorageKind.GOOGLE_DRIVE),
    (StorageKind.GOOGLE_DRIVE,StorageKind.LOCAL),
    (StorageKind.GOOGLE_DRIVE,StorageKind.GOOGLE_DRIVE),
])
@pytest.mark.parametrize("kind",[JobType.ASSESSMENT,JobType.DETAILED_ANALYSIS])
def test_unified_runner_routes_and_cleanup(tmp_path,route,kind):
    result=make_runner(tmp_path,Source(route[0] is StorageKind.GOOGLE_DRIVE)).run(job(tmp_path,*route,jt=kind))
    assert result.status=="succeeded" and result.run_dir.is_dir() and list((tmp_path/"work").iterdir())==[]
def test_drive_metadata_survives(tmp_path):
    Pipeline.calls=[]; make_runner(tmp_path,Source(True)).run(job(tmp_path,StorageKind.GOOGLE_DRIVE,StorageKind.LOCAL))
    document=Pipeline.calls[-1].documents[0]; assert document.document_id=="drive-file-123" and document.filename=="Pliego original.md" and len(document.sha256)==64
def test_local_to_drive_materializes_locally_and_publishes_to_drive(tmp_path):
    source=Source(); publisher=Publisher()
    result=make_runner(tmp_path,source,publisher).run(
        job(tmp_path,StorageKind.LOCAL,StorageKind.GOOGLE_DRIVE))
    assert result.status=="succeeded"
    assert len(publisher.calls)==1
    assert publisher.calls[0][0].output_location=="drive-target"
def test_materialization_failure_skips_pipeline_and_publish(tmp_path):
    Pipeline.calls=[]; publisher=Publisher()
    with pytest.raises(RuntimeError): make_runner(tmp_path,Source(fail=True),publisher).run(job(tmp_path))
    assert Pipeline.calls==[] and publisher.calls==[] and list((tmp_path/"work").iterdir())==[]
def test_invalid_result_not_published_and_run_preserved(tmp_path):
    class Invalid(Pipeline): valid=False
    publisher=Publisher()
    with pytest.raises(ValueError,match="no validado"): make_runner(tmp_path,publisher=publisher,pipeline=Invalid).run(job(tmp_path))
    assert publisher.calls==[] and any((tmp_path/"runs").rglob("validation.json"))
def test_job_runner_recognizes_technical_summary_artifact(tmp_path):
    request=job(tmp_path,jt=JobType.DETAILED_ANALYSIS)
    request = JobRequest(request.job_id, request.job_type, request.input_kind, request.output_kind, request.input_location, request.output_location, {"generation":{"artifacts":["technical-summary"]}})
    class TechnicalSummaryPipeline(Pipeline):
        def execute(self,case,*,case_id,bundle,generation=None):
            run,_=super().execute(case,case_id=case_id,bundle=bundle,generation=generation)
            output=run/"output"; (output/"resumen_tecnico.docx").write_bytes(b"docx")
            (output/"generation_manifest.json").write_text(json.dumps({"documents":[str(output/"resumen_tecnico.docx")],"artifacts":[{"id":"technical-summary"}]}))
            return run,{}
    assert make_runner(tmp_path,pipeline=TechnicalSummaryPipeline).run(request).status=="succeeded"
def test_quota_error_translated(tmp_path):
    with pytest.raises(RuntimeError,match="Shared Drive"): make_runner(tmp_path,Source(True),Publisher("storageQuotaExceeded")).run(job(tmp_path,StorageKind.GOOGLE_DRIVE,StorageKind.GOOGLE_DRIVE))
def test_launcher_calls_compose_once_and_translates(tmp_path):
    calls=[]
    def execute(command,**kwargs):
        calls.append(command); contract=json.loads((Path(kwargs["env"]["LITMAN_ANALYSIS_JOB_DIR"])/"job.json").read_text())
        assert contract["input"]["location"]=="/input" and contract["output"]["location"]=="/output" and contract["options"]["generation"]
        return subprocess.CompletedProcess(command,0,json.dumps({"status":"succeeded","run_dir":"/data/runs/job-1/assessment/run","diagnostics_dir":"/data/runs/job-1/assessment/run","artifacts":[{"name":"output/result.json","uri":"file:///output/job-1-20261008T153045.123456Z/output/result.json","checksum":"x"}]}))
    payload=ContainerJobLauncher(project_root=tmp_path,runner=execute).run(job(tmp_path)).payload
    assert payload["status"]=="succeeded" and payload["run_dir"]==str(tmp_path/"runs/job-1/assessment/run")
    assert payload["artifacts"][0]["uri"]==(tmp_path/"published/job-1-20261008T153045.123456Z/output/result.json").as_uri()
    assert calls==[["docker","compose","run","--rm","litman-analysis","run","/job/job.json"]]
def test_launcher_preserves_drive_ids_and_exit_code(tmp_path):
    seen={}
    def execute(command,**kwargs):
        seen.update(json.loads((Path(kwargs["env"]["LITMAN_ANALYSIS_JOB_DIR"])/"job.json").read_text())); return subprocess.CompletedProcess(command,29,"")
    with pytest.raises(subprocess.CalledProcessError) as error: ContainerJobLauncher(project_root=tmp_path,runner=execute).run(job(tmp_path,StorageKind.GOOGLE_DRIVE,StorageKind.GOOGLE_DRIVE))
    assert error.value.returncode==29 and seen["input"]["location"]=="drive-source" and seen["output"]["location"]=="drive-target"

def test_launcher_translates_local_input_and_preserves_drive_destination(tmp_path):
    seen={}
    def execute(command,**kwargs):
        seen.update(json.loads((Path(kwargs["env"]["LITMAN_ANALYSIS_JOB_DIR"])/"job.json").read_text()))
        return subprocess.CompletedProcess(command,0,json.dumps({"status":"succeeded","artifacts":[]}))
    ContainerJobLauncher(project_root=tmp_path,runner=execute).run(
        job(tmp_path,StorageKind.LOCAL,StorageKind.GOOGLE_DRIVE))
    assert seen["input"]["location"]=="/input"
    assert seen["output"]["location"]=="drive-target"

def test_public_commands_delegate_to_same_launcher(tmp_path,monkeypatch,capsys):
    from litman_analysis import cli
    source=tmp_path/"cli-source"; source.mkdir(); output=tmp_path/"cli-output"
    path=tmp_path/"job.json"; path.write_text(json.dumps({"job_id":"run-id","job_type":"assessment","input":{"kind":"local","location":str(source)},"output":{"kind":"local","location":str(output)}}))
    observed=[]
    class Launcher:
        def run(self,request): observed.append(request); return SimpleNamespace(payload={"status":"succeeded"})
    monkeypatch.setattr(cli,"ContainerJobLauncher",Launcher)
    cli.main(["run",str(path)]); cli.main(["assess",str(source),"--output",str(output),"--job-id","assess-id"])
    cli.main(["analyze",str(source),"--output",str(output),"--job-id","analyze-id"])
    assert [item.job_type for item in observed]==[JobType.ASSESSMENT,JobType.ASSESSMENT,JobType.DETAILED_ANALYSIS]
    assert capsys.readouterr().out.count('"status": "succeeded"')==3

def test_cli_propagates_container_exit_code(tmp_path,monkeypatch):
    from litman_analysis import cli
    source=tmp_path/"cli-source"; source.mkdir()
    class Launcher:
        def run(self,_request): raise subprocess.CalledProcessError(41,"docker compose run")
    monkeypatch.setattr(cli,"ContainerJobLauncher",Launcher)
    with pytest.raises(SystemExit) as error: cli.main(["assess",str(source),"--output",str(tmp_path/"out")])
    assert error.value.code==41
