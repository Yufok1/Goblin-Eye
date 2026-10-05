'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),os=require('os'),path=require('path');
const {spawnSync}=require('child_process'),{acquire}=require('../bridge/instance-lock');
test('a second process cannot acquire the same bridge state; release permits restart',()=>{
 const file=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'wow-lock-')),'bridge.lock'),release=acquire(file);
 const mod=path.resolve(__dirname,'../bridge/instance-lock');
 const code=`try{require(${JSON.stringify(mod)}).acquire(${JSON.stringify(file)});process.exit(99);}catch(e){console.error(e.message);process.exit(2);}`;
 const c=spawnSync(process.execPath,['-e',code],{encoding:'utf8'});assert.equal(c.status,2);assert.match(c.stderr,/Another bridge owns/);assert.equal(JSON.parse(fs.readFileSync(file)).pid,process.pid);
 release();const next=acquire(file);next();assert.equal(fs.existsSync(file),false);
});
test('dead owner recovery is serialized; malformed ownership fails closed',()=>{
 const file=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'wow-lock-')),'bridge.lock');
 const ended=spawnSync(process.execPath,['-e','process.exit(0)']);fs.writeFileSync(file,JSON.stringify({pid:ended.pid,token:'old'}));const release=acquire(file);release();
 fs.writeFileSync(file,'broken');assert.throws(()=>acquire(file),/unreadable/);assert.equal(fs.readFileSync(file,'utf8'),'broken');
});
