import fs from 'node:fs/promises';
import {FileBlob, PresentationFile} from 'file:///C:/Users/harsh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const build='C:/hack n hills project/.ppt-build';
const p=await PresentationFile.importPptx(await FileBlob.load('C:/Users/harsh/Downloads/6aac310a03938_ppt_template.pptx'));
await fs.mkdir(`${build}/before`,{recursive:true});
const inspect=await p.inspect({select:'$.slides[*]',include:['id','index','layout','elements.id','elements.kind','elements.text','elements.position','elements.style']});
await fs.writeFile(`${build}/import-inspection.ndjson`,inspect.ndjson);
console.log(JSON.stringify({slides:p.slides.items.length,masters:p.masters.items.map(x=>({id:x.id,name:x.name})),layouts:p.layouts.items.map(x=>({id:x.id,name:x.name,placeholders:x.placeholders.summary()}))}));
for (const [i,s] of p.slides.items.entries()) {
 const png=await p.export({slide:s,format:'png',scale:0.75});
 await fs.writeFile(`${build}/before/slide-${i+1}.png`,new Uint8Array(await png.arrayBuffer()));
 console.log(`Rendered ${i+1}`);
}
