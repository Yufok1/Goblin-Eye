# Local Windows speech

Speech is optional and uses the Windows voices installed on your computer.
There are no Warcraft recordings, cloned character voices, neural model downloads,
GPU dependencies or voice-service accounts in this edition.

Open **Voice settings** in the chat window:

- **Play TL;DR** reads the saved summary; **Play full** reads the full reply.
- **Test voice** reads a short test sentence; **Stop voice** cancels playback.
- **Auto on/off** controls automatic reading of new replies, off by default.
- **Summary/Full replies** chooses the automatic reading mode.
- Volume and speed apply to Windows speech.

Choose an installed voice with `/wow-ai voice name <Windows voice name>`, or use
`/wow-ai voice name default`. Preferences survive bridge restarts. Old character
preferences migrate to Desktop without loading their reference files.

Text is spoken locally through System.Speech. Formatting, code blocks, links and
item texture codes are cleaned for audio. The bridge never treats reply text as
SSML, PowerShell code or game input. Windows speech performs no gameplay actions.

Chat transcripts are private local data and must not be included in releases.
