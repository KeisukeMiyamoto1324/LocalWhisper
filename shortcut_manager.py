from pynput import keyboard

class ShortcutManager:
    def __init__(self, toggle_callback):
        self.toggle_callback = toggle_callback
        # <cmd>+<`> (バッククォート) をホットキーとして設定
        self.hotkey = keyboard.HotKey(
            keyboard.HotKey.parse('<cmd>+`'),
            self.on_activate
        )
        self.listener = keyboard.Listener(
            on_press=self.for_canonical(self.hotkey.press),
            on_release=self.for_canonical(self.hotkey.release)
        )

    def on_activate(self):
        print("Hotkey activated!")
        self.toggle_callback()

    def for_canonical(self, f):
        return lambda k: f(self.listener.canonical(k))

    def start(self):
        print("Shortcut listener started.")
        self.listener.start()

    def stop(self):
        self.listener.stop()