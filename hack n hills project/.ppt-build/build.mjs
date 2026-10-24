import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {FileBlob, PresentationFile} from 'file:///C:/Users/harsh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
process.env.RUNTIME_NODE_MODULES='C:/Users/harsh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
process.env.RUNTIME_PYTHON='C:/Users/harsh/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const SKILL='C:/Users/harsh/.codex/plugins/cache/openai-primary-runtime/presentations/26.1011.11113/skills/presentations';
const {makeNativeBulletParagraphs}=await import(`file:///${SKILL}/container_tools/artifact_tool_utils.mjs`);
const ROOT='C:/hack n hills project', B=`${ROOT}/.ppt-build`, source='C:/Users/harsh/Downloads/6aac310a03938_ppt_template.pptx';
const p=await PresentationFile.importPptx(await FileBlob.load(source));
const records=(await p.inspect({select:'$.slides[*]',include:['id','index','elements.id','elements.text','elements.kind']})).records;
function style(s,size=37.12,bold=false,font='IBM Plex Sans') {s.text.style={fontSize:size,typeface:font,bold,color:'#1D1D1F',alignment:'left',verticalAlignment:'top',autoFit:'none',wrap:'square',insets:0,lineSpacing:1.05};}
function text(id,t,box,size=37.12,bold=false,font='IBM Plex Sans') {const s=p.resolve(id);s.text=t;s.position=box;style(s,size,bold,font);return s;}
function bullet(id,items,box,size=37.12,space=16) {const s=p.resolve(id);s.text=makeNativeBulletParagraphs(items,{marginLeftPoints:30,hangingPoints:20,spaceAfterPoints:space});s.position=box;style(s,size);for(const item of items){const label=item.split(':')[0];if(item.includes(':'))s.text.get(label+':').bold=true;}return s;}
function title(id,t) {return text(id,t,{left:160,top:215,width:1600,height:70},41.27,true,'Montserrat');}
function extra(slide,t,box,size=32,bold=false) {const s=slide.shapes.add({geometry:'textbox',position:box,fill:'none',line:{fill:'none',width:0}});s.text=t;style(s,size,bold);return s;}
const slides=p.slides.items;
text('sh/298ju94j','AURUM X',{left:128,top:510,width:1660,height:112},80.73,true,'Montserrat');
text('sh/pcz254na',[
 'Track 03: Commodity Derivatives Intelligence',
 'Research for MCX gold futures',
 'Harshit Srivastava: Team Leader',
 'Sameeksha Verma: Team Member',
 'Ritish Yadav: Team Member',
].map((run,i)=>({runs:[{run,style:{bold:i===0}}],spaceAfter:i===1?2200:1000})),{left:160,top:645,width:1600,height:370},39);

title('sh/8vy54jal','PROBLEM STATEMENT & THEME');
text('sh/mtgn29sf','Track 03: Commodity Derivatives Intelligence',{left:180,top:320,width:1560,height:60},39,true);
bullet('sh/7up4vet0',[
 'Problem: GOLDM, GOLDTEN, GOLDGUINEA and GOLDPETAL represent gold, but lot size, quotation base, purity and expiry differ.',
 'Impact: a visible price gap may reflect contract mechanics, maturity or delivery basis. Fees and thin trading can erase an apparent advantage.',
 'Research challenge: compare normalized exact contracts, separate curve movement from roll-down, and replay decisions without future information.',
 'Responsible output: account for costs, contract calendars and gold exposure. Suppress unsupported signals and report when evidence is insufficient.',
],{left:180,top:415,width:1560,height:590},39,23);

title('sh/0vqdgvml','SOLUTION');
extra(slides[2],'Seven analytical workspaces supported by a shared contract and evidence engine',{left:180,top:310,width:1560,height:60},36,true);
bullet('sh/q5oval43',[
 'Relative Value Explorer: six-pair scan, exact-expiry unit/purity normalization, Z/MAD deviations and maturity adjustment.',
 'Futures Curve Laboratory: curve shape, calendar spreads, empirical carry, roll-down and residual shift.',
 'Ghost Market: joint bootstrap across 11 stress classes with fixed seeds, tail summaries and cost sensitivity.',
 'Market Red Team: 21 executable checks for leakage, fills, costs, contract rules and evidence quality.',
],{left:180,top:385,width:750,height:640},37.12,17);
bullet('sh/d8zul0nu',[
 'Time-Locked Replay: session clock, delayed Open fills, integer lots, walk-forward/frozen holdout, equity/P&L and gold exposure.',
 'Profit Survival Map: cost/delay grids, holding, exit, slippage and liquidity slices, plus conditional break-even.',
 'Anomaly DNA: 11-feature prior analogs, robust scaling and non-overlapping completed outcomes.',
],{left:1020,top:385,width:740,height:640},37.12,26);

title('sh/36xw7m5c','ARCHITECTURE');
bullet('sh/h4ve5cn6',[
 'Data Management: CSV, TSV, XLS/XLSX and ZIP ingestion, explicit dates, requested-date checks, duplicate handling, raw hashes and isolated synthetic data.',
 'Contract Genome: versioned quotation, purity, lot and location rules, exact expiry identities, integer hedge sizing and listing/tender/expiry eligibility.',
 'Settings: explicit cost schedules, slippage, capital, liquidity, replay and simulation controls. Session persistence and stale-result detection.',
 'Command Center + Mirage Investigation: coverage dashboard, full pipeline, A/B/C comparisons, candidates, curve adjustments and rejection reasons.',
 'Evidence Center: SQLite experiment ledger, preserved Parquet snapshots, JSON/CSV exports and deterministic reproduction with data, specification and code checks.',
],{left:180,top:320,width:1560,height:625},37.12,18);
text('sh/g3mdw76l','Streamlit + Plotly interface   /   FastAPI + Pydantic API\nDuckDB + Parquet market data   /   SQLite ledger   /   No paid API or required LLM',{left:180,top:930,width:1560,height:105},32,true);

title('sh/1cvit8b2','MARKET RESEARCH/ANALYSIS');
bullet('sh/fqd0rytw',[
 'Target users: commodity research desks, quantitative analysts and finance education teams that need reviewable contract-level research.',
 'Value proposition: one local workflow connects normalization and curve analysis with adverse tests, costed replay and reproducible evidence.',
 'Revenue hypotheses: team software licenses, research pilots and educational deployments. Pricing and willingness to pay need customer testing.',
 'Market size and growth: no validated estimate or adoption forecast yet. Next steps are interviews, pilot usage and retention measurement.',
],{left:180,top:335,width:1560,height:590},39,25);
text('sh/ofm143at','Customer, revenue and growth statements are hypotheses. The prototype has no documented commercial traction.',{left:180,top:950,width:1560,height:75},32,true);

title('sh/0jylgnmh','FUTURE SCOPE');
bullet('sh/yhgjed4b',[
 'Authentic evaluation: ingest daily Bhavcopy history and verify listing/tender calendars, original specification hashes and dated fee sources.',
 'Independent validation: review the methodology and expand untouched periods before making any real trading-performance claim.',
 'Richer research: investigate cointegration, calibrated uncertainty and stronger attribution beyond the current accounting decomposition.',
 'Execution assessment: improve liquidity and fill modeling while retaining explicit lifecycle and basis restrictions.',
 'Long investigations: add persistent background jobs, progress tracking and cancellation. An optional LLM assistant remains future work.',
],{left:180,top:335,width:1560,height:620},39,22);
text('sh/zipk7i5w','Current boundary: local research prototype. Brokerage/order routing and validated real-history performance are unavailable.',{left:180,top:955,width:1560,height:75},32,true);

title('sh/ra9k7ap8','EXTRA: DEMO & VALIDATION');
bullet('sh/i1kzalsj',[
 'Working product: 13 workspaces with charts and CSV/JSON exports. A/B/C policy comparisons plus cash, gold buy-and-hold and fixed-hedge references.',
 'Documented checks: 84 tests passed on 9 October 2026, covering ingestion, financial math, future-data leakage, replay, audit, reproduction and all pages.',
 'Synthetic demo: 2,160 records across four products and 12 fictional expiry identities. Ghost Market ran 11 classes with 500 paths each.',
 'Result: Policy C rejected 17 candidate sessions and made zero trades. Red Team reported 10 pass, 0 fail and 11 not evaluable. Reproduction hashes matched.',
 'Honest verdict: INSUFFICIENT EVIDENCE. Five supplied annual reports contained zero daily observations. Real MCX trading performance remains unvalidated.',
],{left:180,top:320,width:1560,height:655},37.12,19);
text('sh/5ovilgru','Demo flow: import data, inspect contracts, investigate, replay, audit and reproduce',{left:180,top:970,width:1560,height:65},32,true);

const baseNotes=[
 'Team details supplied by the user: Harshit Srivastava (team leader), Sameeksha Verma and Ritish Yadav (team members). Project title and capabilities: README.md. Do not assign unprovided technical responsibilities.',
 'Source: user-supplied Track 03 challenge brief. Official references: https://www.mcxindia.com/market-data/bhavcopy and https://www.mcxindia.com/products/bullion/gold. The product page was opened on 15 October 2026. The Bhavcopy page could not be fetched by the research tool. This deck does not independently verify all specification values or imply real-time data access. GOLDTEN history starts in its listing period. Volume is not market depth, and settlement is not an executable fill.',
 'Sources: README.md, docs/methodology.md and frontend/app.py. All seven named analytical tools have executable functions. Quotes normalize to INR per fine gram, with a common 10g 999 representation. Exact expiry selection prevents artificial continuous-contract rolls. Curve interpolation requires bracketing maturities and does not extrapolate. Replay uses subsequent common-session Open, never substitutes Close, preserves unresolved exits and uses prior-volume participation limits. It separates completed-trade P&L, open marks and equity. The gold factor contribution and relative-value residual are an accounting decomposition, not causal alpha attribution. Scenario and analog summaries are descriptive, not calibrated investment probabilities.',
 'Sources: README.md, docs/methodology.md, docs/validation.md, frontend/app.py and backend/main.py. Data import validates MDY/DMY, expiry strings and padded symbols, rejects annual aggregates, missing/invalid fields, unsafe ZIP paths and excessive expansion. Duplicate/conflicting identities remain inspectable. Real and synthetic data stay separate. The Contract Genome distinguishes quotation and trading units, purity, delivery geography and expiry-effective rules. Unknown real calendar evidence blocks execution. Settings include dated fee schedules/GST/tax assumptions, slippage, delays, participation, capital, seeds, paths and API timeout. Policy A uses normalized spreads, B adds supported maturity adjustment, C adds robust-MAD, lifecycle, basis and prospective bootstrap gates. Command Center and Mirage preserve full investigations. Evidence Center stores failed and successful experiments, flags repeated sample use and refuses changed snapshots/specifications/code during reproduction. Matching hashes establish deterministic reproduction, not an externally secured ledger. Local single-worker FastAPI avoids cross-process DuckDB contention. Docker files exist but Docker execution remains unverified.',
 'Target users and revenue models are product hypotheses based on the prototype capabilities. No customer interviews, market size, revenue, pricing validation, competitive benchmarks or measured commercial traction were supplied. Proposed next validation: interview researchers, observe workflow trials, measure repeat use and willingness to pay.',
 'Sources: README.md Current limits and next work, docs/validation.md Status and remaining limitations. The roadmap items are not implemented claims. The application presently has no optional LLM integration, cointegration/error-correction model, calibrated predictive probabilities, causal alpha attribution, persistent cancellable job queue or order routing. Missing genuine daily observations and verified calendars block authentic historical evaluation.',
 'Source: docs/validation.md, executed validation dated 9 October 2026, and docs/data_sources.md. The deck reports documented prior checks, not a test rerun. Seed 42 synthetic demo: GOLDM/GOLDTEN, 2 January–10 September 2025, window 20, costs 5 bps plus slippage 2 bps, 500 paths. Policy C rejected 17 sessions, no trades. A/B each completed six synthetic trades; gross INR 46,548.671, modeled costs INR 15,234.869, net INR 31,313.802, including two held-out synthetic trades with INR 11,218.268 net. These generated results are software demonstrations only. Five prior analogs were retrieved. The final real-mode investigation had zero observations. Eleven stress classes and twenty-one audit checks are described in the feature inventory and application. Reproduction of the preserved snapshot returned matching result hashes. Test coverage includes independent P&L fixtures, Hypothesis symmetry, strict dates, version changes, lifecycle blocks, future/holdout mutations, no same-session fill, missing Opens, bootstrap dependence, sensitivity, analog cutoffs, snapshot tampering and the 13-page UI.',
 'AURUM X. Team leader: Harshit Srivastava. Members: Sameeksha Verma and Ritish Yadav. Demonstrate the pipeline with clearly labeled synthetic data and inspect the evidence certificate. No real MCX trading edge has been established.'
];
const inventory=JSON.parse(await fs.readFile(`${B}/feature-inventory.json`,'utf8'));
baseNotes[3]=baseNotes[3].replace('delays, participation, capital','delays, capital')+' TSV is supported by the backend. The UI picker exposes CSV, XLS/XLSX and ZIP. Replay uses a prior-volume participation limit with a 1% default.';
for(const w of inventory.workspaces){const i=w.slide-1;baseNotes[i]+='\n\n'+w.name+' implemented feature detail:\n'+w.capabilities.map(x=>'- '+x).join('\n');}
for(const [k,v] of Object.entries(inventory)){if(/stress|audit|scenario|red_team/.test(k))baseNotes[6]+='\n\n'+k+':\n'+JSON.stringify(v,null,2);}
for(let i=0;i<8;i++)slides[i].speakerNotes.text=baseNotes[i];
await fs.mkdir(`${B}/after`,{recursive:true});
for(const [i,s] of slides.entries()) {
 await fs.writeFile(`${B}/after/slide-${i+1}.png`,new Uint8Array(await (await p.export({slide:s,format:'png',scale:0.75})).arrayBuffer()));
 await fs.writeFile(`${B}/after/slide-${i+1}.layout.json`,await (await s.export({format:'layout'})).text());
 console.log(`Rendered ${i+1}`);
}
await fs.writeFile(`${B}/final-content.ndjson`,(await p.inspect({select:'$.slides[*]',include:['id','index','elements.id','elements.text','elements.position','elements.style','notes.text']})).ndjson);
await (await PresentationFile.exportPptx(p)).save(`${B}/candidate.pptx`);
console.log('Exported candidate.pptx');
