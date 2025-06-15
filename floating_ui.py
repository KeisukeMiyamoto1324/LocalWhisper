# floating_ui.py

import AppKit
import numpy as np
from PyObjCTools import AppHelper
import threading
import queue
import objc
import math

# The ModernWaveformView class does not need any changes.
# (Paste the ModernWaveformView class code here)
class ModernWaveformView(AppKit.NSView):
    """
    macOSのモダンデザインに合わせた波形表示ビュー
    (このクラスのコードは変更ありません)
    """
    def initWithFrame_(self, frame):
        self = objc.super(ModernWaveformView, self).initWithFrame_(frame)
        if self:
            self.waveform_data = np.zeros(32, dtype=np.float32)
            self.smoothed_data = np.zeros(32, dtype=np.float32)
            self.peak_level = 0.01
            self.animation_phase = 0.0
            self.setup_colors()
        return self

    def setup_colors(self):
        self.primary_color = AppKit.NSColor.systemBlueColor()
        self.secondary_color = AppKit.NSColor.systemGrayColor()
        self.inactive_color = AppKit.NSColor.tertiaryLabelColor()

    def update_waveform(self, data):
        if data is None or len(data) == 0:
            return
        rms = float(np.sqrt(np.mean(data**2)))
        self.waveform_data = np.roll(self.waveform_data, -1)
        self.waveform_data[-1] = rms
        self.smoothed_data = self.smoothed_data * 0.6 + self.waveform_data * 0.4
        current_max = np.max(self.smoothed_data)
        if current_max > self.peak_level:
            self.peak_level = current_max
        else:
            self.peak_level = max(0.01, self.peak_level * 0.95)
        self.animation_phase += 0.15
        if self.animation_phase > 2 * math.pi:
            self.animation_phase = 0.0
        self.setNeedsDisplay_(True)

    def drawRect_(self, dirtyRect):
        AppKit.NSColor.clearColor().set()
        AppKit.NSRectFill(dirtyRect)
        bounds = self.bounds()
        width = bounds.size.width
        height = bounds.size.height
        center_y = height / 2.0
        if not hasattr(self, 'smoothed_data') or len(self.smoothed_data) == 0:
            return
        num_bars = len(self.smoothed_data)
        spacing = 2.0
        bar_width = max(1.0, (width - spacing * (num_bars - 1)) / num_bars)
        for i, value in enumerate(self.smoothed_data):
            x_pos = i * (bar_width + spacing)
            normalized_value = value / self.peak_level if self.peak_level > 0 else 0
            bar_height = max(2.0, normalized_value * height * 0.8)
            if normalized_value > 0.1:
                wave_effect = math.sin(self.animation_phase + i * 0.2) * 1.0
                bar_height += wave_effect
            bar_rect = AppKit.NSMakeRect(
                x_pos, center_y - bar_height / 2, bar_width, bar_height
            )
            if normalized_value > 0.3:
                color = self.primary_color.colorWithAlphaComponent_(0.8)
            elif normalized_value > 0.1:
                color = self.secondary_color.colorWithAlphaComponent_(0.6)
            else:
                color = self.inactive_color.colorWithAlphaComponent_(0.4)
            color.set()
            path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                bar_rect, bar_width / 2, bar_width / 2
            )
            path.fill()


class FloatingUIController:
    # __init__ and window setup methods are unchanged.
    def __init__(self, data_queue, transcription_queue):
        self.data_queue = data_queue
        self.transcription_queue = transcription_queue
        self.window = None
        self.waveform_view = None
        self.transcription_label = None
        self.timer = None
        
        print("FloatingUIController: Initializing...")
        AppHelper.callLater(0, self.setup_window)

    def setup_window(self):
        print("FloatingUIController: Setting up window...")
        window_width = 320
        window_height = 100
        win_rect = AppKit.NSMakeRect(0, 0, window_width, window_height)
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            win_rect, AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False)
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self.window.setHasShadow_(True)
        self.window.setLevel_(AppKit.NSStatusWindowLevel)
        self.window.setIgnoresMouseEvents_(True)
        self.window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces | 
            AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary)
        self.setup_content_view()
        print("FloatingUIController: Window setup complete.")

    def setup_content_view(self):
        bounds = self.window.contentView().bounds()
        container_view = AppKit.NSView.alloc().initWithFrame_(bounds)
        container_view.setWantsLayer_(True)
        layer = container_view.layer()
        layer.setCornerRadius_(16.0)
        layer.setMasksToBounds_(True)
        bg_color = AppKit.NSColor.blackColor().colorWithAlphaComponent_(0.75)
        layer.setBackgroundColor_(bg_color.CGColor())
        layer.setBorderWidth_(0.5)
        border_color = AppKit.NSColor.separatorColor().colorWithAlphaComponent_(0.3)
        layer.setBorderColor_(border_color.CGColor())
        self.window.setContentView_(container_view)
        self.setup_transcription_view(container_view)
        self.setup_waveform_view(container_view)

    def setup_transcription_view(self, container_view):
        bounds = container_view.bounds()
        padding = 12.0
        waveform_height = 30.0
        text_rect = AppKit.NSMakeRect(
            padding, padding + waveform_height,
            bounds.size.width - 2 * padding,
            bounds.size.height - 2 * padding - waveform_height)
        self.transcription_label = AppKit.NSTextField.alloc().initWithFrame_(text_rect)
        self.transcription_label.setEditable_(False)
        self.transcription_label.setBordered_(False)
        self.transcription_label.setDrawsBackground_(False)
        self.transcription_label.setTextColor_(AppKit.NSColor.whiteColor().colorWithAlphaComponent_(0.9))
        self.transcription_label.setFont_(AppKit.NSFont.systemFontOfSize_weight_(14.0, AppKit.NSFontWeightRegular))
        self.transcription_label.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        self.transcription_label.cell().setUsesSingleLineMode_(False)
        self.transcription_label.cell().setWraps_(True)
        container_view.addSubview_(self.transcription_label)

    def setup_waveform_view(self, container_view):
        bounds = container_view.bounds()
        padding = 12.0
        waveform_height = 30.0
        waveform_rect = AppKit.NSMakeRect(
            padding, padding, bounds.size.width - 2 * padding, waveform_height)
        self.waveform_view = ModernWaveformView.alloc().initWithFrame_(waveform_rect)
        self.waveform_view.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        container_view.addSubview_(self.waveform_view)

    def show_at(self, bounds, screen_visible_frame):
        if self.transcription_label:
            AppHelper.callLater(0, self.update_label_text, "Listening...")
        # (The rest of the positioning logic is unchanged)
        if not self.window: return
        window_size = self.window.frame().size
        screen_frame = screen_visible_frame
        screen_origin = screen_frame.origin
        screen_size = screen_frame.size
        margin = 10
        zero_screen_physical_height = AppKit.NSScreen.screens()[0].frame().size.height
        bounds_y_bottom_up = zero_screen_physical_height - bounds['y']
        textbox_top_on_screen = bounds_y_bottom_up - screen_origin.y
        preferred_y_on_screen = textbox_top_on_screen + margin
        preferred_y = screen_origin.y + preferred_y_on_screen
        if preferred_y + window_size.height > screen_origin.y + screen_size.height:
            textbox_bottom_on_screen = textbox_top_on_screen - bounds['height']
            y = screen_origin.y + textbox_bottom_on_screen - window_size.height - margin
        else:
            y = preferred_y
        x = bounds['x'] + (bounds['width'] / 2) - (window_size.width / 2)
        if x < screen_origin.x + margin:
            x = screen_origin.x + margin
        elif x + window_size.width > screen_origin.x + screen_size.width - margin:
            x = screen_origin.x + screen_size.width - window_size.width - margin
        self.window.setFrameOrigin_(AppKit.NSPoint(x, y))
        self.window.makeKeyAndOrderFront_(None)
        self.start_updating()

    def hide(self):
        if self.transcription_label:
            AppHelper.callLater(0, self.update_label_text, "")
        if not self.window: return
        self.stop_updating()
        self.window.orderOut_(None)

    def start_updating(self):
        if self.timer is None:
            self.timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0/30.0, self, 'update:', None, True)

    def stop_updating(self):
        if self.timer:
            self.timer.invalidate()
            self.timer = None

    def update_(self, timer):
        """Periodically called by the timer to update the UI from queues."""
        # Update waveform from its queue
        try:
            for _ in range(10): # Process up to 10 items per update cycle
                if self.data_queue.empty(): break
                data = self.data_queue.get_nowait()
                if self.waveform_view and data is not None:
                    self.waveform_view.update_waveform(data)
        except queue.Empty:
            pass
        except Exception as e:
            print(f"FloatingUIController: Waveform update error - {type(e).__name__}: {e}")

        # Update transcription label from its queue
        try:
            if not self.transcription_queue.empty():
                text = self.transcription_queue.get_nowait()
                # Use callLater to ensure the UI update happens on the main thread
                AppHelper.callLater(0, self.update_label_text, text)
        except queue.Empty:
            pass
        except Exception as e:
            print(f"FloatingUIController: Transcription update error - {type(e).__name__}: {e}")

    def update_label_text(self, text):
        """A thread-safe method to update the transcription label."""
        if self.transcription_label is None:
            return

        # Ensure text is a string before processing
        text_str = str(text) if text is not None else ""
        
        # Limit the display to the last 3 lines
        lines = text_str.split('\n')
        if len(lines) > 3:
            display_text = '\n'.join(lines[-3:])
        else:
            display_text = text_str
        
        self.transcription_label.setStringValue_(display_text)