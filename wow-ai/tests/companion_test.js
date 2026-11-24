'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('fs'), os = require('os'), path = require('path');
const {CompanionClient} = require('../bridge/companion-client');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
test('background worker starts quietly and launches model helpers only on an explicit request', async t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'goblin-quiet-start-'));
  const marker = path.join(directory, 'cli-started');
  const script = path.join(directory, 'models.js');
  fs.writeFileSync(script, `require('fs').writeFileSync(${JSON.stringify(marker)},'started');
    require('readline').createInterface({input:process.stdin}).on('line',line=>{
      const r=JSON.parse(line);if(r.id)console.log(JSON.stringify({id:r.id,result:r.id===1?{}:{data:[{model:'fixture',displayName:'Fixture'}]}}));
    });`);
  const client = new CompanionClient();
  t.after(async () => {
    const child=client.child;client.close();
    if(child&&child.exitCode===null)await new Promise(resolve=>child.once('exit',resolve));
  });
  const config={agent:'codex',backgroundModelDiscovery:false,
    agents:Object.fromEntries(require('../bridge/agents').agentIds().map(id=>[id,{path:script}]))};
  await client.start({directory,config,background:true,cwd:directory});
  await pause(250);
  assert.equal(fs.existsSync(marker),false,'idle startup must not probe installed CLIs');
  await client.catalog.request({chat:'explicit',text:'{"agent":"codex"}'});
  assert.equal(fs.existsSync(marker),true);
  assert.equal(client.catalog.wire()[0].items[0].id,'fixture');
});

test('separate companion preserves voice settings, replies and model controls across worker restart', async t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'goblin-companion-'));
  const script = path.join(directory, 'models.js');
  const isolation = process.platform === 'win32' ? `
    const check=require('child_process').spawnSync(${JSON.stringify(path.resolve(__dirname,'../../python/python.exe'))},
      [${JSON.stringify(path.join(__dirname,'desktop_probe.py'))},'--assert-only'],{encoding:'utf8'});
    if(check.status!==0)throw Error(check.stderr || 'CLI helper escaped the private desktop');
  ` : '';
  fs.writeFileSync(script, `${isolation}require('readline').createInterface({input:process.stdin}).on('line',line=>{
    const r=JSON.parse(line);if(r.id)console.log(JSON.stringify({id:r.id,result:r.id===1?{}:{data:[{model:'fixture',displayName:'Fixture'}]}}));
  });`);
  const client = new CompanionClient();
  t.after(async () => {const child=client.child;client.close();if(child&&child.exitCode===null)await new Promise(resolve=>child.once('exit',resolve));});
  await client.start({directory, config: {agent: 'codex', agents: {codex: {path: script}}}, background: false, cwd: directory});
  assert.notEqual(client.child.pid, process.pid);
  await client.speech.control('volume', '41');
  assert.equal(client.speech.info().volume, 41);
  assert.equal(JSON.parse(fs.readFileSync(path.join(directory, 'speech-settings.json'))).volume, 41);
  await client.speech.control('listen', 'missing', () => undefined);
  assert.match(client.speech.info().error, /no longer exists/);
  await client.speech.completed('Not automatically spoken while speech is off.');
  assert.equal(client.speech.info().busy, false);
  await client.catalog.request({chat: 'test', text: '{"agent":"codex"}'});
  assert.equal(client.catalog.wire()[0].items[0].id, 'fixture');
  assert.equal(client.catalog.cache.get('codex').items[0].id, 'fixture');
  const old = client.child.pid;
  client.child.kill();
  const until = Date.now()+12000;
  while (Date.now()<until && (!client.child || client.child.pid===old || client.speech.info().error)) await pause(50);
  assert.notEqual(client.child?.pid, old);
  assert.equal(client.speech.info().volume, 41);
  assert.equal(client.speech.info().busy, false, 'restart does not replay speech');
});
