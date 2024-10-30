# Video Block Editor

A browser-based video editor that allows you to edit videos by selecting and removing segments based on silence detection. Built with FFmpeg.wasm for client-side video processing.

## Features

- 🎬 Browser-based video editing - no server uploads required
- 🔊 Automatic silence detection
- ✂️ Easy block-based editing interface
- 🎯 Include/exclude video segments with simple controls
- 💾 Save/load editing sessions
- ⚡ Real-time preview
- 📱 Progressive Web App (PWA) support
- 🧵 Multi-threaded processing support

## Getting Started

1. Open the editor in your browser
2. Click "Open Video" to select a video file
3. Wait for silence detection to complete
4. Use the timeline to preview and select segments:
   - Green blocks are included segments
   - Red blocks are excluded segments
   - Gray blocks are silence
5. Use keyboard shortcuts or buttons to navigate and edit
6. Export your final video when ready

## Keyboard Shortcuts

- `Space`: Play/Pause
- `Left Arrow`: Previous Block
- `Right Arrow`: Next Block
- `T`: Toggle Mode (Include/Exclude)
- `+`: Zoom In Timeline
- `-`: Zoom Out Timeline

## Technical Details

- Built with Vue.js and Tailwind CSS
- Uses FFmpeg.wasm for video processing
- Supports both single and multi-threaded processing
- PWA-enabled for offline support
- Client-side processing - no server required

## Browser Support

Requires a modern browser with:
- WebAssembly support
- SharedArrayBuffer support
- Cross-Origin Isolation support

## Development

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Deploy to Cloudflare Pages
npm run deploy
```

## Contributing

We welcome contributions! Here's how you can help:

### Bug Reports
1. Check if the issue already exists in the Issues section
2. Use the bug report template
3. Include browser and OS details
4. Provide steps to reproduce
5. Add example video if possible

### Feature Requests
1. Check if the feature has been requested
2. Use the feature request template
3. Explain the use case
4. Provide mockups if relevant

### Code Contributions
1. Fork the repository
2. Create a feature branch
3. Follow the coding style
4. Add tests if applicable
5. Submit a pull request

### Known Issues & Future Features

#### Bugs to Fix
- Timeline zooming can be jumpy at certain levels
- Occasional audio desync in exported videos
- Memory leaks during long editing sessions
- Inconsistent block selection in some browsers
- Export progress indicator sometimes stalls

#### Features to Add
- Multiple audio track support
- Video filters and effects
- Custom silence threshold adjustment
- Batch processing capabilities
- Export format options
- Keyboard shortcut customization
- Block merging and splitting
- Waveform visualization
- Cloud storage integration
- Collaborative editing features

#### Performance Improvements
- Optimize silence detection algorithm
- Reduce memory usage during export
- Improve timeline rendering
- Cache processed segments
- Better handling of large files

## License

MIT License - see LICENSE file for details

## Credits

Created by techfren and contributors
