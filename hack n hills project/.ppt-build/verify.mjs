import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from 'file:///C:/Users/harsh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const root='C:/hack n hills project';
const p=await PresentationFile.importPptx(await FileBlob.load(`${root}/output/AURUM_X_Hack_in_Hills.pptx`));
await fs.mkdir(`${root}/.ppt-build/final`,{recursive:true});
for(const [i,s]of p.slides.items.entries()) {await fs.writeFile(`${root}/.ppt-build/final/slide-${i+1}.png`,new Uint8Array(await(await p.export({slide:s,format:'png',scale:.75})).arrayBuffer()));}
console.log('Rendered all 8 exported slides');
