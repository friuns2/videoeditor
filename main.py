import sys
import os
import cv2
import numpy as np
import subprocess
import json
from pydub import AudioSegment
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QSlider, QPushButton, QFileDialog, QLabel, QMessageBox, QProgressBar,
    QGroupBox, QDialog, QProgressDialog, QSizePolicy
)
from PySide6.QtGui import QShortcut, QKeySequence, QPainter, QColor, QFont
from PySide6.QtCore import Qt, QTimer, QUrl, QRect
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False

class AudioBlock:
    def __init__(self, start, end, is_silence):
        self.start = start
        self.end = end
        self.is_silence = is_silence
        self.include = not is_silence  # By default, include non-silence blocks
        self.visited = False  # Track if playhead has visited this block

    def to_dict(self):
        return {
            'start': self.start,
            'end': self.end,
            'is_silence': self.is_silence,
            'include': self.include,
            'visited': self.visited
        }

    @classmethod
    def from_dict(cls, data):
        block = cls(data['start'], data['end'], data['is_silence'])
        block.include = data['include']
        block.visited = data['visited']
        return block

class BlockManager:
    def __init__(self):
        self.blocks = []
        self.video_path = None

    def set_video_path(self, video_path):
        """Just set the video path without processing blocks"""
        self.video_path = video_path
        self.blocks = []

    def process_blocks(self):
        """Process the video to detect silence blocks"""
        if not self.video_path:
            return False
        silence_detector = SilenceDetector(self.video_path)
        self.blocks = silence_detector.detect_blocks()
        return True

    def save_state(self, filepath):
        if not self.blocks:
            return False
        
        state = {
            'video_path': self.video_path,
            'blocks': [block.to_dict() for block in self.blocks]
        }
        
        try:
            with open(filepath, 'w') as f:
                json.dump(state, f)
            return True
        except Exception as e:
            print(f"Error saving state: {e}")
            return False

    def load_state(self, filepath):
        try:
            with open(filepath, 'r') as f:
                state = json.load(f)
            
            self.video_path = state['video_path']
            self.blocks = [AudioBlock.from_dict(block_data) for block_data in state['blocks']]
            # Get the duration from the last block's end time
            if self.blocks:
                self.duration = self.blocks[-1].end
            return True
        except Exception as e:
            print(f"Error loading state: {e}")
            return False

    def reset_blocks(self):
        for block in self.blocks:
            if not block.is_silence:
                block.visited = False
                block.include = True

class CustomSlider(QSlider):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 8px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B1B1B1, stop:1 #c4c4c4);
                margin: 2px 0;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b4b4b4, stop:1 #8f8f8f);
                border: 1px solid #5c5c5c;
                width: 18px;
                margin: -2px 0;
                border-radius: 3px;
            }
        """)

class BlockTimeline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.blocks = []
        self.current_position = 0
        self.visible_blocks = 200
        self.setMinimumHeight(60)
        self.total_duration = 0

    def setBlocks(self, blocks, total_duration):
        self.blocks = blocks
        self.total_duration = total_duration
        self.update()

    def setCurrentPosition(self, position):
        self.current_position = position
        self.update()

    def setVisibleBlocks(self, visible_blocks):
        self.visible_blocks = visible_blocks
        self.update()

    def paintEvent(self, event):
        if not self.blocks or self.total_duration == 0:
            return

        painter = QPainter(self)
        width = self.width()
        height = self.height()

        # Find the current block
        current_block_index = next((i for i, block in enumerate(self.blocks) if block.start <= self.current_position <= block.end), 0)

        # Calculate the range of blocks to display
        start_index = max(0, current_block_index - self.visible_blocks // 2)
        end_index = min(len(self.blocks), start_index + self.visible_blocks)

        # Adjust start_index if we're near the end of the list
        if end_index - start_index < self.visible_blocks:
            start_index = max(0, end_index - self.visible_blocks)

        visible_blocks = self.blocks[start_index:end_index]

        # Calculate the time range for the visible blocks
        time_start = visible_blocks[0].start
        time_end = visible_blocks[-1].end
        time_range = time_end - time_start

        for block in visible_blocks:
            start_x = int(((block.start - time_start) / time_range) * width)
            end_x = int(((block.end - time_start) / time_range) * width)
            
            if block.is_silence:
                color = QColor(200, 200, 200, 100)  # Light gray for silence
            elif block.visited:  # Only color visited blocks
                if block.include:
                    color = QColor(0, 255, 0, 100)  # Green for included non-silence
                else:
                    color = QColor(255, 0, 0, 100)  # Red for excluded non-silence
            else:
                color = QColor(150, 150, 150, 100)  # Neutral color for unvisited blocks

            painter.fillRect(start_x, 0, end_x - start_x, height - 20, color)

        # Draw a marker for the current position
        painter.setPen(Qt.blue)
        position_x = int(((self.current_position - time_start) / time_range) * width)
        painter.drawLine(position_x, 0, position_x, height - 20)

        # Draw zoom level indicator
        painter.setPen(Qt.black)
        painter.setFont(QFont("Arial", 10))
        painter.drawText(0, height - 20, width, 20, Qt.AlignRight, f"Zoom: {self.visible_blocks} blocks")

class VideoPlayer(QMainWindow):
    def __init__(self, debug=False):
        super().__init__()
        self.debug = debug
        self.block_manager = BlockManager()
        self.current_block_index = 0
        self.last_jumped_block_index = 0
        self.green_mode = True

        self.setWindowTitle("Video Player with Block Editor")
        self.setGeometry(100, 100, 400, 600)  # Reduced initial width to 400

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Main container with margins
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(main_container)

        # Video container with responsive sizing
        video_container = QWidget()
        video_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_layout = QVBoxLayout(video_container)
        video_layout.setSpacing(0)
        main_layout.addWidget(video_container, stretch=1)  # Give video container more stretch

        # Video widget with dark background
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: #1a1a1a;")
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_layout.addWidget(self.video_widget, stretch=1)

        # Media player setup
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        # Timeline container
        timeline_container = QWidget()
        timeline_layout = QVBoxLayout(timeline_container)
        timeline_layout.setSpacing(5)
        main_layout.addWidget(timeline_container)

        # Timeline slider with improved style
        self.timeline_slider = CustomSlider(Qt.Horizontal)
        self.timeline_slider.sliderMoved.connect(self.set_position)
        self.timeline_slider.setFixedHeight(20)  # Use fixed height instead of minimum
        self.timeline_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        timeline_layout.addWidget(self.timeline_slider)

        # Block timeline with improved style
        self.block_timeline = BlockTimeline()
        self.block_timeline.setFixedHeight(60)  # Reduced and fixed height
        self.block_timeline.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        timeline_layout.addWidget(self.block_timeline)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        # Mode indicator label
        self.mode_label = QLabel()
        self.update_mode_label()
        layout.addWidget(self.mode_label)

        # Button containers with size policy
        button_container = QWidget()
        button_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        button_layout = QHBoxLayout(button_container)
        button_layout.setSpacing(5)  # Reduced spacing between buttons
        main_layout.addWidget(button_container)

        # Group 1: File Operations
        file_group = QGroupBox("File")
        file_layout = QHBoxLayout(file_group)
        self.open_file_button = QPushButton("Open Video")
        self.open_file_button.clicked.connect(self.open_file)
        self.save_state_button = QPushButton("Save State")
        self.save_state_button.clicked.connect(self.save_state)
        self.load_state_button = QPushButton("Load State")
        self.load_state_button.clicked.connect(self.load_state)
        
        file_layout.addWidget(self.open_file_button)
        file_layout.addWidget(self.save_state_button)
        file_layout.addWidget(self.load_state_button)
        button_layout.addWidget(file_group)

        # Group 2: Playback Controls
        playback_group = QGroupBox("Playback")
        playback_layout = QHBoxLayout(playback_group)
        self.play_pause_button = QPushButton("Play")
        self.play_pause_button.clicked.connect(self.play_pause)
        self.prev_block_button = QPushButton("Previous")
        self.prev_block_button.clicked.connect(self.goto_previous_block)
        self.next_block_button = QPushButton("Next")
        self.next_block_button.clicked.connect(self.goto_next_block)
        
        playback_layout.addWidget(self.play_pause_button)
        playback_layout.addWidget(self.prev_block_button)
        playback_layout.addWidget(self.next_block_button)
        button_layout.addWidget(playback_group)

        # Group 3: Block Controls
        block_group = QGroupBox("Blocks")
        block_layout = QHBoxLayout(block_group)
        self.toggle_mode_button = QPushButton("Toggle Mode")
        self.toggle_mode_button.clicked.connect(self.toggle_mode)
        self.reset_blocks_button = QPushButton("Reset")
        self.reset_blocks_button.clicked.connect(self.reset_blocks)
        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(self.export_green_blocks)
        self.export_button.setEnabled(False)
        
        block_layout.addWidget(self.toggle_mode_button)
        block_layout.addWidget(self.reset_blocks_button)
        block_layout.addWidget(self.export_button)
        button_layout.addWidget(block_group)

        # Group 4: View Controls
        view_group = QGroupBox("View")
        view_layout = QHBoxLayout(view_group)
        self.zoom_in_button = QPushButton("Zoom In")
        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.zoom_out_button = QPushButton("Zoom Out")
        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.help_button = QPushButton("Help")
        self.help_button.clicked.connect(self.show_help)
        
        view_layout.addWidget(self.zoom_in_button)
        view_layout.addWidget(self.zoom_out_button)
        view_layout.addWidget(self.help_button)
        button_layout.addWidget(view_group)

        main_layout.addWidget(button_container)

        # Set initial button states after creating ALL buttons
        self.set_initial_button_states()
        
        # Show welcome screen last
        self.show_welcome_screen()

        # Connect media player signals
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)

        # Set up keyboard shortcuts
        self.shortcut_left = QShortcut(QKeySequence(Qt.Key_Left), self)
        self.shortcut_left.activated.connect(self.goto_previous_block)
        self.shortcut_right = QShortcut(QKeySequence(Qt.Key_Right), self)
        self.shortcut_right.activated.connect(self.goto_next_block)
        self.shortcut_space = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.shortcut_space.activated.connect(self.play_pause)
        self.shortcut_toggle = QShortcut(QKeySequence(Qt.Key_T), self)
        self.shortcut_toggle.activated.connect(self.toggle_mode)
        self.shortcut_zoom_in = QShortcut(QKeySequence(Qt.Key_Plus), self)
        self.shortcut_zoom_in.activated.connect(self.zoom_in)
        self.shortcut_zoom_out = QShortcut(QKeySequence(Qt.Key_Minus), self)
        self.shortcut_zoom_out.activated.connect(self.zoom_out)

        # Timer for skipping silences
        self.skip_timer = QTimer(self)
        self.skip_timer.timeout.connect(self.skip_silence)

    def save_state(self):
        if not self.block_manager.blocks:
            QMessageBox.warning(self, "Warning", "No blocks to save!")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Block State", "", "JSON Files (*.json)"
        )
        if filepath:
            if self.block_manager.save_state(filepath):
                QMessageBox.information(self, "Success", "State saved successfully!")
            else:
                QMessageBox.warning(self, "Error", "Failed to save state!")

    def load_state(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Block State", "", "JSON Files (*.json)"
        )
        if filepath:
            if self.block_manager.load_state(filepath):
                # Update UI with loaded state
                self.media_player.setSource(QUrl.fromLocalFile(self.block_manager.video_path))
                self.current_block_index = 0
                self.last_jumped_block_index = 0
                
                # Wait for media player to load and get duration
                def on_duration_changed(duration):
                    self.block_timeline.setBlocks(self.block_manager.blocks, duration / 1000.0)
                    self.media_player.durationChanged.disconnect(on_duration_changed)
                
                self.media_player.durationChanged.connect(on_duration_changed)
                self.enable_controls()
                QMessageBox.information(self, "Success", "State loaded successfully!")
            else:
                QMessageBox.warning(self, "Error", "Failed to load state!")

    def reset_blocks(self):
        if not self.block_manager.blocks:
            return
        
        self.block_manager.reset_blocks()
        self.block_timeline.update()

    def enable_controls(self):
        self.play_pause_button.setEnabled(True)
        self.prev_block_button.setEnabled(True)
        self.next_block_button.setEnabled(True)
        self.toggle_mode_button.setEnabled(True)
        self.zoom_in_button.setEnabled(True)
        self.zoom_out_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.save_state_button.setEnabled(True)

    def update_mode_label(self):
        mode_text = "Current Mode: GREEN (blocks will be included)" if self.green_mode else "Current Mode: RED (blocks will be excluded)"
        self.mode_label.setText(mode_text)
        self.mode_label.setStyleSheet(f"color: {'green' if self.green_mode else 'red'}; font-weight: bold;")

    def toggle_mode(self):
        self.green_mode = not self.green_mode
        self.update_mode_label()

    def get_video_properties(self, video_path):
        """Get video properties using ffprobe"""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate,codec_name",
            "-of", "json",
            video_path
        ]
        video_info = json.loads(subprocess.check_output(cmd).decode())
        
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,bit_rate",
            "-of", "json",
            video_path
        ]
        audio_info = json.loads(subprocess.check_output(cmd).decode())
        
        # Parse frame rate fraction
        num, den = map(int, video_info['streams'][0]['r_frame_rate'].split('/'))
        frame_rate = num/den
        
        return {
            'video_codec': video_info['streams'][0]['codec_name'],
            'audio_codec': audio_info['streams'][0]['codec_name'],
            'frame_rate': frame_rate,
            'audio_bitrate': audio_info['streams'][0].get('bit_rate', '192k')
        }

    def export_green_blocks(self):
        if not self.block_manager.video_path or not self.block_manager.blocks:
            return

        # Get output file path
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Save Exported Video", "", "Video Files (*.mp4)"
        )
        if not output_path:
            return

        # Create temporary directory for segments
        temp_dir = os.path.abspath("temp_segments")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            # Get video properties
            props = self.get_video_properties(self.block_manager.video_path)
            
            # Get included blocks (only those that are both visited and marked as included)
            included_blocks = [block for block in self.block_manager.blocks if not block.is_silence and block.visited and block.include]
            
            if not included_blocks:
                QMessageBox.warning(self, "Export Error", "No blocks selected for export!")
                return

            # Create segments list file
            segments_file = os.path.join(temp_dir, "segments.txt")
            with open(segments_file, "w") as f:
                for i, block in enumerate(included_blocks):
                    # Extract segment
                    segment_name = f"segment_{i}.mp4"
                    segment_path = os.path.join(temp_dir, segment_name)
                    
                    # Calculate duration and ensure it's at least 0.1 seconds
                    duration = max(0.1, block.end - block.start)
                    
                    # Format timestamps with fixed precision
                    start_time = "{:.3f}".format(block.start)
                    duration_str = "{:.3f}".format(duration)
                    
                    # Cut segment using ffmpeg with matched properties
                    subprocess.run([
                        "ffmpeg", "-y",
                        "-ss", start_time,
                        "-t", duration_str,
                        "-i", self.block_manager.video_path,
                        "-c:v", props['video_codec'],
                        "-c:a", props['audio_codec'],
                        "-r", str(props['frame_rate']),
                        "-b:a", str(props['audio_bitrate']),
                        "-copyts",
                        "-avoid_negative_ts", "make_zero",
                        segment_path
                    ], check=True)
                    
                    # Write to segments list with relative path
                    f.write(f"file '{segment_name}'\n")

            # Concatenate all segments with matched properties
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", segments_file,
                "-c:v", props['video_codec'],
                "-c:a", props['audio_codec'],
                "-r", str(props['frame_rate']),
                "-b:a", str(props['audio_bitrate']),
                output_path
            ], check=True)

            QMessageBox.information(self, "Export Complete", "Video export completed successfully!")

        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Export Error", f"FFmpeg error during export: {str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Error during export: {str(e)}")

        finally:
            # Clean up temporary files
            if os.path.exists(temp_dir):
                for file in os.listdir(temp_dir):
                    try:
                        os.remove(os.path.join(temp_dir, file))
                    except:
                        pass
                try:
                    os.rmdir(temp_dir)
                except:
                    pass

    def open_file(self):
        file_dialog = QFileDialog(self)
        video_path, _ = file_dialog.getOpenFileName(self, "Open Video File", "", "Video Files (*.mp4 *.avi *.mov)")
        
        if video_path:
            self.media_player.setSource(QUrl.fromLocalFile(video_path))
            self.block_manager.set_video_path(video_path)
            
            # Ask user if they want to process blocks
            reply = QMessageBox.question(self, 'Process Blocks', 
                                       'Do you want to process silence blocks now?\n\n'
                                       'Select No if you plan to load a saved state instead.',
                                       QMessageBox.Yes | QMessageBox.No)
            
            if reply == QMessageBox.Yes:
                if self.block_manager.process_blocks():
                    self.current_block_index = 0
                    self.last_jumped_block_index = 0
                    self.block_timeline.setBlocks(self.block_manager.blocks, self.media_player.duration() / 1000.0)
                    self.enable_controls()
                else:
                    QMessageBox.warning(self, "Error", "Failed to process blocks!")
            else:
                # Only enable basic controls when blocks aren't processed
                self.play_pause_button.setEnabled(True)
                self.save_state_button.setEnabled(False)
                self.load_state_button.setEnabled(True)
            
            # Ensure audio is enabled and unmuted
            self.audio_output.setMuted(False)
            self.audio_output.setVolume(1.0)
            

    def play_pause(self):
        if self.media_player.playbackState() == QMediaPlayer.PlayingState:
            self.media_player.pause()
            self.play_pause_button.setText("Play")
            self.skip_timer.stop()
        else:
            self.media_player.play()
            self.play_pause_button.setText("Pause")
            self.skip_timer.start(100)

    def set_position(self, position):
        self.media_player.setPosition(position)

    def position_changed(self, position):
        self.timeline_slider.setValue(position)
        current_position = position / 1000.0  # Convert to seconds
        self.block_timeline.setCurrentPosition(current_position)
        
        if not self.block_manager.blocks:
            return
            
        # Update current block index based on position
        new_block_index = next((i for i, block in enumerate(self.block_manager.blocks) 
                            if block.start <= current_position <= block.end), 0)
        
        if new_block_index < len(self.block_manager.blocks):
            current_block = self.block_manager.blocks[new_block_index]
            
            # Only log for non-silence blocks or when transitioning blocks
            if not current_block.is_silence or self.current_block_index != new_block_index:
                if self.debug:
                    print(f"[DEBUG] Position {current_position:.3f}s - Block {new_block_index}")
                    if not current_block.is_silence:
                        print(f"[DEBUG] Non-silence block: {current_block.start:.3f}s - {current_block.end:.3f}s")
            
            # Mark non-silence blocks as visited and update include state
            if not current_block.is_silence:
                current_block.visited = True
                current_block.include = self.green_mode
                
            # Update current block index
            if self.current_block_index != new_block_index:
                self.current_block_index = new_block_index
            
        self.block_timeline.update()
        self.update_progress_bar()

    def duration_changed(self, duration):
        self.timeline_slider.setRange(0, duration)
        self.block_timeline.setBlocks(self.block_manager.blocks, duration / 1000.0)

    def find_next_non_silence_block(self, start_index, forward=True):
        blocks = self.block_manager.blocks
        if forward:
            for i in range(start_index + 1, len(blocks)):
                if not blocks[i].is_silence:
                    return i
        else:
            for i in range(start_index - 1, -1, -1):
                if not blocks[i].is_silence:
                    return i
        return None

    def goto_previous_block(self):
        if self.debug:
            print(f"[DEBUG] goto_previous_block: Starting from index {self.current_block_index}")
        next_index = self.find_next_non_silence_block(self.current_block_index, forward=False)
        
        if next_index is not None:
            was_playing = self.media_player.playbackState() == QMediaPlayer.PlayingState
            if self.debug:
                print(f"[DEBUG] goto_previous_block: Found next block at index {next_index}, was_playing={was_playing}")
            
            self.current_block_index = next_index
            target_position = int(self.block_manager.blocks[next_index].start * 1000)
            if self.debug:
                print(f"[DEBUG] goto_previous_block: Setting position to {target_position}ms")
            
            self.media_player.setPosition(target_position)
            
            if was_playing:
                if self.debug:
                    print("[DEBUG] goto_previous_block: Resuming playback")
                self.media_player.play()
        else:
            if self.debug:
                print("[DEBUG] goto_previous_block: No previous non-silence block found")

    def goto_next_block(self):
        if self.debug:
            print(f"[DEBUG] goto_next_block: Starting from index {self.current_block_index}")
        next_index = self.find_next_non_silence_block(self.current_block_index, forward=True)
        
        if next_index is not None:
            was_playing = self.media_player.playbackState() == QMediaPlayer.PlayingState
            if self.debug:
                print(f"[DEBUG] goto_next_block: Found next block at index {next_index}, was_playing={was_playing}")
            
            self.current_block_index = next_index
            target_position = int(self.block_manager.blocks[next_index].start * 1000)
            if self.debug:
                print(f"[DEBUG] goto_next_block: Setting position to {target_position}ms")
            
            self.media_player.setPosition(target_position)
            
            if was_playing:
                if self.debug:
                    print("[DEBUG] goto_next_block: Resuming playback")
                self.media_player.play()
        else:
            if self.debug:
                print("[DEBUG] goto_next_block: No next non-silence block found")


    def zoom_in(self):
        self.block_timeline.setVisibleBlocks(max(1, self.block_timeline.visible_blocks - 1))

    def zoom_out(self):
        self.block_timeline.setVisibleBlocks(min(len(self.block_manager.blocks), self.block_timeline.visible_blocks + 1))

    def set_initial_button_states(self):
        """Disable buttons that require a video to be loaded"""
        buttons_requiring_video = [
            self.play_pause_button,
            self.prev_block_button,
            self.next_block_button,
            self.toggle_mode_button,
            self.save_state_button,
            self.reset_blocks_button,
            self.export_button,
            self.zoom_in_button,
            self.zoom_out_button
        ]
        
        for button in buttons_requiring_video:
            button.setEnabled(False)
            
    def show_processing_dialog(self):
        """Show a progress dialog while processing blocks"""
        dialog = QProgressDialog("Processing video blocks...", None, 0, 0, self)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setCancelButton(None)
        dialog.setWindowTitle("Processing")
        dialog.show()
        QApplication.processEvents()
        return dialog

    def confirm_export(self):
        """Show export confirmation dialog with options"""
        msg = QMessageBox()
        msg.setWindowTitle("Export Options")
        msg.setText("Choose export format:")
        msg.addButton("MP4 (H.264)", QMessageBox.AcceptRole)
        msg.addButton("WebM", QMessageBox.AcceptRole)
        msg.addButton("Cancel", QMessageBox.RejectRole)
        return msg.exec_()

    def show_welcome_screen(self):
        """Show welcome screen with quick actions"""
        welcome = QDialog(self)
        welcome.setWindowTitle("Welcome")
        layout = QVBoxLayout(welcome)
        
        label = QLabel("Welcome to Video Block Editor")
        label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(label)
        
        open_btn = QPushButton("Open Video")
        open_btn.clicked.connect(lambda: (welcome.accept(), self.open_file()))
        layout.addWidget(open_btn)
        
        load_btn = QPushButton("Load Previous Session")
        load_btn.clicked.connect(lambda: (welcome.accept(), self.load_state()))
        layout.addWidget(load_btn)
        
        welcome.exec()

    def show_help(self):
        help_text = """
        Hotkeys:
        - Space: Play/Pause
        - Left Arrow: Go to Previous Block
        - Right Arrow: Go to Next Block
        - T: Toggle Mode (Green/Red)
        - +: Zoom In
        - -: Zoom Out

        Buttons:
        - Open Video: Open a video file
        - Play/Pause: Control video playback
        - Previous Block: Move to the previous block
        - Next Block: Move to the next block
        - Toggle Mode: Switch between Green (include) and Red (exclude) modes
        - Save State: Save current block states to a file
        - Load State: Load previously saved block states
        - Reset Blocks: Reset all blocks to unvisited state
        - Export Green Blocks: Export a new video with only included blocks
        - Zoom In: Increase the number of visible blocks
        - Zoom Out: Decrease the number of visible blocks

        Modes:
        - Green Mode: Blocks the playhead passes through will be included
        - Red Mode: Blocks the playhead passes through will be excluded
        """
        QMessageBox.information(self, "Help", help_text)

    def skip_silence(self):
        if not self.block_manager.blocks:
            if self.debug:
                print("[DEBUG] skip_silence: No blocks available")
            return
            
        current_position = self.media_player.position() / 1000.0
        if self.debug:
            print(f"[DEBUG] skip_silence: Current position {current_position:.3f}s")
        
        if self.current_block_index >= len(self.block_manager.blocks):
            if self.debug:
                print(f"[DEBUG] skip_silence: Adjusting index from {self.current_block_index} to {len(self.block_manager.blocks) - 1}")
            self.current_block_index = len(self.block_manager.blocks) - 1
            
        current_block = self.block_manager.blocks[self.current_block_index]
        
        # Don't skip if we just started playing this block (add 0.1s buffer)
        if current_position - current_block.start < 0.1:
            return
            
        if self.debug:
            print(f"[DEBUG] skip_silence: Current block - Index: {self.current_block_index}, Start: {current_block.start:.3f}s, End: {current_block.end:.3f}s, Is Silence: {current_block.is_silence}")
            print(f"[DEBUG] skip_silence: Time in current block: {current_position - current_block.start:.3f}s")

        # Check if we need to skip this block
        should_skip = current_block.is_silence and not current_block.include
        
        # Also skip very short non-silence blocks (less than 0.2 seconds)
        if not current_block.is_silence:
            block_duration = current_block.end - current_block.start
            if block_duration < 0.2:
                if self.debug:
                    print(f"[DEBUG] skip_silence: Block too short ({block_duration:.3f}s), will skip")
                should_skip = True
            
        if should_skip:
            # Find the next suitable non-silence block
            next_block_index = self.current_block_index + 1
            min_block_duration = 0.3  # Increased minimum duration for stability
            
            while next_block_index < len(self.block_manager.blocks):
                next_block = self.block_manager.blocks[next_block_index]
                block_duration = next_block.end - next_block.start
                
                # Skip silence blocks and blocks that are too short
                if not next_block.is_silence and block_duration >= min_block_duration:
                    if self.debug:
                        print(f"[DEBUG] skip_silence: Found suitable block {next_block_index} with duration {block_duration:.3f}s")
                    break
                    
                if self.debug and next_block.is_silence:
                    print(f"[DEBUG] skip_silence: Skipping silence block {next_block_index}")
                elif self.debug:
                    print(f"[DEBUG] skip_silence: Skipping short block {next_block_index} ({block_duration:.3f}s)")
                    
                next_block_index += 1
                
            if next_block_index < len(self.block_manager.blocks):
                next_block = self.block_manager.blocks[next_block_index]
                # Add a small offset to avoid boundary issues
                target_position = next_block.start + 0.05
                if self.debug:
                    print(f"[DEBUG] skip_silence: Skipping to next suitable block at {target_position:.3f}s")
                self.media_player.setPosition(int(target_position * 1000))
                self.current_block_index = next_block_index
            else:
                # If no more suitable blocks, stop playback
                if self.debug:
                    print("[DEBUG] skip_silence: No more suitable blocks, stopping playback")
                self.media_player.stop()
                return
            
            playback_state = self.media_player.playbackState()
            if self.debug:
                print(f"[DEBUG] skip_silence: Playback state is {playback_state}")
            
            if playback_state != QMediaPlayer.PlayingState:
                if self.debug:
                    print("[DEBUG] skip_silence: Resuming playback")
                self.media_player.play()

    def update_progress_bar(self):
        if self.media_player.duration() > 0:
            progress = (self.media_player.position() / self.media_player.duration()) * 100
            self.progress_bar.setValue(int(progress))

class SilenceDetector:
    def __init__(self, input_file, silence_threshold=-40, min_silence_duration=0.1):
        self.input_file = input_file
        self.silence_threshold = silence_threshold
        self.min_silence_duration = min_silence_duration

    def detect_blocks(self):
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", self.input_file,
            "-af", f"silencedetect=noise={self.silence_threshold}dB:d={self.min_silence_duration}",
            "-f", "null",
            "-"
        ]

        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        output = result.stderr

        silence_starts = []
        silence_ends = []
        for line in output.split('\n'):
            if "silence_start" in line:
                time = float(line.split("silence_start: ")[1].split(" ")[0])
                silence_starts.append(time)
            elif "silence_end" in line:
                time = float(line.split("silence_end: ")[1].split(" ")[0])
                silence_ends.append(time)

        # Get the duration of the video
        duration_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            self.input_file
        ]
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
        duration = float(duration_result.stdout.strip())

        blocks = []
        current_time = 0

        for start, end in zip(silence_starts, silence_ends):
            if start > current_time:
                blocks.append(AudioBlock(current_time, start, False))
            blocks.append(AudioBlock(start, end, True))
            current_time = end

        if current_time < duration:
            blocks.append(AudioBlock(current_time, duration, False))

        return blocks

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    if not check_ffmpeg():
        print("Error: ffmpeg is not installed or not found in the system PATH.")
        print("Please install ffmpeg and make sure it's accessible from the command line.")
        return

    app = QApplication([])  # Don't pass sys.argv since we parsed it
    player = VideoPlayer(debug=args.debug)
    player.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
