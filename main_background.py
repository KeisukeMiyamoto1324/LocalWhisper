# main_background.py

import time
import threading
import queue
import traceback
from concurrent.futures import ThreadPoolExecutor  # 追加
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController

from audio_handler import AudioRecorder
from transcription import TranscriptionService
from floating_ui import FloatingUIController

import AppKit
from PyObjCTools import AppHelper

try:
    from ApplicationServices import (
        AXUIElementCreateSystemWide,
        AXUIElementCopyAttributeValue,
        AXUIElementCopyParameterizedAttributeValue,
        AXValueGetValue,
        kAXFocusedUIElementAttribute,
        kAXSelectedTextRangeAttribute,
        kAXBoundsForRangeParameterizedAttribute,
        kAXPositionAttribute,
        kAXSizeAttribute,
        kAXValueCGPointType,
        kAXValueCGSizeType,
        kAXValueCGRectType
    )
    from HIServices import kAXErrorSuccess
    PYOBJC_AVAILABLE = True
except ImportError as e:
    print(f"警告: 必要なmacOSライブラリがインポートできませんでした: {e}")
    PYOBJC_AVAILABLE = False


DOUBLE_TAP_THRESHOLD = 0.4

class BackgroundRecorder:
    def __init__(self):
        self.ui_queue = queue.Queue(maxsize=100)  # キューサイズ制限
        self.ui_controller = FloatingUIController(self.ui_queue)

        # 文字起こしサービスを初期化
        self.transcription_service = TranscriptionService(model_size="large-v3-turbo")

        # オーディオレコーダーを初期化（リアルタイムコールバック付き）
        self.audio_recorder = AudioRecorder(
            ui_queue=self.ui_queue,
            realtime_callback=self.handle_realtime_transcription
        )

        self.keyboard_controller = KeyboardController()

        self.last_option_press_time = 0

        # リアルタイム文字起こし用の状態管理
        self.accumulated_transcription = ""
        self.transcription_lock = threading.Lock()

        # 文字起こし処理用のスレッドプールを作成
        self.transcription_executor = ThreadPoolExecutor(max_workers=1)  # 修正
        self.is_transcribing = False

        print("--- バックグラウンド録音・文字起こしツール ---")
        print("Optionキーを2回素早く押して、録音を開始/停止します。")
        print("このプログラムを終了するには、ターミナルで Ctrl+C を押してください。")

    def handle_realtime_transcription(self, audio_data):
        """リアルタイム文字起こしのコールバック関数"""
        # 既に文字起こし処理中の場合はスキップ
        if self.is_transcribing:
            return

        # 非同期で文字起こしを実行
        self.transcription_executor.submit(self._transcribe_realtime, audio_data)

    def _transcribe_realtime(self, audio_data):
        """リアルタイム文字起こしの実際の処理（別スレッドで実行）"""
        try:
            self.is_transcribing = True

            if audio_data is None or len(audio_data) == 0:
                return

            print("🎤 リアルタイム文字起こし中...")

            # 文字起こしを実行（リアルタイムフラグを設定）
            transcribed_text = self.transcription_service.transcribe(audio_data, is_realtime=True)

            if transcribed_text and transcribed_text.strip():
                with self.transcription_lock:
                    # 新しいテキストを蓄積（重複チェック付き）
                    new_text = transcribed_text.strip()
                    if self.accumulated_transcription:
                        # 簡単な重複チェック
                        words_existing = set(self.accumulated_transcription.lower().split())
                        words_new = set(new_text.lower().split())
                        if len(words_new - words_existing) > 0:  # 新しい単語がある場合のみ追加
                            self.accumulated_transcription += " " + new_text
                    else:
                        self.accumulated_transcription = new_text

                    # 長すぎる場合は最新部分のみ保持
                    if len(self.accumulated_transcription) > 500:
                        words = self.accumulated_transcription.split()
                        self.accumulated_transcription = " ".join(words[-50:])

                    display_text = self.accumulated_transcription

                print(f"📝 リアルタイム結果: {new_text}")

                # UIコントローラーにテキストを送信
                AppHelper.callLater(0, self.ui_controller.update_transcription_text, display_text)

        except Exception as e:
            print(f"❌ リアルタイム文字起こしエラー: {e}")
            # エラーの詳細は本番環境では出力しない
            # traceback.print_exc()
        finally:
            self.is_transcribing = False

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
            err, selected_range_ref = AXUIElementCopyAttributeValue(focused_element_ref, kAXSelectedTextRangeAttribute, None)
            if err != kAXErrorSuccess or not selected_range_ref:
                return None

            # 3.「範囲の境界」を取得するためのパラメータ化された属性を使って、カーソルの具体的な画面座標を要求
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
            print(f"  ↳ Caret found at: [x={rect_value.origin.x}, y={rect_value.origin.y}]")
            return {
                'x': rect_value.origin.x,
                'y': rect_value.origin.y,
                'width': rect_value.size.width,
                'height': rect_value.size.height
            }

        except Exception as e:
            print(f"\n[エラー] カーソル位置の検出中に予期せぬ例外が発生しました: {e}")
            return None

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

            bounds = self.get_caret_bounds()

            if not bounds:
                print("ℹ️ 録音を開始できませんでした。編集可能なテキスト入力欄にカーソルを合わせてください。")
                self.last_option_press_time = 0
                return

            print("▶️ Recording started...")

            # 蓄積された文字起こし結果をリセット
            with self.transcription_lock:
                self.accumulated_transcription = ""

            self.ui_controller.show_at(bounds, active_screen.visibleFrame())
            self.audio_recorder.start_recording()
        else:
            print("⏹️ Recording stopped. Finalizing transcription...")

            # リアルタイム文字起こしの完了を待つ
            if self.is_transcribing:
                print("⏳ Waiting for real-time transcription to complete...")
                while self.is_transcribing:
                    time.sleep(0.1)

            self.ui_controller.hide()
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

    def process_recording(self):
        """録音を停止し、最終的な文字起こしとテキスト設定を行う関数"""
        audio_data = self.audio_recorder.stop_recording()

        if audio_data is not None:
            try:
                # 最終的な完全な文字起こしを実行
                final_transcribed_text = self.transcription_service.transcribe(audio_data, is_realtime=False)
                print(f"   ↳ Final transcription result: {final_transcribed_text}")

                # リアルタイムで蓄積されたテキストと最終結果を比較し、より良い方を選択
                with self.transcription_lock:
                    if final_transcribed_text and len(final_transcribed_text.strip()) > len(self.accumulated_transcription):
                        final_text = final_transcribed_text.strip()
                        print("   ↳ Using final transcription (more complete)")
                    elif self.accumulated_transcription:
                        final_text = self.accumulated_transcription.strip()
                        print("   ↳ Using accumulated real-time transcription")
                    else:
                        final_text = final_transcribed_text.strip() if final_transcribed_text else ""

                if final_text:
                    final_text_with_space = " " + final_text
                    AppHelper.callLater(0, self.paste_text_safely, final_text_with_space)

            except Exception as e:
                print(f"   ↳ Error during final transcription: {e}")
                # リアルタイム結果をフォールバックとして使用
                with self.transcription_lock:
                    if self.accumulated_transcription:
                        final_text_with_space = " " + self.accumulated_transcription.strip()
                        AppHelper.callLater(0, self.paste_text_safely, final_text_with_space)
        else:
            print("   ↳ Recording data was too short; processing cancelled.")

    def cleanup(self):
        """リソースのクリーンアップ"""
        if hasattr(self, 'transcription_executor'):
            self.transcription_executor.shutdown(wait=True)

    def run(self):
        """キーボードリスナーとUIイベントループを開始します"""
        try:
            listener = keyboard.Listener(on_press=self.on_key_press)
            listener_thread = threading.Thread(target=listener.start, daemon=True)
            listener_thread.start()

            AppKit.NSApplication.sharedApplication().run()
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.cleanup()
        except Exception as e:
            print(f"Unexpected error: {e}")
            self.cleanup()


if __name__ == '__main__':
    app = BackgroundRecorder()
    app.run()