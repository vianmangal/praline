import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const workspaceDir=path.resolve(new URL('..',import.meta.url).pathname);
const SKILL_DIR='/Users/vian/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.22227/skills/presentations';
const RUNTIME_PYTHON=process.env.RUNTIME_PYTHON;
if(!RUNTIME_PYTHON) throw new Error('Set bundled RUNTIME_PYTHON and RUNTIME_NODE_MODULES');
const {importRuntimeModule}=await import(pathToFileURL(path.join(SKILL_DIR,'container_tools/runtime_helpers.mjs')).href);
const {Presentation,PresentationFile}=await importRuntimeModule('@oai/artifact-tool');
const {resolvePresentationFont,finalizePresentation}=await import(pathToFileURL(path.join(SKILL_DIR,'container_tools/artifact_tool_utils.mjs')).href);
const font=resolvePresentationFont();
const p=Presentation.create({slideSize:{width:1280,height:720}});
async function read(relative) {try{return JSON.parse(await fs.readFile(path.join(workspaceDir,relative),'utf8'));}catch{return null;}}
const a=await read('submission/evidence/map-cpu/analysis.json');
const v=await read('submission/evidence/map-cpu/validation.json');
const b=await read('submission/evidence/map-cpu/benchmark.json');
const gpu=await read('submission/evidence/map-gpu/analysis.json');
const global=await read('submission/evidence/global_write/analysis.json');
const safe=a?.loops?.find(l=>l.function==='kernel');
const unsafe=global?.loops?.find(l=>l.function==='kernel');
function text(s,value,pos,size=32,bold=false) {
 const box=s.shapes.add({geometry:'textbox',position:pos,fill:'none',line:{fill:'none',width:0}});
 box.text=value;box.text.style={typeface:font,fontSize:size,bold,color:'#20252A',autoFit:'none'};
}
function slide(title,body,notes){
 const s=p.slides.add();s.background.fill='#FFFFFF';
 text(s,title,{left:72,top:52,width:1136,height:90},48,true);
 text(s,body,{left:72,top:175,width:1136,height:440});
 s.speakerNotes.textFrame.setText(notes);return s;
}
slide('Praline','Explain and test helper-aware C loop parallelization\n\nSegFault P05\nLocal prototype / C11 / Clang / OpenMP','Team name and public repository/video links were not supplied.');
slide('The problem','output[i] = apply(input[i]);\n\nA helper can perform independent arithmetic.\nA similar helper can increment shared state.\nThe decision requires effects and dependencies.','Source: examples/helper_map.c and examples/global_write.c.');
slide('How it works','Clang syntax tree and declaration identities\nHelper effects and loop dependency checks\nExplicit alias and bounds assumptions\nSeparate OpenMP source\nWhole-output validation and repeated timings','Compiler interface: docs/CONTRACT.md, schema version 1. Clang instead of ROSE. No calibrated profitability model.');
slide('Seeing through a call',a?`Helper map: ${safe?.decision}\n${safe?.reasons?.map(r=>r.code).join(', ')}\n\nGlobal-write helper: ${unsafe?.decision}\nGLOBAL_WRITE: kernel loop / apply / counter write\nRestrict contracts and separate allocations are explicit.`:'Compiler results unavailable\nNo static-analysis claim is made in this draft.\nThe example uses restrict contracts and separate allocations.','Actual evidence: submission/evidence/map-cpu/analysis.json and global_write/analysis.json. No mock decisions.');
slide('Generated code',`${v?.status==='passed'?'CPU: generated, compiled and output-validated':'CPU compiler-generated validation: not recorded'}\n#pragma omp parallel for default(none) shared(input, n, output)\n\n${['generated','syntax_checked'].includes(gpu?.status)?'GPU: generated and host syntax checked, device unverified':'GPU generation: not recorded'}\nmap(to: input[0:n]) map(tofrom: output[0:n])\nHelper apply is made device-available with declare target.`,'Actual source and patch: submission/evidence/map-cpu and map-gpu. Current Mac has no verified offload device. Code is an explanatory excerpt.');
let lines=[];
if(b?.status==='measured') {
 for(const m of b.measurements.filter(m=>m.seed===1&&m.threads===4&&[1024,65536,1048576].includes(m.size))) {
  lines.push(`n=${m.size}: ${(m.variants.sequential.kernel.median_seconds*1000).toFixed(4)} ms serial / ${(m.variants.generated.kernel.median_seconds*1000).toFixed(4)} ms CPU`);
 }
 const largest=b.measurements.find(m=>m.seed===1&&m.threads===4&&m.size===1048576);
 if(largest) lines.push(`Whole-process speedup at n=1048576: ${largest.end_to_end_speedup.toFixed(3)}x`);
 lines.push(`Whole-output cases passed: ${v.cases.filter(c=>c.status==='passed').length}`);
 lines.push('5 trials after 1 warmup per variant. Kernel medians above.');
 lines.push('Apple Clang 21 / arm64 Mac / libomp 23.1.1');
} else lines=['No compiler-generated benchmark recorded yet.','Only actual measurements will fill the results slide.','GPU device execution is unavailable on this Mac.'];
slide('Results',lines.join('\n'),'Actual measurements: submission/evidence/map-cpu/benchmark.json. Each trial starts a new process. Kernel excludes allocation, initialization and output. End-to-end includes them. Observed equivalence is not proof for all inputs.');
slide('Delivery and gaps','CLI, deterministic examples and execution harness\nPlain HTML report with raw evidence\nFocused C11 subset with explicit assumptions\nGPU hardware verification remains unavailable\nDemo recording and external publication remain pending','See submission/MANIFEST.md. No fabricated public links.');
const build=path.join(workspaceDir,'scripts/.deck-build');
const candidatePath=path.join(build,'candidate.pptx');
await(await PresentationFile.exportPptx(p)).save(candidatePath);
await finalizePresentation({workspaceDir,candidatePath,finalPath:path.join(workspaceDir,process.env.PRALINE_DECK_OUTPUT || 'submission/deck.pptx'),
 explicitTotalSlideCount:7,pythonExecutable:RUNTIME_PYTHON,
 integrityValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
 fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,
 receiptPath:path.join(build,(process.env.PRALINE_DECK_OUTPUT || 'deck.pptx').split('/').at(-1)+'.validation.json')});
for(let i=0;i<p.slides.items.length;i++) {
 const preview=await p.export({slide:p.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(build,`slide-${i+1}.png`),new Uint8Array(await preview.arrayBuffer()));
}
console.log('Created seven-slide deck using '+font);
