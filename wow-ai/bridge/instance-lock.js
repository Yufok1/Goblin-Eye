'use strict';
// Serialize acquisition/recovery so two starters cannot reclaim each other's lock.
const fs=require('fs'),{randomUUID}=require('crypto');
function alive(pid) {
 if(!Number.isSafeInteger(pid)||pid<1)return true; // malformed ownership fails closed
 try{process.kill(pid,0);return true;}catch(e){return e.code!=='ESRCH';}
}
function acquire(file) {
 const guard=file+'.acquiring';
 try{fs.mkdirSync(guard);}catch{throw Error('Another bridge is acquiring its instance lock. Retry after it exits.');}
 const token=randomUUID();
 try {
  if(fs.existsSync(file)) {
   let owner;try{owner=JSON.parse(fs.readFileSync(file,'utf8'));}catch{throw Error('Bridge lock is unreadable; inspect it before removing it.');}
   if(alive(owner.pid))throw Error(`Another bridge owns these state files (PID ${owner.pid}). Stop it before starting a second bridge or --inject.`);
   fs.unlinkSync(file);
  }
  fs.writeFileSync(file,JSON.stringify({pid:process.pid,token}),{flag:'wx'});
 } finally {fs.rmdirSync(guard);}
 return ()=>{try{if(JSON.parse(fs.readFileSync(file,'utf8')).token===token)fs.unlinkSync(file);}catch{}};
}
module.exports={acquire};
