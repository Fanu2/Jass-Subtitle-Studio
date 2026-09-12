# Jass Subtitle Studio

**A simple, focused desktop application for creating, editing, previewing, styling, and burning subtitles into videos.**

Jass Subtitle Studio is a lightweight **PySide6** application designed for one job: making subtitled videos without the complexity of a full video editor.

If you already use Kdenlive or another video editor, Jass Subtitle Studio is intended to complement it — not replace it.

> **Video + SRT/TXT → Preview → Style → Render**

---

## Why Jass Subtitle Studio?

Adding subtitles to a video should be simple.

Jass Subtitle Studio provides a focused workflow for:

- Loading a video
- Loading an existing SRT subtitle file
- Converting TXT text into timed SRT subtitles
- Editing subtitle entries
- Validating subtitle timing
- Previewing subtitles directly on the video
- Styling subtitles
- Burning subtitles permanently into a new video

There is no complicated multi-track timeline or full video-editing workspace.

---

## Features

### 🎬 Video Preview

- Open common video formats
- Play / pause
- Seek through the video
- Jump backward and forward
- Live subtitle preview
- Correct subtitle positioning for:
  - Landscape videos
  - Portrait videos
  - Square videos
  - Other aspect ratios

Subtitles are positioned relative to the **actual video frame**, so portrait videos do not place subtitles in the surrounding letterbox area.

### 📝 Subtitle Support

- Open SRT files
- Save SRT files
- Edit subtitle entries
- Add subtitle entries
- Delete subtitle entries
- Shift subtitles forward or backward
- Validate subtitle timing
- Detect common subtitle problems
- Preview the currently active subtitle

### 📄 TXT → SRT

Convert ordinary text into subtitles.

Options include:

- Time per line
- Maximum characters per line
- Automatic line wrapping
- Automatic SRT numbering and timing

Example:

```text
This is the first line.
This is the second line.
This is the third line.
```

can be converted into:

```srt
1
00:00:00,000 --> 00:00:03,000
This is the first line.

2
00:00:03,000 --> 00:00:06,000
This is the second line.

3
00:00:06,000 --> 00:00:09,000
This is the third line.
```

### 🎨 Subtitle Styling

Customize the appearance of subtitles:

- Font
- Font size
- Text color
- Position
  - Top
  - Center
  - Bottom
- Bold
- Italic
- Outline
- Shadow
- Background box
- Fade in/out

Changes are visible in the video preview.

### 🔥 Render / Burn Subtitles

Jass Subtitle Studio can create a **new video with subtitles permanently burned into the video**.

The original video is not modified.

The renderer always writes to a separate output file. The source video is treated as read-only and is protected from accidental overwrite.

When the source video contains an embedded/selectable subtitle track, Jass Subtitle Studio does **not** copy that subtitle track into the burned-subtitle output. Only the selected Jass subtitle styling is permanently rendered into the video.

Typical workflow:

```text
input.mp4
    +
subtitles.srt
    ↓
Jass Subtitle Studio
    ↓
FFmpeg
    ↓
output_subtitled.mp4
```

The resulting MP4 contains the video with the selected subtitles burned into the picture and the audio, without retaining the source subtitle track.

Rendering is performed through **FFmpeg**.

---

## Screenshots

Add screenshots of the application here as the project develops.

Suggested screenshots:

- Main video preview
- Portrait video with subtitles
- Subtitle editing table
- Style controls
- Render/export screen

---

## Requirements

- Python 3.10+ recommended
- PySide6
- FFmpeg

The application uses Qt Multimedia for video playback and FFmpeg for final subtitle rendering.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/Fanu2/jass-subtitle-studio.git
cd jass-subtitle-studio
```

Create a virtual environment:

### Windows

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the Python dependency:

```bash
python -m pip install --upgrade pip
python -m pip install PySide6
```

---

## FFmpeg

FFmpeg is required for **Render / Burn Subtitles**.

Check whether it is available:

```bash
ffmpeg -version
```

If FFmpeg is installed but not available in your system `PATH`, use the application's **FFmpeg...** option to select `ffmpeg.exe` manually.

The application uses FFmpeg to render the styled subtitles into the output video.

---

## Running

From the project directory:

```bash
python Jass_Subtitle_Studio_v1_2_SIMPLE_PRO.py
```

On Windows, you can also use:

```powershell
py .\Jass_Subtitle_Studio_v1_2_SIMPLE_PRO.py
```

---

## Basic Workflow

### 1. Choose a video

Click:

**Choose Video**

The video appears in the preview.

### 2. Load subtitles

Click:

**Load SRT**

or use:

**TXT → SRT**

### 3. Preview

Press:

**▶ Play**

The subtitles appear directly on the video at their assigned times.

### 4. Adjust the appearance

Use the **Style** controls to change:

- Font
- Size
- Color
- Position
- Outline
- Shadow
- Background

### 5. Render

Click:

**🔥 RENDER / BURN SUBTITLES**

Choose the output file and let FFmpeg create the final video.

---

## Design Philosophy

Jass Subtitle Studio intentionally follows a small and focused philosophy:

### Simple

The user should be able to create a subtitled video in a few steps.

### Focused

This is a subtitle tool, not a replacement for a complete nonlinear video editor.

### Visual

The subtitle should be visible on the actual video during editing.

### Safe

Rendering creates a new output file rather than modifying the source video.

### Practical

SRT editing, TXT conversion, preview, styling, and video rendering are available from one application.

---

## Relationship to Kdenlive

Jass Subtitle Studio is **not intended to compete with Kdenlive as a full video editor**.

Use Kdenlive when you need:

- Multiple video tracks
- Complex editing
- Transitions
- Audio editing
- Effects
- Timeline-based production
- Full video projects

Use Jass Subtitle Studio when you need:

- Subtitles
- SRT editing
- TXT → SRT
- Subtitle styling
- Subtitle preview
- Burning subtitles into a video

The two applications can therefore work well together.

---

## Project Status

**Current baseline: v1.2 Simple Pro — Stable Render Fix**

The current release focuses on a reliable subtitle workflow rather than adding unnecessary video-editing features.

The v1.2 baseline includes:

- Working video preview
- Working subtitle overlay
- Portrait/landscape-aware subtitle placement
- SRT workflow
- TXT → SRT workflow
- Subtitle editing
- Validation
- Subtitle styling
- FFmpeg rendering/burning
- Safe rendering to a separate output file
- Protection against overwriting the source video
- Exclusion of the source video's embedded subtitle track during burned-subtitle export
- 24 pt default subtitle size

The v1.2 Simple Pro baseline is considered stable. Future changes should preserve the current working preview and render workflow and should be limited to clear bug fixes or proportional subtitle-focused improvements.

Future improvements should remain focused on subtitle-related functionality and preserve the simplicity of the application.

---

## Roadmap

Possible future improvements:

- Drag-and-drop video/SRT files
- Better subtitle table editing
- Waveform/audio-assisted subtitle timing
- Automatic subtitle generation through speech recognition
- More subtitle style presets
- Custom subtitle templates
- Batch subtitle rendering
- More export formats
- Subtitle image generation improvements
- Automatic subtitle line balancing
- Keyboard shortcuts
- Project/session saving
- Optional AI-assisted subtitle cleanup and timing

AI features should remain optional and should not be required for the basic offline subtitle workflow.

---

## License

Choose a license for the repository before publishing the project.

A permissive option such as **MIT** is suitable if you want others to freely use, modify, and redistribute the project.

---

## Author

**Jass**

Jass Subtitle Studio is a focused personal desktop tool for making subtitle creation and video subtitling easier.

---

## Repository Name

Recommended repository name:

**`jass-subtitle-studio`**

Recommended GitHub display title:

# Jass Subtitle Studio

Suggested short description:

> Simple PySide6 desktop app for creating, editing, styling, previewing, and burning subtitles into videos.

