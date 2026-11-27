import ast,json
from pathlib import Path
issues=json.loads(Path('.gc/sonar/1834-1793524538771.json').read_text())['issues']
byfile={}
for i in issues:
 if i['rule'] in {'python:S6540','python:S6538'}:
  byfile.setdefault(i['component'].split(':',1)[1],set()).add(i['line'])
returns={
 '__init__':'None','initialize_recovery_port':'None','settle_interrupted_tool':'None',
 'delivery_tools_context':'SimpleNamespace','recovery_port':'ParticipantDeliveryInvocationTools',
 'refusal':'ParticipantToolActionDecision','_admit':'ParticipantToolActionDecision',
 '_decision':'ParticipantToolActionDecision','_receipt':'ParticipantToolActionReceipt',
 '_dispatch':'ParticipantToolActionReceipt','_complete':'ParticipantToolActionReceipt',
 '_cancel':'ParticipantToolActionReceipt','_unknown':'ParticipantToolActionReceipt',
 '_settle_unknown':'None','_commit_crossing':'None',
 'delivery_tool_driver_actions':'frozenset[str]','matching_delivery_tool_offers':'list[object]',
 'execution_offers':'list[object]','require_live_invocation':'None',
 'action_admission':'ParticipantActionAdmissionRequest','prepare_tool_crossing':'tuple[object, object]',
 'tool_binding':'tuple[object, ParticipantToolActionRefusal | None]',
 'require_delivery_invocation_transition':'None','require_delivery_tool_transition':'None',
 'delivery_tool_origin_matches':'bool','reconcile_delivery_tool':'bool',
 'settle_delivery_tool':'None','require_governed_subject':'None',
 'governed_action_request':'ParticipantActionAdmissionRequest',
 'detached_tool_outcome':'ParticipantActionResultModel | None',
 'delivery_create_tool_ledger':'InvocationToolActionLedger',
 'delivery_invocation_record':'ControlPlaneOperationRecord',
 'delivery_commit_invocation_terminal':'object',
 'delivery_live_cut':'ParticipantControlLiveCut','delivery_action_sink_kind':'ParticipantFlowSinkKind',
 'delivery_execution_generation':'int','delivery_require_state_writer':'None',
 'delivery_tool_port_type':'type[ParticipantDeliveryInvocationTools]',
 'delivery_operation_read_allowed':'bool',
}
str_args={'action_id','action_instance_id','operation_id','now','key','failure_class','action','implementation_ref','action_contract_address','stage'}
for file,lines in byfile.items():
 p=Path(file); source=p.read_text(); tree=ast.parse(source); edits=[]
 offsets=[]; n=0
 for line in source.splitlines(keepends=True): offsets.append(n); n+=len(line)
 def pos(l,c):return offsets[l-1]+c
 for node in ast.walk(tree):
  if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) or node.lineno not in lines:continue
  for arg in [*node.args.posonlyargs,*node.args.args,*node.args.kwonlyargs,*([node.args.vararg] if node.args.vararg else []),*([node.args.kwarg] if node.args.kwarg else [])]:
   if arg.annotation is not None or arg.arg in {'self','cls'}:continue
   typ='str' if arg.arg in str_args else 'object'
   if arg.arg=='request' and 'ParticipantToolActionRequest' in source:typ='ParticipantToolActionRequest'
   if arg.arg=='outcome' and 'ParticipantActionResultModel' in source:typ='ParticipantActionResultModel'
   if arg.arg=='entry' and 'InvocationToolEntry' in source:typ='InvocationToolEntry'
   if arg.arg=='settlement' and 'ParticipantToolActionSettlement' in source:typ='ParticipantToolActionSettlement'
   if arg.arg=='invocation' and 'ParticipantDeliveryInvocationContextModel' in source:typ='ParticipantDeliveryInvocationContextModel'
   if arg.arg=='evidence' and 'ParticipantCrossingEvidence' in source:typ='ParticipantCrossingEvidence | None'
   if arg.arg=='temporal_evidence':typ='tuple[ParticipantTemporalEvidenceModel, ...]'
   edits.append((pos(arg.lineno,arg.col_offset)+len(arg.arg), ': '+typ))
  if node.returns is None:
   # The annotation belongs after the final argument parenthesis, before the colon.
   start=pos(node.lineno,node.col_offset); body=pos(node.body[0].lineno,node.body[0].col_offset)
   end=source.rfind(':',start,body); closing=source.rfind(')',start,end)
   edits.append((closing+1,' -> '+returns.get(node.name,'object')))
 for offset,text in sorted(edits,reverse=True):source=source[:offset]+text+source[offset:]
 if 'from __future__ import annotations' not in source:
  module=ast.parse(source); end=module.body[0].end_lineno
  s=source.splitlines(keepends=True);s.insert(end,'\nfrom __future__ import annotations\n');source=''.join(s)
 p.write_text(source)
