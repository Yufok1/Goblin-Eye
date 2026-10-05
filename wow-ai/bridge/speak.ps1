param([int]$ParentId = 0, [string]$OutputPath = '')
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
$speechSynth = $null
try {
    $speechRequest = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($speechRequest.volume -lt 0 -or $speechRequest.volume -gt 100 -or $speechRequest.rate -lt -10 -or $speechRequest.rate -gt 10) { throw 'Invalid speech settings.' }
    Add-Type -AssemblyName System.Speech
    $speechSynth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
    $speechSynth.Volume = [int]$speechRequest.volume
    $speechSynth.Rate = [int]$speechRequest.rate
    if ($speechRequest.voice) { $speechSynth.SelectVoice([string]$speechRequest.voice) }
    if ($OutputPath) { $speechSynth.SetOutputToWaveFile($OutputPath) }
    else { $speechSynth.SetOutputToDefaultAudioDevice() }
    # Audio is a bridge-owned local WAV, never an arbitrary URL or SSML.
    if ($speechRequest.audioFile) {
        $speechAudioFile = [System.IO.Path]::GetFullPath([string]$speechRequest.audioFile)
        if ($speechAudioFile -notmatch '^[A-Za-z]:\\' -or [System.IO.Path]::GetExtension($speechAudioFile) -ne '.wav' -or -not (Test-Path -LiteralPath $speechAudioFile -PathType Leaf)) { throw 'Invalid local speech WAV.' }
        $speechBuilder = [System.Speech.Synthesis.PromptBuilder]::new()
        $speechBuilder.AppendAudio($speechAudioFile)
        $speechPrompt = $speechSynth.SpeakAsync($speechBuilder)
    } else {
        # Literal text; never SSML, Invoke-Expression, UI input, or game APIs.
        $speechPrompt = $speechSynth.SpeakAsync([string]$speechRequest.text)
    }
    while (-not $speechPrompt.IsCompleted) {
        if ($ParentId -gt 0 -and -not (Get-Process -Id $ParentId -ErrorAction SilentlyContinue)) { $speechSynth.SpeakAsyncCancelAll(); break }
        Start-Sleep -Milliseconds 100
    }
    if ($speechPrompt.IsCompleted -and $speechPrompt.Exception) { throw $speechPrompt.Exception }
} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
finally { if ($null -ne $speechSynth) { $speechSynth.Dispose() } }
