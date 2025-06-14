# floating_ui.py

import AppKit
import numpy as np
from PyObjCTools import AppHelper
import threading
import queue
import objc

# (WaveformViewクラスとFloatingUIControllerの__init__, setup_windowに変更はありません)
class WaveformView(AppKit.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(WaveformView, self).initWithFrame_(frame)
        if self:
            self.waveform_data = np.zeros(256, dtype=np.float32)
        return self
    def update_waveform(self, data):
        rms = np.sqrt(np.mean(data**2)); self.waveform_data = np.roll(self.waveform_data, -1); self.waveform_data[-1] = rms; AppHelper.callLater(0, self.setNeedsDisplay_, True)
    def drawRect_(self, dirtyRect):
        objc.super(WaveformView, self).drawRect_(dirtyRect); bounds = self.bounds(); path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bounds, 10.0, 10.0); AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.1, 0.7).set(); path.fill()
        if self.waveform_data is not None and len(self.waveform_data) > 0:
            width, height = bounds.size.width, bounds.size.height; wave_path = AppKit.NSBezierPath.alloc().init(); wave_path.moveToPoint_((0, height / 2)); max_amp = np.max(self.waveform_data) if np.max(self.waveform_data) > 0.01 else 0.01
            for i, value in enumerate(self.waveform_data):
                x = (width / len(self.waveform_data)) * i; y = (height / 2) + (value / max_amp) * (height / 2) * 0.8; wave_path.lineToPoint_((x, y))
            wave_path.setLineWidth_(2.0); AppKit.NSColor.whiteColor().set(); wave_path.stroke()

class FloatingUIController:
    def __init__(self, data_queue):
        self.data_queue = data_queue; self.window = None; self.waveform_view = None; self.timer = None; AppHelper.callLater(0, self.setup_window)
    def setup_window(self):
        win_rect = AppKit.NSMakeRect(0, 0, 150, 50)
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(win_rect, AppKit.NSWindowStyleMaskBorderless, AppKit.NSBackingStoreBuffered, False)
        self.window.setOpaque_(False); self.window.setBackgroundColor_(AppKit.NSColor.clearColor()); self.window.setLevel_(AppKit.NSStatusWindowLevel); self.window.setIgnoresMouseEvents_(True); self.window.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces)
        self.waveform_view = WaveformView.alloc().initWithFrame_(self.window.contentView().bounds()); self.window.setContentView_(self.waveform_view)

    # ▼▼▼ ここが修正箇所 ▼▼▼
    def show_at(self, bounds, screen_visible_frame):
        """
        指定されたテキストボックスの近くにウィンドウを表示する。
        渡された「可視フレーム」を基準に、画面の端で見切れないように位置を自動調整する。
        """
        if not self.window:
            return

        window_size = self.window.frame().size
        # 引数で渡された可視フレームを使用する
        screen_frame = screen_visible_frame
        screen_origin = screen_frame.origin
        screen_size = screen_frame.size
        MARGIN = 8

        # `bounds['y']`（左上原点）を`左下原点`の座標系に変換する。
        # この変換の基準は、物理的なスクリーンの高さである必要がある。
        zero_screen_physical_height = AppKit.NSScreen.screens()[0].frame().size.height
        bounds_y_bottom_up = zero_screen_physical_height - bounds['y']

        # --- Y座標の決定 ---
        textbox_top_on_screen = bounds_y_bottom_up - screen_origin.y
        preferred_y_on_screen = textbox_top_on_screen + MARGIN
        preferred_y = screen_origin.y + preferred_y_on_screen
        
        # UIの上端が「可視フレーム」の上端をはみ出すかチェック
        if preferred_y + window_size.height > screen_origin.y + screen_size.height:
            # はみ出す場合、下側に配置する
            y = screen_origin.y + textbox_top_on_screen - bounds['height'] - window_size.height - MARGIN
        else:
            # はみ出さない場合、上側に配置する
            y = preferred_y

        # --- X座標の決定 ---
        x = bounds['x'] + (bounds['width'] / 2) - (window_size.width / 2)

        # 左右の画面端をはみ出すかチェックして調整
        if x < screen_origin.x + MARGIN:
            x = screen_origin.x + MARGIN
        elif x + window_size.width > screen_origin.x + screen_size.width - MARGIN:
            x = screen_origin.x + screen_size.width - window_size.width - MARGIN

        AppHelper.callLater(0, self.window.setFrameOrigin_, AppKit.NSPoint(x, y))
        AppHelper.callLater(0, self.window.orderFront_, None)
        self.start_updating()
    # ▲▲▲ ここまで ▲▲▲

    def hide(self):
        if not self.window: return
        AppHelper.callLater(0, self.window.orderOut_, None); self.stop_updating()
    def start_updating(self):
        if self.timer is None: self.timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(1.0/30.0, self, 'update:', None, True)
    def stop_updating(self):
        if self.timer: self.timer.invalidate(); self.timer = None
    def update_(self, timer):
        try:
            while not self.data_queue.empty():
                data = self.data_queue.get_nowait()
                if self.waveform_view: self.waveform_view.update_waveform(data)
        except queue.Empty: pass