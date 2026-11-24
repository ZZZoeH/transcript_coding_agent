// Run with bundled Node.js and NODE_PATH set to its bundled node_modules directory.
const pptxgen = require('pptxgenjs');
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; pres.author = 'Tech Girls';
pres.subject = 'CSE 598/494 project draft; live experiments pending';
pres.title = 'Codebook guided coding of scam call transcripts';
pres.company = 'Arizona State University'; pres.lang = 'en-US';
pres.theme = { headFontFace: 'Cambria', bodyFontFace: 'Calibri', lang: 'en-US' };
const C = { maroon:'8C1D40', gold:'FFC627', ink:'242424', paper:'F8F6F2', gray:'5D5D5D', pale:'ECE7E1', white:'FFFFFF' };
const S = pres.ShapeType;
let index=0;
const notes=[];
const durations=[60,90,60,90,90,90,90,90,90,90,120,90,90,60,60,60,90,90];
function text(slide,t,x,y,w,h,size=22,color=C.ink,bold=false,more={}) {
 slide.addText(t,{x,y,w,h,fontFace:'Calibri',fontSize:size,color,bold,margin:0,breakLine:false,valign:'mid',...more});
}
function rect(slide,x,y,w,h,fill=C.pale){slide.addShape(S.rect,{x,y,w,h,line:{color:fill,transparency:100},fill:{color:fill}});}
function slide(title,source='Project implementation and local audit',dark=false) {
 const s=pres.addSlide(); s.background={color:dark?C.maroon:C.paper}; index++;
 text(s,'TECH GIRLS   /   FORENSICS COMPUTING',.6,.38,11.8,.3,12,dark?C.gold:C.maroon,true,{charSpacing:1.5});
 text(s,title,.6,.95,12.1,.9,35,dark?C.white:C.ink,true,{fontFace:'Cambria'});
 text(s,source,.6,6.86,11.5,.25,10,dark?'EBDDE1':C.gray);
 text(s,String(index).padStart(2,'0'),12.05,6.83,.65,.3,11,dark?C.white:C.gray,false,{align:'right'});
 return s;
}
function note(s,title,body) { const n=durations[index-1]; s.addNotes(`DRAFT — ${n} seconds. ${body}`); notes.push({slide:index,title,seconds:n,notes:body}); }
function cards(s,rows) {
 rows.forEach((r,i)=>{let x=.6+i*4.18;rect(s,x,2.15,3.77,3.9,C.white);text(s,String(i+1).padStart(2,'0'),x+.25,2.4,1,.5,30,C.maroon,true);text(s,r[0],x+.25,3.1,3.27,.7,23,C.ink,true);text(s,r[1],x+.25,4.02,3.27,1.7,21,C.gray,false,{valign:'top'});});
}
function two(s,leftTitle,left,rightTitle,right) {
 rect(s,.6,2.12,5.84,3.8,C.white);rect(s,6.9,2.12,5.83,3.8,C.pale);
 text(s,leftTitle,.9,2.4,5.22,.6,25,C.maroon,true);text(s,left,.9,3.3,5.22,2.3,23,C.ink,false,{valign:'top'});
 text(s,rightTitle,7.2,2.4,5.22,.6,25,C.maroon,true);text(s,right,7.2,3.3,5.22,2.3,23,C.ink,false,{valign:'top'});
}
function lines(s,rows){rows.forEach((r,i)=>{let y=2.1+i*1.03;rect(s,.6,y,.12,.72,C.maroon);text(s,r[0],.95,y,3,.72,23,C.maroon,true);text(s,r[1],4.1,y,8.3,.8,22,C.ink);});}
let s=slide('Codebook guided coding\nof scam call transcripts','Draft • November 22, 2026 • Live model results pending',true);
text(s,'Evidence, uncertainty and human review',.65,3.05,10.9,.6,29,C.gold);
text(s,'Mansi Ganga Nayak  ·  Ju-Won Hyun\nShuyi Huang  ·  Pin-Jun Liu',.65,4.28,10.8,.9,23,C.white);
note(s,'Project question','Introduce the task: apply an existing research codebook to redacted transcripts and compare the resulting labels with released human annotations. Distinguish the offline results shown today from live agent experiments still awaiting API access. The final presentation must be updated after those experiments.');
s=slide('The difficult part is interpreting a call','Sources: supplied proposal; local codebook and transcripts');
cards(s,[['Context changes labels','An eligibility question, an information request and a transfer decision depend on surrounding turns.'],['Vocabulary changes','A fixed topic or alias list can miss a new campaign or force it into an existing label.'],['Evidence needs checking','A plausible label can be wrong. We need source turns, explicit unknowns and a review path.']]);
note(s,'Motivation','Use the example of a caller asking about Medicare eligibility before an attempted handoff. Explain why identifying words is easier than interpreting the exchange. A continued conversation does not by itself establish a successful transfer. Avoid claiming that transcript evidence can recover vocal or acoustic observations.');
s=slide('Four questions guide the evaluation');
lines(s,[['Coding agreement','Does the LLM improve on the deterministic baseline?'],['Novelty','Can it detect a withheld topic without excessive false alarms?'],['Qualification','Can humans apply the outcome guide consistently?'],['Human effort','What labor remains after review and auditing?']]);
note(s,'Research questions','State each question and the evidence needed to answer it. Structural validity addresses completeness; agreement addresses interpretation; novelty needs false positives as well as recall; labor needs observed coding and review time. A functioning API client alone does not answer these questions.');
s=slide('The available data defines the claims','Source: runs/audit/dataset_audit.json');
[['2,429','distinct calls'],['1,941','human-coded calls'],['583','frozen test calls']].forEach((a,i)=>{let x=.7+i*4.17;text(s,a[0],x,2.15,3.75,1.1,62,C.maroon,true);text(s,a[1],x,3.4,3.75,.6,23);});
rect(s,.7,4.6,11.9,1.25,C.white);text(s,'1,358 development calls   •   488 uncoded calls\nTest transcript hashes match; organization names are redacted.',1,4.76,11.3,.9,23);
note(s,'Data audit','Explain the difference between all released calls and the subset with codes. No duplicate call IDs were found. The local development labels cover three of the five available category labels. The release contains one codes object per call, and no identifiable pairwise 337-call reliability mapping. These limits constrain generalization and human-baseline comparisons.');
s=slide('A coding decision keeps its source evidence');
const steps=[['1','Source','Unchanged transcript'],['2','Code','LLM and fixed schema'],['3','Check','Turns and evidence'],['4','Review','Unknowns and novelty']];
steps.forEach((r,i)=>{let x=.65+i*3.15;rect(s,x,2.4,2.7,2.75,i%2?C.white:C.pale);text(s,r[0],x+.2,2.65,2.3,.65,36,C.maroon,true);text(s,r[1],x+.2,3.4,2.3,.5,26,C.ink,true);text(s,r[2],x+.2,4.12,2.3,.7,20);if(i<3)text(s,'→',x+2.76,3.45,.35,.5,24,C.maroon);});
text(s,'Requests, raw responses, predictions and input/output hashes are retained.',.7,5.63,11.9,.55,23);
note(s,'Pipeline','Walk through the data flow. The code works on structured source JSON and never rewrites source transcripts. The model sees only call ID and conversation from each source record. Validation either accepts a complete, evidence-grounded object or creates an explicit failure. Review remains part of the measured workflow.');
s=slide('Structured output still needs review');
two(s,'Deterministic checks','Exact caller-turn coverage\nAllowed types and code labels\nValid evidence paths and indices\nBasic transfer consistency','Interpretation checks','Does the cited text support the label?\nIs execution observable from text?\nDoes a low-uncertainty call hide an error?');
note(s,'Schema and evidence','Explain the difference between the API-side JSON Schema and local semantic checks. Every nonempty coded field needs source indices; turn labels cite their own source turn. Negative findings can cite inspected turns. These rules help auditing, but a source pointer is not proof that an interpretation is correct. Unknown material fields trigger review.');
s=slide('The codebook and released labels differ','Sources: codebook.txt; development annotations; CallTrap artifact README');
two(s,'Written definition','Requested information excludes qualification questions.','Released annotation','Age and insurance eligibility questions appear under requested_info.');
text(s,'Primary scoring follows the released labels and documents that choice.',.85,6.12,11.6,.42,22,C.maroon,true);
note(s,'Label alignment','Use age or possession_medicare as examples. Explain why silently removing those human labels would change the scoring target. Complementary labels retain nag/time/dh and the artifact compatibility mapping. Information tiers are derived only where appendix Table 2 supplies a mapping; other open labels remain unmapped.');
s=slide('The reproduced baseline leaves room to improve','Source: runs/baseline/test_scores_extended.md • 583 held-out calls');
const scores=[['Category  κ',.538],['Topic  κ',.677],['Transfer intent  κ',.727],['Transfer success  κ',.323],['Persuasion  F1',.549],['Functional states  F1',.567],['Requested info  F1',.564]];
scores.forEach((r,i)=>{let y=2.04+i*.55;text(s,r[0],.75,y,3.9,.4,20);rect(s,4.8,y+.05,6.6,.25,C.pale);rect(s,4.8,y+.05,6.6*r[1],.25,i<4?C.maroon:'AD8730');text(s,r[1].toFixed(3),11.68,y,.82,.4,20,C.ink,true,{align:'right'});});
note(s,'Baseline results','These are reproduced offline results, not LLM scores. Emphasize transfer intent versus transfer success as different tasks. The report includes all primary fields and bootstrap intervals; avoid treating kappa and F1 as interchangeable. The unchanged baseline uses keyword and phrase heuristics and is an inspectable minimum system.');
s=slide('The ASU integration is prepared for access','Source: docs.aiml.asu.edu/endpoints/query');
cards(s,[['Native CreateAI API','Project ID is configured. Exact approved provider/model IDs still need confirmation.'],['Recorded experiment','Versioned prompt and schema; raw responses; model request metadata; atomic checkpoints.'],['Explicit failure path','Invalid outputs remain failures. Resume preserves valid calls and rejects changed artifacts.']]);
note(s,'ASU runner','Explain that no live requests have been made. The runner reads the token from the local environment and does not save it in request artifacts. The API request includes a nested JSON Schema response format. Actual provider support and backend metadata must be checked using development calls before the final run. Temperature zero does not guarantee identical future outputs.');
s=slide('The topic reference uses development data only','Source: runs/novelty/reference_calibrated.json');
[['1,018','Fit vocabulary\nand topic vectors'],['240','Calibrate threshold\non separate dev calls'],['100','Exclude withheld\naccident_claim calls']].forEach((r,i)=>{let x=.7+i*4.17;rect(s,x,2.25,3.75,3.6,C.white);text(s,r[0],x+.25,2.65,3.25,.95,50,C.maroon,true);text(s,r[1],x+.25,4.0,3.25,1.1,23);});
text(s,'Freeze 44 known topics and the threshold before inference.',.85,6.12,11.6,.42,22,C.maroon,true);
note(s,'Novelty design','Describe fixed lexical vectors and fifth-percentile calibration. Candidate organizations require literal unredacted text; redaction markers never become aliases. Model-inferred out-of-reference topics and unconfirmed candidates add signals to the lexical comparator. Neither model pretraining nor codebook examples are erased by reference withholding.');
s=slide('Lexical novelty shows a difficult tradeoff','Sources: runs/novelty/test_results*.json • revised test result is exploratory');
text(s,'Initial fixed threshold',4.5,1.95,3.3,.4,19,C.maroon,true);text(s,'Dev calibrated',8.6,1.95,3.3,.4,19,'8A651A',true);
[['Withheld recall',93.3,6.7,'28/30 → 2/30'],['Known false positives',75.0,3.9,'409/545 → 21/545']].forEach((r,i)=>{let y=2.72+i*1.55;text(s,r[0],.75,y,3.5,.7,23,C.ink,true);text(s,r[1]+'%',4.5,y,3.4,.7,38,C.maroon,true);text(s,r[2]+'%',8.6,y,3.4,.7,38,'8A651A',true);text(s,r[3],.75,y+.75,11.6,.4,19,C.gray);});
rect(s,.75,5.8,11.8,.85,C.pale);text(s,'Lower review load comes with many missed withheld calls.',.95,5.86,11.4,.36,20,C.ink,true);text(s,'Revised test is exploratory: the initial test results were already inspected.',.95,6.27,11.4,.3,16,C.maroon);
note(s,'Novelty results','Do not present high recall without false-positive cost. The fixed detector flags 443 total calls; calibration reduces that count to 23 while missing most withheld examples. The revised threshold used development data only, but initial test results had already been inspected, so call the revision exploratory. Full model-assisted novelty results remain pending.');
s=slide('Qualification reliability needs independent humans','Sources: qual_sample/coding_guide.md and blank sheets');
lines(s,[['50 calls','Existing packet; both independent sheets are still blank.'],['Three outcomes','Match, mismatch but continue, or operational termination class.'],['Blind adjudication','Resolve disagreements without seeing model predictions.'],['Two comparisons','Human–human reliability; model–adjudicated agreement.']]);
note(s,'Qualification outcomes','Describe the last exchange before the first transfer. Explain that the existing guide places some insufficient-evidence cases into call_terminates; it is not always proof of an actual hang-up. The model should retain uncertainty in those cases. The 50-call outcome study does not reproduce full-codebook reliability or the paper’s separate 337-call sample.');
s=slide('Resample whole calls when measuring agreement');
two(s,'Primary metrics','Call fields: Cohen’s kappa\nTurn labels: micro-F1\nNovelty: recall and false positives\nQualification: kappa and abstentions','Statistical unit','1,000 bootstrap samples of calls\nSame resampled IDs for both systems\nAgent minus baseline with interval\nUndefined kappa remains undefined');
note(s,'Evaluation','Explain turn dependence within calls. Paired resampling measures uncertainty in the difference rather than informally comparing two separate intervals. Call-ID splits can still share campaign templates, so they are not evidence of new-campaign generalization. Failures must remain visible and prediction files must cover requested IDs before scoring.');
s=slide('An audit trail supports checking each decision');
lines(s,[['Preserve','Original conversations and independent coding sheets remain intact.'],['Identify','SHA-256 inputs, outputs, prompt/schema versions and configuration.'],['Retain','Exact requests, raw responses, validated predictions and failures.'],['Check','Evidence pointers and resume hashes; separate review records.']]);
note(s,'Forensic traceability','Clarify the practical scope: hashes detect changes relative to a retained manifest but are not a signed tamper-proof chain of custody. Backend model revision can only be recorded if ASU returns one. Every evidence index is checked for existence; semantic evidence auditing remains a human task.');
s=slide('Live accuracy and cost results remain pending');
cards(s,[['Before final inference','Confirm access and model IDs; smoke-test three development calls; freeze configuration.'],['Then evaluate','Validate all 583 calls; compare every field; measure model-assisted novelty and failure rates.'],['Keep failures visible','Report missing/invalid responses and the proportion routed to review. Never fill with baseline guesses.']]);
note(s,'Pending experiment','Replace this slide after the live run with an actual result table and model identifiers. Until then, say exactly what is implemented and what is unmeasured. API access is the external dependency. A valid draft should not contain invented improvement, token costs or latency figures.');
s=slide('Time savings require measured human effort','Source: coding/time_savings.py; paper audio duration is not coder labor');
text(s,'Manual labor',.8,2.3,4.9,.5,28,C.maroon,true);text(s,'N × manual minutes',.8,3.15,5.2,1.1,32);
text(s,'Assisted labor',7.0,2.3,5.3,.5,28,C.maroon,true);text(s,'Setup + review +\naudit of unflagged calls',7.0,3.15,5.3,1.3,30);
rect(s,.8,5.15,11.7,.95,C.white);text(s,'Record model wall time and token costs separately.',1.05,5.35,11.2,.5,24);
note(s,'Workload analysis','Measure manual minutes, review minutes, setup and review fraction on representative calls. Include a random audit of unflagged calls to estimate missed-error risk. The source paper’s 115 hours describes audio duration, not measured annotation effort. If assisted labor exceeds manual labor, report the negative saving.');
s=slide('The limits belong alongside the results');
lines(s,[['Released sample','Redacted identities; no audio cues; only three observed dev categories.'],['Evaluation scope','Campaign overlap possible; no identified pairwise reliability release.'],['Novelty','Lexical tradeoff is unfavorable; full agent signals are untested.'],['Unknowns','No live LLM comparison, completed human study or measured labor yet.']]);
note(s,'Limitations','Connect each limitation to the claim it restricts. Avoid generalizing this dataset to all scams or treating model agreement as legal attribution. Label mismatch and qualification operationalization should be discussed explicitly. The final report needs errors and uncertainty alongside any eventual improvements.');
s=slide('Complete the evidence before making the claim','Draft • Contributions are proposal assignments, pending team confirmation',true);
text(s,'Mansi and Ju-Won',.75,2.3,4.7,.5,25,C.gold,true);text(s,'Data, baseline, evaluation and independent coding',.75,3.0,5.35,1.1,23,C.white);
text(s,'Shuyi and Pin-Jun',7.0,2.3,5.5,.5,25,C.gold,true);text(s,'Structured agent, novelty, uncertainty and review',7.0,3.0,5.35,1.1,23,C.white);
text(s,'Next: live run → human study → measured effort → final report',.75,5.0,11.7,1.0,27,C.white,true);
note(s,'Contributions and next steps','Confirm actual member contributions before presenting them as completed work. This slide currently summarizes proposal assignments. End with the verified result: the offline comparator and auditable integration are available, while empirical improvement and practical labor savings remain open questions. The report is due December 7 and the presentation materials must precede the actual presentation date.');
(async()=>{
 await pres.writeFile({fileName:path.join(root,'deliverables','Project_Presentation_Draft.pptx')});
 fs.writeFileSync(path.join(root,'deliverables','presentation_notes.md'), '# Presentation notes\n\nDraft with 18 slides and 25 minutes planned speaking time. Rehearse and update pending results before presenting.\n\n' + notes.map(n=>`## ${n.slide} ${n.title} (${n.seconds} seconds)\n\n${n.notes}`).join('\n\n') + '\n\nReferences: https://github.com/sefcom/calltrap-artifact ; https://mschloegel.me/paper/lyu2026scammers.pdf ; https://docs.aiml.asu.edu/endpoints/query\n');
 console.log('Created 18 slides; planned duration',notes.reduce((n,r)=>n+r.seconds,0),'seconds');
})();
