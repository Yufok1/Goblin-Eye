import importlib.util,io,json,queue,sys,threading,unittest
from pathlib import Path
from unittest.mock import patch
source=Path(__file__).resolve().parents[1]/'bridge/neural-worker.py'
spec=importlib.util.spec_from_file_location('voice_worker',source);worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
import voice_pipeline as pipeline

class FakeAudio:
    def __init__(self,release=None,error=None):
        self.events=queue.Queue();self.commands=[];self.returncode=None;self.release=release;self.error=error;self.entered=threading.Event();self.token='';self.stdin=self;self.stdout=self
    def write(self,line):
        command=json.loads(line);self.commands.append(command)
        if command.get('stop'):self.events.put({'token':self.token,'cancelled':True});return
        self.token=command['token'];self.entered.set()
        if self.error:self.events.put({'error':self.error});return
        self.events.put({'token':self.token,'playing':True})
        def complete():
            if self.release:self.release.wait(3)
            self.events.put({'token':command['token'],'done':True})
        threading.Thread(target=complete,daemon=True).start()
    def flush(self):pass
    def close(self):self.returncode=0
    def poll(self):return self.returncode
    def wait(self,timeout=None):self.returncode=0;return 0
    def kill(self):self.returncode=1
    def __iter__(self):
        while True:yield '@audio '+json.dumps(self.events.get())+'\n'

class WorkerTests(unittest.TestCase):
    def test_fast_reader_starts_after_two_chunks_of_a_long_report(self):
        buffer=pipeline.PlaybackBuffer(['x'*90]+['x'*220]*37)
        self.assertFalse(buffer.add(90,6,1)[0])
        self.assertTrue(buffer.add(220,14,2)[0])
    def test_cached_audio_does_not_hide_slow_uncached_rendering(self):
        buffer=pipeline.PlaybackBuffer(['x'*220]*38)
        buffer.add(220,14,20)
        start,reserve=buffer.add(220,14,0,cached=True)
        self.assertFalse(start);self.assertGreater(reserve,100)
    def test_renderer_can_queue_all_38_chunks_without_waiting_for_playback(self):
        with patch.object(pipeline.subprocess,'Popen') as spawn:
            player=worker.AudioPlayer('long',70,38,lambda **event:None,prefill=38)
            for index in range(1,38):player.add(Path(f'C:/chunk{index}.wav'),index,14)
            self.assertEqual(player.pending.qsize(),37)
            player.cancel();player.finish();spawn.assert_not_called()
    def test_rendering_failure_discards_prepared_audio(self):
        with patch.object(pipeline.subprocess,'Popen') as spawn:
            player=worker.AudioPlayer('failed',70,38,lambda **event:None,prefill=38)
            for index in range(1,10):player.add(Path(f'C:/chunk{index}.wav'),index,14)
            player.cancel();player.finish()
            spawn.assert_not_called();self.assertFalse(player.thread.is_alive())
    def test_report_chunks_preserve_all_words_and_start_short(self):
        text=' '.join(['Here is a real report about herbs and auction prices.']*20)
        parts=list(worker.chunks(text));self.assertLessEqual(len(parts[0]),90)
        self.assertEqual(' '.join(parts).split(),text.split());self.assertGreater(len(parts[1]),len(parts[0]))
    def test_playback_prefills_and_reuses_one_helper_for_all_chunks(self):
        fake=FakeAudio();events=[]
        with patch.object(pipeline.subprocess,'Popen',return_value=fake) as spawn:
            player=worker.AudioPlayer('report',70,2,lambda **event:events.append(event))
            player.add(Path('C:/first.wav'),1,3);self.assertFalse(player.start.is_set());spawn.assert_not_called()
            player.add(Path('C:/second.wav'),2,3);player.finish()
        self.assertEqual(spawn.call_count,1);self.assertEqual(len([c for c in fake.commands if c.get('audioFile')]),2)
        self.assertEqual(fake.commands[0]['volume'],70);self.assertEqual([e['playing'] for e in events if 'playing' in e],[1,2])
        self.assertNotIn('shell',spawn.call_args.kwargs)
    def test_stop_cancels_playing_audio_and_discards_queued_chunks(self):
        release=threading.Event();fake=FakeAudio(release)
        with patch.object(pipeline.subprocess,'Popen',return_value=fake):
            player=worker.AudioPlayer('report',70,2,lambda **event:None,prefill=1)
            player.add(Path('C:/first.wav'),1,3);self.assertTrue(fake.entered.wait(3))
            player.add(Path('C:/second.wav'),2,3);player.cancel();player.finish();release.set()
        self.assertEqual(len([c for c in fake.commands if c.get('audioFile')]),1)
        self.assertTrue(any(c.get('stop') for c in fake.commands))
    def test_queued_request_is_cancelled_before_generation(self):
        stream=io.StringIO('{"id":"old","text":"report"}\n{"cancel":"old"}\n')
        inbox=pipeline.Inbox(stream,lambda **event:None);request=inbox.jobs.get(timeout=3)
        self.assertIsNone(inbox.jobs.get(timeout=3))
        with self.assertRaises(pipeline.Cancelled):request.check()
        inbox.completed(request);self.assertEqual(inbox.requests,{})
    def test_audio_failure_is_reported_instead_of_silent_success(self):
        with patch.object(pipeline.subprocess,'Popen',return_value=FakeAudio(error='Audio device failed')):
            player=worker.AudioPlayer('report',70,1,lambda **event:None);player.add(Path('C:/audio.wav'),1,3)
            with self.assertRaisesRegex(RuntimeError,'Audio device failed'):player.finish()
    def test_full_report_waits_for_every_chunk_and_reuses_one_audio_helper(self):
        fake=FakeAudio();events=[]
        with patch.object(pipeline.subprocess,'Popen',return_value=fake) as spawn:
            player=worker.AudioPlayer('full',70,8,lambda **event:events.append(event),prefill=8)
            for index in range(1,8):
                player.add(Path(f'C:/chunk{index}.wav'),index,3)
                self.assertFalse(player.start.is_set());spawn.assert_not_called()
            player.add(Path('C:/chunk8.wav'),8,3);player.finish()
        self.assertEqual(spawn.call_count,1)
        self.assertEqual([e['playing'] for e in events if 'playing' in e],list(range(1,9)))
    def test_stop_during_full_report_preparation_never_starts_audio(self):
        with patch.object(pipeline.subprocess,'Popen') as spawn:
            player=worker.AudioPlayer('full',70,8,lambda **event:None,prefill=8)
            for index in range(1,5):player.add(Path(f'C:/chunk{index}.wav'),index,3)
            player.cancel();player.finish();spawn.assert_not_called()
if __name__=='__main__':unittest.main()


class EncodingTests(unittest.TestCase):
    def test_windows_legacy_streams_are_reconfigured_before_json_input(self):
        import hashlib
        text='ASCII; “quotes”; café’s résumé; Éowyn — done.'
        source=io.BytesIO((json.dumps({'text':text},ensure_ascii=False)+'\n').encode('utf-8'))
        sink=io.BytesIO()
        incoming=io.TextIOWrapper(source,encoding='cp1252',errors='surrogateescape')
        outgoing=io.TextIOWrapper(sink,encoding='cp1252')
        with patch.object(worker.sys,'stdin',incoming),patch.object(worker.sys,'stdout',outgoing),patch.object(worker.sys,'stderr',outgoing):
            worker.configure_utf8_streams()
            decoded=json.loads(incoming.readline())['text']
            self.assertEqual(decoded,text)
            self.assertEqual(hashlib.sha256(decoded.encode('utf-8')).hexdigest(),hashlib.sha256(text.encode('utf-8')).hexdigest())
            outgoing.write(decoded);outgoing.flush()
            self.assertEqual(sink.getvalue().decode('utf-8'),text)
