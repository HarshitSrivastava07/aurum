import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
process.env.RUNTIME_NODE_MODULES='C:/Users/harsh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const S='C:/Users/harsh/.codex/plugins/cache/openai-primary-runtime/presentations/26.1011.11113/skills/presentations';
const {finalizePresentation}=await import(`file:///${S}/container_tools/artifact_tool_utils.mjs`);
const root='C:/hack n hills project', src='C:/Users/harsh/Downloads/6aac310a03938_ppt_template.pptx';
await fs.mkdir(`${root}/output`,{recursive:true});
const result=await finalizePresentation({workspaceDir:root,candidatePath:`${root}/.ppt-build/candidate.pptx`,finalPath:`${root}/output/AURUM_X_Hack_in_Hills.pptx`,pythonExecutable:'C:/Users/harsh/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',integrityValidatorPath:`${S}/container_tools/inspect_presentation_package_integrity.py`,layoutValidatorPath:`${S}/container_tools/inspect_presentation_layout_geometry.py`,layoutArgs:['--expected-slide-size-emu','18288000,10287000','--validate-bullet-geometry','--validate-heading-fit'],explicitTotalSlideCount:8,requiredNativeChartOwnerSlides:[],requiredNativeTableOwnerSlides:[],fontPolicy:{basis:'reference',families:['Montserrat','IBM Plex Sans','Caveat'],referencePath:src,referenceSha256:createHash('sha256').update(await fs.readFile(src)).digest('hex')},sourceTemplatePath:src,verifyArtifactToolImport:true,receiptPath:`${root}/.ppt-build/validation.json`});
console.log(JSON.stringify(result));
