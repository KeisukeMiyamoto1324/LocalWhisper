# floating_ui.py

import AppKit
import numpy as np
from PyObjCTools import AppHelper
import threading
import queue
import objc # objcライブラリをインポート

# NSViewを継承して、波形を描画するためのカスタムビューを作成します
class WaveformView(AppKit.NSView):
    def initWithFrame_(self, frame):
        # objc.super() を使用するよう修正
        self = objc.super(WaveformView, self).initWithFrame_(frame)
        if self:
            # 描画する波形データを初期化します
            self.waveform_data = np.zeros(256, dtype=np.float32)
        return self

    def update_waveform(self, data):
        """外部から新しい音声データを受け取り、再描画を要求します"""
        rms = np.sqrt(np.mean(data**2))
        
        self.waveform_data = np.roll(self.waveform_data, -1)
        self.waveform_data[-1] = rms
        
        AppHelper.callLater(0, self.setNeedsDisplay_, True)

    def drawRect_(self, dirtyRect):
        """ビューの描画処理です"""
        # objc.super() を使用するよう修正
        objc.super(WaveformView, self).drawRect_(dirtyRect)
        
        bounds = self.bounds()
        path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bounds, 10.0, 10.0)
        AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.1, 0.7).set()
        path.fill()

        if self.waveform_data is not None and len(self.waveform_data) > 0:
            width, height = bounds.size.width, bounds.size.height
            
            wave_path = AppKit.NSBezierPath.alloc().init()
            wave_path.moveToPoint_((0, height / 2))

            max_amp = np.max(self.waveform_data) if np.max(self.waveform_data) > 0.01 else 0.01

            for i, value in enumerate(self.waveform_data):
                x = (width / len(self.waveform_data)) * i
                y = (height / 2) + (value / max_amp) * (height / 2) * 0.8
                wave_path.lineToPoint_((x, y))

            wave_path.setLineWidth_(2.0)
            AppKit.NSColor.whiteColor().set()
            wave_path.stroke()


# フローティングウィンドウを管理するコントローラーです
class FloatingUIController:
    # (このクラスに変更はありませんが、念のため全体を載せておきます)
    def __init__(self, data_queue):
        self.data_queue = data_queue
        self.window = None
        self.waveform_view = None
        self.timer = None
        AppHelper.callLater(0, self.setup_window)

    def setup_window(self):
        """ウィンドウとビューを初期化します"""
        win_rect = AppKit.NSMakeRect(0, 0, 150, 50)
        
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            win_rect,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False
        )
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self.window.setLevel_(AppKit.NSStatusWindowLevel)
        self.window.setIgnoresMouseEvents_(True)
        self.window.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces)

        self.waveform_view = WaveformView.alloc().initWithFrame_(self.window.contentView().bounds())
        self.window.setContentView_(self.waveform_view)

    def show_at(self, bounds):
        """指定された座標の近くにウィンドウを表示します"""
        if not self.window:
            return
            
        screen_frame = AppKit.NSScreen.mainScreen().frame()
        screen_height = screen_frame.size.height
        
        x = bounds['x'] + bounds['width']
        y = screen_height - bounds['y'] - bounds['height'] - self.window.frame().size.height - 10
        
        AppHelper.callLater(0, self.window.setFrameOrigin_, AppKit.NSPoint(x, y))
        AppHelper.callLater(0, self.window.orderFront_, None)
        self.start_updating()

    def hide(self):
        """ウィンドウを非表示にします"""
        if not self.window:
            return
        AppHelper.callLater(0, self.window.orderOut_, None)
        self.stop_updating()

    def start_updating(self):
        """キューからデータを取得して波形を更新するタイマーを開始します"""
        if self.timer is None:
            self.timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0/30.0, self, 'update:', None, True
            )

    def stop_updating(self):
        """タイマーを停止します"""
        if self.timer:
            self.timer.invalidate()
            self.timer = None
    
    def update_(self, timer):
        """タイマーによって呼び出され、キューのデータを処理します"""
        try:
            while not self.data_queue.empty():
                data = self.data_queue.get_nowait()
                if self.waveform_view:
                    self.waveform_view.update_waveform(data)
        except queue.Empty:
            pass