'use strict';
const fs=require('fs'),path=require('path'),os=require('os'),{performance}=require('perf_hooks');
const {SnapshotWriter}=require('../bridge/publisher');
async function measure(asynchronous) {
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'goblin-chat-disk-'));
 const files=Array.from({length:201},(_,i)=>({file:path.join(dir,String(i)+'.lua'),data:'-- saved research\n'+'x'.repeat(32768)}));
 const start=performance.now();
 const timer=new Promise(resolve=>setTimeout(()=>resolve(performance.now()-start),0));
 if(asynchronous)await new SnapshotWriter().enqueue(files);
 else for(const {file,data} of files){fs.writeFileSync(file+'.tmp',data);fs.renameSync(file+'.tmp',file);}
 const completionMs=performance.now()-start,timerDelayMs=await timer;
 return {files:201,bytesPerFile:Buffer.byteLength(files[0].data),completionMs:Math.round(completionMs),timerDelayMs:Math.round(timerDelayMs)};
}
(async()=>{
 const baseline=await measure(false),optimized=await measure(true);
 const result={baseline,optimized,scope:'One scratch-directory snapshot on this PC. Timer delay measures Node responsiveness; completion measures full disk delivery. Not a model/MCP or in-game FPS benchmark.'};
 fs.writeFileSync(path.join(__dirname,'../disk-benchmark.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
