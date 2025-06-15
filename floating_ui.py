# floating_ui.py

import AppKit
import numpy as np
from PyObjCTools import AppHelper
import threading
import queue
import objc
import math

class ModernWaveformView(AppKit.NSView):
    """
    macOSのモダンデザインに合わせた波形表示ビュー
    """
    def initWithFrame_(self, frame):
        self = objc.super(ModernWaveformView, self).initWithFrame_(frame)
        if self:
            # 波形データの初期化
            self.waveform_data = np.zeros(32, dtype=np.float32)
            self.smoothed_data = np.zeros(32, dtype=np.float32)
            self.peak_level = 0.01
            self.animation_phase = 0.0

            # 色の設定
            self.setup_colors()

        return self

    def setup_colors(self):
        """色の設定"""
        self.primary_color = AppKit.NSColor.systemBlueColor()
        self.secondary_color = AppKit.NSColor.systemGrayColor()
        self.inactive_color = AppKit.NSColor.tertiaryLabelColor()

    def update_waveform(self, data):
        """波形データの更新"""
        if data is None or len(data) == 0:
            return

        # RMS値を計算
        rms = float(np.sqrt(np.mean(data**2)))

        # データをシフトして新しい値を追加
        self.waveform_data = np.roll(self.waveform_data, -1)
        self.waveform_data[-1] = rms

        # スムージング
        self.smoothed_data = self.smoothed_data * 0.6 + self.waveform_data * 0.4

        # ピークレベルの更新
        current_max = np.max(self.smoothed_data)
        if current_max > self.peak_level:
            self.peak_level = current_max
        else:
            self.peak_level = max(0.01, self.peak_level * 0.95)

        # アニメーション位相の更新
        self.animation_phase += 0.15
        if self.animation_phase > 2 * math.pi:
            self.animation_phase = 0.0

        # 再描画を要求
        self.setNeedsDisplay_(True)

    def drawRect_(self, dirtyRect):
        """波形の描画"""
        AppKit.NSColor.clearColor().set()
        AppKit.NSRectFill(dirtyRect)

        bounds = self.bounds()
        width = bounds.size.width
        height = bounds.size.height
        center_y = height / 2.0

        if not hasattr(self, 'smoothed_data') or len(self.smoothed_data) == 0:
            return

        # バーの設定
        num_bars = len(self.smoothed_data)
        spacing = 2.0
        bar_width = max(1.0, (width - spacing * (num_bars - 1)) / num_bars)

        # 各バーを描画
        for i, value in enumerate(self.smoothed_data):
            x_pos = i * (bar_width + spacing)

            # バーの高さを計算
            normalized_value = value / self.peak_level if self.peak_level > 0 else 0
            bar_height = max(2.0, normalized_value * height * 0.8)

            # 微細なアニメーション効果
            if normalized_value > 0.1:
                wave_effect = math.sin(self.animation_phase + i * 0.2) * 1.0
                bar_height += wave_effect

            # バーの矩形を作成
            bar_rect = AppKit.NSMakeRect(
                x_pos,
                center_y - bar_height / 2,
                bar_width,
                bar_height
            )

            # 色を選択（値に応じて）
            if normalized_value > 0.3:
                color = self.primary_color.colorWithAlphaComponent_(0.8)
            elif normalized_value > 0.1:
                color = self.secondary_color.colorWithAlphaComponent_(0.6)
            else:
                color = self.inactive_color.colorWithAlphaComponent_(0.4)

            # バーを描画
            color.set()
            path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                bar_rect, bar_width / 2, bar_width / 2
            )
            path.fill()


class FloatingUIController:
    """
    リアルタイム文字起こし結果表示機能付きフローティングUI
    """
    def __init__(self, data_queue):
        self.data_queue = data_queue
        self.window = None
        self.waveform_view = None
        self.text_view = None
        self.timer = None

        # リアルタイム文字起こし用
        self.transcription_text = ""
        self.text_queue = queue.Queue()

        print("FloatingUIController: 初期化中...")
        AppHelper.callLater(0, self.setup_window)

    def setup_window(self):
        """ウィンドウの作成とセットアップ"""
        print("FloatingUIController: ウィンドウをセットアップ中...")

        # ウィンドウサイズを大きくしてテキスト表示領域を確保
        window_width = 320
        window_height = 120
        win_rect = AppKit.NSMakeRect(0, 0, window_width, window_height)

        # ボーダーレスウィンドウを作成
        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            win_rect,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False
        )

        # ウィンドウの基本設定
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self.window.setHasShadow_(True)
        self.window.setLevel_(AppKit.NSStatusWindowLevel)
        self.window.setIgnoresMouseEvents_(True)
        self.window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces | 
            AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        )

        # コンテンツビューの作成
        self.setup_content_view()

        print("FloatingUIController: ウィンドウセットアップ完了")

    def setup_content_view(self):
        """コンテンツビューのセットアップ"""
        bounds = self.window.contentView().bounds()

        # メインコンテナビューを作成
        container_view = AppKit.NSView.alloc().initWithFrame_(bounds)
        container_view.setWantsLayer_(True)

        # 背景レイヤーの設定
        layer = container_view.layer()
        layer.setCornerRadius_(12.0)
        layer.setMasksToBounds_(True)

        # 背景色設定
        try:
            if hasattr(AppKit.NSApp, 'effectiveAppearance'):
                appearance = AppKit.NSApp.effectiveAppearance()
                is_dark = 'Dark' in str(appearance.name())
            else:
                is_dark = False

            if is_dark:
                bg_color = AppKit.NSColor.blackColor().colorWithAlphaComponent_(0.85)
            else:
                bg_color = AppKit.NSColor.whiteColor().colorWithAlphaComponent_(0.92)
        except:
            bg_color = AppKit.NSColor.whiteColor().colorWithAlphaComponent_(0.92)

        layer.setBackgroundColor_(bg_color.CGColor())

        # 境界線の追加
        layer.setBorderWidth_(0.5)
        border_color = AppKit.NSColor.separatorColor().colorWithAlphaComponent_(0.3)
        layer.setBorderColor_(border_color.CGColor())

        # ウィンドウにコンテナビューを設定
        self.window.setContentView_(container_view)

        # 波形ビューとテキストビューを作成
        self.setup_waveform_view(container_view)
        self.setup_text_view(container_view)

    def setup_waveform_view(self, container_view):
        """波形ビューのセットアップ"""
        bounds = container_view.bounds()

        # 波形ビューは上部に配置
        padding = 8.0
        waveform_height = 40.0
        waveform_rect = AppKit.NSMakeRect(
            padding,
            bounds.size.height - waveform_height - padding,
            bounds.size.width - 2 * padding,
            waveform_height
        )

        # 波形ビューを作成
        self.waveform_view = ModernWaveformView.alloc().initWithFrame_(waveform_rect)
        self.waveform_view.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin
        )

        # コンテナビューに追加
        container_view.addSubview_(self.waveform_view)

    def setup_text_view(self, container_view):
        """テキスト表示ビューのセットアップ"""
        bounds = container_view.bounds()

        # テキストビューは下部に配置
        padding = 8.0
        text_height = 60.0
        text_rect = AppKit.NSMakeRect(
            padding,
            padding,
            bounds.size.width - 2 * padding,
            text_height
        )

        # スクロールビューを作成
        scroll_view = AppKit.NSScrollView.alloc().initWithFrame_(text_rect)
        scroll_view.setHasVerticalScroller_(False)
        scroll_view.setHasHorizontalScroller_(False)
        scroll_view.setBorderType_(AppKit.NSNoBorder)
        scroll_view.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewMaxYMargin
        )

        # テキストビューを作成
        text_view_rect = AppKit.NSMakeRect(0, 0, text_rect.size.width, text_rect.size.height)
        self.text_view = AppKit.NSTextView.alloc().initWithFrame_(text_view_rect)
        self.text_view.setEditable_(False)
        self.text_view.setSelectable_(True)
        self.text_view.setRichText_(True)
        self.text_view.setBackgroundColor_(AppKit.NSColor.clearColor())
        self.text_view.setTextContainerInset_(AppKit.NSMakeSize(4, 4))

        # フォントと色の設定
        font = AppKit.NSFont.systemFontOfSize_(12.0)
        self.text_view.setFont_(font)

        try:
            if hasattr(AppKit.NSApp, 'effectiveAppearance'):
                appearance = AppKit.NSApp.effectiveAppearance()
                is_dark = 'Dark' in str(appearance.name())
            else:
                is_dark = False

            if is_dark:
                text_color = AppKit.NSColor.whiteColor()
            else:
                text_color = AppKit.NSColor.blackColor()
        except:
            text_color = AppKit.NSColor.blackColor()

        self.text_view.setTextColor_(text_color)

        # スクロールビューにテキストビューを設定
        scroll_view.setDocumentView_(self.text_view)

        # コンテナビューに追加
        container_view.addSubview_(scroll_view)

        print("FloatingUIController: テキストビューセットアップ完了")

    def update_transcription_text(self, text):
        """リアルタイム文字起こしテキストの更新"""
        try:
            self.text_queue.put(text)
        except Exception as e:
            print(f"FloatingUIController: テキスト更新エラー - {e}")

    def show_at(self, bounds, screen_visible_frame):
        """指定位置にウィンドウを表示"""
        if not self.window:
            print("FloatingUIController: ウィンドウが初期化されていません")
            return

        print(f"FloatingUIController: ウィンドウを表示 bounds={bounds}")

        window_size = self.window.frame().size
        screen_frame = screen_visible_frame
        screen_origin = screen_frame.origin
        screen_size = screen_frame.size
        margin = 10

        # 座標変換
        zero_screen_physical_height = AppKit.NSScreen.screens()[0].frame().size.height
        bounds_y_bottom_up = zero_screen_physical_height - bounds['y']

        # Y座標の決定
        textbox_top_on_screen = bounds_y_bottom_up - screen_origin.y
        preferred_y_on_screen = textbox_top_on_screen + margin
        preferred_y = screen_origin.y + preferred_y_on_screen

        if preferred_y + window_size.height > screen_origin.y + screen_size.height:
            textbox_bottom_on_screen = textbox_top_on_screen - bounds['height']
            y = screen_origin.y + textbox_bottom_on_screen - window_size.height - margin
        else:
            y = preferred_y

        # X座標の決定
        x = bounds['x'] + (bounds['width'] / 2) - (window_size.width / 2)

        # 画面端のチェック
        if x < screen_origin.x + margin:
            x = screen_origin.x + margin
        elif x + window_size.width > screen_origin.x + screen_size.width - margin:
            x = screen_origin.x + screen_size.width - window_size.width - margin

        # ウィンドウを表示
        self.window.setFrameOrigin_(AppKit.NSPoint(x, y))
        self.window.makeKeyAndOrderFront_(None)

        # タイマーを開始
        self.start_updating()
        print("FloatingUIController: ウィンドウ表示完了")

    def hide(self):
        """ウィンドウを非表示"""
        if not self.window:
            return

        print("FloatingUIController: ウィンドウを非表示")
        self.stop_updating()
        self.window.orderOut_(None)

        # テキストをクリア
        if self.text_view:
            self.text_view.setString_("")

    def start_updating(self):
        """更新タイマーを開始"""
        if self.timer is None:
            print("FloatingUIController: 更新タイマー開始")
            self.timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0/30.0, self, 'update:', None, True
            )

    def stop_updating(self):
        """更新タイマーを停止"""
        if self.timer:
            print("FloatingUIController: 更新タイマー停止")
            self.timer.invalidate()
            self.timer = None

    def update_(self, timer):
        """データキューから音声データとテキストを取得して更新"""
        try:
            # 音声データの更新
            data_updated = False
            while not self.data_queue.empty():
                data = self.data_queue.get_nowait()
                if self.waveform_view and data is not None:
                    self.waveform_view.update_waveform(data)
                    data_updated = True

            # テキストの更新
            text_updated = False
            while not self.text_queue.empty():
                text = self.text_queue.get_nowait()
                if self.text_view and text is not None:
                    self.text_view.setString_(text)
                    text_updated = True

        except queue.Empty:
            pass
        except Exception as e:
            print(f"FloatingUIController: 更新エラー - {e}")