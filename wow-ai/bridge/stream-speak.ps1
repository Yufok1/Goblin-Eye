param([int]$ParentId = 0)
$ErrorActionPreference='Stop'
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$synth=$null
function Send-AudioEvent($event){[Console]::Out.WriteLine(('@audio '+($event|ConvertTo-Json -Compress)));[Console]::Out.Flush()}
try {
 Add-Type -AssemblyName System.Speech
 $synth=[System.Speech.Synthesis.SpeechSynthesizer]::new()
 $synth.SetOutputToDefaultAudioDevice()
 $inputReader=[IO.StreamReader]::new([Console]::OpenStandardInput(),[Text.Encoding]::UTF8)
 $prompt=$null;$token='';$read=$inputReader.ReadLineAsync()
 Send-AudioEvent @{ready=$true}
 while($true){
  if($ParentId -gt 0 -and -not (Get-Process -Id $ParentId -ErrorAction SilentlyContinue)){break}
  if($read.IsCompleted){
   $line=$read.GetAwaiter().GetResult()
   if($null -eq $line){break}
   $request=$line|ConvertFrom-Json
   if($request.stop){
    $synth.SpeakAsyncCancelAll()
    if($prompt){Send-AudioEvent @{token=$token;cancelled=$true};$prompt=$null}
   }else{
    if($prompt){throw 'Another audio chunk is already playing.'}
    $file=[IO.Path]::GetFullPath([string]$request.audioFile)
    if($file -notmatch '^[A-Za-z]:\\' -or [IO.Path]::GetExtension($file) -ne '.wav' -or -not (Test-Path -LiteralPath $file -PathType Leaf)){throw 'Invalid local speech WAV.'}
    if($request.volume -lt 0 -or $request.volume -gt 100){throw 'Invalid speech volume.'}
    $synth.Volume=[int]$request.volume;$synth.Rate=0
    $builder=[System.Speech.Synthesis.PromptBuilder]::new();$builder.AppendAudio($file)
    $token=[string]$request.token;$prompt=$synth.SpeakAsync($builder)
    Send-AudioEvent @{token=$token;playing=$true}
   }
   $read=$inputReader.ReadLineAsync()
  }
  if($prompt -and $prompt.IsCompleted){
   if($prompt.Exception){throw $prompt.Exception}
   Send-AudioEvent @{token=$token;done=$true};$prompt=$null
  }
  Start-Sleep -Milliseconds 20
 }
}catch{Send-AudioEvent @{error=$_.Exception.Message};exit 1}
finally{if($synth){$synth.SpeakAsyncCancelAll();$synth.Dispose()}}
