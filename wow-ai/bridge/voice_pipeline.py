"""Cancelable requests, bounded prebuffer, and continuous desktop playback."""
from pathlib import Path
import json,os,queue,subprocess,threading,time

class Cancelled(Exception):pass

class Request:
    def __init__(self,data):self.data=data;self.cancelled=threading.Event();self.player=None
    def check(self):
        if self.cancelled.is_set():raise Cancelled()
    def cancel(self):
        self.cancelled.set()
        if self.player:self.player.cancel()

class Inbox:
    def __init__(self,stream,emit):
        self.jobs=queue.Queue();self.requests={};self.lock=threading.Lock();self.emit=emit
        threading.Thread(target=self.read,args=(stream,),daemon=True).start()
    def read(self,stream):
        try:
            for line in stream:
                data=json.loads(line)
                with self.lock:
                    if 'cancel' in data:
                        request=self.requests.get(data['cancel'])
                        if request:request.cancel()
                        continue
                    request=Request(data)
                    if data.get('id'):self.requests[data['id']]=request
                    self.jobs.put(request)
        except Exception as error:self.emit(error=str(error)[:300])
        finally:self.jobs.put(None)
    def completed(self,request):
        with self.lock:self.requests.pop(request.data.get('id'),None)

class AudioPlayer:
    def __init__(self,request_id,volume,total,emit,cancellation=None,prefill=2,helper=None):
        self.id=request_id;self.volume=volume;self.total=total;self.emit=emit
        # The queue contains file paths, not waveforms. Let fast generation get
        # well ahead of playback instead of stopping after three chunks.
        self.cancelled=cancellation or threading.Event();self.pending=queue.Queue(maxsize=max(3,total))
        self.start=threading.Event();self.lock=threading.Lock();self.child=None;self.error=None;self.added=0
        self.prefill=min(prefill,total);self.helper=helper or Path(__file__).with_name('stream-speak.ps1')
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def send(self,data):
        with self.lock:
            if self.child and self.child.poll() is None:
                self.child.stdin.write(json.dumps(data)+'\n');self.child.stdin.flush()
    def cancel(self):
        self.cancelled.set();self.start.set()
        try:self.send({'stop':True})
        except (OSError,ValueError):pass
    def run(self):
        self.start.wait();last_end=None
        try:
            while True:
                item=self.pending.get()
                try:
                    if item is None:return
                    if self.cancelled.is_set() or self.error:continue
                    target,index,duration=item
                    if self.child is None:
                        self.child=subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(self.helper),'-ParentId',str(os.getpid())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    if self.cancelled.is_set():continue
                    token=f'{self.id}:{index}';self.send({'audioFile':str(target),'volume':self.volume,'token':token})
                    for line in self.child.stdout:
                        if not line.startswith('@audio '):continue
                        event=json.loads(line[7:])
                        if event.get('error'):raise RuntimeError(event['error'])
                        if event.get('token')!=token:continue
                        if event.get('playing'):
                            now=time.monotonic();gap=round(now-last_end,3) if last_end else 0
                            self.emit(id=self.id,phase=f'Playing {index}/{self.total}',playing=index,total=self.total,gap_seconds=gap)
                            if self.cancelled.is_set():self.send({'stop':True})
                        if event.get('done') or event.get('cancelled'):
                            last_end=time.monotonic();self.emit(id=self.id,played=index,total=self.total);break
                    else:raise RuntimeError('Character audio helper exited unexpectedly.')
                finally:self.pending.task_done()
        except Exception as error:self.error=error
        finally:
            if self.child:
                try:self.child.stdin.close();self.child.wait(timeout=3)
                except Exception:self.child.kill()
            # Unblock producers after a helper failure.
            while True:
                try:self.pending.get_nowait();self.pending.task_done()
                except queue.Empty:break
    def add(self,target,index,duration):
        if self.cancelled.is_set():raise Cancelled()
        if self.error:raise self.error
        while True:
            try:self.pending.put((target,index,duration),timeout=0.1);break
            except queue.Full:
                if self.error:raise self.error
                if self.cancelled.is_set():raise Cancelled()
        self.added+=1
        if self.added>=self.prefill:self.start.set()
    def finish(self):
        self.start.set()
        while self.thread.is_alive():
            try:self.pending.put(None,timeout=0.1);break
            except queue.Full:pass
        self.thread.join()
        if self.error:raise self.error

class PlaybackBuffer:
    """Begin after a small reserve when rendering is faster than playback.

    A slower renderer needs enough reserve for its predicted remaining deficit.
    Cached chunks contribute audio but never make uncached rendering look fast.
    """
    def __init__(self, parts):
        self.total_chars=sum(map(len,parts));self.done_chars=0;self.audio=0.;self.ratios=[];self.parts=0
    def add(self, characters, duration, generation_seconds, cached=False):
        self.done_chars+=characters;self.audio+=duration;self.parts+=1
        if not cached:self.ratios.append(generation_seconds/max(duration,0.01))
        seconds_per_char=self.audio/max(self.done_chars,1)
        remaining_audio=(self.total_chars-self.done_chars)*seconds_per_char
        ratio=max(self.ratios[-6:],default=0)*1.15
        reserve=max(12.,max(0.,ratio-1.)*remaining_audio+10.)
        return self.parts>=2 and self.audio>=reserve,round(reserve,1)

def single_batch_meanflow(original):
    """Remove identical CFG batch duplication when meanflow has CFG disabled."""
    def solve(self,x,t_span,mu,mask,spks,cond,meanflow=False):
        if not meanflow or self.inference_cfg_rate!=0:
            return original(x,t_span,mu,mask,spks,cond,meanflow=meanflow)
        initial_dtype=x.dtype;dtype=self.estimator.dtype
        x,t_span,mu,mask,spks,cond=[v.to(dtype=dtype) if v.dtype.is_floating_point else v for v in (x,t_span,mu,mask,spks,cond)]
        batch=x.size(0)
        for t,r in zip(t_span[:-1],t_span[1:]):
            velocity=self.estimator.forward(x=x,mask=mask,mu=mu,t=t.expand(batch),spks=spks,cond=cond,r=r.expand(batch))
            x=x+(r-t)*velocity
        return x.to(initial_dtype)
    return solve

def bounded_hift(original,frames=192,overlap=32,check=None):
    """Bound waveform-convolution memory, preserving full F0/source continuity.

    The central region of each overlapping window retains its surrounding
    convolution context. Source harmonics are computed once for the full text.
    """
    def inference(self,speech_feat,cache_source=None):
        import torch
        if speech_feat.shape[-1]<=frames:
            if cache_source is None:cache_source=torch.zeros(1,1,0,device=speech_feat.device)
            return original(speech_feat,cache_source)
        f0=self.f0_predictor(speech_feat)
        source=self.f0_upsamp(f0[:,None]).transpose(1,2)
        source,_,_=self.m_source(source);source=source.transpose(1,2)
        if cache_source is not None and cache_source.shape[-1]:source[:,:,:cache_source.shape[-1]]=cache_source
        hop=source.shape[-1]//speech_feat.shape[-1];pieces=[];total=speech_feat.shape[-1]
        for start in range(0,total,frames):
            if check:check()
            end=min(start+frames,total);left=max(0,start-overlap);right=min(total,end+overlap)
            wav=self.decode(speech_feat[:,:,left:right],source[:,:,left*hop:right*hop])
            pieces.append(wav[:,(start-left)*hop:(end-left)*hop].clone())
        return torch.cat(pieces,dim=-1),source
    return inference

def decode_speech(t3,t3_cond,text_tokens,temperature=0.7,top_k=1000,top_p=0.95,repetition_penalty=1.2,max_gen_len=1000,check_every=8):
    """Same sampling, with batched EOS checks to avoid per-token GPU fences."""
    import torch
    from transformers.generation.logits_process import LogitsProcessorList,TemperatureLogitsWarper,TopKLogitsWarper,TopPLogitsWarper,RepetitionPenaltyLogitsProcessor
    processors=LogitsProcessorList([TemperatureLogitsWarper(temperature),TopKLogitsWarper(top_k),TopPLogitsWarper(top_p),RepetitionPenaltyLogitsProcessor(repetition_penalty)])
    start=t3.hp.start_speech_token*torch.ones_like(text_tokens[:,:1])
    embeds,_=t3.prepare_input_embeds(t3_cond=t3_cond,text_tokens=text_tokens,speech_tokens=start,cfg_weight=0.0)
    output=t3.tfmr(inputs_embeds=embeds,use_cache=True);past=output.past_key_values
    logits=processors(start,t3.speech_head(output[0][:,-1:])[:,-1,:])
    token=torch.multinomial(torch.nn.functional.softmax(logits,dim=-1),num_samples=1);generated=[token]
    for index in range(max_gen_len):
        output=t3.tfmr(inputs_embeds=t3.speech_emb(token),past_key_values=past,use_cache=True);past=output.past_key_values
        logits=processors(torch.cat(generated,dim=1),t3.speech_head(output[0])[:,-1,:])
        token=torch.multinomial(torch.nn.functional.softmax(logits,dim=-1),num_samples=1);generated.append(token)
        if len(generated)%check_every==0 or index==max_gen_len-1:
            block=torch.cat(generated[-check_every:],dim=1)
            if bool((block==t3.hp.stop_speech_token).any()):
                complete=torch.cat(generated,dim=1);stop=(complete[0]==t3.hp.stop_speech_token).nonzero()[0,0].item()
                return complete[:,:stop]
    return torch.cat(generated,dim=1)
