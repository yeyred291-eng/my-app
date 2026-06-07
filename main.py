from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.list import ThreeLineListItem
from kivymd.uix.button import MDIconButton, MDRoundFlatButton, MDFillRoundFlatButton
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.dialog import MDDialog
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.label import MDLabel
from kivy.metrics import dp
from kivy.properties import StringProperty, ListProperty
from kivy.core.audio import SoundLoader
from kivy.clock import Clock
import datetime
import json
import os
import shutil

# Für echte System-Benachrichtigungen (funktioniert auf PC & Android)
try:
    from plyer import filechooser, notification
except ImportError:
    filechooser = None
    notification = None

DATA_FILE = "erinnerungen.json"
SETTINGS_FILE = "einstellungen.json"

class HomeScreen(MDScreen):
    pass

class SettingsScreen(MDScreen):
    pass

class WindowManager(MDScreenManager):
    pass

class ListItemWithMenu(ThreeLineListItem):
    def __init__(self, reminder_index, **kwargs):
        super().__init__(**kwargs)
        self.reminder_index = reminder_index
        self.right_icon = MDIconButton(
            icon="dots-vertical",
            pos_hint={"center_x": .95, "center_y": .5},
            on_release=lambda x: MDApp.get_running_app().open_actions_menu(x, self.reminder_index)
        )
        self.add_widget(self.right_icon)

class ReminderApp(MDApp):
    current_sound = StringProperty("Radar 🎵")
    selected_days = ListProperty([]) 
    edit_dialog = None
    time_picker_dialog = None
    active_edit_index = None
    
    # Temporäre Variablen für den Zeitwähler
    chosen_hour = "00"
    target_field = None # Welches Feld bekommt die Uhrzeit?

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "DeepPurple"
        self.theme_cls.accent_palette = "Amber"
        
        self.reminders = self.load_data()
        self.load_settings()
        
        self.sm = WindowManager()
        self.sm.add_widget(HomeScreen(name="home"))
        self.sm.add_widget(SettingsScreen(name="settings"))
        
        # SCHARF SCHALTEN: Jede Sekunde im Hintergrund prüfen, ob eine Erinnerung fällig ist!
        Clock.schedule_interval(self.check_reminders, 1)
        
        return self.sm

    def on_start(self):
        self.update_reminder_list()

    def load_data(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.reminders, f, ensure_ascii=False, indent=4)

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
                self.current_sound = settings.get("sound", "Radar 🎵")

    def save_settings(self):
        settings = {"sound": self.current_sound}
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)

    # --- DER NEUE, ABGERUNDETE ZEIT-WÄHLER (TIME PICKER) ---
    def open_time_picker(self, field_id):
        self.target_field = field_id
        self.show_hours_layout()

    def show_hours_layout(self):
        # Layout für Stunden (4 Spalten x 6 Reihen = 24 Stunden)
        content = MDBoxLayout(orientation="vertical", spacing="10dp", size_hint_y=None, height="320dp")
        content.add_widget(MDLabel(text="Wähle die Stunde:", halign="center", bold=True, size_hint_y=None, height="30dp"))
        
        grid = MDGridLayout(cols=4, spacing="8dp")
        for h in range(24):
            hour_str = f"{h:02d}"
            btn = MDFillRoundFlatButton(
                text=hour_str, 
                md_bg_color=[0.15, 0.15, 0.2, 1],
                on_release=lambda x, val=hour_str: self.select_hour(val)
            )
            grid.add_widget(btn)
        
        content.add_widget(grid)
        
        if self.time_picker_dialog:
            self.time_picker_dialog.dismiss()
            
        self.time_picker_dialog = MDDialog(title="🕒 Zeit einstellen", type="custom", content_cls=content)
        self.time_picker_dialog.open()

    def select_hour(self, hour):
        self.chosen_hour = hour
        self.show_minutes_layout()

    def show_minutes_layout(self):
        # Layout für Minuten (Schritte von 5 Minuten für eine schnelle Bedienung)
        content = MDBoxLayout(orientation="vertical", spacing="10dp", size_hint_y=None, height="260dp")
        content.add_widget(MDLabel(text=f"Gewählt: {self.chosen_hour}:... Uhr\nWähle die Minuten:", halign="center", bold=True, size_hint_y=None, height="40dp"))
        
        grid = MDGridLayout(cols=4, spacing="8dp")
        for m in range(0, 60, 5):
            min_str = f"{m:02d}"
            btn = MDFillRoundFlatButton(
                text=min_str,
                md_bg_color=self.theme_cls.primary_color,
                on_release=lambda x, val=min_str: self.finish_time_selection(val)
            )
            grid.add_widget(btn)
            
        content.add_widget(grid)
        self.time_picker_dialog.dismiss()
        self.time_picker_dialog = MDDialog(title="🕒 Zeit einstellen", type="custom", content_cls=content)
        self.time_picker_dialog.open()

    def finish_time_selection(self, minute):
        final_time = f"{self.chosen_hour}:{minute}"
        self.target_field.text = final_time
        self.time_picker_dialog.dismiss()

    # --- ERINNERUNGS-LOGIK IM HINTERGRUND ---
    def check_reminders(self, dt):
        now = datetime.datetime.now()
        current_time_str = now.strftime("%H:%M")
        current_sec = now.strftime("%S")
        current_day_index = now.weekday() # 0=Mo, 1=Di ... 6=So

        # Wir prüfen nur genau in der 00. Sekunde einer Minute, um Mehrfach-Alarme zu verhindern
        if current_sec != "00":
            return

        for reminder in self.reminders:
            if reminder["time"] == current_time_str:
                days = reminder.get("days", [])
                # Wenn die Liste leer ist ("Einmalig") ODER der heutige Tag ausgewählt ist
                if not days or current_day_index in days:
                    self.trigger_alarm(reminder)

    def trigger_alarm(self, reminder):
        # 1. Echte System-Benachrichtigung senden (wichtig für Android & PC-Sperrbildschirm)
        if notification:
            try:
                notification.notify(
                    title="⏰ MyRemind Alarm!",
                    message=f"Erinnerung: {reminder['title']}",
                    app_name="MyRemind",
                    timeout=10
                )
            except Exception as e:
                print("System-Benachrichtigung Fehler:", e)

        # 2. Sound abspielen
        sound_name = reminder.get("sound", "Radar 🎵")
        if sound_name != "Nur Benachrichtigung (Stumm) 🔕":
            sound_dict = {"Radar 🎵": "radar.wav", "Glockenspiel 🔔": "glocken.wav", "Digitaler Alarm 🚨": "alarm.wav"}
            file = sound_dict.get(sound_name, sound_name)
            sound = SoundLoader.load(file)
            if sound: sound.play()

        # 3. Großes visuelles Alarm-Fenster mitten in der App öffnen
        alarm_dialog = MDDialog(
            title="🔔 ERINNERUNG!",
            text=f"[b]{reminder['title']}[/b]\nEs ist {reminder['time']} Uhr!",
            buttons=[MDRoundFlatButton(text="Gelesen / Schließen", on_release=lambda x: alarm_dialog.dismiss())]
        )
        alarm_dialog.open()

    # --- SOUNDS UND DATEIEN ---
    def select_sound(self, sound_name):
        self.current_sound = sound_name
        self.save_settings()
        if sound_name == "Nur Benachrichtigung (Stumm) 🔕": return
        sound_dict = {"Radar 🎵": "radar.wav", "Glockenspiel 🔔": "glocken.wav", "Digitaler Alarm 🚨": "alarm.wav"}
        file = sound_dict.get(sound_name, sound_name)
        sound = SoundLoader.load(file)
        if sound: sound.play()

    def import_own_sound(self):
        success = False
        if filechooser:
            try:
                path = filechooser.open_file(title="Wähle einen Klingelton", filters=[("Audio", "*.mp3", "*.wav")])
                if path:
                    self.process_imported_file(path[0])
                    success = True
            except Exception: pass
        if not success:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3 *.wav")])
                if path: self.process_imported_file(path)
            except Exception as e: print("Fehler beim Datei-Öffnen:", e)

    def process_imported_file(self, source_path):
        filename = os.path.basename(source_path)
        destination = os.path.join(os.getcwd(), filename)
        shutil.copy(source_path, destination)
        self.select_sound(filename)

    def toggle_day(self, day_index, button):
        if day_index in self.selected_days:
            self.selected_days.remove(day_index)
            button.md_bg_color = [0.2, 0.2, 0.25, 1] 
        else:
            self.selected_days.append(day_index)
            button.md_bg_color = self.theme_cls.primary_color 

    def get_days_string(self, days_list):
        if not days_list: return "Einmalig"
        day_names = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        return ", ".join([day_names[i] for i in sorted(days_list)])

    def add_reminder(self):
        home = self.sm.get_screen("home")
        title = home.ids.title_input.text
        time = home.ids.time_input.text
        
        if title and time:
            new_reminder = {
                "title": title,
                "time": time,
                "days": list(self.selected_days),
                "sound": self.current_sound
            }
            self.reminders.append(new_reminder)
            self.save_data()
            self.update_reminder_list()
            
            home.ids.title_input.text = ""
            home.ids.time_input.text = ""
            self.selected_days = []
            for btn in [home.ids.mo, home.ids.di, home.ids.mi, home.ids.do, home.ids.fr, home.ids.sa, home.ids.so]:
                btn.md_bg_color = [0.2, 0.2, 0.25, 1]

    def update_reminder_list(self):
        list_view = self.sm.get_screen("home").ids.container
        list_view.clear_widgets()
        
        for index, item in enumerate(self.reminders):
            days_str = self.get_days_string(item.get("days", []))
            ton_anzeige = item.get("sound", "Standard")
            if ton_anzeige == "Nur Benachrichtigung (Stumm) 🔕":
                ton_anzeige = "Stumm (Nur Text) 🔕"
                
            list_item = ListItemWithMenu(
                reminder_index=index,
                text=f"🔔 {item['title']}",
                secondary_text=f"Zeit: {item['time']} Uhr | Tage: {days_str}",
                tertiary_text=f"Modus: {ton_anzeige}"
            )
            list_view.add_widget(list_item)

    def open_actions_menu(self, button, index):
        menu_items = [
            {"text": "✏️ Bearbeiten", "viewclass": "OneLineListItem", "on_release": lambda i=index: self.menu_action("edit", i)},
            {"text": "🗑️ Löschen", "viewclass": "OneLineListItem", "on_release": lambda i=index: self.menu_action("delete", i)}
        ]
        self.actions_menu = MDDropdownMenu(caller=button, items=menu_items, width_mult=4)
        self.actions_menu.open()

    def menu_action(self, action_type, index):
        self.actions_menu.dismiss()
        if action_type == "edit":
            self.open_edit_dialog(index)
        elif action_type == "delete":
            self.delete_reminder(index)

    def delete_reminder(self, index):
        if 0 <= index < len(self.reminders):
            self.reminders.pop(index)
            self.save_data()
            self.update_reminder_list()

    # --- BEARBEITEN DIALOG (MIT ZEIT-WÄHLER SUPPORT) ---
    def open_edit_dialog(self, index):
        self.active_edit_index = index
        reminder = self.reminders[index]
        
        from kivymd.uix.textfield import MDTextField
        
        content = MDBoxLayout(orientation="vertical", spacing="12dp", size_hint_y=None, height="140dp")
        self.edit_title = MDTextField(text=reminder["title"], hint_text="Titel ändern", mode="rectangle")
        
        # Ein Klick-Feld für die Uhrzeit im Bearbeiten-Fenster
        self.edit_time = MDTextField(text=reminder["time"], hint_text="Uhrzeit ändern", mode="rectangle", focus_behavior=False)
        self.edit_time.bind(focus=lambda instance, value: self.open_time_picker(self.edit_time) if value else None)
        
        content.add_widget(self.edit_title)
        content.add_widget(self.edit_time)
        
        self.edit_dialog = MDDialog(
            title="Erinnerung bearbeiten",
            type="custom",
            content_cls=content,
            buttons=[
                MDRoundFlatButton(text="Abbrechen", on_release=lambda x: self.edit_dialog.dismiss()),
                MDRoundFlatButton(text="Speichern", md_bg_color=self.theme_cls.primary_color, on_release=self.save_edited_reminder)
            ]
        )
        self.edit_dialog.open()

    def save_edited_reminder(self, x):
        index = self.active_edit_index
        self.reminders[index]["title"] = self.edit_title.text
        self.reminders[index]["time"] = self.edit_time.text
        self.save_data()
        self.update_reminder_list()
        self.edit_dialog.dismiss()


from kivy.lang import Builder
Builder.load_string("""
<HomeScreen>:
    MDBoxLayout:
        orientation: 'vertical'
        spacing: dp(10)
        padding: dp(20)

        MDBoxLayout:
            size_hint_y: None
            height: dp(60)
            MDLabel:
                text: "⏰ MyRemind"
                font_style: "H4"
                bold: True
            MDIconButton:
                icon: "cog"
                icon_size: dp(30)
                on_release: app.root.current = "settings"

        MDTextField:
            id: title_input
            hint_text: "Was gibt es zu tun?"
            mode: "rectangle"

        # Klick auf dieses Feld öffnet sofort den neuen grafischen Zeitwähler!
        MDTextField:
            id: time_input
            hint_text: "Uhrzeit wählen (Hier klicken)"
            mode: "rectangle"
            focus_behavior: False
            on_focus: if self.focus: app.open_time_picker(self)

        MDLabel:
            text: "Wiederholen am:"
            font_style: "Subtitle2"
            size_hint_y: None
            height: dp(20)

        MDBoxLayout:
            orientation: 'horizontal'
            spacing: dp(4)
            size_hint_y: None
            height: dp(45)
            
            MDFillRoundFlatButton:
                id: mo
                text: "Mo"
                size_hint_x: 1
                md_bg_color: [0.2, 0.2, 0.25, 1]
                on_release: app.toggle_day(0, self)
            MDFillRoundFlatButton:
                id: di
                text: "Di"
                size_hint_x: 1
                md_bg_color: [0.2, 0.2, 0.25, 1]
                on_release: app.toggle_day(1, self)
            MDFillRoundFlatButton:
                id: mi
                text: "Mi"
                size_hint_x: 1
                md_bg_color: [0.2, 0.2, 0.25, 1]
                on_release: app.toggle_day(2, self)
            MDFillRoundFlatButton:
                id: do
                text: "Do"
                size_hint_x: 1
                md_bg_color: [0.2, 0.2, 0.25, 1]
                on_release: app.toggle_day(3, self)
            MDFillRoundFlatButton:
                id: fr
                text: "Fr"
                size_hint_x: 1
                md_bg_color: [0.2, 0.2, 0.25, 1]
                on_release: app.toggle_day(4, self)
            MDFillRoundFlatButton:
                id: sa
                text: "Sa"
                size_hint_x: 1
                md_bg_color: [0.2, 0.2, 0.25, 1]
                on_release: app.toggle_day(5, self)
            MDFillRoundFlatButton:
                id: so
                text: "So"
                size_hint_x: 1
                md_bg_color: [0.2, 0.2, 0.25, 1]
                on_release: app.toggle_day(6, self)

        MDRaisedButton:
            text: "Erinnerung sichern"
            pos_hint: {"center_x": .5}
            size_hint_x: 1
            on_release: app.add_reminder()

        MDScrollView:
            MDList:
                id: container
                spacing: dp(10)

<SettingsScreen>:
    MDBoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(15)

        MDBoxLayout:
            size_hint_y: None
            height: dp(60)
            MDIconButton:
                icon: "arrow-left"
                icon_size: dp(28)
                on_release: app.root.current = "home"
            MDLabel:
                text: "Optionen"
                font_style: "H4"
                bold: True

        MDLabel:
            text: "🎵 Sound-Profil wählen"
            font_style: "H6"
            bold: True
            size_hint_y: None
            height: dp(30)

        MDRaisedButton:
            text: "Nur Benachrichtigung (Stumm) 🔕"
            size_hint_x: 1
            md_bg_color: app.theme_cls.primary_color if app.current_sound == "Nur Benachrichtigung (Stumm) 🔕" else [0.2, 0.2, 0.25, 1]
            on_release: app.select_sound("Nur Benachrichtigung (Stumm) 🔕")

        MDRaisedButton:
            text: "Radar 🎵"
            size_hint_x: 1
            md_bg_color: app.theme_cls.primary_color if app.current_sound == "Radar 🎵" else [0.2, 0.2, 0.25, 1]
            on_release: app.select_sound("Radar 🎵")
            
        MDRaisedButton:
            text: "Sanftes Glockenspiel 🔔"
            size_hint_x: 1
            md_bg_color: app.theme_cls.primary_color if app.current_sound == "Glockenspiel 🔔" else [0.2, 0.2, 0.25, 1]
            on_release: app.select_sound("Glockenspiel 🔔")

        MDRaisedButton:
            text: "Digitaler Alarm 🚨"
            size_hint_x: 1
            md_bg_color: app.theme_cls.primary_color if app.current_sound == "Digitaler Alarm 🚨" else [0.2, 0.2, 0.25, 1]
            on_release: app.select_sound("Digitaler Alarm 🚨")

        MDCard:
            size_hint_y: None
            height: dp(50)
            radius: [25,]
            md_bg_color: 0.12, 0.12, 0.18, 1
            ripple_behavior: True
            on_release: app.import_own_sound()
            
            MDBoxLayout:
                orientation: 'horizontal'
                padding: dp(15)
                spacing: dp(10)
                
                MDIcon:
                    icon: "file-music"
                    pos_hint: {"center_y": .5}
                    theme_text_color: "Custom"
                    text_color: 1, 1, 1, 1
                
                MDLabel:
                    text: "Eignen Sound importieren 📁"
                    bold: True
                    theme_text_color: "Custom"
                    text_color: 1, 1, 1, 1
                    pos_hint: {"center_y": .5}

        MDLabel:
            text: "Aktiv: " + app.current_sound
            font_style: "Caption"
            halign: "center"
            theme_text_color: "Secondary"

        Widget:
""")

if __name__ == "__main__":
    ReminderApp().run()