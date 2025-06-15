# main_background.py

import time
import threading
import queue
import traceback
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController

from audio_handler import AudioRecorder
from transcription import TranscriptionService
from floating_ui import FloatingUIController

import AppKit
from PyObjCTools import AppHelper

# ▼▼▼ 変更点 1: 必要な定数をインポートリストに追加 ▼▼▼
try:
    from ApplicationServices import (
        AXUIElementCreateSystemWide,
        AXUIElementCopyAttributeValue,
        AXUIElementCopyParameterizedAttributeValue, # パラメータ付き属性を取得する関数
        AXValueGetValue,
        kAXFocusedUIElementAttribute,
        kAXSelectedTextRangeAttribute,              # 選択されたテキスト範囲の属性
        kAXBoundsForRangeParameterizedAttribute,    # 範囲の境界を取得するためのパラメータ付き属性
        kAXPositionAttribute,                       # (フォールバック用に残す)
        kAXSizeAttribute,                           # (フォールバック用に残す)
        kAXValueCGPointType,                        # (フォールバック用に残す)
        kAXValueCGSizeType,                         # (フォールバック用に残す)
        kAXValueCGRectType                          # CGRect型の値を取得するために必要
    )
    from HIServices import kAXErrorSuccess
    PYOBJC_AVAILABLE = True
except ImportError as e:
    print(f"警告: 必要なmacOSライブラリがインポートできませんでした: {e}")
    PYOBJC_AVAILABLE = False


DOUBLE_TAP_THRESHOLD = 0.4

class BackgroundRecorder:
    def __init__(self):
        self.ui_queue = queue.Queue()
        self.ui_controller = FloatingUIController(self.ui_queue)
        
        self.audio_recorder = AudioRecorder(ui_queue=self.ui_queue)
        self.transcription_service = TranscriptionService(model_size="large-v3-turbo")
        self.keyboard_controller = KeyboardController()
        
        self.last_option_press_time = 0
        
        print("--- バックグラウンド録音・文字起こしツール ---")
        print("Optionキーを2回素早く押して、録音を開始/停止します。")
        print("このプログラムを終了するには、ターミナルで Ctrl+C を押してください。")

    # ▼▼▼ 変更点 2: 新しい高精度なカーソル位置検出関数を実装 ▼▼▼
    def get_caret_bounds(self):
        """
        Accessibility APIを使い、現在フォーカスされているUI要素の
        テキストカーソル（キャレット）の正確な画面座標を取得する。
        """
        if not PYOBJC_AVAILABLE:
            return None
        
        try:
            # 1. システム全体でフォーカスされているUI要素を取得
            system_wide_element = AXUIElementCreateSystemWide()
            err, focused_element_ref = AXUIElementCopyAttributeValue(system_wide_element, kAXFocusedUIElementAttribute, None)
            if err != kAXErrorSuccess or not focused_element_ref:
                return None

            # 2. フォーカスされた要素の「選択されたテキスト範囲」を取得
            #    カーソルがあるだけの場合、これは位置情報を持つ「長さゼロの範囲」となる
            err, selected_range_ref = AXUIElementCopyAttributeValue(focused_element_ref, kAXSelectedTextRangeAttribute, None)
            if err != kAXErrorSuccess or not selected_range_ref:
                return None

            # 3.「範囲の境界」を取得するためのパラメータ化された属性を使って、カーソルの具体的な画面座標を要求
            #    これがSwiftプロジェクトで使われていた核心的な技術
            err, bounds_for_range_ref = AXUIElementCopyParameterizedAttributeValue(
                focused_element_ref,
                kAXBoundsForRangeParameterizedAttribute,
                selected_range_ref,
                None
            )
            if err != kAXErrorSuccess or not bounds_for_range_ref:
                return None

            # 4. 取得したAXValueからCGRect（座標とサイズ）を抽出
            success, rect_value = AXValueGetValue(bounds_for_range_ref, kAXValueCGRectType, None)
            if not success:
                return None
            
            # 5. フローティングUIが扱える辞書形式で座標を返す
            #    注意: ここで得られる Y 座標は画面の上端が原点 (Top-Left)
            print(f"  ↳ Caret found at: [x={rect_value.origin.x}, y={rect_value.origin.y}]")
            return {
                'x': rect_value.origin.x,
                'y': rect_value.origin.y,
                'width': rect_value.size.width,
                'height': rect_value.size.height
            }

        except Exception as e:
            print(f"\n[エラー] カーソル位置の検出中に予期せぬ例外が発生しました: {e}")
            traceback.print_exc()
            return None

    # (以前の get_editable_text_input_bounds 関数は不要になったため削除)

    def on_key_press(self, key):
        if key == Key.alt or key == Key.alt_r:
            current_time = time.time()
            time_diff = current_time - self.last_option_press_time
            self.last_option_press_time = current_time

            if time_diff < DOUBLE_TAP_THRESHOLD:
                AppHelper.callLater(0, self.handle_double_tap)

    def handle_double_tap(self):
        if not self.audio_recorder.is_recording:
            mouse_location = AppKit.NSEvent.mouseLocation()
            active_screen = AppKit.NSScreen.mainScreen()
            for screen in AppKit.NSScreen.screens():
                if AppKit.NSMouseInRect(mouse_location, screen.frame(), False):
                    active_screen = screen
                    break
            
            # ▼▼▼ 変更点 3: 新しい検出関数を呼び出すように変更 ▼▼▼
            bounds = self.get_caret_bounds()
            
            if not bounds:
                print("ℹ️ 録音を開始できませんでした。編集可能なテキスト入力欄にカーソルを合わせてください。")
                self.last_option_press_time = 0
                return

            print("▶️ Recording started...")
            self.ui_controller.show_at(bounds, active_screen.visibleFrame())
            self.audio_recorder.start_recording()
        else:
            print("⏹️ Recording stopped. Starting transcription...")
            # UIを文字起こし処理中の表示に変更（非表示にしない）
            self.ui_controller.show_processing()
            processing_thread = threading.Thread(target=self.process_recording)
            processing_thread.start()

    def paste_text_safely(self, text_to_paste):
        """
        現在のクリップボードの内容をバックアップ・復元しながら、安全にテキストをペーストする。
        """
        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        saved_items = []
        try:
            types = pasteboard.types()
            if types:
                for a_type in types:
                    data = pasteboard.dataForType_(a_type)
                    if data:
                        saved_items.append({'type': a_type, 'data': data})
            print("   ↳ Clipboard content backed up.")
        except Exception as e:
            print(f"   ↳ Warning: Could not back up clipboard content: {e}")

        try:
            pasteboard.clearContents()
            pasteboard.setString_forType_(text_to_paste, AppKit.NSStringPboardType)
            time.sleep(0.1)
            with self.keyboard_controller.pressed(Key.cmd):
                self.keyboard_controller.press('v')
                self.keyboard_controller.release('v')
            print("   ↳ Paste command sent.")

        finally:
            try:
                time.sleep(0.1)
                pasteboard.clearContents()
                for item in saved_items:
                    pasteboard.setData_forType_(item['data'], item['type'])
                print("   ↳ Clipboard content restored.")
            except Exception as e:
                print(f"   ↳ Warning: Could not restore clipboard content: {e}")
    
    def paste_text_and_hide_ui(self, text_to_paste):
        """テキストをペーストした後にUIを非表示にする"""
        self.paste_text_safely(text_to_paste)
        # ペースト処理の後、少し待ってからUIを非表示にする
        AppHelper.callLater(0.1, self.ui_controller.hide)

    def process_recording(self):
        """録音を停止し、文字起こしとテキスト設定を行う関数"""
        audio_data = self.audio_recorder.stop_recording()

        if audio_data is not None:
            transcribed_text = self.transcription_service.transcribe(audio_data)
            print(f"   ↳ Transcription result: {transcribed_text}")

            if transcribed_text:
                final_text = " " + transcribed_text.strip()
                AppHelper.callLater(0, self.paste_text_and_hide_ui, final_text)
            else:
                # 文字起こし結果が空の場合はUIを非表示にする
                AppHelper.callLater(0, self.ui_controller.hide)
        else:
            print("   ↳ Recording data was too short; processing cancelled.")
            # 録音データが短すぎる場合はUIを非表示にする
            AppHelper.callLater(0, self.ui_controller.hide)

    def run(self):
        """キーボードリスナーとUIイベントループを開始します"""
        listener = keyboard.Listener(on_press=self.on_key_press)
        listener_thread = threading.Thread(target=listener.start, daemon=True)
        listener_thread.start()
        
        AppKit.NSApplication.sharedApplication().run()


if __name__ == '__main__':
    app = BackgroundRecorder()
    app.run()