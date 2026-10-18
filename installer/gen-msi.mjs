import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const root = path.resolve(process.argv[2] ?? '.');
const stage = path.resolve(process.argv[3] ?? 'artifacts/stage');
const version = process.argv[4] ?? '1.0.0';
const outFile = path.resolve(root, process.argv[5] ?? 'installer/CamStream.wxs');

const skip = new Set([
  'setup.cmd', 'setup.ps1', 'Start-CamStream.cmd', 'Start-CamStream.ps1',
  'Uninstall-CamStream.cmd', 'CamStreamPayload.zip', 'CamStream.WinUI.pdb'
]);
const runtimeName = 'WindowsAppRuntimeInstall-x64.exe';

function guidFor(key) {
  const h = crypto.createHash('md5').update('CamStream|' + key).digest();
  h[6] = (h[6] & 0x0f) | 0x30;
  h[8] = (h[8] & 0x3f) | 0x80;
  const s = h.toString('hex').toUpperCase();
  return `${s.slice(0, 8)}-${s.slice(8, 12)}-${s.slice(12, 16)}-${s.slice(16, 20)}-${s.slice(20, 32)}`;
}
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const files = [];
function walk(dir, rel = '') {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const relPath = rel ? `${rel}/${entry.name}` : entry.name;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, relPath);
    else files.push({ rel: relPath, full, name: entry.name, size: fs.statSync(full).size });
  }
}
walk(stage);

const runtime = files.find(f => f.rel === runtimeName);
const content = files.filter(f => !skip.has(f.rel) && f.rel !== runtimeName);
content.sort((a, b) => a.rel.localeCompare(b.rel));

// Build directory tree
const tree = { name: '', children: new Map(), files: [] };
for (const f of content) {
  const parts = f.rel.split('/');
  let node = tree;
  for (const part of parts.slice(0, -1)) {
    if (!node.children.has(part)) node.children.set(part, { name: part, children: new Map(), files: [] });
    node = node.children.get(part);
  }
  node.files.push(f);
}

const dirIds = [];
function idFor(rel) {
  return 'dir' + crypto.createHash('md5').update(rel).digest('hex').slice(0, 12);
}
function emitDir(node, rel, parentId, depth) {
  const pad = '  '.repeat(depth);
  let xml = '';
  const kids = [...node.children.keys()].sort();
  for (const childName of kids) {
    const childRel = rel ? `${rel}/${childName}` : childName;
    const child = node.children.get(childName);
    const childId = idFor(childRel);
    dirIds.push(childId);
    xml += `${pad}<Directory Id="${childId}" Name="${esc(childName)}">\n`;
    xml += emitDir(child, childRel, childId, depth + 1);
    xml += `${pad}</Directory>\n`;
  }
  return xml;
}

const components = [];
const componentIds = [];
function emitComponents(node, rel, parentId) {
  for (const childName of [...node.children.keys()].sort()) {
    const childRel = rel ? `${rel}/${childName}` : childName;
    emitComponents(node.children.get(childName), childRel, idFor(childRel));
  }
  for (const f of node.files.sort((a, b) => a.rel.localeCompare(b.rel))) {
    const h = crypto.createHash('md5').update(f.rel).digest('hex');
    const compId = 'cmp' + h.slice(0, 16);
    const fileId = 'fil' + h.slice(16, 32);
    componentIds.push(compId);
    components.push(
      `    <Component Id="${compId}" Directory="${parentId}" Guid="${guidFor(f.rel)}">\n` +
      `      <File Id="${fileId}" Source="${esc(f.full)}" KeyPath="yes" />\n` +
      `    </Component>`
    );
  }
}

const dirXml = emitDir(tree, '', 'INSTALLFOLDER', 3);
emitComponents(tree, '', 'INSTALLFOLDER');

const features = componentIds.map(id => `      <ComponentRef Id="${id}" />`);
if (runtime) features.push('      <ComponentRef Id="cmpWindowsAppRuntimeInstaller" />');

const customAction = runtime
  ? `
    <CustomAction Id="InstallWindowsAppRuntime" FileRef="RuntimeInstallerFile" ExeCommand="/quiet /norestart"
                  Execute="deferred" Impersonate="no" Return="ignore" />
    <InstallExecuteSequence>
      <Custom Action="InstallWindowsAppRuntime" After="InstallFiles" Condition="NOT Installed AND NOT WINDOWSAPPRUNTIME16" />
    </InstallExecuteSequence>`
  : '';

const runtimeComponent = runtime
  ? `    <Component Id="cmpWindowsAppRuntimeInstaller" Directory="INSTALLFOLDER" Guid="${guidFor('WindowsAppRuntimeInstall-x64.exe')}">
      <File Id="RuntimeInstallerFile" Source="${esc(runtime.full)}" KeyPath="yes" />
    </Component>`
  : '';

const runtimeSearch = runtime
  ? `    <Property Id="WINDOWSAPPRUNTIME16">
      <RegistrySearch Id="SearchRuntime16" Root="HKLM" Key="SOFTWARE\\Microsoft\\WindowsAppRuntime\\InstalledVersions\\1.6\\x64" Name="Version" Type="raw" Bitness="always64" />
    </Property>`
  : '';

const wxs = `<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="CamStream" Manufacturer="CamStream" Version="${version}" UpgradeCode="8F2B6C1E-4D3A-4B77-9C55-1A2E4D6F8B90"
           Scope="perMachine" Compressed="yes" Language="2052">
    <SummaryInformation Description="CamStream camera to RTSP streaming" Manufacturer="CamStream" />
    <MajorUpgrade DowngradeErrorMessage="A newer version of CamStream is already installed." />
    <MediaTemplate EmbedCab="yes" CompressionLevel="high" />

    <StandardDirectory Id="ProgramFiles6432Folder">
      <Directory Id="INSTALLFOLDER" Name="CamStream">
${dirXml}      </Directory>
    </StandardDirectory>
    <StandardDirectory Id="ProgramMenuFolder">
      <Directory Id="AppProgramMenuDir" Name="CamStream" />
    </StandardDirectory>
    <StandardDirectory Id="DesktopFolder" />

${runtimeSearch}
    <Feature Id="ProductFeature" Title="CamStream" Level="1">
${features.join('\n')}
      <ComponentGroupRef Id="Shortcuts" />
    </Feature>
${customAction}
  </Package>

  <Fragment>
${components.join('\n')}
${runtimeComponent}
  </Fragment>

  <Fragment>
    <ComponentGroup Id="Shortcuts">
      <Component Id="cmpStartMenuShortcut" Directory="AppProgramMenuDir" Guid="${guidFor('shortcut-startmenu')}">
        <Shortcut Id="StartMenuShortcut" Name="CamStream" Description="CamStream RTSP streaming"
                  Target="[INSTALLFOLDER]CamStream.WinUI.exe" WorkingDirectory="INSTALLFOLDER" />
        <RemoveFolder Id="RemoveAppProgramMenuDir" Directory="AppProgramMenuDir" On="uninstall" />
        <RegistryValue Root="HKMU" Key="Software\\CamStream" Name="startmenu" Type="integer" Value="1" KeyPath="yes" />
      </Component>
      <Component Id="cmpDesktopShortcut" Directory="DesktopFolder" Guid="${guidFor('shortcut-desktop')}">
        <Shortcut Id="DesktopShortcut" Name="CamStream" Description="CamStream RTSP streaming"
                  Target="[INSTALLFOLDER]CamStream.WinUI.exe" WorkingDirectory="INSTALLFOLDER" />
        <RegistryValue Root="HKMU" Key="Software\\CamStream" Name="desktop" Type="integer" Value="1" KeyPath="yes" />
      </Component>
      <Component Id="cmpAppRegistry" Directory="INSTALLFOLDER" Guid="${guidFor('registry-app')}">
        <RegistryValue Root="HKMU" Key="Software\\CamStream" Name="InstallDir" Type="string" Value="[INSTALLFOLDER]" KeyPath="yes" />
      </Component>
    </ComponentGroup>
  </Fragment>
</Wix>
`;

fs.mkdirSync(path.dirname(outFile), { recursive: true });
fs.writeFileSync(outFile, wxs, 'utf8');
console.log(JSON.stringify({ outFile, files: content.length, directories: dirIds.length, runtime: Boolean(runtime) }, null, 2));
