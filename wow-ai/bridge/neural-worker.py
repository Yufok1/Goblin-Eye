"""Local character speech: verified local models and buffered desktop audio."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,sys,threading,time,types
sys.path.insert(0,str(Path(__file__).resolve().parent))
from voice_pipeline import AudioPlayer,Inbox,Cancelled,PlaybackBuffer,single_batch_meanflow,bounded_hift,decode_speech
from graph_decoder import decode_graph
def emit(**data):print('@voice '+json.dumps(data),flush=True)

def trim_causal_masks(transformer,limit=2048):
    for block in transformer.h:
        block.attn.bias=block.attn.bias[:,:,:limit,:limit].clone()
def chunks(text,first=90,following=220):
    current='';limit=first
    for word in text.split():
        if current and len(current)+len(word)+1>limit:yield current;current='';limit=following
        current=(current+' '+word).strip()
        if len(current)>=limit*0.7 and re.search(r'[.!?]$',word):yield current;current='';limit=following
    if current:yield current
def configure_utf8_streams():
    # The bridge writes UTF-8 JSON over pipes; Windows locale is not its codec.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='strict')


def main():
    configure_utf8_streams()
    ap=argparse.ArgumentParser();ap.add_argument('--assets',required=True);ap.add_argument('--parent',type=int,required=True)
    ap.add_argument('--quantize',action='store_true');ap.add_argument('--engine',choices=['chatterbox','nano'],default='chatterbox')
    ap.add_argument('--device',choices=['cpu','hybrid','cuda-fp16','cuda-hybrid'],default='cpu');ap.add_argument('--threads',type=int,default=2)
    ap.add_argument('--packages');ap.add_argument('--torch-package')
    args=ap.parse_args();assets=Path(args.assets).resolve();os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    # Synchronization handle watches our owning bridge, never the game process.
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    handles=[kernel.OpenProcess(0x100000,False,parent) for parent in dict.fromkeys([args.parent,os.getppid()])]
    if not all(handles):raise RuntimeError('Owning speech process is unavailable')
    def watch():
        while True:
            # Windows venv python.exe can be a launcher. Stop kills that parent;
            # watching only the still-running bridge would orphan this worker.
            if any(kernel.WaitForSingleObject(handle,0)==0 for handle in handles):os._exit(0)
            if kernel.WaitForSingleObject(handles[0],1000)==0:os._exit(0)
    threading.Thread(target=watch,daemon=True).start();emit(phase='Loading character voice')
    current_request=None;metrics={}
    if args.packages:sys.path.insert(0,str(Path(args.packages).resolve()))
    if args.torch_package:sys.path.insert(0,str(Path(args.torch_package).resolve()))
    import torch,soundfile as sf
    torch.set_num_threads(max(1,min(args.threads,os.cpu_count() or 1)));decoder_device='cpu';vocoder_device='cpu';voice_dtype=torch.float32
    if args.engine=='nano':
        sys.path.insert(0,str(assets/'nano-code'))
        from chatterbox.tts_turbo import ChatterboxTurboTTS,Conditionals,punc_norm
        from chatterbox.models.s3gen.const import S3GEN_SIL
        emit(phase='Loading local voice weights',engine='nano',device='cpu')
        model=ChatterboxTurboTTS.from_local(assets/'models/nano',device='cpu',nano=True)
        del model.t3.text_head  # Training-only logits, unused by speech inference.
        # Upstream GPT2 allocates 8196-square causal masks (~769 MiB). Our
        # bounded chunks need at most 375 prompt + 512 text + 1001 speech tokens.
        # Copy the top-left mask; a view would retain the entire allocation.
        trim_causal_masks(model.t3.tfmr)
        def check_cancel(module,inputs):
            if current_request:current_request.check()
        model.t3.tfmr.register_forward_pre_hook(check_cancel)
        decoder=model.s3gen.flow.decoder;original_solver=decoder.solve_euler
        optimized_solver=types.MethodType(single_batch_meanflow(original_solver),decoder)
        decoder.solve_euler=optimized_solver
        hift=model.s3gen.mel2wav;original_hift=hift.inference
        optimized_hift=types.MethodType(bounded_hift(original_hift,check=lambda:current_request.check() if current_request else None),hift)
        hift.inference=optimized_hift
        if args.device=='hybrid' and torch.cuda.is_available():
            free,_=torch.cuda.mem_get_info()
            if free>=1800*1024*1024:
                try:model.t3.to('cuda');decoder_device='cuda'
                except torch.cuda.OutOfMemoryError:model.t3.to('cpu');torch.cuda.empty_cache()
        if args.quantize and decoder_device=='cpu':
            # GPT-2 uses transposed Conv1D projections; expose them as equivalent
            # Linear layers so CPU int8 quantization covers its actual decoder.
            from transformers.pytorch_utils import Conv1D
            def linearize(module):
                for name,child in list(module.named_children()):
                    if isinstance(child,Conv1D):
                        linear=torch.nn.Linear(child.weight.shape[0],child.weight.shape[1],bias=True)
                        linear.weight.data=child.weight.detach().t().contiguous();linear.bias.data=child.bias.detach().clone()
                        linear.nf=child.nf;setattr(module,name,linear)
                    else:linearize(child)
            linearize(model.t3.tfmr)
            model.t3.tfmr=torch.ao.quantization.quantize_dynamic(model.t3.tfmr,{torch.nn.Linear},dtype=torch.qint8,inplace=True)
        def generate(text,settings,compare=False):
            nonlocal metrics
            started=time.monotonic()
            tokens=model.tokenizer(punc_norm(text),return_tensors='pt',padding=True,truncation=True,max_length=512).input_ids.to(decoder_device)
            model.conds.t3=model.conds.t3.to(device=decoder_device,dtype=voice_dtype)
            decoder_comparison=None
            with torch.autocast(device_type='cuda',dtype=torch.float16,enabled=decoder_device=='cuda'):
                if compare:
                    torch.manual_seed(737);original_start=time.monotonic()
                    original_tokens=model.t3.inference_turbo(t3_cond=model.conds.t3,text_tokens=tokens,temperature=0.7,top_k=1000,top_p=0.95,repetition_penalty=1.2)
                    if decoder_device=='cuda':torch.cuda.synchronize()
                    original_seconds=time.monotonic()-original_start;torch.manual_seed(737)
                fast_start=time.monotonic()
                if decoder_device=='cuda' and not compare:
                    speech=decode_graph(model.t3,model.conds.t3,tokens,current_request.check if current_request else None)
                else:speech=decode_speech(model.t3,model.conds.t3,tokens)
                if compare:
                    if decoder_device=='cuda':torch.cuda.synchronize()
                    identical=torch.equal(speech,original_tokens)
                    decoder_comparison={'original_seconds':round(original_seconds,3),'optimized_seconds':round(time.monotonic()-fast_start,3),'identical_tokens':identical}
                    if not identical:raise RuntimeError('Optimized speech tokens did not match baseline.')
            if decoder_device=='cuda':torch.cuda.synchronize()
            decoded=time.monotonic()
            speech=torch.cat([speech[speech<6561].to(vocoder_device),torch.tensor([S3GEN_SIL]*3,device=vocoder_device).long()])
            comparison=None
            if compare:
                decoder.solve_euler=original_solver;hift.inference=original_hift;torch.manual_seed(991)
                baseline,_=model.s3gen.inference(speech_tokens=speech,ref_dict=model.conds.gen,n_cfm_timesteps=2)
                if vocoder_device=='cuda':torch.cuda.synchronize()
                baseline_time=time.monotonic()-decoded
                decoder.solve_euler=optimized_solver;hift.inference=optimized_hift;torch.manual_seed(991)
            render_start=time.monotonic()
            wav,_=model.s3gen.inference(speech_tokens=speech,ref_dict=model.conds.gen,n_cfm_timesteps=2)
            if vocoder_device=='cuda':torch.cuda.synchronize()
            rendered=time.monotonic()
            if compare:
                difference=(baseline-wav).abs()
                comparison={'baseline_seconds':round(baseline_time,3),'optimized_seconds':round(rendered-render_start,3),'max_difference':difference.max().item(),'rms_difference':difference.square().mean().sqrt().item()}
                if not torch.allclose(wav,baseline,atol=0.003,rtol=0.01):raise RuntimeError('Optimized audio did not match baseline.')
            audio=model.watermarker.apply_watermark(wav.squeeze(0).detach().float().cpu().numpy(),sample_rate=model.sr)
            metrics={'decoder_seconds':round(decoded-started,3),'renderer_seconds':round(rendered-render_start,3),'watermark_seconds':round(time.monotonic()-rendered,3),'audio_seconds':round(len(audio)/model.sr,3)}
            if decoder_device=='cuda':metrics['peak_gpu_mb']=round(torch.cuda.max_memory_allocated()/1048576)
            if comparison:metrics['comparison']=comparison
            if decoder_comparison:metrics['decoder_comparison']=decoder_comparison
            return audio
        engine_identity='nano-71ccd1d-v1'
    else:
        from chatterbox.tts import ChatterboxTTS,Conditionals
        model=ChatterboxTTS.from_local(assets/'models/checkpoints',device='cpu')
        if args.quantize:model.t3.tfmr=torch.ao.quantization.quantize_dynamic(model.t3.tfmr,{torch.nn.Linear},dtype=torch.qint8,inplace=True)
        def generate(text,settings):return model.generate(text,**settings).squeeze().detach().cpu().numpy()
        engine_identity='chatterbox-original-v1'
    profiles={'orc':{'exaggeration':0.3,'cfg_weight':0.6},'goblin':{'exaggeration':0.9,'cfg_weight':0.8}}
    conds={};output=assets/'playback';cache=output/'cache';cache.mkdir(parents=True,exist_ok=True);conditions=assets/'conditioning';conditions.mkdir(exist_ok=True)
    def prepare(profile):
        if profile not in profiles:raise ValueError('Unknown character voice')
        if profile in conds:model.conds=conds[profile];return
        reference=assets/'references'/f'{profile}.wav';key=hashlib.sha256(reference.read_bytes()).hexdigest()[:16]
        cached=conditions/f'{engine_identity}-{profile}-{key}.pt'
        if cached.exists():model.conds=Conditionals.load(cached,map_location='cpu')
        else:model.prepare_conditionals(str(reference),exaggeration=profiles[profile]['exaggeration']);model.conds.save(cached)
        conds[profile]=model.conds
    if args.engine=='nano' and args.device in ('cuda-fp16','cuda-hybrid'):
        if not torch.cuda.is_available():raise RuntimeError('The configured GPU voice runtime cannot access CUDA.')
        # Read device capacity and limit only this audio process's allocator.
        free,total=torch.cuda.mem_get_info()
        try:
            available=subprocess.run(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=5)
            if available.returncode==0:free=min(free,int(available.stdout.strip().splitlines()[0])*1024*1024)
        except Exception:pass
        budget=min((2400 if args.device=='cuda-fp16' else 1000)*1024*1024,free-650*1024*1024)
        if budget<(2000 if args.device=='cuda-fp16' else 600)*1024*1024:raise RuntimeError('Not enough free graphics memory for the fast voice reader. Desktop speech remains available.')
        torch.cuda.set_per_process_memory_fraction(budget/total)
        with torch.inference_mode():
            for profile in profiles:prepare(profile)
        # Both supported voice references are now embedded. The tokenizer and
        # speaker encoder are only used to prepare references, never to render
        # from these cached conditionals. Keep a tiny parameter for s3gen.device.
        removed=sum(p.numel()*p.element_size() for module in (model.s3gen.tokenizer,model.s3gen.speaker_encoder) for p in module.parameters())
        class PreparedReferenceOnly(torch.nn.Module):
            def __init__(self):
                super().__init__();self.anchor=torch.nn.Parameter(torch.empty(0),requires_grad=False)
            def forward(self,*args,**kwargs):raise RuntimeError('Voice references must be prepared before GPU rendering.')
        model.s3gen.tokenizer=PreparedReferenceOnly();model.s3gen.speaker_encoder=None
        emit(phase='Using prepared voice references',released_reference_mb=round(removed/1048576))
        emit(phase='Preparing GPU voice',engine='nano',device='cuda')
        model.t3=model.t3.half().to('cuda');decoder_device='cuda';voice_dtype=torch.float16
        # Waveform rendering needs float32: half precision can generate NaNs.
        if args.device=='cuda-fp16':model.s3gen=model.s3gen.to('cuda');vocoder_device='cuda'
        engine_identity+='-'+args.device+'-v2'
    emit(phase='Voice model loaded',loaded=True,engine=args.engine,device=decoder_device);kernels_ready=False
    # Do not hold stdin's buffered-reader lock while native libraries initialize.
    inbox=Inbox(sys.stdin,emit)
    while True:
        queued=inbox.jobs.get()
        if queued is None:break
        request={};player=None
        try:
            current_request=queued;queued.check();request=queued.data;profile=request['profile']
            if request.get('warm'):
                with torch.inference_mode():
                    prepare(profile)
                    if decoder_device=='cuda' and not kernels_ready:
                        emit(phase='Warming speech renderer',engine=args.engine,device=decoder_device)
                        generate('Voice ready.',profiles[profile]);kernels_ready=True
                emit(warmed=True,phase='Voice ready',engine=args.engine,device=decoder_device);continue
            text=request['text'];request_id=request['id'];volume=request['volume']
            if profile not in profiles or not isinstance(text,str) or not text.strip() or len(text)>16000:raise ValueError('Invalid neural speech request')
            if not isinstance(volume,int) or not 0<=volume<=100:raise ValueError('Invalid speech volume')
            if request.get('compare'):
                with torch.inference_mode():prepare(profile);generate(text,profiles[profile],compare=True)
                emit(id=request_id,done=True,metrics=metrics);continue
            parts=list(chunks(text));prefill=len(parts);buffer=PlaybackBuffer(parts)
            player=AudioPlayer(request_id,volume,len(parts),emit,queued.cancelled,prefill=prefill);queued.player=player;settings=profiles[profile]
            with torch.inference_mode():
                prepare(profile)
                for index,chunk in enumerate(parts,1):
                    queued.check();cached=False;chunk_started=time.monotonic()
                    key=hashlib.sha256((engine_identity+'-lichfx1\n'+profile+'\n'+chunk).encode()).hexdigest();target=cache/f'{key}.wav'
                    if request.get('fresh'):target=cache/(hashlib.sha256((request_id+key).encode()).hexdigest()+'.wav')
                    if not target.exists():
                        emit(id=request_id,phase=f'Generating {index}/{len(parts)}',generating=index,total=len(parts))
                        wav=generate(chunk,settings)
                        queued.check()
                        peak=float(abs(wav).max())
                        if not 0.0001<=peak<100:raise RuntimeError('Voice generated invalid or near-silent audio.')
                        if peak>0.95:wav=wav*(0.95/peak)
                        sf.write(target,wav,model.sr,subtype='PCM_16')
                    else:cached=True
                    audio=sf.info(target);target.touch();emit(id=request_id,rendered=index,total=len(parts),cached=cached,metrics=metrics if not cached else {'audio_seconds':round(audio.duration,3)})
                    player.add(target,index,audio.duration);emit(id=request_id,queued=index,total=len(parts))
                    can_start,reserve=buffer.add(len(chunk),audio.duration,time.monotonic()-chunk_started,cached)
                    if can_start:player.start.set()
                    if not player.start.is_set():emit(id=request_id,phase=f'Buffering voice: {round(buffer.audio)}s ready',buffer_seconds=round(buffer.audio,1),reserve_seconds=reserve)
            player.finish();player=None;emit(id=request_id,done=True,phase='Idle')
            cached_files=sorted(cache.glob('*.wav'),key=lambda p:p.stat().st_mtime,reverse=True);size=0
            for cached_file in cached_files:
                size+=cached_file.stat().st_size
                if size>64*1024*1024:cached_file.unlink(missing_ok=True)
        except Cancelled:
            if player:player.cancel();player.finish();player=None
            emit(id=request.get('id',''),cancelled=True)
        except Exception as error:
            # Never turn a rendering failure into partial playback and postpone
            # the error until that partial report finishes speaking.
            if player:
                player.cancel()
                try:player.finish()
                except Exception:pass
            emit(id=request.get('id',''),error=str(error)[:300])
        finally:current_request=None;inbox.completed(queued)
if __name__=='__main__':
    try:main()
    except Exception as error:emit(error=str(error)[:300]);sys.exit(1)
