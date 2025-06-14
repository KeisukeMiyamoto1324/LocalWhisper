# floating_ui.py

import AppKit
import numpy as np
from PyObjCTools import AppHelper
import threading
import queue
import objc

class WaveformView(AppKit.NSView):
    """
    画像で指定されたような、シンプルな垂直線の波形を描画するカスタムビュー。
    """
    def initWithFrame_(self, frame):
        self = objc.super(WaveformView, self).initWithFrame_(frame)
        if self:
            # UIの見た目に合わせて、表示するデータポイント数を調整
            self.waveform_data = np.zeros(64, dtype=np.float32)
            # 線の色を設定 (少し透明度を持たせた黒)
            self.line_color = AppKit.NSColor.blackColor().colorWithAlphaComponent_(0.85)
        return self

    def update_waveform(self, data):
        """新しい音声データで波形を更新し、再描画を要求します。"""
        rms = np.sqrt(np.mean(data**2))
        self.waveform_data = np.roll(self.waveform_data, -1)
        self.waveform_data[-1] = rms
        AppHelper.callLater(0, self.setNeedsDisplay_, True)

    def drawRect_(self, dirtyRect):
        """ビューの描画処理"""
        objc.super(WaveformView, self).drawRect_(dirtyRect)

        if not hasattr(self, 'waveform_data') or len(self.waveform_data) == 0:
            return

        bounds = self.bounds()
        width, height = bounds.size.width, bounds.size.height
        mid_y = height / 2

        # 波形の最大振幅を計算（0除算を避ける）
        max_amp = np.max(self.waveform_data)
        if max_amp < 0.01:
            max_amp = 0.01
            
        # 線の太さと間隔を計算
        num_lines = len(self.waveform_data)
        total_spacing = 20 # 線と線の間の合計の空白
        line_width = (width - total_spacing) / num_lines
        line_spacing = line_width + (total_spacing / (num_lines -1 if num_lines > 1 else 1))

        # 線の色を設定
        self.line_color.set()

        # 各データポイントを垂直線として描画
        for i, value in enumerate(self.waveform_data):
            # 振幅をビューの高さに合わせてスケーリング
            # 0.95を掛けて、上下に少し余白を作る
            scaled_height = (value / max_amp) * height * 0.95
            
            # 線のX座標
            x_pos = i * line_spacing
            
            # パスを作成して線を描画
            path = AppKit.NSBezierPath.bezierPath()
            path.moveToPoint_((x_pos, mid_y - scaled_height / 2))
            path.lineToPoint_((x_pos, mid_y + scaled_height / 2))
            path.setLineWidth_(line_width)
            path.setLineCapStyle_(AppKit.NSLineCapStyleRound) # 線の先端を丸くする
            path.stroke()


class FloatingUIController:
    def __init__(self, data_queue):
        self.data_queue = data_queue
        self.window = None
        self.waveform_view = None
        self.timer = None
        AppHelper.callLater(0, self.setup_window)

    def setup_window(self):
        """ウィンドウとビューをシンプルなデザインでセットアップします。"""
        win_rect = AppKit.NSMakeRect(0, 0, 220, 40) # UIに合わせてサイズを調整

        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            win_rect,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False
        )

        # ウィンドウを透明にし、背景色をクリアに設定
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(AppKit.NSColor.clearColor())
        # 他のウィンドウより手前に表示
        self.window.setLevel_(AppKit.NSStatusWindowLevel)
        # マウスイベントを無視する
        self.window.setIgnoresMouseEvents_(True)
        # 全てのデスクトップスペースで表示
        self.window.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary)
        # シンプルなUIなので影はなしにする
        self.window.setHasShadow_(False)

        # --- 波形ビューを作成し、ウィンドウのコンテンツビューとして直接設定 ---
        self.waveform_view = WaveformView.alloc().initWithFrame_(self.window.contentView().bounds())
        self.waveform_view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        self.window.setContentView_(self.waveform_view)


    def show_at(self, bounds, screen_visible_frame):
        """
        指定されたテキストボックスの近くにウィンドウを表示する。
        """
        if not self.window:
            return

        window_size = self.window.frame().size
        screen_frame = screen_visible_frame
        screen_origin = screen_frame.origin
        screen_size = screen_frame.size
        MARGIN = 10

        zero_screen_physical_height = AppKit.NSScreen.screens()[0].frame().size.height
        bounds_y_bottom_up = zero_screen_physical_height - bounds['y']

        # --- Y座標の決定 ---
        textbox_top_on_screen = bounds_y_bottom_up - screen_origin.y
        preferred_y_on_screen = textbox_top_on_screen + MARGIN
        preferred_y = screen_origin.y + preferred_y_on_screen
        
        if preferred_y + window_size.height > screen_origin.y + screen_size.height:
            textbox_bottom_on_screen = textbox_top_on_screen - bounds['height']
            y = screen_origin.y + textbox_bottom_on_screen - window_size.height - MARGIN
        else:
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

    def hide(self):
        if not self.window: return
        AppHelper.callLater(0, self.window.orderOut_, None)
        self.stop_updating()

    def start_updating(self):
        # 更新頻度 (30fpsで十分)
        if self.timer is None:
            self.timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0/30.0, self, 'update:', None, True
            )

    def stop_updating(self):
        if self.timer:
            self.timer.invalidate()
            self.timer = None

    def update_(self, timer):
        try:
            while not self.data_queue.empty():
                data = self.data_queue.get_nowait()
                if self.waveform_view:
                    self.waveform_view.update_waveform(data)
        except queue.Empty:
            pass